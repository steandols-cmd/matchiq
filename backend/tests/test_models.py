import json
import unittest
from datetime import datetime, timedelta

import numpy as np
from helpers import make_app, seed_history

from matchiq.forecast import compute
from matchiq.models import baseline, v2, v3
from matchiq.models.data import HistoryStore
from matchiq.models.evaluate import build_targets, evaluation_source_ids, summarize, walk_forward
from matchiq.models.metrics import brier, calibration_bins, logloss, summarize_counts
from matchiq.timeutil import UTC


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.clock, _ = make_app()
        cls.teams = seed_history(cls.app)
        cls.store = HistoryStore.load(cls.app.db, None, competitions=["UCL"])

    def test_probabilities_sum_to_one(self):
        view = self.store.view(datetime(2026, 9, 1, tzinfo=UTC))
        for mod in (v2, v3, baseline):
            out = mod.predict(view, "UCL", self.teams[0], self.teams[1])
            p = out["probs"]
            self.assertAlmostEqual(p["p_home"] + p["p_draw"] + p["p_away"], 1.0, places=12)
            for m in ("goals", "shots", "sot", "corners"):
                blk = out["metrics"][m]
                self.assertIsNotNone(blk)
                self.assertLessEqual(blk["home"]["lo"], blk["home"]["mean"] + 1)
                self.assertGreaterEqual(blk["home"]["hi"], blk["home"]["lo"])

    def test_no_leakage_after_cutoff(self):
        """Data efter datagränsen får inte påverka prognosen – även om den finns i databasen."""
        cutoff = datetime(2025, 1, 1, tzinfo=UTC)
        h, a = self.teams[2], self.teams[3]
        before = {}
        for mod in (v2, v3, baseline):
            store = HistoryStore.load(self.app.db, None, competitions=["UCL"])
            before[mod.MODEL_ID] = mod.predict(store.view(cutoff), "UCL", h, a)
        # 1) extrema matcher EFTER datagränsen
        for d in range(5):
            mid, _ = self.app.repo.upsert_match(competition_code="UCL",
                                                kickoff_utc=cutoff + timedelta(days=d + 1, hours=19),
                                                home_team_id=h, away_team_id=a, source_id="manual", status="finished")
            self.app.repo.upsert_result(mid, "manual", {"home_goals_90": 9, "away_goals_90": 0})
            self.app.repo.upsert_team_stats(mid, h, True, "manual", {"shots": 60, "shots_on_target": 30,
                                                                      "corners": 25})
            self.app.repo.upsert_team_stats(mid, a, False, "manual", {"shots": 0, "shots_on_target": 0, "corners": 0})
        # 2) en match FÖRE datagränsen vars resultat publicerades EFTER datagränsen
        mid, _ = self.app.repo.upsert_match(competition_code="UCL", kickoff_utc=cutoff - timedelta(hours=1),
                                            home_team_id=h, away_team_id=a, source_id="manual", status="finished")
        self.app.repo.upsert_result(mid, "manual", {"home_goals_90": 8, "away_goals_90": 0},
                                    available_at=cutoff + timedelta(hours=2))
        for mod in (v2, v3, baseline):
            store = HistoryStore.load(self.app.db, None, competitions=["UCL"])
            after = mod.predict(store.view(cutoff), "UCL", h, a)
            self.assertEqual(json.dumps(before[mod.MODEL_ID], sort_keys=True, default=str),
                             json.dumps(after, sort_keys=True, default=str), f"läckage i {mod.MODEL_ID}")
            # sanity: med en senare datagräns syns de nya matcherna
            later = mod.predict(store.view(cutoff + timedelta(days=30)), "UCL", h, a)
            self.assertNotEqual(json.dumps(after["probs"]), json.dumps(later["probs"]))

    def test_view_asserts_on_cutoff(self):
        view = self.store.view(datetime(2024, 1, 1, tzinfo=UTC))
        d = view.metric("goals", ("UCL",))
        self.assertTrue(np.all(d["kickoff"] < datetime(2024, 1, 1, tzinfo=UTC).timestamp()))

    def test_missing_metric_is_none_not_zero(self):
        app, _, _ = make_app()
        teams = seed_history(app, seasons=(2024, 2025), with_stats=False)
        store = HistoryStore.load(app.db, None, competitions=["UCL"])
        out = v2.predict(store.view(datetime(2026, 9, 1, tzinfo=UTC)), "UCL", teams[0], teams[1])
        self.assertIsNotNone(out["metrics"]["goals"])
        for m in ("shots", "sot", "corners"):
            self.assertIsNone(out["metrics"][m])
            self.assertEqual(out["coverage"][m]["status"], "spärrad")

    def test_walk_forward_and_metrics(self):
        ev = HistoryStore.load(self.app.db, evaluation_source_ids(self.app.db), competitions=["UCL"])
        targets = build_targets(ev, "UCL", ["2024/25", "2025/26"])
        rows = walk_forward(self.store, v2.predict, None, targets, "test")
        s = summarize(rows)
        self.assertGreater(s["all"]["1x2"]["n"], 100)
        base = summarize(walk_forward(self.store, baseline.predict, None, targets, "test"))
        self.assertLess(s["all"]["1x2"]["logloss"], base["all"]["1x2"]["logloss"],
                        "V2 ska slå konstant baslinje på data med verklig styrkeskillnad")
        for m in ("shots", "sot", "corners", "goals"):
            self.assertIsNotNone(s["all"][m]["mae"])
            self.assertIsNotNone(s["all"][m]["coverage"])

    def test_metric_functions(self):
        self.assertAlmostEqual(brier((1.0, 0.0, 0.0), "1"), 0.0)
        self.assertAlmostEqual(brier((0.0, 1.0, 0.0), "1"), 2.0)
        self.assertAlmostEqual(logloss((0.5, 0.25, 0.25), "1"), 0.6931471805599453)
        c = summarize_counts([(5.0, 7, 3, 8), (5.0, 3, 3, 8), (2.0, None, 0, 4)])
        self.assertEqual(c["n"], 2)
        self.assertAlmostEqual(c["mae"], 2.0)
        self.assertAlmostEqual(c["bias"], 0.0)
        self.assertAlmostEqual(c["coverage"], 1.0)
        bins = calibration_bins([((0.6, 0.2, 0.2), "1"), ((0.6, 0.2, 0.2), "X")], 5)
        self.assertEqual(sum(b["n"] for b in bins), 6)

    def test_compute_payload_has_coverage_sources_and_flags(self):
        m = self.app.db.one("SELECT id FROM matches ORDER BY kickoff_utc DESC LIMIT 1")["id"]
        self.app.db.execute("UPDATE matches SET status='scheduled', kickoff_utc='2026-10-20T19:00:00Z' WHERE id=?", (m,))
        pl = compute(self.app, m, datetime(2026, 10, 20, 18, 30, tzinfo=UTC))
        self.assertIn("V2", pl["models"])
        self.assertIn("V3", pl["models"])
        self.assertEqual(pl["lineups"]["home"]["status"], "unpublished")
        self.assertEqual(pl["lineups"]["home"]["players"], [])
        self.assertTrue(any(f["code"] == "lineup_home" for f in pl["flags"]))
        self.assertIn("openfootball", pl["training_sources"])
        self.assertTrue(any(b["id"] == "uefa" for b in pl["blocked_sources"]))


class SelectionTests(unittest.TestCase):
    def test_selection_locks_params_before_test_and_v3_never_auto_production(self):
        from matchiq.models import selection
        app, _, _ = make_app()
        seed_history(app, n_teams=20)
        old = (selection.HL_GRID, selection.K_GRID)
        selection.HL_GRID, selection.K_GRID = [365.0, 1460.0], [4.0, 8.0]
        try:
            res = selection.run_selection(app, "UCL", ["2023/24", "2024/25"], ["2025/26"])
        finally:
            selection.HL_GRID, selection.K_GRID = old
        self.assertTrue(res["params"]["calibrated"])
        self.assertEqual(res["params"]["selected_on"], ["2023/24", "2024/25"])
        # inga valideringsloggar får komma från testsäsongen: valet görs innan testkörningen
        self.assertTrue(all(step["stage"] in ("hl_k", "bridge", "rho") for step in res["selection_log"]))
        status = app.db.scalar("SELECT status FROM model_versions WHERE id='V3-3.0'")
        self.assertIn(status, ("experimentell", "kandidat"))
        self.assertFalse(res["gates"]["production_possible"], "utan frysta T−30-prognoser kan V3 inte bli produktion")


if __name__ == "__main__":
    unittest.main()
