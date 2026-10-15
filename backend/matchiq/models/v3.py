"""V3 – EXPERIMENTELL modell. Får inte markeras som produktionsklar förrän den klarat tidsordnad validering.

Komponenter
-----------
1. Motståndarjusterade attack-/försvarsmultiplikatorer per lag och mått, skattade med tidsviktad
   (exponentiellt avtagande, halveringstid h) Poisson-likelihood och konjugerad Gamma-prior
   (empirisk-Bayes-shrinkage). Priorstyrkan k mäts i "matchekvivalenter" och VÄLJS PÅ VALIDERINGS-
   PERIODEN – inga godtyckliga koefficienter.
2. Separat inhemsk styrka: lagens relativa styrka i den egna ligan skattas på inhemska resultat.
   Ligafaktorn (hur starka ligans lag är i Europa) skattas ENBART från kronologiskt tidigare
   europeiska möten före datagränsen. Priorn för ett lag blir ligafaktor × inhemsk styrka^β.
   Bryggan ("bridge") aktiveras bara om den förbättrar valideringen.
3. Räknevariabler (skott, skott på mål, hörnor) modelleras separat. Negativ binomial används när
   träningsresidualerna visar överspridning; annars Poisson.
4. 1X2 summeras ur målmatrisen med valfri Dixon–Coles-korrektion (ρ väljs på validering).
"""
from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np

from .common import THIN_HISTORY, counts_block, goals_block
from .data import DataView
from .dist import nb_logpmf

MODEL_ID = "V3-3.0"
DEFAULT_PARAMS = {
    "half_life_days": 365.0, "k": 4.0,              # mål
    "half_life_days_counts": 365.0, "k_counts": 4.0,  # skott/SOT/hörnor
    "bridge": "off",                                  # off | league | domestic
    "beta": 0.5,
    "rho": 0.0,
    "window_days": 3650.0,
    "calibrated": False,
}
_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_CACHE_MAX = 512


def _cache_get(key):
    v = _CACHE.get(key)
    if v is not None:
        _CACHE.move_to_end(key)
    return v


def _cache_put(key, val):
    _CACHE[key] = val
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def clear_cache() -> None:
    _CACHE.clear()


def fit_ratings(home: np.ndarray, away: np.ndarray, yh: np.ndarray, ya: np.ndarray, w: np.ndarray,
                k: float, prior_att: dict[int, float] | None = None, prior_def: dict[int, float] | None = None,
                iters: int = 30) -> dict:
    """Tidsviktad Poisson med Gamma-prior. Returnerar multiplikatorer (genomsnitt = 1) och basnivåer."""
    teams = np.unique(np.concatenate([home, away]))
    tix = {int(t): i for i, t in enumerate(teams)}
    hi = np.array([tix[int(t)] for t in home], dtype=np.int64)
    ai = np.array([tix[int(t)] for t in away], dtype=np.int64)
    n = len(teams)
    a0 = np.ones(n)
    d0 = np.ones(n)
    if prior_att:
        for t, v in prior_att.items():
            if t in tix:
                a0[tix[t]] = v
    if prior_def:
        for t, v in prior_def.items():
            if t in tix:
                d0[tix[t]] = v
    sw = w.sum()
    mu_h = float((w * yh).sum() / sw)
    mu_a = float((w * ya).sum() / sw)
    mu_team = (mu_h + mu_a) / 2
    att = a0.copy()
    dfn = d0.copy()
    pk = k * mu_team  # prior-exponering i enheter av förväntat utfall
    for _ in range(iters):
        num = np.bincount(hi, w * yh, n) + np.bincount(ai, w * ya, n) + pk * a0
        den = np.bincount(hi, w * mu_h * dfn[ai], n) + np.bincount(ai, w * mu_a * dfn[hi], n) + pk
        att = num / den
        num = np.bincount(ai, w * yh, n) + np.bincount(hi, w * ya, n) + pk * d0
        den = np.bincount(ai, w * mu_h * att[hi], n) + np.bincount(hi, w * mu_a * att[ai], n) + pk
        dfn = num / den
        mu_h = float((w * yh).sum() / (w * att[hi] * dfn[ai]).sum())
        mu_a = float((w * ya).sum() / (w * att[ai] * dfn[hi]).sum())
    exp_h = mu_h * att[hi] * dfn[ai]
    exp_a = mu_a * att[ai] * dfn[hi]
    # Överspridning (momentmetoden, viktad): Var = E + E²/r
    e = np.concatenate([exp_h, exp_a])
    y = np.concatenate([yh, ya])
    ww = np.concatenate([w, w])
    excess = float((ww * ((y - e) ** 2 - e)).sum())
    r = float((ww * e ** 2).sum() / excess) if excess > 1e-9 else None
    exposure = np.bincount(hi, w, n) + np.bincount(ai, w, n)
    return {"tix": tix, "att": att, "def": dfn, "mu_h": mu_h, "mu_a": mu_a, "r": r, "exposure": exposure}


def _weights(kickoff: np.ndarray, cutoff_ts: float, half_life_days: float, window_days: float) -> np.ndarray:
    age_days = (cutoff_ts - kickoff) / 86400.0
    w = np.power(0.5, age_days / half_life_days)
    w[age_days > window_days] = 0.0
    return w


_TEAM_LEAGUES: dict[int, dict[int, str]] = {}


def _team_league(view: DataView) -> dict[int, str]:
    """Lag -> inhemsk tävlingskod (sätts av anroparen via set_team_leagues)."""
    return _TEAM_LEAGUES.get(id(view.store), {})


def set_team_leagues(store, mapping: dict[int, str]) -> None:
    _TEAM_LEAGUES[id(store)] = dict(mapping)


def _fit_metric(view: DataView, comp: str, metric: str, hl: float, k: float, window: float,
                prior_att=None, prior_def=None, prior_key: str = "") -> dict | None:
    key = ("fit", id(view.store), view.cutoff_ts, comp, metric, hl, k, window, prior_key)
    v = _cache_get(key)
    if v is not None:
        return v
    d = view.metric(metric, (comp,))
    if len(d["h"]) < 20:
        _cache_put(key, None)
        return None
    w = _weights(d["kickoff"], view.cutoff_ts, hl, window)
    keep = w > 0
    if keep.sum() < 20:
        _cache_put(key, None)
        return None
    fit = fit_ratings(d["home"][keep], d["away"][keep], d["h"][keep], d["a"][keep], w[keep], k, prior_att,
                      prior_def)
    fit["n_by_team"] = {}
    for t in np.concatenate([d["home"], d["away"]]):
        fit["n_by_team"][int(t)] = fit["n_by_team"].get(int(t), 0) + 1
    _cache_put(key, fit)
    return fit


def _bridge_priors(view: DataView, comp: str, metric: str, p: dict) -> tuple[dict, dict, str]:
    """Priorer från ligafaktor (europeiska möten) och ev. inhemsk styrka. Endast data före datagränsen."""
    if p["bridge"] == "off":
        return {}, {}, ""
    hl, k, window = p["half_life_days"], p["k"], p["window_days"]
    base = _fit_metric(view, comp, metric, hl, k, window)
    if base is None:
        return {}, {}, ""
    leagues = _team_league(view)
    # ligafaktor: exponeringsviktat medel av europeiska multiplikatorer per liga, shrinkat mot 1
    acc: dict[str, list] = {}
    for t, i in base["tix"].items():
        lg = leagues.get(t)
        if not lg:
            continue
        acc.setdefault(lg, []).append((base["att"][i], base["def"][i], base["exposure"][i]))
    lf_att, lf_def = {}, {}
    for lg, vals in acc.items():
        arr = np.array(vals)
        ex = arr[:, 2].sum()
        lf_att[lg] = float((arr[:, 0] * arr[:, 2]).sum() + 5.0) / (ex + 5.0)
        lf_def[lg] = float((arr[:, 1] * arr[:, 2]).sum() + 5.0) / (ex + 5.0)
    prior_att, prior_def = {}, {}
    dom_fits: dict[str, dict | None] = {}
    for t, lg in leagues.items():
        if lg not in lf_att:
            continue
        a, dd = lf_att[lg], lf_def[lg]
        if p["bridge"] == "domestic" and metric == "goals":
            if lg not in dom_fits:
                dom_fits[lg] = _fit_metric(view, lg, "goals", hl, k, window)
            df = dom_fits[lg]
            if df is not None and t in df["tix"]:
                j = df["tix"][t]
                a *= float(df["att"][j]) ** p["beta"]
                dd *= float(df["def"][j]) ** p["beta"]
        prior_att[t], prior_def[t] = a, dd
    return prior_att, prior_def, f"{p['bridge']}:{p['beta']}"


def predict(view: DataView, competition: str, home_id: int, away_id: int, params: dict | None = None) -> dict:
    p = {**DEFAULT_PARAMS, **(params or {})}
    out: dict = {"model_id": MODEL_ID, "family": "V3", "params": p, "metrics": {}, "coverage": {}, "warnings": [],
                 "probs": None}
    if not p.get("calibrated"):
        out["warnings"].append("V3 använder standardparametrar – hyperparametrarna är inte valda på validering.")
    for metric in ("goals", "shots", "sot", "corners"):
        hl = p["half_life_days"] if metric == "goals" else p["half_life_days_counts"]
        k = p["k"] if metric == "goals" else p["k_counts"]
        pa, pd_, pkey = _bridge_priors(view, competition, metric, {**p, "half_life_days": hl, "k": k})
        fit = _fit_metric(view, competition, metric, hl, k, p["window_days"], pa or None, pd_ or None, pkey)
        if fit is None:
            d = view.metric(metric, (competition,))
            out["metrics"][metric] = None
            out["coverage"][metric] = {"league_n": len(d["h"]), "home_n": 0, "away_n": 0,
                                       "status": "spärrad" if len(d["h"]) == 0 else "otillräcklig"}
            continue
        tix = fit["tix"]

        def mult(t: int, arr: np.ndarray, prior: dict) -> float:
            if t in tix:
                return float(arr[tix[t]])
            return float(prior.get(t, 1.0))  # okänt lag: prior (ligafaktor) eller genomsnitt

        lam_h = fit["mu_h"] * mult(home_id, fit["att"], pa) * mult(away_id, fit["def"], pd_)
        lam_a = fit["mu_a"] * mult(away_id, fit["att"], pa) * mult(home_id, fit["def"], pd_)
        n_h, n_a = fit["n_by_team"].get(home_id, 0), fit["n_by_team"].get(away_id, 0)
        out["coverage"][metric] = {"league_n": int(sum(fit["n_by_team"].values()) // 2), "home_n": n_h,
                                   "away_n": n_a, "status": "ok" if min(n_h, n_a) >= THIN_HISTORY else "tunn",
                                   "dispersion_r": fit["r"]}
        if metric == "goals":
            probs, block = goals_block(lam_h, lam_a, p["rho"])
            out["probs"] = probs
            out["metrics"]["goals"] = block
        else:
            out["metrics"][metric] = counts_block(lam_h, lam_a, fit["r"], fit["r"])
    return out


def count_nll(rows: list[dict], metric: str) -> float | None:
    """Medel negativ log-likelihood för räknevariabler i walk-forward-rader (för modellval)."""
    vals = []
    for r in rows:
        d = r["metrics"].get(metric)
        if not d:
            continue
        rr = d.get("r")
        vals.append(-nb_logpmf(int(d["act_h"]), d["pred_h"], rr))
        vals.append(-nb_logpmf(int(d["act_a"]), d["pred_a"], rr))
    return float(np.mean(vals)) if vals else None


def logloss_rows(rows: list[dict]) -> float | None:
    v = [-math.log(max(r["probs"][("1", "X", "2").index(r["outcome"])], 1e-15))
         for r in rows if r["probs"] and r["outcome"]]
    return float(np.mean(v)) if v else None
