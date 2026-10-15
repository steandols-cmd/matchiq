"""API-Football (API-Sports v3) – fixtures, bekräftade startelvor, skador och matchstatistik.

Kräver API-nyckel (lagras i operativsystemets nyckelförråd). Gratisnivån har 100 anrop/dygn;
dygnskvoten i källkatalogen respekteras och pollningen anpassas efter avståndet till avspark.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import secrets_store
from ..timeutil import parse_iso
from .base import CALENDAR_LEAGUES, Adapter, season_label
from .http import SourceBlocked

BASE = "https://v3.football.api-sports.io"
LEAGUES = {"UCL": 2, "ENG1": 39, "ESP1": 140, "GER1": 78, "ITA1": 135, "FRA1": 61, "SWE1": 113}
FINISHED = {"FT", "AET", "PEN", "AWD", "WO"}
STATUS_MAP = {"NS": "scheduled", "TBD": "scheduled", "PST": "postponed", "CANC": "cancelled", "ABD": "cancelled",
              "1H": "live", "HT": "live", "2H": "live", "ET": "live", "BT": "live", "P": "live", "LIVE": "live",
              "INT": "live", "SUSP": "postponed"}
STAT_KEYS = {"Total Shots": "shots", "Shots on Goal": "shots_on_target", "Corner Kicks": "corners",
             "Fouls": "fouls", "Yellow Cards": "yellow_cards", "Red Cards": "red_cards", "Offsides": "offsides",
             "Goalkeeper Saves": "saves", "Total passes": "passes", "expected_goals": "xg"}


def _num(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip().rstrip("%")
        if not v:
            return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


class ApiFootballAdapter(Adapter):
    source_id = "api_football"
    label = "API-Football"
    jobs = ("fixtures", "lineups", "injuries", "statistics")

    def _headers(self) -> dict:
        key = secrets_store.get_secret("api_football")
        if not key:
            raise SourceBlocked("API-nyckel för API-Football saknas (Inställningar → API-nycklar).")
        return {"x-apisports-key": key}

    def _get(self, path: str, params: dict, job: str):
        res = self.http.get(self.source_id, BASE + path, job=job, params=params, headers=self._headers(),
                            conditional=False)
        if res.status != 200:
            return res, []
        data = res.json() or {}
        if data.get("errors"):
            self.http.finish(res.fetch_id, "error", error=str(data["errors"]))
            return res, []
        return res, data.get("response") or []

    def run(self, job: str = "fixtures", competitions: list[str] | None = None, match_id: int | None = None,
            days_back: int = 3, days_ahead: int = 14) -> dict:
        if job == "fixtures":
            now = self.now()
            for comp in competitions or list(LEAGUES):
                cal = comp in CALENDAR_LEAGUES
                season = now.year if cal else (now.year if now.month >= 7 else now.year - 1)
                res, items = self._get("/fixtures", {"league": LEAGUES[comp], "season": season, "timezone": "UTC",
                                                     "from": (now - timedelta(days=days_back)).strftime("%Y-%m-%d"),
                                                     "to": (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")},
                                       job)
                self.store_fixtures(items, comp, season_label(season, cal), res.fetch_id)
        elif match_id is not None:
            fx = self.app.db.one("SELECT source_match_id FROM match_source_ids WHERE match_id=? AND source_id=?",
                                 (match_id, self.source_id))
            if fx is None:
                return {"skipped": "matchen saknar API-Football-ID"}
            fid = fx["source_match_id"]
            if job == "lineups":
                res, items = self._get("/fixtures/lineups", {"fixture": fid}, job)
                self.store_lineups(items, match_id, res.fetch_id)
            elif job == "injuries":
                res, items = self._get("/injuries", {"fixture": fid}, job)
                self.store_injuries(items, match_id, res.fetch_id)
            elif job == "statistics":
                res, items = self._get("/fixtures/statistics", {"fixture": fid}, job)
                self.store_statistics(items, match_id, res.fetch_id)
        return self.summary()

    # ------------------------------------------------------------------ parse/store
    def store_fixtures(self, items: list[dict], comp: str, season: str, fetch_id: int) -> None:
        c = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        for it in items:
            fx, teams, goals, score = it.get("fixture") or {}, it.get("teams") or {}, it.get("goals") or {}, \
                it.get("score") or {}
            ko = parse_iso(fx.get("date"))
            if ko is None or not teams.get("home") or not teams.get("away"):
                c["skipped"] += 1
                continue
            short = (fx.get("status") or {}).get("short", "NS")
            status = "finished" if short in FINISHED else STATUS_MAP.get(short, "unknown")
            h = self.team(teams["home"]["name"], context=comp, source_team_id=teams["home"].get("id"))
            a = self.team(teams["away"]["name"], context=comp, source_team_id=teams["away"].get("id"))
            mid, act = self.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                              source_id=self.source_id, status=status, season_label=season,
                                              source_match_id=str(fx.get("id")),
                                              round_=(it.get("league") or {}).get("round"),
                                              venue=(fx.get("venue") or {}).get("name"), fetch_id=fetch_id)
            c[act if act in c else "updated"] += 1
            if status == "finished":
                ft = score.get("fulltime") or {}
                et = score.get("extratime") or {}
                pen = score.get("penalty") or {}
                ht = score.get("halftime") or {}
                vals = {"home_goals_90": ft.get("home"), "away_goals_90": ft.get("away"),
                        "home_goals_ht": ht.get("home"), "away_goals_ht": ht.get("away")}
                if et.get("home") is not None:
                    vals.update({"home_goals_aet": (ft.get("home") or 0) + et["home"],
                                 "away_goals_aet": (ft.get("away") or 0) + et["away"], "decided_by": "extra_time"})
                if pen.get("home") is not None:
                    vals.update({"home_pens": pen["home"], "away_pens": pen["away"], "decided_by": "penalties"})
                if vals["home_goals_90"] is None and goals.get("home") is not None and short == "FT":
                    vals.update({"home_goals_90": goals["home"], "away_goals_90": goals["away"]})
                self.repo.upsert_result(mid, self.source_id, vals, fetch_id=fetch_id,
                                        original_home=teams["home"]["name"], original_away=teams["away"]["name"])
        self.http.finish(fetch_id, "ok", c)
        for k, v in c.items():
            self.counts[k] += v

    def store_lineups(self, items: list[dict], match_id: int, fetch_id: int) -> None:
        m = self.app.db.one("SELECT home_team_id, away_team_id FROM matches WHERE id=?", (match_id,))
        for it in items:
            team = it.get("team") or {}
            tid = self.repo.find_team(team.get("name", ""), self.source_id, source_team_id=str(team.get("id")))
            if tid not in (m["home_team_id"], m["away_team_id"]):
                self.counts["lineup_team_mismatch"] += 1
                continue
            players = []
            for e in it.get("startXI") or []:
                p = e.get("player") or {}
                if not p.get("name"):
                    continue
                players.append({"name": p["name"], "number": p.get("number"), "position": p.get("pos"),
                                "is_starter": True,
                                "player_id": self.repo.resolve_player(p["name"], self.source_id, p.get("id"))})
            if len(players) < 11:
                self.counts["lineup_incomplete"] += 1  # ofullständig elva sparas inte som bekräftad
                continue
            r = self.repo.upsert_lineup(match_id, tid, self.source_id, "confirmed", players, fetched_at=self.now(),
                                        formation=it.get("formation"), fetch_id=fetch_id)
            self.counts[f"lineup_{r}"] += 1
        self.http.finish(fetch_id, "ok", {"inserted": self.counts.get("lineup_inserted", 0)})

    def store_injuries(self, items: list[dict], match_id: int, fetch_id: int) -> None:
        for it in items:
            p, team = it.get("player") or {}, it.get("team") or {}
            tid = self.repo.find_team(team.get("name", ""), self.source_id, source_team_id=str(team.get("id")))
            if tid is None or not p.get("name"):
                continue
            typ = (p.get("type") or "").lower()
            kind = "suspension" if "suspen" in (p.get("reason") or "").lower() else (
                "doubtful" if "questionable" in typ or "doubt" in typ else "injury")
            r = self.repo.add_availability(match_id=match_id, team_id=tid, player_name=p["name"], kind=kind,
                                           reason=p.get("reason"), source_id=self.source_id, fetched_at=self.now())
            self.counts[f"availability_{r}"] += 1
        self.http.finish(fetch_id, "ok")

    def store_statistics(self, items: list[dict], match_id: int, fetch_id: int) -> None:
        m = self.app.db.one("SELECT home_team_id, away_team_id FROM matches WHERE id=?", (match_id,))
        for it in items:
            team = it.get("team") or {}
            tid = self.repo.find_team(team.get("name", ""), self.source_id, source_team_id=str(team.get("id")))
            if tid not in (m["home_team_id"], m["away_team_id"]):
                continue
            vals = {}
            for s in it.get("statistics") or []:
                key = STAT_KEYS.get(s.get("type"))
                if key:
                    v = _num(s.get("value"))
                    vals[key] = None if v is None else (v if key == "xg" else int(v))
            r = self.repo.upsert_team_stats(match_id, tid, tid == m["home_team_id"], self.source_id, vals,
                                            fetch_id=fetch_id)
            self.counts[f"stats_{r}"] += 1
        self.http.finish(fetch_id, "ok")
        _ = datetime
