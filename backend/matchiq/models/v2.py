"""V2 – enkel jämförelsebaslinje enligt den tidigare arbetsbokens metod.

Metod (från arbetsbokens blad KALIBRERING): "UCL-only: senaste 15 matcher per lag; 8 matcher
motsvarande ligamedel i shrinkage. Testmatchens datum och senare matcher uteslutna. Målprognos med
Poissonmodell för lagens gjorda/insläppta mål. 1X2 summeras ur målfördelningen."

Generaliserat till valfri tävling: historiken hämtas från samma tävling som matchen.
För räknevariablerna (skott, skott på mål, hörnor) används samma konstruktion per mått.
Saknade värden räknas inte som 0 – de utesluts, och antalet faktiska observationer redovisas.
"""
from __future__ import annotations

import numpy as np

from .common import THIN_HISTORY, counts_block, goals_block, team_rows
from .data import DataView

MODEL_ID = "V2-2.0"
DEFAULT_PARAMS = {"last_n": 15, "k": 8.0}


def _rates(d: dict, team_id: int, last_n: int, k: float, mu_team: float) -> tuple[float, float, int]:
    f, ag, _ = team_rows(d, team_id, last_n)
    n = len(f)
    att = (float(f.sum()) + k * mu_team) / (n + k)
    dfn = (float(ag.sum()) + k * mu_team) / (n + k)
    return att, dfn, n


def predict(view: DataView, competition: str, home_id: int, away_id: int, params: dict | None = None) -> dict:
    p = {**DEFAULT_PARAMS, **(params or {})}
    comps = (competition,)
    out: dict = {"model_id": MODEL_ID, "family": "V2", "params": p, "metrics": {}, "coverage": {}, "warnings": []}
    for metric in ("goals", "shots", "sot", "corners"):
        d = view.metric(metric, comps)
        n_league = len(d["h"])
        if n_league < 20:
            out["metrics"][metric] = None
            out["coverage"][metric] = {"league_n": n_league, "home_n": 0, "away_n": 0,
                                       "status": "spärrad" if n_league == 0 else "otillräcklig"}
            continue
        mu_h = float(np.mean(d["h"]))
        mu_a = float(np.mean(d["a"]))
        mu_team = (mu_h + mu_a) / 2
        att_h, def_h, n_h = _rates(d, home_id, p["last_n"], p["k"], mu_team)
        att_a, def_a, n_a = _rates(d, away_id, p["last_n"], p["k"], mu_team)
        lam_h = mu_h * (att_h / mu_team) * (def_a / mu_team)
        lam_a = mu_a * (att_a / mu_team) * (def_h / mu_team)
        out["coverage"][metric] = {"league_n": n_league, "home_n": n_h, "away_n": n_a,
                                   "status": "ok" if min(n_h, n_a) >= THIN_HISTORY else "tunn"}
        if metric == "goals":
            probs, block = goals_block(lam_h, lam_a)
            out["probs"] = probs
            out["metrics"]["goals"] = block
        else:
            out["metrics"][metric] = counts_block(lam_h, lam_a)
    if "probs" not in out:
        out["probs"] = None
    return out
