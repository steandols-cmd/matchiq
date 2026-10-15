"""Verifiering mellan källor: bekräftade värden, avvikelser och en avisering per match."""
import unittest
from datetime import datetime, timedelta

from helpers import make_app

from matchiq import verification
from matchiq.timeutil import UTC


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, _ = make_app(datetime(2026, 10, 15, 8, 0, tzinfo=UTC))
        r = self.app.repo
        self.h = r.resolve_team("Arsenal FC", "manual", context="UCL")
        self.a = r.resolve_team("LOSC Lille", "manual", context="UCL")
        self.mid, _ = r.upsert_match(competition_code="UCL", kickoff_utc=datetime(2026, 10, 13, 19, 0, tzinfo=UTC),
                                     home_team_id=self.h, away_team_id=self.a, source_id="manual", status="finished",
                                     season_label="2026/27")

    def _xi(self, numbers, prefix="P"):
        return [{"name": f"{prefix} Spelare{n}", "number": n, "position": None, "is_starter": True} for n in numbers]

    def _part(self, v, key):
        return next(p for p in v["parts"] if p["key"] == key)

    def test_single_source_is_not_called_confirmed(self):
        self.app.repo.upsert_result(self.mid, "api_football", {"home_goals_90": 3, "away_goals_90": 0})
        v = verification.verify_match(self.app, self.mid)
        self.assertEqual(self._part(v, "result")["status"], "en_kalla")
        self.assertEqual(self._part(v, "corners")["status"], "saknas")

    def test_agreeing_sources_confirm_and_differences_are_shown_per_source(self):
        r = self.app.repo
        r.upsert_result(self.mid, "api_football", {"home_goals_90": 3, "away_goals_90": 0})
        r.upsert_result(self.mid, "uefa", {"home_goals_90": 3, "away_goals_90": 0})
        r.upsert_team_stats(self.mid, self.h, True, "api_football", {"corners": 7, "shots": 16})
        r.upsert_team_stats(self.mid, self.a, False, "api_football", {"corners": 0, "shots": 4})
        r.upsert_team_stats(self.mid, self.h, True, "uefa", {"corners": 7, "shots": 17})
        r.upsert_team_stats(self.mid, self.a, False, "uefa", {"corners": 0, "shots": 4})
        v = verification.verify_match(self.app, self.mid)
        self.assertEqual(self._part(v, "result")["status"], "bekraftad")
        self.assertEqual(self._part(v, "corners")["status"], "bekraftad")
        shots = self._part(v, "shots")
        self.assertEqual(shots["status"], "avvikelse")
        self.assertEqual(sorted((x["home"], x["away"]) for x in shots["values"]), [(16, 4), (17, 4)])
        self.assertEqual(self._part(v, "sot")["status"], "saknas")     # inget värde hittas på
        self.assertEqual(v["status"], "avvikelse")

    def test_lineups_compared_on_shirt_numbers(self):
        r = self.app.repo
        t = self.clock.now() - timedelta(days=2)
        r.upsert_lineup(self.mid, self.h, "api_football", "confirmed", self._xi(range(1, 12), "A"), fetched_at=t)
        r.upsert_lineup(self.mid, self.h, "uefa", "confirmed", self._xi(range(1, 12), "U"), fetched_at=t)
        r.upsert_lineup(self.mid, self.a, "api_football", "confirmed", self._xi(range(1, 12)), fetched_at=t)
        r.upsert_lineup(self.mid, self.a, "uefa", "confirmed", self._xi([*range(1, 11), 23]), fetched_at=t)
        lu = self._part(verification.verify_match(self.app, self.mid), "lineups")
        self.assertEqual(lu["status"], "avvikelse")
        self.assertEqual({(d["side"], d["players"]) for d in lu["differences"]}, {("home", 0), ("away", 1)})

    def test_discrepancy_notified_once(self):
        r = self.app.repo
        r.upsert_result(self.mid, "api_football", {"home_goals_90": 3, "away_goals_90": 0})
        r.upsert_result(self.mid, "football_data_org", {"home_goals_90": 3, "away_goals_90": 1})
        self.assertEqual(verification.notify_new_discrepancies(self.app), 1)
        self.assertEqual(verification.notify_new_discrepancies(self.app), 0)
        n = self.app.db.one("SELECT * FROM notifications WHERE match_id=?", (self.mid,))
        self.assertIn("Källorna skiljer sig", n["title"])
        listing = verification.verify(self.app, days=30, only="avvikelse")
        self.assertEqual(listing["counts"]["avvikelse"], 1)
        self.assertEqual([m["id"] for m in listing["matches"]], [self.mid])


if __name__ == "__main__":
    unittest.main()
