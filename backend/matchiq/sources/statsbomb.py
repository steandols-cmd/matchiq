"""StatsBomb Open Data (Hudl): händelsedata för ett UTVALT urval av tävlingar och säsonger.

Hämtas via GitHubs REST-API. Lag- och spelarstatistik beräknas ur händelserna för ordinarie
speltid (period 1–2); förlängning (3–4) och straffläggning (5) räknas inte in. Minuter är
uppskattade ur händelseklockan och markeras som uppskattade. Träning kräver att användaren
godkänt StatsBombs villkor (källkatalogen).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .. import secrets_store
from ..timeutil import UTC
from .base import Adapter

API = "https://api.github.com/repos/statsbomb/open-data/contents/data/{path}"
COMP_MAP = {  # StatsBomb competition_name -> vår kod
    "Champions League": "UCL", "Premier League": "ENG1", "La Liga": "ESP1", "1. Bundesliga": "GER1",
    "Serie A": "ITA1", "Ligue 1": "FRA1",
}
SOT_OUTCOMES = {"Goal", "Saved", "Saved To Post", "Saved to Post"}


def team_stats_from_events(events: list[dict]) -> dict[int, dict]:
    """Lagstatistik ur StatsBomb-händelser (endast period 1–2)."""
    st: dict[int, dict] = defaultdict(lambda: {"shots": 0, "shots_on_target": 0, "corners": 0, "fouls": 0,
                                               "yellow_cards": 0, "red_cards": 0, "passes": 0, "xg": 0.0,
                                               "name": None})
    for ev in events:
        if ev.get("period") not in (1, 2):
            continue
        team = ev.get("team") or {}
        tid = team.get("id")
        if tid is None:
            continue
        s = st[tid]
        s["name"] = team.get("name")
        typ = (ev.get("type") or {}).get("name")
        if typ == "Shot":
            shot = ev.get("shot") or {}
            if (shot.get("type") or {}).get("name") == "Penalty" and ev.get("period") == 5:
                continue
            s["shots"] += 1
            if (shot.get("outcome") or {}).get("name") in SOT_OUTCOMES:
                s["shots_on_target"] += 1
            s["xg"] += float(shot.get("statsbomb_xg") or 0.0)
        elif typ == "Pass":
            s["passes"] += 1
            if ((ev.get("pass") or {}).get("type") or {}).get("name") == "Corner":
                s["corners"] += 1
        elif typ == "Foul Committed":
            s["fouls"] += 1
            card = ((ev.get("foul_committed") or {}).get("card") or {}).get("name")
            if card == "Yellow Card":
                s["yellow_cards"] += 1
            elif card in ("Red Card", "Second Yellow"):
                s["red_cards"] += 1
        elif typ == "Bad Behaviour":
            card = ((ev.get("bad_behaviour") or {}).get("card") or {}).get("name")
            if card == "Yellow Card":
                s["yellow_cards"] += 1
            elif card in ("Red Card", "Second Yellow"):
                s["red_cards"] += 1
    return dict(st)


def player_stats_from_events(events: list[dict]) -> dict[int, dict]:
    ps: dict[int, dict] = defaultdict(lambda: {"name": None, "team_id": None, "started": 0, "on": None, "off": None,
                                               "goals": 0, "shots": 0, "shots_on_target": 0, "xg": 0.0, "passes": 0,
                                               "key_passes": 0, "tackles": 0, "interceptions": 0, "fouls": 0,
                                               "yellow_cards": 0, "red_cards": 0})
    end_minute = 90.0
    for ev in events:
        if ev.get("period") in (1, 2):
            end_minute = max(end_minute, float(ev.get("minute") or 0) + float(ev.get("second") or 0) / 60)
    for ev in events:
        typ = (ev.get("type") or {}).get("name")
        team_id = (ev.get("team") or {}).get("id")
        if typ == "Starting XI":
            for e in ((ev.get("tactics") or {}).get("lineup") or []):
                pl = e.get("player") or {}
                p = ps[pl.get("id")]
                p.update({"name": pl.get("name"), "team_id": team_id, "started": 1, "on": 0.0})
            continue
        if ev.get("period") not in (1, 2):
            continue
        pl = ev.get("player") or {}
        pid = pl.get("id")
        minute = float(ev.get("minute") or 0) + float(ev.get("second") or 0) / 60
        if typ == "Substitution":
            if pid is not None:
                ps[pid]["off"] = minute
            rep = ((ev.get("substitution") or {}).get("replacement") or {})
            if rep.get("id") is not None:
                q = ps[rep["id"]]
                q.update({"name": rep.get("name"), "team_id": team_id, "on": minute})
            continue
        if pid is None:
            continue
        p = ps[pid]
        p["name"] = p["name"] or pl.get("name")
        p["team_id"] = p["team_id"] or team_id
        if typ == "Shot":
            shot = ev.get("shot") or {}
            p["shots"] += 1
            p["xg"] += float(shot.get("statsbomb_xg") or 0.0)
            oc = (shot.get("outcome") or {}).get("name")
            if oc in SOT_OUTCOMES:
                p["shots_on_target"] += 1
            if oc == "Goal":
                p["goals"] += 1
        elif typ == "Pass":
            p["passes"] += 1
            if (ev.get("pass") or {}).get("shot_assist") or (ev.get("pass") or {}).get("goal_assist"):
                p["key_passes"] += 1
        elif typ == "Duel" and ((ev.get("duel") or {}).get("type") or {}).get("name") == "Tackle":
            p["tackles"] += 1
        elif typ == "Interception":
            p["interceptions"] += 1
        elif typ == "Foul Committed":
            p["fouls"] += 1
    for p in ps.values():
        if p["on"] is not None:
            p["minutes"] = round((p["off"] if p["off"] is not None else end_minute) - p["on"], 1)
        else:
            p["minutes"] = None
    return dict(ps)


class StatsBombAdapter(Adapter):
    source_id = "statsbomb_open"
    label = "StatsBomb Open Data"
    jobs = ("matches",)

    def _get(self, path: str, job: str):
        headers = {"Accept": "application/vnd.github.raw", "X-GitHub-Api-Version": "2022-11-28"}
        tok = secrets_store.get_secret("github_token")
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        return self.http.get(self.source_id, API.format(path=path), job=job, headers=headers)

    def run(self, job: str = "matches", max_matches: int = 60, competitions: list[str] | None = None) -> dict:
        comps = self._get("competitions.json", job)
        if comps.status != 200:
            return {"error": f"competitions.json HTTP {comps.status}"}
        wanted = set(competitions or COMP_MAP.values())
        done_ids = {r["source_match_id"] for r in self.app.db.query(
            "SELECT source_match_id FROM match_source_ids WHERE source_id=?", (self.source_id,))}
        budget = max_matches
        for c in comps.json():
            code = COMP_MAP.get(c.get("competition_name"))
            if code not in wanted:
                continue
            ml = self._get(f"matches/{c['competition_id']}/{c['season_id']}.json", job)
            if ml.status != 200:
                continue
            for m in ml.json():
                if budget <= 0:
                    return self.summary()
                if str(m["match_id"]) in done_ids:
                    self.counts["unchanged"] += 1
                    continue
                self._import_match(m, code, c.get("season_name"), ml.fetch_id, job)
                budget -= 1
        return self.summary()

    def _import_match(self, m: dict, comp: str, season_name: str | None, list_fetch: int, job: str) -> None:
        d = datetime.strptime(m["match_date"], "%Y-%m-%d")
        ko_t = (m.get("kick_off") or "20:00:00")[:5]
        ko = d.replace(hour=int(ko_t[:2]), minute=int(ko_t[3:5]), tzinfo=ZoneInfo("Europe/Paris")).astimezone(UTC)
        home = m["home_team"]
        away = m["away_team"]
        hid = self.team(home["home_team_name"], context=comp, source_team_id=home["home_team_id"])
        aid = self.team(away["away_team_name"], context=comp, source_team_id=away["away_team_id"])
        season = (season_name or "").replace("/20", "/") if season_name and len(season_name) == 9 else season_name
        mid, act = self.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=hid, away_team_id=aid,
                                          source_id=self.source_id, status="finished", season_label=season,
                                          source_match_id=str(m["match_id"]), fetch_id=list_fetch,
                                          stage=(m.get("competition_stage") or {}).get("name"))
        self.counts[f"match_{act}"] += 1
        ev = self._get(f"events/{m['match_id']}.json", job)
        if ev.status != 200:
            self.counts["events_missing"] += 1
            return
        events = ev.json()
        ts = team_stats_from_events(events)
        goals_90 = {hid: 0, aid: 0}
        sb_to_ours = {home["home_team_id"]: hid, away["away_team_id"]: aid}
        for e in events:
            if e.get("period") in (1, 2) and (e.get("type") or {}).get("name") == "Shot" and \
                    ((e.get("shot") or {}).get("outcome") or {}).get("name") == "Goal":
                goals_90[sb_to_ours[(e.get("team") or {}).get("id")]] += 1
            if e.get("period") in (1, 2) and (e.get("type") or {}).get("name") == "Own Goal For":
                goals_90[sb_to_ours[(e.get("team") or {}).get("id")]] += 1
        went_et = any(e.get("period") in (3, 4) for e in events)
        vals = {"home_goals_90": goals_90[hid], "away_goals_90": goals_90[aid]}
        if went_et:
            vals.update({"home_goals_aet": m.get("home_score"), "away_goals_aet": m.get("away_score"),
                         "decided_by": "extra_time"})
        avail = ko + timedelta(hours=3)
        self.repo.upsert_result(mid, self.source_id, vals, fetch_id=ev.fetch_id, available_at=avail,
                                original_home=home["home_team_name"], original_away=away["away_team_name"])
        for sb_id, s in ts.items():
            tid = sb_to_ours.get(sb_id)
            if tid is None:
                continue
            self.repo.upsert_team_stats(mid, tid, tid == hid, self.source_id,
                                        {k: s[k] for k in ("shots", "shots_on_target", "corners", "fouls",
                                                           "yellow_cards", "red_cards", "passes")} |
                                        {"xg": round(s["xg"], 3)}, fetch_id=ev.fetch_id, available_at=avail)
        ps = player_stats_from_events(events)
        lineups = defaultdict(list)
        with self.app.db.tx() as c:
            for pid, p in ps.items():
                if pid is None or p["team_id"] not in sb_to_ours:
                    continue
                our_pid = self.repo.resolve_player(p["name"], self.source_id, str(pid))
                c.execute("""INSERT OR IGNORE INTO player_match_stats (match_id, player_id, team_id, source_id, fetch_id,
                    started, minutes, minutes_estimated, goals, shots, shots_on_target, xg, passes, key_passes, tackles,
                    interceptions, fouls, available_at_utc, observed_at_utc) VALUES
                    (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?)""",
                          (mid, our_pid, sb_to_ours[p["team_id"]], self.source_id, ev.fetch_id, p["started"],
                           p["minutes"], p["goals"], p["shots"], p["shots_on_target"], round(p["xg"], 3), p["passes"],
                           p["key_passes"], p["tackles"], p["interceptions"], p["fouls"],
                           avail.strftime("%Y-%m-%dT%H:%M:%SZ"), self.now().strftime("%Y-%m-%dT%H:%M:%SZ")))
                if p["started"]:
                    lineups[sb_to_ours[p["team_id"]]].append({"name": p["name"], "player_id": our_pid,
                                                              "is_starter": True})
        for tid, players in lineups.items():
            # Historisk elva ur händelsedata – "bekräftad" i efterhand; tillgänglig först efter match.
            self.repo.upsert_lineup(mid, tid, self.source_id, "confirmed", players, fetched_at=avail,
                                    fetch_id=ev.fetch_id)
        self.http.finish(ev.fetch_id, "ok", {"inserted": 1})
        self.counts["events_imported"] += 1
