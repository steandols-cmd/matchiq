"""HTTP-API: säkerhet, matcher, eftermatch, modellstatus, nycklar och databasexport."""
import socket
import threading
import time
import unittest
from datetime import datetime, timedelta

import requests
import uvicorn
from helpers import make_app, seed_history

from matchiq.api.app import create_app
from matchiq.timeutil import UTC

TOKEN = "t" * 40


class ApiServer:
    def __init__(self, app, allow_simulation=False):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(create_app(app, TOKEN, allow_simulation=allow_simulation),
                                                    log_level="error", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        while not self.server.started:
            time.sleep(0.02)
        self.base = f"http://127.0.0.1:{self.port}/api"
        self.s = requests.Session()
        self.s.trust_env = False
        self.s.headers["Authorization"] = f"Bearer {TOKEN}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(5)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.clock, _ = make_app(datetime(2026, 10, 18, 12, 0, tzinfo=UTC))
        cls.teams = seed_history(cls.app, seasons=(2024, 2025), n_teams=10)
        cls.ko = datetime(2026, 10, 20, 19, 0, tzinfo=UTC)
        cls.mid, _ = cls.app.repo.upsert_match(competition_code="UCL", kickoff_utc=cls.ko, home_team_id=cls.teams[0],
                                               away_team_id=cls.teams[1], source_id="manual", status="scheduled")
        cls.srv = ApiServer(cls.app, allow_simulation=True)

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def test_auth_required_and_host_checked(self):
        r = requests.get(self.srv.base + "/meta", proxies={"http": None, "https": None})
        self.assertEqual(r.status_code, 401)
        r = self.srv.s.get(self.srv.base + "/meta", headers={"Host": "evil.example"})
        self.assertEqual(r.status_code, 421)
        r = self.srv.s.get(self.srv.base + "/meta", headers={"Authorization": "Bearer fel"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.srv.s.get(self.srv.base + "/health").json(), {"ok": True})

    def test_cors_only_for_app_origin(self):
        r = self.srv.s.options(self.srv.base + "/matches", headers={"Origin": "app://matchiq"})
        self.assertEqual(r.headers.get("access-control-allow-origin"), "app://matchiq")
        r = self.srv.s.options(self.srv.base + "/matches", headers={"Origin": "https://evil.example"})
        self.assertIsNone(r.headers.get("access-control-allow-origin"))

    def test_match_list_and_detail(self):
        rows = self.srv.s.get(self.srv.base + "/matches", params={"competition": "UCL", "from": "2026-10-01"}).json()
        self.assertEqual(rows[0]["id"], self.mid)
        d = self.srv.s.get(f"{self.srv.base}/matches/{self.mid}").json()
        pv = d["preview"]
        self.assertIsNone(d["frozen"])
        for fam in ("V2", "V3"):
            p = pv["models"][fam]["probs"]
            self.assertAlmostEqual(p["p_home"] + p["p_draw"] + p["p_away"], 1.0, places=9)
            self.assertIn(pv["models"][fam]["status"], ("baslinje", "experimentell", "kandidat"))
        self.assertEqual(pv["lineups"]["home"]["status"], "unpublished")

    def test_sources_show_terms_and_training_status(self):
        src = {s["id"]: s for s in self.srv.s.get(self.srv.base + "/sources").json()}
        self.assertFalse(src["football_data_couk"]["training_allowed"])
        self.assertIn("Spärrad", src["football_data_couk"]["training_status"])
        self.assertTrue(src["openfootball"]["training_allowed"])
        self.assertIn("license", src["uefa"])
        r = self.srv.s.post(self.srv.base + "/sources/football_data_couk/training", json={"approve": True, "note": "x"})
        self.assertEqual(r.status_code, 400)

    def test_coverage_endpoint(self):
        cov = self.srv.s.get(self.srv.base + "/coverage", params={"competition": "UCL"}).json()
        self.assertTrue(cov["seasons"])
        self.assertIn("pct_training", cov["seasons"][0]["metrics"]["corners"])

    def test_secrets_never_returned(self):
        r = self.srv.s.put(self.srv.base + "/secrets/api_football", json={"value": "SUPERHEMLIG"})
        self.assertEqual(r.status_code, 200)
        body = self.srv.s.get(self.srv.base + "/secrets").text
        self.assertNotIn("SUPERHEMLIG", body)
        self.assertIn('"configured":true', body)
        self.srv.s.delete(self.srv.base + "/secrets/api_football")

    def test_model_production_requires_gates(self):
        r = self.srv.s.post(self.srv.base + "/models/V3-3.0/status", json={"status": "produktion"})
        self.assertEqual(r.status_code, 409)

    def test_outcome_flow_and_evaluation_links_frozen_snapshot(self):
        app = self.app
        mid, _ = app.repo.upsert_match(competition_code="UCL", kickoff_utc=self.clock.now() + timedelta(hours=2),
                                       home_team_id=self.teams[2], away_team_id=self.teams[3], source_id="manual",
                                       status="scheduled")
        r = self.srv.s.post(f"{self.srv.base}/matches/{mid}/freeze", json={"pdf": False})
        self.assertEqual(r.status_code, 200, r.text)
        snap_before = app.db.query("SELECT * FROM forecast_snapshots WHERE match_id=?", (mid,))
        r = self.srv.s.post(f"{self.srv.base}/matches/{mid}/outcome", json={"home_goals": 2, "away_goals": 1})
        self.assertEqual(r.status_code, 409, "facit kan inte anges före avspark")
        self.clock.advance(hours=5)
        r = self.srv.s.post(f"{self.srv.base}/matches/{mid}/outcome",
                            json={"home_goals": 2, "away_goals": 1, "home_corners": 6, "away_corners": "",
                                  "home_shots": 15, "away_shots": 8, "home_sot": 6, "away_sot": 2})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["outcome"]["away_corners"], "tomt fält ska bli NULL, inte 0")
        snap_after = app.db.query("SELECT * FROM forecast_snapshots WHERE match_id=?", (mid,))
        self.assertEqual([dict(x) for x in snap_before], [dict(x) for x in snap_after])
        ev = self.srv.s.get(self.srv.base + "/evaluation").json()
        rows = [row for row in ev["prospective"]["V2-2.0"]["rows"] if row["match_id"] == mid]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "1")
        self.assertTrue(app.db.scalar("SELECT COUNT(*) FROM change_log WHERE entity='match_outcome'") >= 1)
        self.clock.set(datetime(2026, 10, 18, 12, 0, tzinfo=UTC))

    def test_db_export(self):
        r = self.srv.s.post(self.srv.base + "/db/export").json()
        self.assertTrue(r["path"].endswith(".zip"))
        info = self.srv.s.get(self.srv.base + "/db").json()
        self.assertEqual(info["schema_version"], 1)

    def test_simulated_tick_creates_t30_report(self):
        r = self.srv.s.post(self.srv.base + "/scheduler/simulate",
                            json={"now_utc": (self.ko - timedelta(minutes=45)).isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.srv.s.post(self.srv.base + "/scheduler/simulate",
                            json={"now_utc": (self.ko - timedelta(minutes=30)).isoformat()})
        reps = self.srv.s.get(self.srv.base + "/reports").json()
        mine = [x for x in reps if x["match_id"] == self.mid]
        self.assertEqual(mine[0]["kind"], "T-30")
        pdf = self.srv.s.get(f"{self.srv.base}/reports/{mine[0]['id']}/file")
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.clock.set(datetime(2026, 10, 18, 12, 0, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
