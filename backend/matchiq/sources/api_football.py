"""API-Football (API-Sports v3) – fixtures, bekräftade startelvor, skador och matchstatistik.

Kräver API-nyckel (lagras i operativsystemets nyckelförråd). Gratisnivån har 100 anrop/dygn;
dygnskvoten i källkatalogen respekteras och pollningen anpassas efter avståndet till avspark.

Historik (jobbet ``backfill``): per tävling och säsong hämtas spelschemat med ett anrop och därefter
matchdetaljer (lagstatistik med skott/skott på mål/hörnor, startelvor och spelarstatistik) för upp till
20 matcher per anrop med parametern ``ids`` (API-Footballs dokumenterade sätt att spara anrop). Om
abonnemanget inte omfattar en säsong svarar API:t med ett felmeddelande; säsongen markeras då som
"kräver annat abonnemang" och hoppas över tills användaren ändrar något – inga värden fylls i.
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
    jobs = ("fixtures", "details", "lineups", "injuries", "statistics")

    def _headers(self) -> dict:
        key = secrets_store.get_secret("api_football")
        if not key:
            raise SourceBlocked("API-nyckel för API-Football saknas (Inställningar → API-nycklar).")
        return {"x-apisports-key": key}

    def _get2(self, path: str, params: dict, job: str):
        """Som _get men returnerar även API:ts felobjekt (t.ex. {'plan': '...'})."""
        res = self.http.get(self.source_id, BASE + path, job=job, params=params, headers=self._headers(),
                            conditional=False)
        if res.status != 200:
            return res, [], {"http": f"HTTP {res.status}"}
        data = res.json() or {}
        errs = data.get("errors")
        if errs:
            errs = errs if isinstance(errs, dict) else {"error": str(errs)}
            self.http.finish(res.fetch_id, "error", error=str(errs))
            if "requests" in errs or "rateLimit" in errs:
                raise SourceBlocked(f"API-Football: {next(iter(errs.values()))}")
            if "token" in errs or "access" in errs:
                raise SourceBlocked(f"API-Football: {next(iter(errs.values()))}")
            return res, [], errs
        return res, data.get("response") or [], None

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
            days_back: int = 3, days_ahead: int = 14, seasons: list[int] | None = None, progress=None) -> dict:
        if job == "backfill":
            return self.backfill(competitions, seasons, progress)
        if job == "details":
            return self.recent_details()
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

    # ------------------------------------------------------------------ historik
    def _scope_state(self, scope: str) -> dict:
        r = self.app.db.one("SELECT * FROM sync_state WHERE source_id=? AND job='backfill' AND scope=?",
                            (self.source_id, scope))
        return dict(r) if r else {}

    def _save_scope(self, scope: str, status: str, error: str | None = None) -> None:
        self.app.db.execute("""INSERT INTO sync_state (source_id, job, scope, last_run_utc, last_status, last_error)
            VALUES (?,?,?,?,?,?) ON CONFLICT(source_id, job, scope) DO UPDATE SET last_run_utc=excluded.last_run_utc,
            last_status=excluded.last_status, last_error=excluded.last_error""",
                            (self.source_id, "backfill", scope, self.now().strftime("%Y-%m-%dT%H:%M:%SZ"), status,
                             error))

    def backfill(self, competitions: list[str] | None, seasons: list[int] | None, progress=None) -> dict:
        from ..linking import link_source_teams
        now = self.now()
        comps = competitions or list(LEAGUES)
        plan = []
        for comp in comps:
            cal = comp in CALENDAR_LEAGUES
            cur = now.year if cal else (now.year if now.month >= 7 else now.year - 1)
            for season in sorted(seasons or range(cur - 4, cur + 1), reverse=True):  # nyast först
                plan.append((comp, season, cal))
        for i, (comp, season, cal) in enumerate(plan, 1):
            scope = f"{comp}:{season}"
            st = self._scope_state(scope)
            if st.get("last_status") == "plan_restricted":
                self.counts["seasons_plan_restricted"] += 1
                continue
            if progress:
                progress(f"API-Football {comp} {season_label(season, cal)}: spelschema", i, len(plan))
            res, items, errs = self._get2("/fixtures", {"league": LEAGUES[comp], "season": season,
                                                        "timezone": "UTC"}, "backfill")
            if errs:
                status = "plan_restricted" if "plan" in errs else "error"
                self._save_scope(scope, status, "; ".join(f"{k}: {v}" for k, v in errs.items()))
                self.counts[f"seasons_{status}"] += 1
                continue
            fx = []
            for it in items:
                fxo, teams, sc = it.get("fixture") or {}, it.get("teams") or {}, it.get("score") or {}
                ft = sc.get("fulltime") or {}
                if (fxo.get("status") or {}).get("short") in FINISHED and teams.get("home") and teams.get("away"):
                    fx.append({"date": (fxo.get("date") or "")[:10], "home_sid": teams["home"].get("id"),
                               "away_sid": teams["away"].get("id"), "home_name": teams["home"].get("name"),
                               "away_name": teams["away"].get("name"), "hg": ft.get("home"), "ag": ft.get("away")})
            link = link_source_teams(self.app, self.source_id, comp, fx)
            self.counts["teams_linked"] += len(link["linked"])
            self.store_fixtures(items, comp, season_label(season, cal), res.fetch_id)
            fids = [str((it.get("fixture") or {}).get("id")) for it in items
                    if ((it.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
            done = self.details_backfill(comp, season, cal, progress, i, len(plan), fids)
            self._save_scope(scope, "ok" if done else "partial")
        return self.summary()

    def details_backfill(self, comp: str, season: int, cal: bool, progress, i: int, n: int,
                         fixture_ids: list[str] | None = None) -> bool:
        """Matchdetaljer för spelade matcher (i det hämtade spelschemat) som saknar statistik från
        API-Football. True = allt klart för säsongen."""
        def pending() -> list[tuple[str, int]]:
            if not fixture_ids:
                return []
            ph = ",".join("?" * len(fixture_ids))
            rows = self.app.db.query(f"""SELECT s.source_match_id fid, m.id mid FROM match_source_ids s
                JOIN matches m ON m.id = s.match_id
                WHERE s.source_id = ? AND s.source_match_id IN ({ph}) AND m.status = 'finished'
                  AND NOT EXISTS (SELECT 1 FROM team_match_stats t WHERE t.match_id = m.id AND t.source_id = ?)
                  AND NOT EXISTS (SELECT 1 FROM sync_state x WHERE x.source_id = ? AND x.job = '_nostats'
                                  AND x.scope = s.source_match_id)
                ORDER BY m.kickoff_utc""", (self.source_id, *fixture_ids, self.source_id, self.source_id))
            return [(r["fid"], r["mid"]) for r in rows]
        ids = pending()
        self.counts["details_todo"] += len(ids)

        def label(done: int, total: int) -> None:
            if progress:
                progress(f"API-Football {comp} {season_label(season, cal)}: matchdetaljer {done}/{total}", i, n)
        self._fetch_details(ids, "backfill", label)
        return len(pending()) == 0

    def _fetch_details(self, ids: list[tuple[str, int]], job: str, label=None, final=None) -> None:
        """Statistik, startelvor och spelarstatistik för matcherna i ``ids`` [(API-Football-ID, match-ID)].
        Med abonnemang som tillåter ``ids`` hämtas 20 matcher per anrop, annars statistik per match.
        ``final(fid)`` avgör om en match utan statistik ska markeras så att den inte efterfrågas igen."""
        use_ids = self.app.get_setting("api_football_ids_supported") is not False
        for k in range(0, len(ids), 20):
            batch = ids[k:k + 20]
            if label:
                label(k + len(batch), len(ids))
            if use_ids:
                res, items, errs = self._get2("/fixtures", {"ids": "-".join(str(f) for f, _ in batch)}, job)
                if errs and ("ids" in errs or "plan" in errs):
                    # Abonnemanget tillåter inte ids: växla till ett anrop per match (statistik)
                    self.app.set_setting("api_football_ids_supported", False)
                    use_ids = False
                elif errs:
                    self.counts["details_errors"] += 1
                    continue
                else:
                    by_id = {str((it.get("fixture") or {}).get("id")): it for it in items}
                    for fid, mid in batch:
                        it = by_id.get(str(fid))
                        if it is None:
                            self.counts["details_missing"] += 1
                            continue
                        self.store_details(it, mid, res.fetch_id)
                        if not it.get("statistics") and (final is None or final(fid)):
                            self._mark_no_stats(fid)
                    self.http.finish(res.fetch_id, "ok", {"inserted": len(items)})
                    continue
            for fid, mid in batch:
                res, items, errs = self._get2("/fixtures/statistics", {"fixture": fid}, job)
                if errs:
                    self.counts["details_errors"] += 1
                    continue
                if not items and (final is None or final(fid)):
                    self._mark_no_stats(fid)
                self.store_statistics(items, mid, res.fetch_id)

    def recent_details(self, days: int = 7) -> dict:
        """Efter varje matchdag: statistik, startelvor och spelarstatistik för matcher som spelats de senaste
        dagarna och ännu saknar statistik från API-Football. Inga anrop görs när inget saknas. API-Football
        publicerar statistiken under och strax efter matchen; saknas den fortfarande två dygn efter avspark
        markeras matchen så att kvoten inte förbrukas igen."""
        now = self.now()
        rows = self.app.db.query("""SELECT s.source_match_id fid, m.id mid, m.kickoff_utc ko FROM match_source_ids s
            JOIN matches m ON m.id = s.match_id
            WHERE s.source_id = ? AND m.status = 'finished' AND m.kickoff_utc >= ? AND m.kickoff_utc <= ?
              AND NOT EXISTS (SELECT 1 FROM team_match_stats t WHERE t.match_id = m.id AND t.source_id = ?)
              AND NOT EXISTS (SELECT 1 FROM sync_state x WHERE x.source_id = ? AND x.job = '_nostats'
                              AND x.scope = s.source_match_id)
            ORDER BY m.kickoff_utc""", (self.source_id, (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), self.source_id,
                                        self.source_id))
        ids = [(r["fid"], r["mid"]) for r in rows]
        kickoff = {r["fid"]: parse_iso(r["ko"]) for r in rows}
        self.counts["details_todo"] += len(ids)
        if ids:
            self._fetch_details(ids, "details",
                                final=lambda fid: now - kickoff[fid] > timedelta(hours=48))  # type: ignore[operator]
        return self.summary()

    def _mark_no_stats(self, fid: str) -> None:
        """Källan har ingen statistik för matchen – kom ihåg det så att kvoten inte förbrukas igen."""
        self.app.db.execute("""INSERT OR IGNORE INTO sync_state (source_id, job, scope, last_run_utc, last_status)
            VALUES (?,?,?,?,?)""", (self.source_id, "_nostats", str(fid), self.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "no_statistics"))
        self.counts["stats_not_published"] += 1

    def store_details(self, it: dict, match_id: int, fetch_id: int) -> None:
        """Ett svar från /fixtures?ids=… : statistik, startelvor och spelarstatistik för en match."""
        m = self.app.db.one("SELECT kickoff_utc FROM matches WHERE id=?", (match_id,))
        avail = parse_iso(m["kickoff_utc"]) + timedelta(hours=3)
        if it.get("statistics"):
            self.store_statistics(it["statistics"], match_id, fetch_id, finish=False, available_at=avail)
        if it.get("lineups"):
            self.store_lineups(it["lineups"], match_id, fetch_id, finish=False)
        for team_block in it.get("players") or []:
            team = team_block.get("team") or {}
            tid = self.repo.find_team(team.get("name", ""), self.source_id, source_team_id=str(team.get("id")))
            if tid is None:
                continue
            with self.app.db.tx() as c:
                for pb in team_block.get("players") or []:
                    pl = pb.get("player") or {}
                    stt = (pb.get("statistics") or [{}])[0]
                    games, shots, goals = stt.get("games") or {}, stt.get("shots") or {}, stt.get("goals") or {}
                    passes, fouls, cards = stt.get("passes") or {}, stt.get("fouls") or {}, stt.get("cards") or {}
                    if not pl.get("name") or games.get("minutes") is None:
                        continue  # spelaren deltog inte – ingen rad (inte 0 minuter)
                    pid = self.repo.resolve_player(pl["name"], self.source_id, str(pl.get("id")))
                    c.execute("""INSERT OR IGNORE INTO player_match_stats (match_id, player_id, team_id, source_id,
                        fetch_id, started, minutes, minutes_estimated, goals, assists, shots, shots_on_target, passes,
                        key_passes, fouls, yellow_cards, red_cards, available_at_utc, observed_at_utc)
                        VALUES (?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?)""",
                              (match_id, pid, tid, self.source_id, fetch_id, 0 if games.get("substitute") else 1,
                               games.get("minutes"), goals.get("total"), goals.get("assists"), shots.get("total"),
                               shots.get("on"), passes.get("total"), passes.get("key"), fouls.get("committed"),
                               cards.get("yellow"), cards.get("red"), avail.strftime("%Y-%m-%dT%H:%M:%SZ"),
                               self.now().strftime("%Y-%m-%dT%H:%M:%SZ")))
                    self.counts["player_rows"] += 1

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

    def store_lineups(self, items: list[dict], match_id: int, fetch_id: int, finish: bool = True) -> None:
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
        if finish:
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

    def store_statistics(self, items: list[dict], match_id: int, fetch_id: int, finish: bool = True,
                         available_at: datetime | None = None) -> None:
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
                                            fetch_id=fetch_id, available_at=available_at)
            self.counts[f"stats_{r}"] += 1
        if finish:
            self.http.finish(fetch_id, "ok")
