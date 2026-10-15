"""Modellval för V3 på valideringsperioden och en enda slututvärdering på orörd holdout.

Ordningen är låst i koden: hyperparametrar väljs med ``walk_forward`` på valideringssäsongerna;
först därefter körs testsäsongerna – en gång – med de låsta parametrarna. Resultat, valda
parametrar och statusgrindar sparas i databasen (backtest_runs, model_versions).
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from ..core import App
from ..timeutil import to_iso
from . import baseline, v2, v3
from .data import HistoryStore
from .evaluate import (build_targets, evaluation_source_ids, gates, store_run, summarize, walk_forward)

DEFAULT_VALIDATION = ["2023/24", "2024/25"]
DEFAULT_TEST = ["2025/26", "2026/27"]
HL_GRID = [180.0, 365.0, 730.0, 1460.0, 2920.0]
K_GRID = [2.0, 4.0, 8.0, 16.0]
BRIDGE_GRID = [("off", 0.0), ("league", 0.0), ("domestic", 0.5), ("domestic", 1.0)]
RHO_GRID = [0.0, -0.05, -0.10]
MIN_GAIN = 0.002  # en komponent aktiveras bara om valideringens log loss förbättras minst så mycket


def team_league_map(app: App) -> dict[int, str]:
    return {int(r["id"]): r["domestic_competition_code"] for r in
            app.db.query("SELECT id, domestic_competition_code FROM teams WHERE domestic_competition_code IS NOT NULL")}


def prospective_counts(app: App, family: str) -> dict:
    """Antal frysta förmatchsprognoser (T−30) med facit per mått för en modellfamilj."""
    rows = app.db.query("""SELECT s.goals_home, s.corners_home, s.shots_home, s.sot_home, o.home_goals, o.home_corners,
        o.home_shots, o.home_sot FROM forecast_snapshots s JOIN match_outcomes o ON o.match_id=s.match_id
        WHERE s.model_family=? AND s.prematch_eligible=1 AND s.kind IN ('T-30','manual')""", (family,))
    n = {"1x2": 0, "goals": 0, "corners": 0, "shots": 0, "sot": 0}
    for r in rows:
        if r["home_goals"] is not None:
            n["1x2"] += 1
            n["goals"] += 1
        for m, (p, o) in {"corners": ("corners_home", "home_corners"), "shots": ("shots_home", "home_shots"),
                          "sot": ("sot_home", "home_sot")}.items():
            if r[p] is not None and r[o] is not None:
                n[m] += 1
    return {"per_metric": n, "min_n": min(n.values()) if n else 0}


def run_selection(app: App, competition: str = "UCL", validation: list[str] | None = None,
                  test: list[str] | None = None, progress=None) -> dict:
    validation = validation or DEFAULT_VALIDATION
    test = test or DEFAULT_TEST
    progress = progress or (lambda msg, done, total: None)
    t0 = time.time()
    leagues = sorted(set(team_league_map(app).values()))
    train = HistoryStore.load(app.db, None, competitions=[competition] + leagues,
                              counts_max_age_days=app.get_setting("counts_max_age_days"))
    ev = HistoryStore.load(app.db, evaluation_source_ids(app.db), competitions=[competition])
    v3.clear_cache()
    v3.set_team_leagues(train, team_league_map(app))
    t_val = build_targets(ev, competition, validation)
    t_test = build_targets(ev, competition, test)
    if len(t_val) < 50:
        raise ValueError(f"För få valideringsmatcher ({len(t_val)}) med tillåtna källor för {competition}.")

    log: list[dict] = []
    total_steps = len(HL_GRID) * len(K_GRID) + len(BRIDGE_GRID) + len(RHO_GRID) + 3
    step = 0

    def evaluate(params: dict) -> dict:
        rows = walk_forward(train, v3.predict, params, t_val, "validation")
        res = {"logloss": v3.logloss_rows(rows)}
        nll = [v3.count_nll(rows, m) for m in ("shots", "sot", "corners")]
        nll = [x for x in nll if x is not None]
        res["count_nll"] = sum(nll) / len(nll) if nll else None
        return res

    # Steg 1: halveringstid och priorstyrka (mål och räknevariabler var för sig)
    best_g, best_c = None, None
    for hl in HL_GRID:
        for k in K_GRID:
            step += 1
            progress(f"V3-val: halveringstid {hl:.0f} d, k={k:.0f}", step, total_steps)
            prm = {**v3.DEFAULT_PARAMS, "half_life_days": hl, "k": k, "half_life_days_counts": hl, "k_counts": k}
            r = evaluate(prm)
            log.append({"stage": "hl_k", "half_life_days": hl, "k": k, **r})
            if r["logloss"] is not None and (best_g is None or r["logloss"] < best_g[0]):
                best_g = (r["logloss"], hl, k)
            if r["count_nll"] is not None and (best_c is None or r["count_nll"] < best_c[0]):
                best_c = (r["count_nll"], hl, k)
    params = {**v3.DEFAULT_PARAMS, "half_life_days": best_g[1], "k": best_g[2]}
    if best_c:
        params.update({"half_life_days_counts": best_c[1], "k_counts": best_c[2]})
    current = best_g[0]
    # Steg 2: ligabrygga / inhemsk styrka
    choice = ("off", 0.0)
    for bridge, beta in BRIDGE_GRID[1:]:
        step += 1
        progress(f"V3-val: brygga {bridge} β={beta}", step, total_steps)
        r = evaluate({**params, "bridge": bridge, "beta": beta})
        log.append({"stage": "bridge", "bridge": bridge, "beta": beta, **r})
        if r["logloss"] is not None and r["logloss"] < current - MIN_GAIN:
            current, choice = r["logloss"], (bridge, beta)
    params.update({"bridge": choice[0], "beta": choice[1]})
    # Steg 3: Dixon–Coles ρ
    best_rho = 0.0
    for rho in RHO_GRID[1:]:
        step += 1
        progress(f"V3-val: ρ={rho}", step, total_steps)
        r = evaluate({**params, "rho": rho})
        log.append({"stage": "rho", "rho": rho, **r})
        if r["logloss"] is not None and r["logloss"] < current - MIN_GAIN:
            current, best_rho = r["logloss"], rho
    params["rho"] = best_rho
    params["calibrated"] = True
    params["selected_on"] = validation
    params["selected_at_utc"] = to_iso(app.clock.now())
    selection_locked_at = app.clock.now()

    # Slututvärdering: validering + orörd holdout, samma mål för alla modeller
    results = {}
    for name, fn, prm, mid in (("V3", v3.predict, params, v3.MODEL_ID), ("V2", v2.predict, None, v2.MODEL_ID),
                               ("BASE", baseline.predict, None, baseline.MODEL_ID)):
        step += 1
        progress(f"Walk-forward {name} (validering + holdout)", step, total_steps)
        rows = (walk_forward(train, fn, prm, t_val, "validation") + walk_forward(train, fn, prm, t_test, "test"))
        summ = summarize(rows)
        cfg = {"competition": competition, "validation": validation, "test": test, "params": prm,
               "train_sources": sorted(train.training_sources), "cutoff_rule": "matchdagens början (Stockholm)",
               "selection_locked_at_utc": to_iso(selection_locked_at)}
        run_id = store_run(app.db, mid, cfg, rows, summ, app.clock.now())
        results[name] = {"run_id": run_id, "summary": summ}
    seasons_covered = len(set(validation) | set(test))
    gate = gates(results["V3"]["summary"], results["V2"]["summary"], results["BASE"]["summary"],
                 prospective_counts(app, "V3"), True, seasons_covered)
    now = to_iso(app.clock.now())
    with app.db.tx() as c:
        old = c.execute("SELECT status FROM model_versions WHERE id=?", (v3.MODEL_ID,)).fetchone()["status"]
        new_status = "produktion" if old == "produktion" and gate["production_possible"] else gate["suggested_status"]
        c.execute("""UPDATE model_versions SET params_json=?, gate_report_json=?, status=?, status_reason=?,
                     status_changed_at_utc=? WHERE id=?""",
                  (json.dumps(params), json.dumps({"gates": gate, "selection_log": log}), new_status,
                   "Automatisk bedömning efter walk-forward-validering", now, v3.MODEL_ID))
        if new_status != old:
            c.execute("INSERT INTO model_status_history (model_version_id, old_status, new_status, reason, at_utc) "
                      "VALUES (?,?,?,?,?)", (v3.MODEL_ID, old, new_status, "Statusgrindar efter validering", now))
        v2_gate = gates(results["V2"]["summary"], None, results["BASE"]["summary"], prospective_counts(app, "V2"),
                        True, seasons_covered)
        c.execute("UPDATE model_versions SET gate_report_json=? WHERE id=?",
                  (json.dumps({"gates": v2_gate}), v2.MODEL_ID))
    return {"params": params, "selection_log": log, "gates": gate, "elapsed_s": round(time.time() - t0, 1),
            "runs": {k: v["run_id"] for k, v in results.items()},
            "summaries": {k: v["summary"] for k, v in results.items()},
            "n_validation": len(t_val), "n_test": len(t_test)}
