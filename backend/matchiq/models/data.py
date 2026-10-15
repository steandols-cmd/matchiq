"""Tidsgränssäker dataåtkomst för modeller.

``HistoryStore`` läser in avslutade matcher med resultat och lagstatistik från källor som får
användas för träning. ``HistoryStore.view(cutoff)`` returnerar en ``DataView`` som ENDAST
innehåller observationer där

    avspark < cutoff  OCH  observationens tillgänglighetstid <= cutoff.

Modellerna får bara en DataView – de kan alltså inte se data som publicerats efter prognosens
datagräns. Detta verifieras av läckagetestet i testsviten.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from ..catalog import training_source_ids
from ..db import Database
from ..timeutil import parse_iso

RESULT_PRIORITY = ["manual", "uefa", "api_football", "football_data_org", "openfootball", "statsbomb_open",
                   "football_data_couk", "user_file"]
METRICS = ("goals", "shots", "sot", "corners")
STAT_COLS = {"shots": "shots", "sot": "shots_on_target", "corners": "corners"}


def _ts(s: str | None) -> float:
    if not s:
        return float("nan")
    return parse_iso(s).timestamp()  # type: ignore[union-attr]


@dataclass
class Arrays:
    match_id: np.ndarray
    comp: np.ndarray
    season: np.ndarray
    kickoff: np.ndarray
    home: np.ndarray
    away: np.ndarray
    # per mått: hemma-/bortavärde och tillgänglighetstid (NaN = saknas)
    vals_h: dict[str, np.ndarray]
    vals_a: dict[str, np.ndarray]
    avail: dict[str, np.ndarray]
    src: dict[str, np.ndarray]
    et: np.ndarray            # avgjord i förlängning/straffar (utesluts från träning)


class HistoryStore:
    def __init__(self, arrays: Arrays, training_sources: set[str]):
        self.a = arrays
        self.training_sources = training_sources

    @classmethod
    def load(cls, db: Database, training_sources: set[str] | None = None,
             competitions: list[str] | None = None) -> "HistoryStore":
        allowed = training_sources if training_sources is not None else training_source_ids(db)
        comp_filter = ""
        params: list = []
        if competitions:
            comp_filter = f" AND co.code IN ({','.join('?' * len(competitions))})"
            params = list(competitions)
        rows = db.query(f"""SELECT m.id, co.code, COALESCE(s.label,'') AS season, m.kickoff_utc, m.home_team_id,
                            m.away_team_id FROM matches m JOIN competitions co ON co.id=m.competition_id
                            LEFT JOIN seasons s ON s.id=m.season_id
                            WHERE m.status='finished' {comp_filter} ORDER BY m.kickoff_utc, m.id""", params)
        idx = {r["id"]: i for i, r in enumerate(rows)}
        n = len(rows)
        vals_h = {k: np.full(n, np.nan) for k in METRICS}
        vals_a = {k: np.full(n, np.nan) for k in METRICS}
        avail = {k: np.full(n, np.nan) for k in METRICS}
        src = {k: np.full(n, "", dtype=object) for k in METRICS}
        prio = {s: i for i, s in enumerate(RESULT_PRIORITY)}
        best_rank = {k: np.full(n, 10 ** 6) for k in METRICS}
        if allowed:
            ph = ",".join("?" * len(allowed))
            for r in db.query(f"""SELECT match_id, source_id, home_goals_90, away_goals_90, available_at_utc
                                 FROM match_results WHERE source_id IN ({ph})
                                 AND home_goals_90 IS NOT NULL AND away_goals_90 IS NOT NULL""", list(allowed)):
                i = idx.get(r["match_id"])
                if i is None:
                    continue
                rank = prio.get(r["source_id"], 99)
                if rank < best_rank["goals"][i]:
                    best_rank["goals"][i] = rank
                    vals_h["goals"][i] = r["home_goals_90"]
                    vals_a["goals"][i] = r["away_goals_90"]
                    avail["goals"][i] = _ts(r["available_at_utc"])
                    src["goals"][i] = r["source_id"]
            stat_rows = db.query(f"""SELECT match_id, is_home, source_id, shots, shots_on_target, corners,
                                    available_at_utc FROM team_match_stats WHERE source_id IN ({ph})""",
                                 list(allowed))
            # välj per match/mått den högst prioriterade källan som har BÅDA lagens värden
            per: dict[tuple, dict] = {}
            for r in stat_rows:
                for metric, col in STAT_COLS.items():
                    if r[col] is None:
                        continue
                    key = (r["match_id"], metric, r["source_id"])
                    d = per.setdefault(key, {})
                    d["h" if r["is_home"] else "a"] = r[col]
                    d["t"] = max(d.get("t", 0.0), _ts(r["available_at_utc"]))
            for (mid, metric, sid), d in per.items():
                i = idx.get(mid)
                if i is None or "h" not in d or "a" not in d:
                    continue
                rank = prio.get(sid, 99)
                if rank < best_rank[metric][i]:
                    best_rank[metric][i] = rank
                    vals_h[metric][i] = d["h"]
                    vals_a[metric][i] = d["a"]
                    avail[metric][i] = d["t"]
                    src[metric][i] = sid
        et_ids = {r["match_id"] for r in db.query(
            "SELECT DISTINCT match_id FROM match_results WHERE decided_by IN ('extra_time','penalties')")}
        arrays = Arrays(
            match_id=np.array([r["id"] for r in rows], dtype=np.int64),
            comp=np.array([r["code"] for r in rows], dtype=object),
            season=np.array([r["season"] for r in rows], dtype=object),
            kickoff=np.array([_ts(r["kickoff_utc"]) for r in rows]),
            home=np.array([r["home_team_id"] for r in rows], dtype=np.int64),
            away=np.array([r["away_team_id"] for r in rows], dtype=np.int64),
            vals_h=vals_h, vals_a=vals_a, avail=avail, src=src,
            et=np.array([r["id"] in et_ids for r in rows], dtype=bool))
        return cls(arrays, set(allowed))

    def view(self, cutoff: datetime, exclude_match_ids: set[int] | None = None,
             include_extra_time: bool = False) -> "DataView":
        """Matcher avgjorda i förlängning/straffar utesluts som standard (90-minutersstatistiken är
        inte separerad från förlängningen i alla källor)."""
        return DataView(self, cutoff.timestamp(), exclude_match_ids or set(), include_extra_time)

    def view_ts(self, cutoff_ts: float, include_extra_time: bool = False) -> "DataView":
        return DataView(self, cutoff_ts, set(), include_extra_time)


class DataView:
    """Ögonblicksbild av historiken vid en datagräns."""

    def __init__(self, store: HistoryStore, cutoff_ts: float, exclude: set[int], include_extra_time: bool = False):
        self.store = store
        self.cutoff_ts = cutoff_ts
        a = store.a
        base = a.kickoff < cutoff_ts
        if not include_extra_time:
            base &= ~a.et
        if exclude:
            base &= ~np.isin(a.match_id, np.array(sorted(exclude), dtype=np.int64))
        self._masks = {}
        for metric in METRICS:
            m = base & ~np.isnan(a.vals_h[metric]) & (a.avail[metric] <= cutoff_ts)
            self._masks[metric] = m

    def metric(self, metric: str, competitions: tuple[str, ...] | None = None) -> dict[str, np.ndarray]:
        a = self.store.a
        m = self._masks[metric]
        if competitions:
            m = m & np.isin(a.comp, np.array(competitions, dtype=object))
        assert np.all(a.kickoff[m] < self.cutoff_ts), "läckage: match efter datagräns"
        assert np.all(a.avail[metric][m] <= self.cutoff_ts), "läckage: observation publicerad efter datagräns"
        return {"match_id": a.match_id[m], "kickoff": a.kickoff[m], "home": a.home[m], "away": a.away[m],
                "h": a.vals_h[metric][m], "a": a.vals_a[metric][m], "comp": a.comp[m], "season": a.season[m],
                "src": a.src[metric][m]}

    def count(self, metric: str, team_id: int, competitions: tuple[str, ...] | None = None) -> int:
        d = self.metric(metric, competitions)
        return int(np.sum((d["home"] == team_id) | (d["away"] == team_id)))

    def sources_used(self, metric: str, competitions: tuple[str, ...] | None = None) -> dict[str, int]:
        d = self.metric(metric, competitions)
        out: dict[str, int] = {}
        for s in d["src"]:
            out[s] = out.get(s, 0) + 1
        return out
