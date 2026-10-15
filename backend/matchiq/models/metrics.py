"""Utvärderingsmått: Brier, log loss, kalibrering (1X2) samt MAE, RMSE, bias och intervalltäckning (antal)."""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

OUTCOMES = ("1", "X", "2")


def outcome_label(hg: float, ag: float) -> str:
    return "1" if hg > ag else ("X" if hg == ag else "2")


def brier(p: tuple[float, float, float], outcome: str) -> float:
    """Multiklass-Brier: summan av de tre klassernas kvadrerade fel (0 = perfekt, 2 = sämst)."""
    o = [1.0 if outcome == k else 0.0 for k in OUTCOMES]
    return float(sum((pi - oi) ** 2 for pi, oi in zip(p, o)))


def logloss(p: tuple[float, float, float], outcome: str, eps: float = 1e-15) -> float:
    return float(-math.log(max(p[OUTCOMES.index(outcome)], eps)))


def summarize_1x2(rows: Iterable[tuple[tuple[float, float, float], str]]) -> dict:
    rows = list(rows)
    if not rows:
        return {"n": 0, "brier": None, "logloss": None, "hit_rate": None}
    b = [brier(p, o) for p, o in rows]
    ll = [logloss(p, o) for p, o in rows]
    hits = [OUTCOMES[int(np.argmax(p))] == o for p, o in rows]
    return {"n": len(rows), "brier": float(np.mean(b)), "logloss": float(np.mean(ll)),
            "hit_rate": float(np.mean(hits))}


def calibration_bins(rows: Iterable[tuple[tuple[float, float, float], str]], n_bins: int = 10) -> list[dict]:
    """Tillförlitlighetsdiagram: alla tre klassernas sannolikheter poolade i lika breda intervall."""
    preds, obs = [], []
    for p, o in rows:
        for k, pk in zip(OUTCOMES, p):
            preds.append(pk)
            obs.append(1.0 if o == k else 0.0)
    if not preds:
        return []
    preds_a, obs_a = np.array(preds), np.array(obs)
    edges = np.linspace(0, 1, n_bins + 1)
    out = []
    for i in range(n_bins):
        m = (preds_a >= edges[i]) & ((preds_a < edges[i + 1]) if i < n_bins - 1 else (preds_a <= edges[i + 1]))
        if m.sum() == 0:
            out.append({"lo": float(edges[i]), "hi": float(edges[i + 1]), "n": 0, "mean_pred": None, "obs_freq": None})
            continue
        out.append({"lo": float(edges[i]), "hi": float(edges[i + 1]), "n": int(m.sum()),
                    "mean_pred": float(preds_a[m].mean()), "obs_freq": float(obs_a[m].mean())})
    return out


def summarize_counts(rows: Iterable[tuple[float, float, float | None, float | None]]) -> dict:
    """rows: (prognos, utfall, P10, P90) per lag och match. Saknade utfall ska redan vara bortfiltrerade."""
    rows = [r for r in rows if r[0] is not None and r[1] is not None]
    if not rows:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "coverage": None, "coverage_n": 0}
    pred = np.array([r[0] for r in rows], dtype=float)
    act = np.array([r[1] for r in rows], dtype=float)
    err = pred - act
    cov_rows = [r for r in rows if r[2] is not None and r[3] is not None]
    coverage = (float(np.mean([r[2] <= r[1] <= r[3] for r in cov_rows])) if cov_rows else None)
    return {"n": len(rows), "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "bias": float(np.mean(err)), "coverage": coverage, "coverage_n": len(cov_rows)}
