"""Enkel baslinje: tävlingens historiska utfallsfrekvenser (1X2) och tävlingsmedel för antal (Poisson)."""
from __future__ import annotations

import numpy as np

from .common import counts_block
from .data import DataView
from .dist import count_summary, total_summary

MODEL_ID = "BASE-1.0"


def predict(view: DataView, competition: str, home_id: int, away_id: int, params: dict | None = None) -> dict:
    out: dict = {"model_id": MODEL_ID, "family": "BASE", "params": {}, "metrics": {}, "coverage": {}, "warnings": []}
    for metric in ("goals", "shots", "sot", "corners"):
        d = view.metric(metric, (competition,))
        n = len(d["h"])
        out["coverage"][metric] = {"league_n": n, "home_n": None, "away_n": None,
                                   "status": "ok" if n >= 20 else ("spärrad" if n == 0 else "otillräcklig")}
        if n < 20:
            out["metrics"][metric] = None
            continue
        mu_h, mu_a = float(np.mean(d["h"])), float(np.mean(d["a"]))
        if metric == "goals":
            hw = float(np.mean(d["h"] > d["a"]))
            dr = float(np.mean(d["h"] == d["a"]))
            # Laplace-utjämning så att ingen klass får sannolikhet 0
            ph, pd_, pa = (hw * n + 1) / (n + 3), (dr * n + 1) / (n + 3), ((1 - hw - dr) * n + 1) / (n + 3)
            s = ph + pd_ + pa
            ph, pd_ = ph / s, pd_ / s
            out["probs"] = {"p_home": ph, "p_draw": pd_, "p_away": 1.0 - ph - pd_}
            out["metrics"]["goals"] = {"home": count_summary(mu_h), "away": count_summary(mu_a),
                                       "total": total_summary(mu_h, mu_a, None, None), "extras": {}}
        else:
            out["metrics"][metric] = counts_block(mu_h, mu_a)
    out.setdefault("probs", None)
    return out
