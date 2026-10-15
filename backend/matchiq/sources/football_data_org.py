"""football-data.org API v4 – fixtures och resultat (nyckel krävs, gratisnivå 10 anrop/min)."""
from __future__ import annotations

from datetime import timedelta

from .. import secrets_store
from ..timeutil import parse_iso
from .base import Adapter, season_label
from .http import SourceBlocked

BASE = "https://api.football-data.org/v4"
CODES = {"UCL": "CL", "ENG1": "PL", "ESP1": "PD", "GER1": "BL1", "ITA1": "SA", "FRA1": "FL1", "NED1": "DED",
         "POR1": "PPL"}
STATUS = {"SCHEDULED": "scheduled", "TIMED": "scheduled", "IN_PLAY": "live", "PAUSED": "live",
          "FINISHED": "finished", "POSTPONED": "postponed", "SUSPENDED": "postponed", "CANCELLED": "cancelled",
          "AWARDED": "awarded"}


class FootballDataOrgAdapter(Adapter):
    source_id = "football_data_org"
    label = "football-data.org"
    jobs = ("fixtures",)

    def run(self, job: str = "fixtures", competitions: list[str] | None = None, days_back: int = 3,
            days_ahead: int = 21) -> dict:
        key = secrets_store.get_secret("football_data_org")
        if not key:
            raise SourceBlocked("API-nyckel för football-data.org saknas (Inställningar → API-nycklar).")
        now = self.now()
        for comp in competitions or list(CODES):
            res = self.http.get(self.source_id, f"{BASE}/competitions/{CODES[comp]}/matches", job=job,
                                params={"dateFrom": (now - timedelta(days=days_back)).strftime("%Y-%m-%d"),
                                        "dateTo": (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")},
                                headers={"X-Auth-Token": key}, conditional=False)
            if res.status != 200:
                self.counts["errors"] += 1
                continue
            self.store(res.json().get("matches") or [], comp, res.fetch_id)
        return self.summary()

    def store(self, matches: list[dict], comp: str, fetch_id: int) -> None:
        c = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        for m in matches:
            ko = parse_iso(m.get("utcDate"))
            ht, at = m.get("homeTeam") or {}, m.get("awayTeam") or {}
            if ko is None or not ht.get("name") or not at.get("name"):
                c["skipped"] += 1
                continue
            h = self.team(ht["name"], context=comp, source_team_id=ht.get("id"))
            a = self.team(at["name"], context=comp, source_team_id=at.get("id"))
            status = STATUS.get(m.get("status"), "unknown")
            sy = ko.year if ko.month >= 7 else ko.year - 1
            season = (m.get("season") or {}).get("startDate", "")[:4]
            mid, act = self.repo.upsert_match(
                competition_code=comp, kickoff_utc=ko, home_team_id=h, away_team_id=a, source_id=self.source_id,
                status=status, season_label=season_label(int(season) if season.isdigit() else sy),
                source_match_id=str(m.get("id")), matchday=str(m["matchday"]) if m.get("matchday") else None,
                stage=m.get("stage"), fetch_id=fetch_id)
            c[act if act in c else "updated"] += 1
            sc = m.get("score") or {}
            if status == "finished":
                dur = sc.get("duration", "REGULAR")
                reg = sc.get("regularTime") or (sc.get("fullTime") if dur == "REGULAR" else None) or {}
                full = sc.get("fullTime") or {}
                vals = {"home_goals_90": reg.get("home"), "away_goals_90": reg.get("away"),
                        "home_goals_ht": (sc.get("halfTime") or {}).get("home"),
                        "away_goals_ht": (sc.get("halfTime") or {}).get("away")}
                if dur in ("EXTRA_TIME", "PENALTY_SHOOTOUT"):
                    et = sc.get("extraTime") or {}
                    if reg.get("home") is not None and et.get("home") is not None:
                        vals.update({"home_goals_aet": reg["home"] + et["home"],
                                     "away_goals_aet": reg["away"] + et["away"]})
                    vals["decided_by"] = "penalties" if dur == "PENALTY_SHOOTOUT" else "extra_time"
                    pens = sc.get("penalties") or {}
                    if pens.get("home") is not None:
                        vals.update({"home_pens": pens["home"], "away_pens": pens["away"]})
                if vals["home_goals_90"] is None and dur == "REGULAR":
                    vals.update({"home_goals_90": full.get("home"), "away_goals_90": full.get("away")})
                self.repo.upsert_result(mid, self.source_id, vals, fetch_id=fetch_id, original_home=ht["name"],
                                        original_away=at["name"])
        self.http.finish(fetch_id, "ok", c)
        for k, v in c.items():
            self.counts[k] += v
