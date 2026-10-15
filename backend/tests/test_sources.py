"""Källadaptrar mot inspelade/dokumenterade svarsformat (inget nätverk krävs).

OBS: Svaren nedan är testfixturer konstruerade efter respektive källas dokumenterade format –
inte inspelningar av riktiga anrop. Adaptrarna loggar parserfel i stället för att gissa värden.
"""
import json
import unittest
from datetime import datetime

from helpers import FakeResponse, FakeSession, make_app

from matchiq import catalog, secrets_store
from matchiq.sources import sync
from matchiq.sources.api_football import ApiFootballAdapter
from matchiq.sources.football_data_couk import FootballDataCoUkAdapter, parse_csv
from matchiq.sources.football_data_org import FootballDataOrgAdapter
from matchiq.sources.http import HttpClient, SourceBlocked
from matchiq.sources.odds_api import OddsApiAdapter
from matchiq.sources.openfootball import OpenFootballAdapter, parse_football_json, parse_football_txt
from matchiq.sources.statsbomb import StatsBombAdapter, team_stats_from_events
from matchiq.timeutil import UTC

CL_TXT = """= UEFA Champions League 2026/27

» League, Matchday 3
  Tue Oct 20 2026
    18:45  Fenerbahçe (TUR)   v Slavia Praha (CZE)
    21:00  Liverpool FC (ENG) v Villarreal CF (ESP)
» League, Matchday 1
  Tue Sep 8 2026
    21:00  Arsenal FC (ENG)   v Inter (ITA)   2-1 (1-0)
    21:00  Real Madrid (ESP)  v Manchester City (ENG)  1-1 (0-0)
"""
EPL_JSON = {"name": "English Premier League 2026/27", "matches": [
    {"round": "Matchday 1", "date": "2026-08-15", "time": "15:00", "team1": "Arsenal FC", "team2": "Brentford FC",
     "score": {"ht": [1, 0], "ft": [3, 1]}},
    {"round": "Matchday 9", "date": "2026-10-24", "time": "17:30", "team1": "Liverpool FC", "team2": "Everton FC"},
]}


def gh(repo, path):
    return f"https://raw.githubusercontent.com/openfootball/{repo}/master/{path}"


def of_routes(files: dict, sha_suffix: str = "1") -> dict:
    """Bygger GitHub-svar (repo, filträd, filinnehåll) för OpenFootball-repona i testet."""
    routes = {}
    for repo in ("football.json", "champions-league", "europe"):
        routes[f"https://api.github.com/repos/openfootball/{repo}"] = FakeResponse(200, {"default_branch": "master"})
        tree = [{"path": p, "type": "blob", "sha": f"{abs(hash(p))}-{sha_suffix}"}
                for (r, p) in files if r == repo]
        routes[f"https://api.github.com/repos/openfootball/{repo}/git/trees/master"] = FakeResponse(
            200, {"tree": tree, "truncated": False})
    for (repo, path), body in files.items():
        routes[gh(repo, path)] = body
    return routes


SWE_TXT = """= Allsvenskan 2023

  Sat Apr 1
    15:00  Malmö FF  v  IFK Göteborg   2-0
  Sun Nov 12
    15:00  AIK  v  Hammarby IF   1-1
  Sat Jun 3
    15:00  IFK Göteborg  v  AIK   0-1
"""


class OpenFootballTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, _ = make_app(datetime(2026, 10, 15, 8, 0, tzinfo=UTC))
        self.files = {
            ("champions-league", "2026-27/cl.txt"): FakeResponse(200, CL_TXT.encode()),
            ("football.json", "2026-27/en.1.json"): FakeResponse(200, EPL_JSON),
            ("football.json", "2015-16/en.1.json"): FakeResponse(200, {"matches": [
                {"date": "2015-08-08", "team1": "Arsenal FC", "team2": "Brentford FC", "score": {"ft": [0, 2]}}]}),
        }
        self.session = FakeSession(of_routes(self.files))
        self.http = HttpClient(self.app, self.session, sleep=lambda s: None)

    def test_parsers(self):
        rows = parse_football_txt(CL_TXT, 2026)
        self.assertEqual(len(rows), 4)
        self.assertIsNone(rows[0]["ft"])
        self.assertEqual(rows[2]["ft"], [2, 1])
        self.assertEqual(rows[2]["team1"], "Arsenal FC")
        j = parse_football_json(EPL_JSON)
        self.assertEqual(j[0]["ft"], [3, 1])
        self.assertIsNone(j[1]["ft"])

    def test_calendar_league_never_rolls_year(self):
        rows = parse_football_txt(SWE_TXT, 2023, calendar=True)
        self.assertEqual([r["date"] for r in rows], ["2023-04-01", "2023-11-12", "2023-06-03"])
        # Utan kalenderflagga skulle juni efter november tolkas som nästa år (höst–vår-säsong)
        rows2 = parse_football_txt(SWE_TXT, 2023)
        self.assertEqual(rows2[2]["date"], "2024-06-03")

    def test_sync_twice_no_duplicates_and_logged(self):
        ad = OpenFootballAdapter(self.app, self.http)
        ad.run(competitions=["UCL", "ENG1"])
        n1 = {t: self.app.db.scalar(f"SELECT COUNT(*) FROM {t}") for t in ("matches", "match_results", "teams")}
        calls_first = len(self.session.calls)
        OpenFootballAdapter(self.app, self.http).run(competitions=["UCL", "ENG1"])
        n2 = {t: self.app.db.scalar(f"SELECT COUNT(*) FROM {t}") for t in ("matches", "match_results", "teams")}
        self.assertEqual(n1, n2)
        self.assertEqual(n1["matches"], 6)  # 2015/16 ingår inte i det dagliga jobbet
        # Andra körningen: bara repo + filträd (6 anrop) – oförändrade filer (samma blob-SHA) hämtas inte igen
        self.assertEqual(len(self.session.calls) - calls_first, 6)
        f = self.app.db.query("SELECT * FROM fetches WHERE source_id='openfootball' AND url LIKE '%raw.githubusercontent%'")
        self.assertTrue(all(r["sha256"] and r["http_status"] == 200 for r in f))
        self.assertTrue(all(r["parser_status"] in ("ok", "partial") for r in f))
        # Liverpool i CL (TXT) och i PL (JSON) blir samma lag via exakta alias
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM teams WHERE name='Liverpool'"), 1)
        # Fenerbahçe–Slavia är planerad, utan resultat
        st = self.app.db.scalar("""SELECT m.status FROM matches m JOIN teams h ON h.id=m.home_team_id
                                   WHERE h.name='Fenerbahçe'""")
        self.assertEqual(st, "scheduled")
        # GitHubs API för filträdet, GitHubs värd för rå filer för innehållet (ingen skrapning av webbsidor)
        self.assertTrue(all(c[0].startswith(("https://api.github.com/", "https://raw.githubusercontent.com/"))
                            for c in self.session.calls))
        self.assertTrue(any("/git/trees/" in c[0] for c in self.session.calls))

    def test_backfill_takes_all_seasons_and_changed_files_only(self):
        OpenFootballAdapter(self.app, self.http).run("backfill", competitions=["ENG1"])
        self.assertEqual(self.app.db.scalar("""SELECT COUNT(*) FROM matches m JOIN seasons s ON s.id=m.season_id
                                               WHERE s.label='2015/16'"""), 1)
        # Källan ändrar en fil (ny blob-SHA) -> bara den filen hämtas igen
        session2 = FakeSession(of_routes(self.files, sha_suffix="2"))
        OpenFootballAdapter(self.app, HttpClient(self.app, session2, sleep=lambda s: None)).run(
            "backfill", competitions=["ENG1"])
        self.assertEqual(len([c for c in session2.calls if "raw.githubusercontent" in c[0]]), 2)

    def test_missing_file_logged_not_hidden(self):
        files = {("europe", "sweden/2026_se1.txt"): FakeResponse(404)}
        http = HttpClient(self.app, FakeSession(of_routes(files)), sleep=lambda s: None)
        OpenFootballAdapter(self.app, http).run(competitions=["SWE1"])
        f = self.app.db.one("SELECT * FROM fetches WHERE source_id='openfootball' AND url LIKE '%raw.githubusercontent%'")
        self.assertEqual(f["http_status"], 404)
        self.assertEqual(f["parser_status"], "error")

    def test_github_rate_limit_stops_with_clear_message(self):
        routes = of_routes(self.files)
        routes["https://api.github.com/repos/openfootball/football.json"] = FakeResponse(
            403, b"{}", headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1792065600"})
        res = sync.run_source(self.app, "openfootball", "backfill",
                              HttpClient(self.app, FakeSession(routes), sleep=lambda s: None))
        self.assertEqual(res["status"], "blocked")
        self.assertIn("anropsgräns", res["error"])


class HttpPolicyTests(unittest.TestCase):
    def setUp(self):
        self.app, _, _ = make_app()

    def test_retry_with_backoff_then_success(self):
        url = "https://api.github.com/repos/openfootball/x/contents/y"
        session = FakeSession({url: [FakeResponse(503), FakeResponse(429, headers={"Retry-After": "1"}),
                                     FakeResponse(200, b"ok")]})
        sleeps = []
        res = HttpClient(self.app, session, sleep=sleeps.append).get("openfootball", url, job="t")
        self.assertEqual(res.status, 200)
        self.assertEqual(len(session.calls), 3)
        self.assertIn(2.0, sleeps)
        self.assertIn(1.0, sleeps)
        self.assertEqual(self.app.db.scalar("SELECT attempt FROM fetches WHERE id=?", (res.fetch_id,)), 3)

    def test_disabled_source_blocked(self):
        with self.assertRaises(SourceBlocked):
            HttpClient(self.app, FakeSession({}), sleep=lambda s: None).get("uefa", "https://match.uefa.com/x", job="t")

    def test_daily_quota(self):
        url = "https://api.github.com/q"
        self.app.db.execute("UPDATE sources SET daily_quota=2 WHERE id='openfootball'")
        http = HttpClient(self.app, FakeSession({url: FakeResponse(200, b"x")}), sleep=lambda s: None)
        http.get("openfootball", url, job="t", conditional=False)
        http.get("openfootball", url, job="t", conditional=False)
        with self.assertRaises(SourceBlocked):
            http.get("openfootball", url, job="t", conditional=False)

    def test_robots_respected(self):
        catalog.set_source_enabled(self.app.db, "football_data_couk", True, datetime(2026, 1, 1, tzinfo=UTC))
        session = FakeSession({"https://www.football-data.co.uk/robots.txt":
                               FakeResponse(200, b"User-agent: *\nDisallow: /mmz4281/\n")})
        HttpClient._robots.clear()
        with self.assertRaises(SourceBlocked):
            HttpClient(self.app, session, sleep=lambda s: None).get(
                "football_data_couk", "https://www.football-data.co.uk/mmz4281/2627/E0.csv", job="t",
                respect_robots=True)
        HttpClient._robots.clear()

    def test_api_key_redacted_in_log(self):
        secrets_store.set_secret("the_odds_api", "HEMLIG-NYCKEL")
        catalog.set_source_enabled(self.app.db, "the_odds_api", True, datetime(2026, 1, 1, tzinfo=UTC))
        sess = FakeSession({"https://api.the-odds-api.com/v4/sports/soccer_epl/odds": FakeResponse(200, [])})
        OddsApiAdapter(self.app, HttpClient(self.app, sess, sleep=lambda s: None)).run(competitions=["ENG1"])
        urls = [r["url"] for r in self.app.db.query("SELECT url FROM fetches")]
        self.assertTrue(urls and all("HEMLIG" not in u for u in urls))
        secrets_store.delete_secret("the_odds_api")


class ApiAdaptersTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, _ = make_app(datetime(2026, 10, 18, 8, 0, tzinfo=UTC))
        for s in ("api_football", "football_data_org"):
            catalog.set_source_enabled(self.app.db, s, True, self.clock.now())
        secrets_store.set_secret("api_football", "k1")
        secrets_store.set_secret("football_data_org", "k2")

    def tearDown(self):
        secrets_store.delete_secret("api_football")
        secrets_store.delete_secret("football_data_org")

    def test_missing_key_blocks(self):
        secrets_store.delete_secret("api_football")
        res = sync.run_source(self.app, "api_football", "fixtures", HttpClient(self.app, FakeSession({}), sleep=lambda s: None))
        self.assertEqual(res["status"], "blocked")
        self.assertIn("nyckel", res["error"])

    def test_api_football_fixture_lineup_stats(self):
        fixtures = {"response": [
            {"fixture": {"id": 9001, "date": "2026-10-20T16:45:00+00:00", "status": {"short": "NS"},
                         "venue": {"name": "Şükrü Saracoğlu"}},
             "league": {"round": "League Stage - 3"},
             "teams": {"home": {"id": 611, "name": "Fenerbahce"}, "away": {"id": 560, "name": "Slavia Praha"}},
             "goals": {"home": None, "away": None}, "score": {}},
            {"fixture": {"id": 9000, "date": "2026-09-08T19:00:00+00:00", "status": {"short": "FT"}},
             "league": {"round": "League Stage - 1"},
             "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 505, "name": "Inter"}},
             "goals": {"home": 2, "away": 1},
             "score": {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 2, "away": 1},
                       "extratime": {"home": None, "away": None}, "penalty": {"home": None, "away": None}}}]}
        xi = [{"player": {"id": i, "name": f"Spelare {i}", "number": i, "pos": "M"}} for i in range(1, 12)]
        lineups = {"response": [{"team": {"id": 611, "name": "Fenerbahce"}, "formation": "4-2-3-1", "startXI": xi},
                                {"team": {"id": 560, "name": "Slavia Praha"}, "formation": "3-4-3",
                                 "startXI": xi[:9]}]}
        stats = {"response": [
            {"team": {"id": 42, "name": "Arsenal"}, "statistics": [{"type": "Total Shots", "value": 16},
                                                                   {"type": "Shots on Goal", "value": 7},
                                                                   {"type": "Corner Kicks", "value": None},
                                                                   {"type": "expected_goals", "value": "1.84"}]},
            {"team": {"id": 505, "name": "Inter"}, "statistics": [{"type": "Total Shots", "value": 9},
                                                                  {"type": "Shots on Goal", "value": 3},
                                                                  {"type": "Corner Kicks", "value": 4}]}]}
        base = "https://v3.football.api-sports.io"
        sess = FakeSession({f"{base}/fixtures": FakeResponse(200, fixtures),
                            f"{base}/fixtures/lineups": FakeResponse(200, lineups),
                            f"{base}/fixtures/statistics": FakeResponse(200, stats)})
        http = HttpClient(self.app, sess, sleep=lambda s: None)
        ApiFootballAdapter(self.app, http).run("fixtures", competitions=["UCL"])
        ApiFootballAdapter(self.app, http).run("fixtures", competitions=["UCL"])
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM matches"), 2)
        fen = self.app.db.one("""SELECT m.id FROM matches m JOIN teams h ON h.id=m.home_team_id
                                 WHERE h.name='Fenerbahçe'""")
        self.assertIsNotNone(fen, "'Fenerbahce' ska matcha det kanoniska laget Fenerbahçe via exakt alias")
        ApiFootballAdapter(self.app, http).run("lineups", match_id=fen["id"])
        lus = self.app.db.query("SELECT * FROM lineups WHERE match_id=?", (fen["id"],))
        self.assertEqual(len(lus), 1, "ofullständig elva (9 spelare) får inte sparas som bekräftad")
        ars = self.app.db.one("""SELECT m.id, m.home_team_id FROM matches m JOIN teams h ON h.id=m.home_team_id
                                 WHERE h.name='Arsenal'""")
        ApiFootballAdapter(self.app, http).run("statistics", match_id=ars["id"])
        st = self.app.db.one("SELECT * FROM team_match_stats WHERE match_id=? AND team_id=?",
                             (ars["id"], ars["home_team_id"]))
        self.assertEqual((st["shots"], st["shots_on_target"]), (16, 7))
        self.assertIsNone(st["corners"])
        self.assertAlmostEqual(st["xg"], 1.84)
        res = self.app.db.one("SELECT * FROM match_results WHERE match_id=?", (ars["id"],))
        self.assertEqual((res["home_goals_90"], res["away_goals_90"], res["decided_by"]), (2, 1, "regular"))

    def test_football_data_org_extra_time(self):
        payload = {"matches": [{"id": 77, "utcDate": "2026-04-15T19:00:00Z", "status": "FINISHED", "stage": "QUARTER_FINALS",
                                "season": {"startDate": "2025-08-01"},
                                "homeTeam": {"id": 1, "name": "Real Madrid CF"}, "awayTeam": {"id": 2, "name": "Arsenal FC"},
                                "score": {"duration": "PENALTY_SHOOTOUT", "fullTime": {"home": 5, "away": 4},
                                          "regularTime": {"home": 1, "away": 1}, "extraTime": {"home": 0, "away": 0},
                                          "penalties": {"home": 4, "away": 3}, "halfTime": {"home": 0, "away": 1}}}]}
        sess = FakeSession({"https://api.football-data.org/v4/competitions/CL/matches": FakeResponse(200, payload)})
        FootballDataOrgAdapter(self.app, HttpClient(self.app, sess, sleep=lambda s: None)).run(competitions=["UCL"])
        r = self.app.db.one("SELECT * FROM match_results")
        self.assertEqual((r["home_goals_90"], r["away_goals_90"], r["home_goals_aet"], r["home_pens"], r["decided_by"]),
                         (1, 1, 1, 4, "penalties"))


class StatsBombTests(unittest.TestCase):
    def test_team_stats_from_events_regular_time_only(self):
        ev = [
            {"period": 1, "team": {"id": 1, "name": "A"}, "type": {"name": "Shot"},
             "shot": {"statsbomb_xg": 0.3, "outcome": {"name": "Goal"}}},
            {"period": 2, "team": {"id": 1, "name": "A"}, "type": {"name": "Shot"},
             "shot": {"statsbomb_xg": 0.1, "outcome": {"name": "Off T"}}},
            {"period": 3, "team": {"id": 1, "name": "A"}, "type": {"name": "Shot"},
             "shot": {"statsbomb_xg": 0.5, "outcome": {"name": "Saved"}}},
            {"period": 2, "team": {"id": 2, "name": "B"}, "type": {"name": "Pass"}, "pass": {"type": {"name": "Corner"}}},
            {"period": 2, "team": {"id": 2, "name": "B"}, "type": {"name": "Foul Committed"},
             "foul_committed": {"card": {"name": "Yellow Card"}}},
        ]
        st = team_stats_from_events(ev)
        self.assertEqual((st[1]["shots"], st[1]["shots_on_target"]), (2, 1))
        self.assertAlmostEqual(st[1]["xg"], 0.4)
        self.assertEqual((st[2]["corners"], st[2]["yellow_cards"], st[2]["fouls"]), (1, 1, 1))

    def test_statsbomb_adapter_imports_match(self):
        app, _, _ = make_app()
        base = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/"
        comps = [{"competition_id": 16, "season_id": 4, "competition_name": "Champions League",
                  "season_name": "2018/2019"}]
        matches = [{"match_id": 22912, "match_date": "2019-06-01", "kick_off": "21:00:00.000",
                    "home_team": {"home_team_id": 38, "home_team_name": "Tottenham Hotspur"},
                    "away_team": {"away_team_id": 24, "away_team_name": "Liverpool"}, "home_score": 0, "away_score": 2,
                    "competition_stage": {"name": "Final"}}]
        events = [{"type": {"name": "Starting XI"}, "team": {"id": 24}, "period": 1,
                   "tactics": {"lineup": [{"player": {"id": 100 + i, "name": f"L{i}"}} for i in range(11)]}},
                  {"type": {"name": "Shot"}, "team": {"id": 24, "name": "Liverpool"}, "period": 1, "minute": 1,
                   "player": {"id": 100, "name": "L0"}, "shot": {"statsbomb_xg": 0.76, "outcome": {"name": "Goal"}}},
                  {"type": {"name": "Shot"}, "team": {"id": 24, "name": "Liverpool"}, "period": 2, "minute": 87,
                   "player": {"id": 101, "name": "L1"}, "shot": {"statsbomb_xg": 0.2, "outcome": {"name": "Goal"}}}]
        sess = FakeSession({"https://api.github.com/repos/statsbomb/open-data": FakeResponse(200, {"default_branch": "master"}),
                            base + "competitions.json": FakeResponse(200, comps),
                            base + "matches/16/4.json": FakeResponse(200, matches),
                            base + "events/22912.json": FakeResponse(200, events)})
        StatsBombAdapter(app, HttpClient(app, sess, sleep=lambda s: None)).run(competitions=["UCL"])
        StatsBombAdapter(app, HttpClient(app, sess, sleep=lambda s: None)).run(competitions=["UCL"])
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM matches"), 1)
        r = app.db.one("SELECT * FROM match_results")
        self.assertEqual((r["home_goals_90"], r["away_goals_90"]), (0, 2))
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM player_match_stats WHERE minutes_estimated=1"), 11)


class FootballDataCsvTests(unittest.TestCase):
    CSV = ("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST,HC,AC,B365H,B365D,B365A\n"
           "E0,16/08/2025,20:00,Liverpool,Bournemouth,4,2,19,10,10,3,6,7,1.3,6,9.5\n"
           "E0,17/08/2025,14:00,Aston Villa,Newcastle,0,0,3,16,1,3,,6,2.4,3.4,2.9\n")

    def test_parse_and_null_corners(self):
        rows = parse_csv(self.CSV)
        self.assertEqual(rows[1]["hc"], None)
        self.assertEqual(rows[0]["hst"], 10)

    def test_never_training_data(self):
        app, clock, _ = make_app()
        catalog.set_source_enabled(app.db, "football_data_couk", True, clock.now())
        HttpClient._robots.clear()
        sess = FakeSession({"https://www.football-data.co.uk/robots.txt": FakeResponse(404),
                            "https://www.football-data.co.uk/mmz4281/2526/E0.csv": FakeResponse(200, self.CSV.encode())})
        FootballDataCoUkAdapter(app, HttpClient(app, sess, sleep=lambda s: None)).run(competitions=["ENG1"],
                                                                                     season="2526")
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM team_match_stats WHERE corners IS NULL"), 1)
        self.assertEqual(app.db.scalar("SELECT COUNT(*) FROM market_odds"), 2)
        from matchiq.models.data import HistoryStore
        st = HistoryStore.load(app.db, None, competitions=["ENG1"])
        self.assertTrue(all(len(v) == 0 or all(x != x for x in v) for v in [st.a.vals_h["goals"]]))
        HttpClient._robots.clear()


if __name__ == "__main__":
    unittest.main()
