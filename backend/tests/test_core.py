import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from helpers import make_app, seed_history

from matchiq import catalog
from matchiq.db import Database, latest_schema_version
from matchiq.entities import normalize_name
from matchiq.timeutil import UTC


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, _ = make_app()

    def test_paris_is_not_paris_fc(self):
        r = self.app.repo
        psg_uefa = r.resolve_team("Paris", "uefa")
        psg_full = r.resolve_team("Paris Saint-Germain", "openfootball", context="FRA1")
        paris_fc = r.resolve_team("Paris FC", "openfootball", context="FRA1")
        paris_of = r.resolve_team("Paris", "openfootball", context="FRA1")
        self.assertEqual(psg_uefa, psg_full)
        self.assertNotEqual(psg_full, paris_fc)
        self.assertNotEqual(paris_of, psg_full, "'Paris' utanför UEFA-källan får inte bli PSG")
        self.assertNotEqual(paris_of, paris_fc)

    def test_slovan_is_not_slovan_liberec(self):
        r = self.app.repo
        bratislava = r.resolve_team("S. Bratislava", "uefa")
        liberec = r.resolve_team("Slovan Liberec", "openfootball", context="CZE1")
        slovan = r.resolve_team("Slovan", "openfootball", context="CZE1")
        self.assertEqual(self.app.db.scalar("SELECT name FROM teams WHERE id=?", (bratislava,)), "Slovan Bratislava")
        self.assertEqual(len({bratislava, liberec, slovan}), 3)

    def test_source_ids_beat_names(self):
        a = self.app.repo.resolve_team("Man Utd", "uefa", source_team_id="52682")
        b = self.app.repo.resolve_team("Manchester United FC", "openfootball", context="ENG1")
        self.assertEqual(a, b)

    def test_normalization_is_exact_not_fuzzy(self):
        self.assertEqual(normalize_name("Bodø/Glimt"), normalize_name("Bodo/Glimt"))
        self.assertEqual(normalize_name("Paris Saint-Germain"), normalize_name("paris saint germain"))
        self.assertNotEqual(normalize_name("Paris"), normalize_name("Paris FC"))

    def test_new_similar_team_flagged_for_review(self):
        tid = self.app.repo.resolve_team("Paris FC", "openfootball", context="FRA1")
        self.assertEqual(self.app.db.scalar("SELECT needs_review FROM teams WHERE id=?", (tid,)), 1)


class DbTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, self.tmp = make_app()

    def test_migrations_applied_and_idempotent(self):
        self.assertEqual(self.app.db.schema_version(), latest_schema_version())
        self.assertEqual(self.app.db.migrate(), [])

    def test_catalog_seed_keeps_user_decisions(self):
        catalog.set_training_approval(self.app.db, "statsbomb_open", True, "", self.clock.now())
        catalog.seed(self.app.db, self.clock.now())
        row = dict(self.app.db.one("SELECT * FROM sources WHERE id='statsbomb_open'"))
        self.assertTrue(catalog.training_allowed(row))

    def test_upserts_idempotent_and_null_preserved(self):
        r = self.app.repo
        h = r.resolve_team("Arsenal", "uefa")
        a = r.resolve_team("Inter", "uefa")
        ko = datetime(2026, 9, 1, 19, 0, tzinfo=UTC)
        m1, act1 = r.upsert_match(competition_code="UCL", kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                  source_id="uefa", status="finished", source_match_id="X1")
        m2, act2 = r.upsert_match(competition_code="UCL", kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                  source_id="uefa", status="finished", source_match_id="X1")
        self.assertEqual(m1, m2)
        self.assertEqual((act1, act2), ("inserted", "unchanged"))
        # annan källa utan ID, samma lag och datum -> samma match (naturlig nyckel)
        m3, _ = r.upsert_match(competition_code="UCL", kickoff_utc=ko + timedelta(hours=1), home_team_id=h,
                               away_team_id=a, source_id="openfootball", status="finished",
                               kickoff_time_known=False)
        self.assertEqual(m1, m3)
        r.upsert_team_stats(m1, h, True, "uefa", {"shots": 14, "corners": None})
        self.assertEqual(r.upsert_team_stats(m1, h, True, "uefa", {"shots": 14, "corners": None}), "unchanged")
        row = self.app.db.one("SELECT shots, corners, shots_on_target FROM team_match_stats WHERE match_id=?", (m1,))
        self.assertEqual(row["shots"], 14)
        self.assertIsNone(row["corners"], "saknat värde ska vara NULL, aldrig 0")
        self.assertIsNone(row["shots_on_target"])
        self.assertEqual(r.upsert_team_stats(m1, a, False, "uefa", {"shots": None}), "skipped")

    def test_90_minutes_extra_time_and_penalties_separate(self):
        r = self.app.repo
        h, a = r.resolve_team("Inter", "uefa"), r.resolve_team("Barcelona", "uefa")
        mid, _ = r.upsert_match(competition_code="UCL", kickoff_utc=datetime(2025, 5, 6, 19, tzinfo=UTC),
                                home_team_id=h, away_team_id=a, source_id="uefa", status="finished")
        r.upsert_result(mid, "uefa", {"home_goals_90": 3, "away_goals_90": 3, "home_goals_aet": 4,
                                      "away_goals_aet": 3})
        row = self.app.db.one("SELECT * FROM match_results WHERE match_id=?", (mid,))
        self.assertEqual((row["home_goals_90"], row["home_goals_aet"], row["decided_by"]), (3, 4, "extra_time"))
        self.assertIsNone(row["home_pens"])

    def test_snapshots_and_reports_immutable(self):
        seed_history(self.app, seasons=(2024, 2025), n_teams=8)
        from matchiq.forecast import freeze
        m = self.app.db.one("SELECT id FROM matches LIMIT 1")["id"]
        self.app.db.execute("UPDATE matches SET status='scheduled', kickoff_utc='2026-10-20T19:00:00Z' WHERE id=?", (m,))
        fr = freeze(self.app, m, self.clock.now(), kind="manual", created_by="test")
        sid = fr["snapshot_ids"]["V2"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.app.db.execute("UPDATE forecast_snapshots SET p_home=0.9 WHERE id=?", (sid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.app.db.execute("DELETE FROM forecast_snapshots WHERE id=?", (sid,))

    def test_probabilities_must_sum_to_one_in_db(self):
        seed_history(self.app, seasons=(2025,), n_teams=4)
        m = self.app.db.one("SELECT id FROM matches LIMIT 1")["id"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.app.db.execute("""INSERT INTO forecast_snapshots (id, match_id, model_version_id, model_family, kind,
                created_at_utc, data_cutoff_utc, kickoff_utc_at_creation, minutes_before_kickoff, prematch_eligible,
                created_by, p_home, p_draw, p_away, payload_json, inputs_hash) VALUES
                ('x', ?, 'V2-2.0', 'V2', 'manual', 'a', 'a', 'a', 1, 1, 't', 0.5, 0.3, 0.3, '{}', 'h')""", (m,))

    def test_export_import_roundtrip(self):
        seed_history(self.app, seasons=(2025,), n_teams=6)
        n = self.app.db.scalar("SELECT COUNT(*) FROM matches")
        out = self.tmp / "exports" / "e.zip"
        manifest = self.app.db.export_bundle(out)
        self.assertEqual(manifest["tables"]["matches"]["rows"], n)
        Database.verify_bundle(out)
        app2, _, _ = make_app()
        # en anslutning i en annan tråd (som API-servern) måste stängas före ersättningen och öppnas på nytt efteråt
        import threading
        seen: list[int] = []
        t = threading.Thread(target=lambda: seen.append(app2.db.scalar("SELECT COUNT(*) FROM matches")))
        t.start(); t.join()
        res = app2.db.import_bundle(out)
        self.assertEqual(app2.db.scalar("SELECT COUNT(*) FROM matches"), n)
        self.assertTrue(res["backup"])
        self.assertFalse(out.with_suffix(".tmp.sqlite").exists())
        t = threading.Thread(target=lambda: seen.append(app2.db.scalar("SELECT COUNT(*) FROM matches")))
        t.start(); t.join()
        self.assertEqual(seen, [0, n])

    def test_backup_before_migration(self):
        db = Database(self.tmp / "other.sqlite", self.tmp / "bk")
        db.migrate()
        self.assertEqual(list((self.tmp / "bk").glob("*.sqlite")), [], "ingen backup av tom databas")


class LicensingTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, _ = make_app()

    def test_default_training_sources(self):
        ids = catalog.training_source_ids(self.app.db)
        self.assertIn("openfootball", ids)
        self.assertIn("manual", ids)
        for blocked in ("uefa", "football_data_couk", "the_odds_api", "statsbomb_open", "user_file", "statmuse_legacy"):
            self.assertNotIn(blocked, ids)

    def test_blocked_source_requires_documented_permission(self):
        with self.assertRaises(ValueError):
            catalog.set_training_approval(self.app.db, "football_data_couk", True, "ok", self.clock.now())
        catalog.set_training_approval(self.app.db, "football_data_couk", True,
                                      "Skriftligt tillstånd från Football-Data, mejl 2026-10-01", self.clock.now())
        self.assertIn("football_data_couk", catalog.training_source_ids(self.app.db))
        catalog.set_training_approval(self.app.db, "football_data_couk", False, "återkallad", self.clock.now())
        self.assertNotIn("football_data_couk", catalog.training_source_ids(self.app.db))

    def test_blocked_data_not_used_for_training(self):
        from matchiq.models.data import HistoryStore
        seed_history(self.app, seasons=(2024, 2025), n_teams=8, source="football_data_couk", with_stats=False)
        store = HistoryStore.load(self.app.db, None, competitions=["UCL"])
        self.assertEqual(len(store.a.match_id), len(store.a.match_id))
        view = store.view(datetime(2027, 1, 1, tzinfo=UTC))
        self.assertEqual(len(view.metric("goals", ("UCL",))["h"]), 0, "spärrad källa får inte bli träningsdata")

    def test_disabled_fetch_requires_note(self):
        with self.assertRaises(ValueError):
            catalog.set_source_enabled(self.app.db, "statmuse_legacy", True, self.clock.now(), "")
        catalog.set_source_enabled(self.app.db, "statmuse_legacy", True, self.clock.now(),
                                   "Villkoren granskade 2026-10-15")
        self.assertEqual(self.app.db.scalar("SELECT enabled FROM sources WHERE id='statmuse_legacy'"), 1)

    def test_uefa_terms_block_fetching_and_revoke_earlier_training_approval(self):
        # Före granskningen: källan var "oklar" och användaren godkände träning med en anteckning
        self.app.db.execute("""UPDATE sources SET training_policy='unclear', automated_fetch='disabled', enabled=1,
            training_approval='approved', training_approval_note='Godkänt av mig för egen analys' WHERE id='uefa'""")
        self.assertTrue(catalog.training_allowed(dict(self.app.db.one("SELECT * FROM sources WHERE id='uefa'"))))
        catalog.seed(self.app.db, self.clock.now())  # ny version med granskade villkor
        src = dict(self.app.db.one("SELECT * FROM sources WHERE id='uefa'"))
        self.assertFalse(catalog.training_allowed(src))
        self.assertEqual((src["training_policy"], src["training_approval"], src["enabled"]), ("blocked", "revoked", 0))
        self.assertEqual(json.loads(src["allowed_uses"]), ["display"])
        self.assertTrue(self.app.db.scalar("SELECT COUNT(*) FROM notifications WHERE title LIKE 'UEFA%'"))
        self.assertTrue(self.app.db.scalar(
            "SELECT COUNT(*) FROM source_audit WHERE source_id='uefa' AND action LIKE 'träning återkallad%'"))
        with self.assertRaises(ValueError):
            catalog.set_source_enabled(self.app.db, "uefa", True, self.clock.now(), "Jag vill hämta från UEFA")
        # Ny seed ändrar inget mer (idempotent)
        catalog.seed(self.app.db, self.clock.now())
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM notifications WHERE title LIKE 'UEFA%'"), 1)


if __name__ == "__main__":
    unittest.main()
