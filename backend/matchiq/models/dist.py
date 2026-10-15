"""Sannolikhetsfördelningar för räknevariabler (Poisson och negativ binomial) och 1X2 ur målmatris."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

MAX_GOALS = 10


def poisson_pmf_vec(lam: float, n: int) -> np.ndarray:
    k = np.arange(n + 1)
    lam = max(lam, 1e-9)
    logp = k * math.log(lam) - lam - np.array([math.lgamma(i + 1) for i in k])
    return np.exp(logp)


def nb_pmf_vec(mu: float, r: float | None, n: int) -> np.ndarray:
    """Negativ binomial med medel mu och storleksparameter r (Var = mu + mu²/r). r=None => Poisson."""
    if r is None or r <= 0 or not math.isfinite(r) or r > 1e6:
        return poisson_pmf_vec(mu, n)
    mu = max(mu, 1e-9)
    k = np.arange(n + 1)
    p = r / (r + mu)
    logp = (np.array([math.lgamma(i + r) - math.lgamma(r) - math.lgamma(i + 1) for i in k])
            + r * math.log(p) + k * math.log(1 - p))
    return np.exp(logp)


def quantile_from_pmf(pmf: np.ndarray, q: float) -> int:
    c = np.cumsum(pmf)
    c = c / c[-1] if c[-1] > 0 else c
    return int(np.searchsorted(c, q, side="left"))


def count_summary(mu: float, r: float | None = None, lo_q: float = 0.10, hi_q: float = 0.90) -> dict:
    """Förväntat värde, P10/P90 och fördelningstyp för en räknevariabel."""
    n = int(max(30, mu * 4 + 20))
    pmf = nb_pmf_vec(mu, r, n)
    return {
        "mean": float(mu),
        "lo": quantile_from_pmf(pmf, lo_q),
        "hi": quantile_from_pmf(pmf, hi_q),
        "dist": "poisson" if (r is None or r > 1e6) else "negbin",
        "r": None if r is None else float(r),
        "interval_level": hi_q - lo_q,
    }


def total_summary(mu_h: float, mu_a: float, r_h: float | None, r_a: float | None) -> dict:
    """Summan av två oberoende räknevariabler, approximerad med momentmatchning."""
    var_h = mu_h + (mu_h ** 2 / r_h if r_h else 0.0)
    var_a = mu_a + (mu_a ** 2 / r_a if r_a else 0.0)
    mu = mu_h + mu_a
    extra = (var_h + var_a) - mu
    r = (mu ** 2 / extra) if extra > 1e-9 else None
    return count_summary(mu, r)


def score_matrix(lam_h: float, lam_a: float, rho: float = 0.0, max_goals: int = MAX_GOALS) -> np.ndarray:
    ph = poisson_pmf_vec(lam_h, max_goals)
    pa = poisson_pmf_vec(lam_a, max_goals)
    m = np.outer(ph, pa)
    if rho:
        # Dixon–Coles-korrektion för låga resultat
        m[0, 0] *= 1 - lam_h * lam_a * rho
        m[0, 1] *= 1 + lam_h * rho
        m[1, 0] *= 1 + lam_a * rho
        m[1, 1] *= 1 - rho
        m = np.clip(m, 0, None)
    return m / m.sum()


def outcome_probs(m: np.ndarray) -> tuple[float, float, float]:
    """1X2 ur målmatris. Summerar exakt till 1."""
    p_home = float(np.tril(m, -1).sum())
    p_draw = float(np.trace(m))
    p_away = float(np.triu(m, 1).sum())
    s = p_home + p_draw + p_away
    p_home, p_draw = p_home / s, p_draw / s
    return p_home, p_draw, 1.0 - p_home - p_draw


def btts_prob(m: np.ndarray) -> float:
    return float(1.0 - m[0, :].sum() - m[:, 0].sum() + m[0, 0])


def over_prob(m: np.ndarray, line: float) -> float:
    n = m.shape[0]
    tot = np.add.outer(np.arange(n), np.arange(n))
    return float(m[tot > line].sum())


def fair_odds(p: float) -> float | None:
    return None if p <= 0 else 1.0 / p


@lru_cache(maxsize=4096)
def _lg(x: float) -> float:
    return math.lgamma(x)


def nb_logpmf(y: int, mu: float, r: float | None) -> float:
    mu = max(mu, 1e-9)
    if r is None or r > 1e6:
        return y * math.log(mu) - mu - math.lgamma(y + 1)
    p = r / (r + mu)
    return _lg(y + r) - _lg(r) - math.lgamma(y + 1) + r * math.log(p) + y * math.log(1 - p)
