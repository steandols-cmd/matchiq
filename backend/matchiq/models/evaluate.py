"""Tidsordnad walk-forward-utvärdering (expanding window), statusgrindar och lagring av körningar.

Principer:
* Varje testmatch prognostiseras med data som var tillgänglig före matchdagen (matchens datum och
  senare matcher utesluts – samma regel som i den tidigare arbetsboken).
* Modellval (hyperparametrar) görs ENDAST på valideringssäsongerna. Slutsäsongen (holdout) är orörd
  tills valet är låst och utvärderas en gång.
* Utfall för utvärdering får hämtas från källor vars villkor tillåter utvärdering; träningsdata
  begränsas till källor som får användas för träning.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

import numpy as np

from ..db import Database
from ..timeutil import STOCKHOLM, UTC, to_iso
from .data import METRICS, HistoryStore
from .metrics import calibration_bins, outcome_label, summarize_1x2, summarize_counts

PredictFn = Callable[..., dict]


@dataclass
class Target:
    match_id: int
    comp: str
    season: str
    kickoff_ts: float
    home: int
    away: int
    actual: dict  # metric -> (h, a) | None


def evaluation_source_ids(db: Database) -> set[str]:
    out = set()
    for r in db.query("SELECT id, allowed_uses FROM sources"):
        if "evaluation" in json.loads(r["allowed_uses"] or "[]"):
            out.add(r["id"])
    return out


def build_targets(eval_store: HistoryStore, comp: str, seasons: list[str]) -> list[Target]:
    a = eval_store.a
    out = []
    for i in range(len(a.match_id)):
        if a.comp[i] != comp or a.season[i] not in seasons or a.et[i]:
            continue
        if np.isnan(a.vals_h["goals"][i]):
            continue
        actual = {}
        for m in METRICS:
            h, aw = a.vals_h[m][i], a.vals_a[m][i]
            actual[m] = None if (np.isnan(h) or np.isnan(aw)) else (float(h), float(aw))
        out.append(Target(int(a.match_id[i]), comp, str(a.season[i]), float(a.kickoff[i]), int(a.home[i]),
                          int(a.away[i]), actual))
    out.sort(key=lambda t: t.kickoff_ts)
    return out


def day_cutoff_ts(kickoff_ts: float) -> float:
    """Start på matchdagen (Europe/Stockholm) – matcher samma dag och senare utesluts."""
    loc = datetime.fromtimestamp(kickoff_ts, UTC).astimezone(STOCKHOLM)
    start = loc.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp()


def walk_forward(train_store: HistoryStore, predict: PredictFn, params: dict | None, targets: list[Target],
                 split: str, cutoff_fn: Callable[[float], float] = day_cutoff_ts,
                 context: dict | None = None) -> list[dict]:
    rows: list[dict] = []
    by_cut: dict[float, list[Target]] = defaultdict(list)
    for t in targets:
        by_cut[cutoff_fn(t.kickoff_ts)].append(t)
    for cut in sorted(by_cut):
        view = train_store.view_ts(cut)
        for t in by_cut[cut]:
            out = predict(view, t.comp, t.home, t.away, params, **(context or {})) if context else \
                predict(view, t.comp, t.home, t.away, params)
            row = {"match_id": t.match_id, "season": t.season, "comp": t.comp, "split": split, "cutoff_ts": cut,
                   "probs": None, "outcome": None, "metrics": {}}
            if out.get("probs") and t.actual.get("goals"):
                pr = out["probs"]
                row["probs"] = (pr["p_home"], pr["p_draw"], pr["p_away"])
                row["outcome"] = outcome_label(*t.actual["goals"])
            for m in METRICS:
                blk = (out.get("metrics") or {}).get(m)
                act = t.actual.get(m)
                if blk is None or act is None:
                    continue
                row["metrics"][m] = {"pred_h": blk["home"]["mean"], "pred_a": blk["away"]["mean"],
                                     "lo_h": blk["home"]["lo"], "hi_h": blk["home"]["hi"],
                                     "lo_a": blk["away"]["lo"], "hi_a": blk["away"]["hi"],
                                     "act_h": act[0], "act_a": act[1], "r": blk["home"].get("r")}
            rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    def one(rs: list[dict]) -> dict:
        res = {"1x2": summarize_1x2((r["probs"], r["outcome"]) for r in rs if r["probs"] and r["outcome"])}
        for m in METRICS:
            cnt = []
            for r in rs:
                d = r["metrics"].get(m)
                if d:
                    cnt.append((d["pred_h"], d["act_h"], d["lo_h"], d["hi_h"]))
                    cnt.append((d["pred_a"], d["act_a"], d["lo_a"], d["hi_a"]))
            res[m] = summarize_counts(cnt)
        return res

    out = {"all": one(rows), "by_split": {}, "by_season": {}, "by_competition": {}}
    for key, field in (("by_split", "split"), ("by_season", "season"), ("by_competition", "comp")):
        groups: dict[str, list] = defaultdict(list)
        for r in rows:
            groups[r[field]].append(r)
        out[key] = {k: one(v) for k, v in sorted(groups.items())}
    out["calibration"] = {
        split: calibration_bins((r["probs"], r["outcome"]) for r in rows if r["split"] == split and r["probs"])
        for split in sorted({r["split"] for r in rows})}
    return out


# ------------------------------------------------------------------------- statusgrindar
GATE_MIN_OBS = 200


def gates(model_summary: dict, v2_summary: dict | None, base_summary: dict | None, prospective: dict | None,
          selection_locked_before_test: bool, seasons_covered: int) -> dict:
    """Bedöm om en modell kan bli kandidat respektive övervägas för produktion."""
    test = model_summary["by_split"].get("test", {})
    checks = []

    def add(key: str, ok: bool, text: str) -> None:
        checks.append({"key": key, "ok": bool(ok), "text": text})

    for m in ("1x2",) + METRICS:
        n = (test.get(m) or {}).get("n", 0) or 0
        add(f"n_{m}", n >= GATE_MIN_OBS, f"{m}: {n} tidsordnade testobservationer (krav ≥ {GATE_MIN_OBS})")
    add("seasons", seasons_covered >= 2, f"{seasons_covered} säsonger i validering+test (krav ≥ 2)")
    add("holdout", selection_locked_before_test, "Modellval låst före orörd slutsäsong")
    t1 = test.get("1x2") or {}
    for ref_name, ref in (("V2", v2_summary), ("baslinje", base_summary)):
        if ref is None:  # ingen jämförelse mot sig själv (V2 bedöms bara mot baslinjen)
            continue
        r1 = ((ref or {}).get("by_split", {}).get("test", {}) or {}).get("1x2") or {}
        ok = (t1.get("logloss") is not None and r1.get("logloss") is not None and t1["logloss"] < r1["logloss"]
              and t1["brier"] < r1["brier"])
        add(f"beats_{ref_name}", ok, f"Lägre Brier och log loss än {ref_name} på holdout")
    for m in ("shots", "sot", "corners", "goals"):
        cov = (test.get(m) or {}).get("coverage")
        add(f"coverage_{m}", cov is not None and 0.70 <= cov <= 0.90,
            f"{m}: 80 %-intervallets faktiska täckning {'' if cov is None else f'{cov:.0%}'} (krav 70–90 %)")
    backtest_ok = all(c["ok"] for c in checks)
    pn = (prospective or {}).get("min_n", 0)
    prospective_ok = pn >= GATE_MIN_OBS
    checks.append({"key": "prospective", "ok": prospective_ok,
                   "text": f"Frysta T−30-prognoser med facit: {pn} per mått (krav ≥ {GATE_MIN_OBS})"})
    status = "experimentell"
    if backtest_ok:
        status = "kandidat"
    return {"checks": checks, "backtest_ok": backtest_ok, "prospective_ok": prospective_ok,
            "suggested_status": status, "production_possible": backtest_ok and prospective_ok}


def store_run(db: Database, model_version_id: str, config: dict, rows: list[dict], summary: dict,
              now: datetime) -> int:
    with db.tx() as c:
        cur = c.execute("INSERT INTO backtest_runs (model_version_id, created_at_utc, config_json, summary_json) "
                        "VALUES (?,?,?,?)", (model_version_id, to_iso(now), json.dumps(config),
                                             json.dumps(summary)))
        run_id = int(cur.lastrowid)
        for r in rows:
            p = r["probs"] or (None, None, None)
            c.execute("""INSERT INTO backtest_predictions (run_id, match_id, split, season, competition_code,
                cutoff_utc, p_home, p_draw, p_away, outcome, preds_json, actuals_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (run_id, r["match_id"], r["split"], r["season"], r["comp"],
                       to_iso(datetime.fromtimestamp(r["cutoff_ts"], UTC)), p[0], p[1], p[2], r["outcome"],
                       json.dumps({m: {k: v for k, v in d.items() if k.startswith(("pred", "lo", "hi"))}
                                   for m, d in r["metrics"].items()}),
                       json.dumps({m: [d["act_h"], d["act_a"]] for m, d in r["metrics"].items()})))
    return run_id
