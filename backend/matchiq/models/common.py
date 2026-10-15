"""Gemensamma hjälpfunktioner för modellerna."""
from __future__ import annotations

import numpy as np

from .dist import count_summary, outcome_probs, score_matrix, total_summary, btts_prob, over_prob

METRIC_LABELS = {"goals": "Mål", "shots": "Skott", "sot": "Skott på mål", "corners": "Hörnor"}
THIN_HISTORY = 5   # färre matcher än så per lag => varning för tunn historik


def team_rows(d: dict, team_id: int, last_n: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For-/emot-värden för ett lag (senaste först om last_n anges). Returnerar (for, against, kickoff)."""
    mh = d["home"] == team_id
    ma = d["away"] == team_id
    f = np.concatenate([d["h"][mh], d["a"][ma]])
    ag = np.concatenate([d["a"][mh], d["h"][ma]])
    ko = np.concatenate([d["kickoff"][mh], d["kickoff"][ma]])
    order = np.argsort(-ko)
    f, ag, ko = f[order], ag[order], ko[order]
    if last_n is not None:
        f, ag, ko = f[:last_n], ag[:last_n], ko[:last_n]
    return f, ag, ko


def goals_block(lam_h: float, lam_a: float, rho: float = 0.0, r_h=None, r_a=None) -> tuple[dict, dict]:
    m = score_matrix(lam_h, lam_a, rho)
    p = outcome_probs(m)
    block = {
        "home": count_summary(lam_h, r_h),
        "away": count_summary(lam_a, r_a),
        "total": total_summary(lam_h, lam_a, r_h, r_a),
    }
    extras = {"btts": btts_prob(m), "over_2_5": over_prob(m, 2.5), "over_1_5": over_prob(m, 1.5),
              "most_likely_score": [int(x) for x in np.unravel_index(np.argmax(m), m.shape)]}
    return {"p_home": p[0], "p_draw": p[1], "p_away": p[2]}, {**block, "extras": extras}


def counts_block(mu_h: float, mu_a: float, r_h=None, r_a=None) -> dict:
    return {"home": count_summary(mu_h, r_h), "away": count_summary(mu_a, r_a),
            "total": total_summary(mu_h, mu_a, r_h, r_a)}
