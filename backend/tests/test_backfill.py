"""Historikhämtning: lagkoppling via matcher, Wyscout-import, API-Football-historik och driftstatus.

Svaren är testfixturer byggda efter källornas dokumenterade format (inga nätverksanrop).
"""
import io
import json
import unittest
import zipfile
from datetime import datetime, timedelta

from helpers import FakeResponse, FakeSession, make_app

from matchiq import analytics, catalog, secrets_store
from matchiq.linking import link_source_teams
from matchiq.models.data import HistoryStore
from matchiq.sources import sync
from matchiq.sources.api_football import ApiFootballAdapter
from matchiq.sources.http import HttpClient
from matchiq.sources.wyscout import aggregate_events, minutes_from_formation, required_tags, tag_ids
from matchiq.timeutil import UTC

TAGS_CSV = "Tag,Label,Description\n101,Goal,Goal\n1801,accurate,accurate\n1802,not_accurate,not accurate\n" \
           "302,key_pass,Key pass\n1702,yellow_card,Yellow card\n1701,red_card,Red card\n" \
           "1703,second_yellow_card,Second yellow card\n"


def base_league(app, comp="ENG1", start=datetime(2017, 8, 12, 14, tzinfo=UTC)):
    """Fyra lag och åtta spelade matcher från 'openfootball' (som befintlig grunddata)."""
    names = ["Arsenal FC", "Chelsea FC", "Liverpool FC", "Everton FC"]
    ids = [app.repo.resolve_team(n, "openfootball", context=comp) for n in names]
    fixtures = []
    scores = [(2, 0), (1, 1), (3, 2), (0, 1), (2, 2), (4, 0), (1, 0), (0, 0)]
    pairs = [(0, 1), (2, 3), (1, 2), (3, 0), (1, 0), (3, 2), (2, 1), (0, 3)]
    for k, ((h, a), (hg, ag)) in enumerate(zip(pairs, scores)):
        ko = start + timedelta(days=7 * k)
        mid, _ = app.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=ids[h], away_team_id=ids[a],
                                       source_id="openfootball", status="finished", season_label="2017/18")
        app.repo.upsert_result(mid, "openfootball", {"home_goals_90": hg, "away_goals_90": ag},
                               available_at=ko + timedelta(hours=3))
        fixtures.append((ko, h, a, hg, ag, mid))
    return ids, fixtures


class LinkingTests(unittest.TestCase):
    def setUp(self):
        self.app, _, _ = make_app(datetime(2026, 10, 15, tzinfo=UTC))
        self.ids, self.fx = base_league(self.app)

    def test_links_by_shared_matches_not_by_names(self):
        # Källan använder egna ID:n och andra namn (t.ex. utan "FC")
        src_names = {0: "Arsenal", 1: "Chelsea", 2: "Liverpool", 3: "Everton"}
        fixtures = [{"date": ko.strftime("%Y-%m-%d"), "home_sid": 100 + h, "away_sid": 100 + a,
                     "home_name": src_names[h], "away_name": src_names[a], "hg": hg, "ag": ag}
                    for ko, h, a, hg, ag, _ in self.fx]
        r = link_source_teams(self.app, "wyscout_public", "ENG1", fixtures)
        self.assertEqual(r["linked"], {str(100 + i): self.ids[i] for i in range(4)})
        # Därefter löses lagen via käll-ID – inga nya lag och inga dubblettmatcher
        n_teams = self.app.db.scalar("SELECT COUNT(*) FROM teams")
        for ko, h, a, hg, ag, mid in self.fx:
            th = self.app.repo.resolve_team(src_names[h], "wyscout_public", "ENG1", source_team_id=str(100 + h))
            ta = self.app.repo.resolve_team(src_names[a], "wyscout_public", "ENG1", source_team_id=str(100 + a))
            m2, act = self.app.repo.upsert_match(competition_code="ENG1", kickoff_utc=ko, home_team_id=th,
                                                 away_team_id=ta, source_id="wyscout_public", status="finished",
                                                 source_match_id=f"w{mid}")
            self.assertEqual(m2, mid)
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM teams"), n_teams)
        self.assertTrue(self.app.db.scalar("SELECT COUNT(*) FROM change_log WHERE entity='team_link'") >= 4)

    def test_wrong_scores_do_not_link(self):
        fixtures = [{"date": ko.strftime("%Y-%m-%d"), "home_sid": 100 + h, "away_sid": 100 + a, "home_name": "x",
                     "away_name": "y", "hg": hg + 5, "ag": ag} for ko, h, a, hg, ag, _ in self.fx]
        r = link_source_teams(self.app, "wyscout_public", "ENG1", fixtures)
        self.assertEqual(r["linked"], {})
        self.assertEqual(len(r["unlinked"]), 4)


class WyscoutTests(unittest.TestCase):
    def test_tags_are_read_from_source_file(self):
        tags = required_tags(tag_ids(TAGS_CSV))
        self.assertEqual(tags["goal"], 101)
        self.assertEqual(tags["accurate"], 1801)
        with self.assertRaises(ValueError):
            required_tags(tag_ids("Tag,Label\n101,Goal\n"))

    def test_aggregate_counts_regular_time_only(self):
        tags = required_tags(tag_ids(TAGS_CSV))
        ev = [
            {"matchId": 1, "teamId": 10, "playerId": 7, "matchPeriod": "1H", "eventName": "Shot",
             "subEventName": "Shot", "tags": [{"id": 101}, {"id": 1801}]},
            {"matchId": 1, "teamId": 10, "playerId": 7, "matchPeriod": "2H", "eventName": "Shot",
             "subEventName": "Shot", "tags": [{"id": 1802}]},
            {"matchId": 1, "teamId": 20, "playerId": 8, "matchPeriod": "2H", "eventName": "Free Kick",
             "subEventName": "Corner", "tags": []},
            {"matchId": 1, "teamId": 20, "playerId": 8, "matchPeriod": "2H", "eventName": "Free Kick",
             "subEventName": "Penalty", "tags": [{"id": 101}, {"id": 1801}]},
            {"matchId": 1, "teamId": 20, "playerId": 9, "matchPeriod": "E1", "eventName": "Shot",
             "subEventName": "Shot", "tags": [{"id": 101}]},
            {"matchId": 2, "teamId": 20, "playerId": 9, "matchPeriod": "1H", "eventName": "Shot",
             "subEventName": "Shot", "tags": []},
        ]
        team, player, seen, kinds = aggregate_events(ev, tags, {1})
        self.assertEqual(team[(1, 10)]["shots"], 2)
        self.assertEqual(team[(1, 10)]["shots_on_target"], 1)
        self.assertEqual(team[(1, 20)]["corners"], 1)
        self.assertEqual(team[(1, 20)]["shots"], 1)  # straffen räknas; förlängningens skott inte
        self.assertEqual(player[(1, 10, 7)]["goals"], 1)
        self.assertEqual(seen, {1})

    def test_minutes_from_formation(self):
        m = minutes_from_formation({"lineup": [{"playerId": 1}, {"playerId": 2}],
                                    "substitutions": [{"playerIn": 3, "playerOut": 2, "minute": 60}]})
        self.assertEqual((m[1]["minutes"], m[2]["minutes"], m[3]["minutes"], m[3]["started"]), (90.0, 60.0, 30.0, 0))

    def test_full_import_from_figshare_format(self):
        app, _, _ = make_app(datetime(2026, 10, 15, tzinfo=UTC))
        ids, fx = base_league(app)
        comps = [{"wyId": 364, "name": "English first division", "area": {"name": "England"}, "type": "club"}]
        teams = [{"wyId": 1000 + i, "name": n, "officialName": n + " FC"}
                 for i, n in enumerate(["Arsenal", "Chelsea", "Liverpool", "Everton"])]
        players = [{"wyId": 5000 + i, "firstName": "Spelare", "lastName": str(i), "role": {"name": "Forward"}}
                   for i in range(4)]
        matches, events = [], []
        for k, (ko, h, a, hg, ag, mid) in enumerate(fx):
            wid = 900 + k
            matches.append({"wyId": wid, "competitionId": 364, "status": "Played", "gameweek": k + 1,
                            "dateutc": ko.strftime("%Y-%m-%d %H:%M:%S"),
                            "teamsData": {
                                str(1000 + h): {"teamId": 1000 + h, "side": "home", "score": hg, "scoreHT": 0,
                                                "hasFormation": 1, "formation": {
                                                    "lineup": [{"playerId": 5000 + h}], "substitutions": []}},
                                str(1000 + a): {"teamId": 1000 + a, "side": "away", "score": ag, "scoreHT": 0,
                                                "hasFormation": 1, "formation": {
                                                    "lineup": [{"playerId": 5000 + a}], "substitutions": []}}}})
            for _ in range(3):
                events.append({"matchId": wid, "teamId": 1000 + h, "playerId": 5000 + h, "matchPeriod": "1H",
                               "eventName": "Free Kick", "subEventName": "Corner", "tags": []})
            events.append({"matchId": wid, "teamId": 1000 + a, "playerId": 5000 + a, "matchPeriod": "2H",
                           "eventName": "Shot", "subEventName": "Shot", "tags": [{"id": 1801}]})

        def zbytes(name, obj):
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w") as z:
                z.writestr(name, json.dumps(obj))
            return b.getvalue()
        base = "https://ndownloader.figshare.com/files/"
        files = {"competitions.json": json.dumps(comps).encode(), "teams.json": json.dumps(teams).encode(),
                 "players.json": json.dumps(players).encode(), "tags2name.csv": TAGS_CSV.encode(),
                 "matches.zip": zbytes("matches_England.json", matches),
                 "events.zip": zbytes("events_England.json", events)}
        routes = {"https://api.figshare.com/v2/collections/4415000/articles": FakeResponse(200, [{"id": 1}]),
                  "https://api.figshare.com/v2/articles/1": FakeResponse(200, {"files": [
                      {"name": n, "download_url": base + n} for n in files]})}
        routes["https://api.figshare.com/v2/collections/4415000/articles?page_size=100"] = routes[
            "https://api.figshare.com/v2/collections/4415000/articles"]
        for n, b in files.items():
            routes[base + n] = FakeResponse(200, b)
        n_teams = app.db.scalar("SELECT COUNT(*) FROM teams")
        res = sync.run_source(app, "wyscout_public", "backfill", HttpClient(app, FakeSession(routes),
                                                                           sleep=lambda s: None))
        self.assertEqual(res["status"], "ok", res)
        # Alla åtta matcher landade på de befintliga (ingen dubblett), med hörnor för båda lagen
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM matches"), 8)
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM team_match_stats WHERE source_id='wyscout_public'"), 16)
        self.assertEqual(app.db.scalar("""SELECT SUM(corners) FROM team_match_stats
                                          WHERE source_id='wyscout_public' AND is_home=1"""), 24)
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM teams"), n_teams)
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM player_match_stats WHERE source_id='wyscout_public'"), 16)


class ApiFootballBackfillTests(unittest.TestCase):
    def setUp(self):
        self.app, _, _ = make_app(datetime(2026, 10, 15, tzinfo=UTC))
        secrets_store.set_secret("api_football", "test-nyckel")
        self.ids, self.fx = base_league(self.app, "ENG1", datetime(2024, 8, 17, 14, tzinfo=UTC))
        names = ["Arsenal", "Chelsea", "Liverpool", "Everton"]
        self.items = []
        for k, (ko, h, a, hg, ag, mid) in enumerate(self.fx):
            self.items.append({"fixture": {"id": 7000 + k, "date": ko.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                                           "status": {"short": "FT"}},
                               "league": {"round": f"Regular Season - {k + 1}"},
                               "teams": {"home": {"id": 40 + h, "name": names[h]}, "away": {"id": 40 + a, "name": names[a]}},
                               "goals": {"home": hg, "away": ag},
                               "score": {"fulltime": {"home": hg, "away": ag}, "halftime": {"home": 0, "away": 0}}})
        self.calls = []

        def fixtures(url, params, headers):
            self.calls.append(dict(params))
            if "ids" in params:
                out = []
                for fid in params["ids"].split("-"):
                    it = next(i for i in self.items if str(i["fixture"]["id"]) == fid)
                    h, a = it["teams"]["home"], it["teams"]["away"]
                    out.append({**it, "statistics": [
                        {"team": h, "statistics": [{"type": "Corner Kicks", "value": 6},
                                                   {"type": "Total Shots", "value": 14},
                                                   {"type": "Shots on Goal", "value": 5}]},
                        {"team": a, "statistics": [{"type": "Corner Kicks", "value": 3},
                                                   {"type": "Total Shots", "value": 9},
                                                   {"type": "Shots on Goal", "value": None}]}],
                        "players": [{"team": h, "players": [
                            {"player": {"id": 1, "name": "A. Spelare"},
                             "statistics": [{"games": {"minutes": 90, "substitute": False},
                                             "shots": {"total": 3, "on": 1}, "goals": {"total": 1}}]},
                            {"player": {"id": 2, "name": "B. Bänk"},
                             "statistics": [{"games": {"minutes": None, "substitute": True}}]}]}]})
                if getattr(self, "no_stats", False):
                    for o in out:
                        o["statistics"] = []
                return FakeResponse(200, {"errors": [], "response": out})
            if params.get("season") == 2023:
                return FakeResponse(200, {"errors": {"plan": "Free plans do not have access to this season, "
                                                             "try from 2022 to 2024."}, "response": []})
            if params.get("season") == 2024:
                return FakeResponse(200, {"errors": [], "response": self.items})
            return FakeResponse(200, {"errors": [], "response": []})
        self.session = FakeSession({"https://v3.football.api-sports.io/fixtures": fixtures})
        self.app.db.execute("UPDATE sources SET enabled=1 WHERE id='api_football'")

    def test_backfill_batches_details_and_records_plan_limits(self):
        http = HttpClient(self.app, self.session, sleep=lambda s: None)
        res = ApiFootballAdapter(self.app, http).run("backfill", competitions=["ENG1"], seasons=[2024, 2023])
        self.assertEqual(res.get("seasons_plan_restricted"), 1)
        # 8 matcher -> ett anrop för spelschemat + ett ids-anrop (högst 20 per anrop)
        self.assertEqual(len([c for c in self.calls if "ids" in c]), 1)
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM matches"), 8)  # kopplade, inga dubbletter
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM team_match_stats WHERE source_id='api_football'"), 16)
        # Saknat värde (Shots on Goal = null) lagras som NULL, inte 0
        self.assertEqual(self.app.db.scalar("""SELECT COUNT(*) FROM team_match_stats WHERE source_id='api_football'
                                               AND shots_on_target IS NULL"""), 8)
        # Spelare som inte spelade får ingen rad
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM player_match_stats WHERE source_id='api_football'"), 8)
        st = self.app.db.one("SELECT * FROM sync_state WHERE source_id='api_football' AND job='backfill' AND scope='ENG1:2023'")
        self.assertEqual(st["last_status"], "plan_restricted")
        self.assertIn("2022 to 2024", st["last_error"])
        # Andra körningen: begränsad säsong hoppas över och redan hämtade detaljer hämtas inte igen
        n = len(self.calls)
        ApiFootballAdapter(self.app, http).run("backfill", competitions=["ENG1"], seasons=[2024, 2023])
        self.assertEqual([c for c in self.calls[n:] if "ids" in c], [])

    def test_matchday_details_are_imported_automatically(self):
        http = HttpClient(self.app, self.session, sleep=lambda s: None)
        ApiFootballAdapter(self.app, http).run("backfill", competitions=["ENG1"], seasons=[2024])
        # Senaste matchen: spelschema och resultat finns (fixtures-jobbet), men ännu ingen statistik
        last = self.app.db.one("""SELECT m.id, m.kickoff_utc, s.source_match_id FROM matches m JOIN match_source_ids s
            ON s.match_id=m.id AND s.source_id='api_football' ORDER BY m.kickoff_utc DESC LIMIT 1""")
        for t in ("team_match_stats", "player_match_stats"):
            self.app.db.execute(f"DELETE FROM {t} WHERE match_id=? AND source_id='api_football'", (last["id"],))
        ko = datetime.fromisoformat(last["kickoff_utc"].replace("Z", "+00:00"))
        self.app.clock.set(ko + timedelta(hours=1))           # matchen pågår fortfarande
        n = len(self.calls)
        ApiFootballAdapter(self.app, http).run("details")
        self.assertEqual(self.calls[n:], [])
        self.app.clock.set(ko + timedelta(hours=3))           # efter slutsignal: ett anrop för den matchen
        res = ApiFootballAdapter(self.app, http).run("details")
        self.assertEqual([c.get("ids") for c in self.calls[n:]], [last["source_match_id"]])
        self.assertEqual(res.get("details_todo"), 1)
        self.assertEqual(self.app.db.scalar("""SELECT COUNT(*) FROM team_match_stats WHERE match_id=?
                                               AND source_id='api_football'""", (last["id"],)), 2)
        self.assertEqual(self.app.db.scalar("""SELECT COUNT(*) FROM player_match_stats WHERE match_id=?
                                               AND source_id='api_football'""", (last["id"],)), 1)
        n = len(self.calls)
        ApiFootballAdapter(self.app, http).run("details")    # inget saknas -> inga anrop
        self.assertEqual(self.calls[n:], [])

    def test_unpublished_statistics_are_retried_for_two_days(self):
        http = HttpClient(self.app, self.session, sleep=lambda s: None)
        ApiFootballAdapter(self.app, http).run("backfill", competitions=["ENG1"], seasons=[2024])
        last = self.app.db.one("""SELECT m.id, m.kickoff_utc, s.source_match_id FROM matches m JOIN match_source_ids s
            ON s.match_id=m.id AND s.source_id='api_football' ORDER BY m.kickoff_utc DESC LIMIT 1""")
        self.app.db.execute("DELETE FROM team_match_stats WHERE match_id=? AND source_id='api_football'", (last["id"],))
        ko = datetime.fromisoformat(last["kickoff_utc"].replace("Z", "+00:00"))
        self.no_stats = True
        self.app.clock.set(ko + timedelta(hours=3))
        ApiFootballAdapter(self.app, http).run("details")
        nostats = "SELECT COUNT(*) FROM sync_state WHERE source_id='api_football' AND job='_nostats' AND scope=?"
        self.assertEqual(self.app.db.scalar(nostats, (last["source_match_id"],)), 0)   # försök igen senare
        self.app.clock.set(ko + timedelta(hours=50))
        ApiFootballAdapter(self.app, http).run("details")
        self.assertEqual(self.app.db.scalar(nostats, (last["source_match_id"],)), 1)   # ge upp efter två dygn
        n = len(self.calls)
        ApiFootballAdapter(self.app, http).run("details")
        self.assertEqual(self.calls[n:], [])


class OperationalTests(unittest.TestCase):
    def test_status_follows_real_data_licence_and_age(self):
        app, _, _ = make_app(datetime(2026, 10, 15, tzinfo=UTC))
        ids = [app.repo.resolve_team(f"Lag {i}", "manual", context="SWE1") for i in range(10)]
        k = 0
        for d in range(0, 300, 2):  # 150 matcher de senaste 300 dagarna
            ko = datetime(2026, 10, 1, 15, tzinfo=UTC) - timedelta(days=d)
            h, a = ids[k % 10], ids[(k + 3) % 10]
            k += 1
            mid, _ = app.repo.upsert_match(competition_code="SWE1", kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                           source_id="manual", status="finished")
            app.repo.upsert_result(mid, "manual", {"home_goals_90": 1, "away_goals_90": 0})
            for tid, home in ((h, True), (a, False)):
                app.repo.upsert_team_stats(mid, tid, home, "api_football", {"corners": 5, "shots": 10})
        st = analytics.operational_status(app, ["SWE1"])["competitions"][0]["metrics"]
        self.assertEqual(st["goals"]["status"], "operativ")
        # API-Football är villkorad: data finns men är spärrad tills användaren godkänt villkoren
        self.assertEqual(st["corners"]["status"], "spärrad")
        self.assertEqual(st["sot"]["status"], "saknas")
        catalog.set_training_approval(app.db, "api_football", True, "Villkoren lästa och godkända för egen analys.",
                                      app.clock.now())
        st = analytics.operational_status(app, ["SWE1"])["competitions"][0]["metrics"]
        self.assertEqual(st["corners"]["status"], "operativ")
        app.set_setting("counts_max_age_days", 90)
        st = analytics.operational_status(app, ["SWE1"])["competitions"][0]["metrics"]
        self.assertEqual(st["corners"]["status"], "begränsad")

    def test_history_store_drops_old_count_data(self):
        app, _, _ = make_app(datetime(2026, 10, 15, tzinfo=UTC))
        ids, fx = base_league(app, "ENG1", datetime(2017, 8, 12, 14, tzinfo=UTC))
        for ko, h, a, hg, ag, mid in fx:
            app.repo.upsert_team_stats(mid, ids[h], True, "manual", {"corners": 6})
            app.repo.upsert_team_stats(mid, ids[a], False, "manual", {"corners": 4})
        cut = datetime(2026, 10, 1, tzinfo=UTC)
        self.assertEqual(len(HistoryStore.load(app.db, {"manual", "openfootball"}).view(cut).metric("corners")["h"]), 8)
        st = HistoryStore.load(app.db, {"manual", "openfootball"}, counts_max_age_days=450)
        self.assertEqual(len(st.view(cut).metric("corners")["h"]), 0)
        self.assertEqual(len(st.view(cut).metric("goals")["h"]), 8)  # målen påverkas inte


if __name__ == "__main__":
    unittest.main()


class ResumeTests(unittest.TestCase):
    def test_rate_limited_backfill_resumes_automatically(self):
        from test_sources import of_routes, EPL_JSON
        app, clock, _ = make_app(datetime(2026, 10, 15, 8, 0, tzinfo=UTC))
        routes = of_routes({("football.json", "2026-27/en.1.json"): FakeResponse(200, EPL_JSON)})
        limited = dict(routes)
        limited["https://api.github.com/repos/openfootball/football.json"] = FakeResponse(
            403, b"{}", headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1792065600"})
        r = sync.run_backfill(app, ["openfootball"], HttpClient(app, FakeSession(limited), sleep=lambda s: None))
        self.assertEqual(r[0]["status"], "blocked")
        pending = app.get_setting("backfill_pending")
        self.assertEqual(pending["sources"], ["openfootball"])
        # För tidigt: inget händer
        self.assertIsNone(sync.resume_pending_backfill(app, HttpClient(app, FakeSession(routes), sleep=lambda s: None)))
        clock.advance(minutes=16)
        res = sync.resume_pending_backfill(app, HttpClient(app, FakeSession(routes), sleep=lambda s: None))
        self.assertEqual(res[0]["status"], "ok")
        self.assertIsNone(app.get_setting("backfill_pending"))
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM matches"), 2)
