"""T−30-schemaläggning med simulerad klocka, sen rapport, PDF-innehåll och startelvor."""
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pdfplumber
from helpers import make_app, seed_history

from matchiq import scheduler
from matchiq.forecast import load_snapshot
from matchiq.timeutil import UTC, fmt_local, to_iso


def pdf_text(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, _ = make_app(datetime(2026, 10, 18, 12, 0, tzinfo=UTC))
        self.teams = seed_history(self.app)
        self.ko = datetime(2026, 10, 20, 19, 0, tzinfo=UTC)
        self.mid, _ = self.app.repo.upsert_match(competition_code="UCL", kickoff_utc=self.ko,
                                                 home_team_id=self.teams[0], away_team_id=self.teams[1],
                                                 source_id="manual", status="scheduled", season_label="2026/27")

    def test_t30_job_runs_exactly_with_simulated_clock(self):
        scheduler.tick(self.app)
        job = self.app.db.one("SELECT * FROM report_jobs WHERE match_id=?", (self.mid,))
        self.assertEqual(job["due_at_utc"], to_iso(self.ko - timedelta(minutes=30)))
        self.clock.set(self.ko - timedelta(minutes=31))
        scheduler.tick(self.app)
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM reports WHERE match_id=?", (self.mid,)), 0)
        self.clock.set(self.ko - timedelta(minutes=29, seconds=50))
        scheduler.tick(self.app)
        rep = self.app.db.one("SELECT * FROM reports WHERE match_id=?", (self.mid,))
        self.assertIsNotNone(rep)
        self.assertEqual(rep["kind"], "T-30")
        self.assertEqual(rep["data_cutoff_utc"], to_iso(self.ko - timedelta(minutes=30)))
        self.assertEqual(self.app.db.scalar("SELECT status FROM report_jobs WHERE match_id=?", (self.mid,)), "done")
        snaps = self.app.db.query("SELECT * FROM forecast_snapshots WHERE match_id=?", (self.mid,))
        self.assertEqual({s["model_family"] for s in snaps}, {"V2", "V3", "BASE"})
        for s in snaps:
            self.assertEqual(s["kind"], "T-30")
            self.assertEqual(s["prematch_eligible"], 1)
            self.assertEqual(s["clock"], "simulated")
        # en senare tick skapar ingen ny rapport och den frysta prognosen ändras inte
        before = [dict(s) for s in snaps]
        self.clock.advance(minutes=10)
        scheduler.tick(self.app)
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM reports WHERE match_id=?", (self.mid,)), 1)
        after = [dict(s) for s in self.app.db.query("SELECT * FROM forecast_snapshots WHERE match_id=?", (self.mid,))]
        self.assertEqual(before, after)
        self.assertTrue(self.app.db.scalar("SELECT COUNT(*) FROM notifications WHERE match_id=?", (self.mid,)) >= 1)

    def test_pdf_contains_snapshot_probabilities_and_times(self):
        scheduler.tick(self.app)
        self.clock.set(self.ko - timedelta(minutes=30))
        scheduler.tick(self.app)
        rep = self.app.db.one("SELECT * FROM reports WHERE match_id=?", (self.mid,))
        text = pdf_text(rep["path"])
        import json
        ids = json.loads(rep["snapshot_ids_json"])
        for fam, sid in ids.items():
            sn = load_snapshot(self.app, sid)
            self.assertIn(sid, text.replace("\n", ""), f"snapshot-ID för {fam} saknas i PDF")
            total = sn["p_home"] + sn["p_draw"] + sn["p_away"]
            self.assertAlmostEqual(total, 1.0, places=12)
            for p in (sn["p_home"], sn["p_draw"], sn["p_away"]):
                self.assertIn(f"{p * 100:.1f} %".replace(".", ","), text)
        self.assertIn("100,0 %", text)
        self.assertIn(fmt_local(self.ko - timedelta(minutes=30)), text)       # datagräns, lokal tid
        self.assertIn((self.ko - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M UTC"), text)
        self.assertIn("T−30-RAPPORT", text)
        self.assertIn("Opublicerad", text)                                    # ingen elva -> öppet redovisat
        self.assertIn("inte ett löfte om utfall", text)
        self.assertTrue(Path(rep["path"]).name.endswith("_T-30.pdf"))
        self.assertIn("/2026-10-20/UCL/", rep["path"].replace("\\", "/"))

    def test_missed_deadline_creates_clearly_marked_late_report(self):
        scheduler.tick(self.app)                                   # jobbet skapas medan matchen är känd
        self.clock.set(self.ko - timedelta(minutes=5))             # appen var nere vid T−30
        scheduler.tick(self.app)
        job = self.app.db.one("SELECT * FROM report_jobs WHERE match_id=?", (self.mid,))
        self.assertEqual(job["status"], "late_done")
        self.assertGreaterEqual(job["late_by_seconds"], 25 * 60)
        rep = self.app.db.one("SELECT * FROM reports WHERE match_id=?", (self.mid,))
        self.assertEqual(rep["kind"], "late")
        self.assertEqual(rep["is_late"], 1)
        self.assertEqual(rep["created_at_utc"], to_iso(self.ko - timedelta(minutes=5)))
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM forecast_snapshots WHERE match_id=? AND kind='T-30'",
                                            (self.mid,)), 0, "en sen rapport får aldrig låtsas vara T−30")
        text = pdf_text(rep["path"])
        self.assertIn("SEN RAPPORT", text)
        self.assertIn("missades", text)
        self.assertTrue(rep["path"].endswith("_SEN.pdf"))

    def test_late_after_kickoff_never_uses_post_kickoff_data(self):
        scheduler.tick(self.app)
        self.clock.set(self.ko + timedelta(hours=5))
        scheduler.tick(self.app)
        rep = self.app.db.one("SELECT * FROM reports WHERE match_id=?", (self.mid,))
        self.assertEqual(rep["data_cutoff_utc"], to_iso(self.ko))
        s = self.app.db.one("SELECT * FROM forecast_snapshots WHERE match_id=? LIMIT 1", (self.mid,))
        self.assertEqual(s["prematch_eligible"], 0)

    def test_kickoff_change_reschedules_pending_job(self):
        scheduler.tick(self.app)
        new_ko = self.ko + timedelta(hours=2)
        self.app.repo.upsert_match(competition_code="UCL", kickoff_utc=new_ko, home_team_id=self.teams[0],
                                   away_team_id=self.teams[1], source_id="manual", status="scheduled")
        scheduler.tick(self.app)
        jobs = self.app.db.query("SELECT * FROM report_jobs WHERE match_id=? ORDER BY id", (self.mid,))
        self.assertEqual([j["status"] for j in jobs], ["superseded", "pending"])
        self.assertEqual(jobs[1]["due_at_utc"], to_iso(new_ko - timedelta(minutes=30)))

    def test_match_registered_after_deadline_gets_no_automatic_job(self):
        self.clock.set(self.ko + timedelta(minutes=1))
        mid, _ = self.app.repo.upsert_match(competition_code="UCL", kickoff_utc=self.ko, home_team_id=self.teams[2],
                                            away_team_id=self.teams[3], source_id="manual", status="scheduled")
        scheduler.tick(self.app)
        self.assertIsNone(self.app.db.one("SELECT 1 FROM report_jobs WHERE match_id=?", (mid,)))


class LineupTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, _ = make_app(datetime(2026, 10, 20, 17, 0, tzinfo=UTC))
        self.teams = seed_history(self.app, seasons=(2024, 2025), n_teams=8)
        self.ko = datetime(2026, 10, 20, 19, 0, tzinfo=UTC)
        self.mid, _ = self.app.repo.upsert_match(competition_code="UCL", kickoff_utc=self.ko,
                                                 home_team_id=self.teams[0], away_team_id=self.teams[1],
                                                 source_id="manual", status="scheduled")

    def _xi(self, prefix):
        return [{"name": f"{prefix} {i}", "number": i, "position": None, "is_starter": True} for i in range(1, 12)]

    def test_lineup_states_and_no_fabrication(self):
        from matchiq.forecast import lineup_state
        cutoff = self.ko - timedelta(minutes=30)
        # hemmalaget: bekräftad elva före datagränsen; bortalaget: förväntad före + bekräftad EFTER datagränsen
        self.app.repo.upsert_lineup(self.mid, self.teams[0], "manual", "confirmed", self._xi("H"),
                                    fetched_at=cutoff - timedelta(minutes=10))
        self.app.repo.upsert_lineup(self.mid, self.teams[1], "manual", "expected", self._xi("B"),
                                    fetched_at=cutoff - timedelta(hours=20))
        self.app.repo.upsert_lineup(self.mid, self.teams[1], "manual", "confirmed", self._xi("BB"),
                                    fetched_at=cutoff + timedelta(minutes=5))
        h = lineup_state(self.app, self.mid, self.teams[0], cutoff)
        a = lineup_state(self.app, self.mid, self.teams[1], cutoff)
        self.assertEqual(h["status"], "confirmed")
        self.assertEqual(len(h["players"]), 11)
        self.assertEqual(a["status"], "expected", "elva publicerad efter datagränsen får inte användas")
        self.assertTrue(all(p["name"].startswith("B ") for p in a["players"]))
        # en match helt utan elva
        mid2, _ = self.app.repo.upsert_match(competition_code="UCL", kickoff_utc=self.ko, home_team_id=self.teams[2],
                                             away_team_id=self.teams[3], source_id="manual", status="scheduled")
        none = lineup_state(self.app, mid2, self.teams[2], cutoff)
        self.assertEqual(none["status"], "unpublished")
        self.assertEqual(none["players"], [])

    def test_late_lineup_flagged_in_report(self):
        cutoff = self.ko - timedelta(minutes=30)
        self.app.repo.upsert_lineup(self.mid, self.teams[0], "manual", "confirmed", self._xi("H"),
                                    fetched_at=cutoff + timedelta(minutes=2))  # för sen
        self.app.db.execute("UPDATE matches SET created_at_utc='2026-10-01T00:00:00Z' WHERE id=?", (self.mid,))
        self.clock.set(cutoff - timedelta(minutes=1))
        scheduler.tick(self.app)
        self.clock.set(cutoff)
        scheduler.tick(self.app)
        rep = self.app.db.one("SELECT * FROM reports WHERE match_id=? AND kind='T-30'", (self.mid,))
        text = pdf_text(rep["path"])
        self.assertIn("Opublicerad", text)
        self.assertIn("registrerades senare", text)
        self.assertNotIn("H 1", text)


if __name__ == "__main__":
    unittest.main()
