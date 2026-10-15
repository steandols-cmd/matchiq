"""Import av Excel/CSV: inspektion, förhandsvisning, idempotens och originalfilens orördhet."""
import hashlib
import os
import unittest
from pathlib import Path

import openpyxl
from helpers import make_app

from matchiq.importers import generic
from matchiq.importers.reader import read_any


def write_xlsx(path: Path, rows: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resultat"
    ws.append(["Kommentar: exportfil från egen källa"])
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


ROWS = [["Datum", "Tid", "Hemmalag", "Bortalag", "MH", "MB", "Hörnor H", "Hörnor B"],
        ["2025-09-16", "21:00", "Arsenal", "Inter", 2, 1, 7, None],
        ["2025-09-17", "18:45", "Paris FC", "Paris Saint-Germain", 0, 3, 2, 9],
        ["2025-09-17", "18:45", "Paris FC", "Paris Saint-Germain", 0, 3, 2, 9],  # dubblettrad
        ["", "", "Okänt", "", None, None, None, None]]


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock, self.tmp = make_app()
        self.file = write_xlsx(self.tmp / "egen.xlsx", ROWS)
        self.digest = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.mapping = {"date": "Datum", "time": "Tid", "home": "Hemmalag", "away": "Bortalag",
                        "home_goals": "MH", "away_goals": "MB", "home_corners": "Hörnor H", "away_corners": "Hörnor B"}
        self.options = {"competition": "UCL", "source_id": "manual", "timezone": "Europe/Stockholm"}

    def test_inspect_reports_missing_and_duplicates(self):
        info = generic.inspect_file(self.app, self.file)
        sh = info["sheets"][0]
        self.assertEqual(sh["header_row"], 2)
        self.assertEqual(sh["rows"], 4)
        self.assertEqual(sh["duplicate_rows"], 1)
        miss = {c["name"]: c["missing"] for c in sh["columns"]}
        self.assertEqual(miss["Hörnor B"], 2)
        self.assertEqual(miss["Datum"], 1)

    def test_preview_then_import_twice_no_duplicates(self):
        info = generic.inspect_file(self.app, self.file)
        stored = Path(info["stored_copy"])
        pv = generic.preview(self.app, stored, "Resultat", None, "matches", self.mapping, self.options)
        self.assertEqual(pv["stats"]["errors"], 1)
        self.assertEqual(pv["stats"]["duplicate_keys"], 1)
        self.assertIn("Paris FC", pv["stats"]["new_teams"])
        self.assertNotIn("Paris Saint-Germain", pv["stats"]["new_teams"])
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM matches"), 0, "förhandsvisningen skriver inget")
        generic.run(self.app, stored, "Resultat", None, "matches", self.mapping, self.options)
        n1 = {t: self.app.db.scalar(f"SELECT COUNT(*) FROM {t}") for t in ("matches", "match_results",
                                                                          "team_match_stats")}
        generic.run(self.app, stored, "Resultat", None, "matches", self.mapping, self.options)
        n2 = {t: self.app.db.scalar(f"SELECT COUNT(*) FROM {t}") for t in ("matches", "match_results",
                                                                          "team_match_stats")}
        self.assertEqual(n1, n2)
        self.assertEqual(n1["matches"], 2)
        # Inter saknar hörnvärde: ingen rad (eller NULL) – aldrig 0
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM team_match_stats WHERE corners = 0"), 0)
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM team_match_stats"), 3)
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(), self.digest, "originalfilen ändrad!")
        self.assertEqual(self.app.db.scalar("SELECT COUNT(*) FROM imports WHERE status='done'"), 2)

    def test_csv_reader_keeps_leading_zeros(self):
        p = self.tmp / "x.csv"
        p.write_text("Match-ID;Hemmalag;Bortalag\n007;A;B\n", encoding="utf-8")
        t = read_any(p)[0]
        self.assertEqual(t.rows[0][0], "007")


@unittest.skipUnless(os.environ.get("MATCHIQ_WORKBOOK"), "sätt MATCHIQ_WORKBOOK till den tidigare arbetsboken")
class WorkbookImportTests(unittest.TestCase):
    """Körs mot den riktiga arbetsboken när den finns: kontrollvärden, idempotens och V2-benchmark."""

    @classmethod
    def setUpClass(cls):
        from matchiq.importers.workbook_ucl import import_workbook
        cls.app, cls.clock, _ = make_app()
        cls.path = Path(os.environ["MATCHIQ_WORKBOOK"])
        cls.digest = hashlib.sha256(cls.path.read_bytes()).hexdigest()
        cls.res = import_workbook(cls.app, cls.path)
        cls.counts1 = {t: cls.app.db.scalar(f"SELECT COUNT(*) FROM {t}") for t in
                       ("matches", "match_results", "team_match_stats", "lineups", "forecast_snapshots")}
        cls.res2 = import_workbook(cls.app, cls.path)

    def test_inventory_controls(self):
        inv = {r["key"]: r for r in self.res["inventory"]}
        self.assertEqual(inv["cl_matches"]["found"], 2024)
        self.assertEqual(inv["domestic_legacy"]["found"], 15340)
        self.assertEqual(inv["uefa_squad_rows"]["status"], "saknas i filen")
        self.assertEqual(inv["cl_missing_Hörnor B"]["found"], 21)

    def test_idempotent_and_original_untouched(self):
        counts2 = {t: self.app.db.scalar(f"SELECT COUNT(*) FROM {t}") for t in self.counts1}
        self.assertEqual(self.counts1, counts2)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), self.digest)

    def test_missing_stats_null(self):
        null_rows = self.app.db.scalar("SELECT COUNT(*) FROM team_match_stats WHERE source_id='uefa' AND corners IS NULL")
        absent = 2 * 2024 - self.app.db.scalar("SELECT COUNT(*) FROM team_match_stats WHERE source_id='uefa'")
        self.assertEqual(null_rows + absent, 11 + 21, "32 lagrader saknar hörnor och ska vara tomma, inte 0")

    def test_v2_benchmark_reproduced(self):
        from datetime import datetime as dt
        from matchiq.models import baseline, v2
        from matchiq.models.data import HistoryStore
        from matchiq.models.evaluate import build_targets, evaluation_source_ids, summarize, walk_forward
        from matchiq.timeutil import UTC
        # Reproduktion av arbetsbokens egna siffror (körs bara lokalt när MATCHIQ_WORKBOOK anges). Källorna anges
        # uttryckligen: i appen används UEFA-data varken för träning eller utvärdering (UEFA:s villkor 6.2).
        train = HistoryStore.load(self.app.db, {"uefa", "openfootball"}, competitions=["UCL"])
        ev = HistoryStore.load(self.app.db, {"uefa", "openfootball"}, competitions=["UCL"])
        _ = evaluation_source_ids
        tg = [t for t in build_targets(ev, "UCL", ["2023/24", "2024/25", "2025/26", "2026/27"])
              if not (t.season == "2026/27" and t.kickoff_ts > dt(2026, 9, 12, tzinfo=UTC).timestamp())]
        self.assertEqual(len(tg), 517)
        s2 = summarize(walk_forward(train, v2.predict, None, tg, "test"))["all"]["1x2"]
        sb = summarize(walk_forward(train, baseline.predict, None, tg, "test"))["all"]["1x2"]
        self.assertAlmostEqual(s2["brier"], 0.556, places=3)
        self.assertAlmostEqual(s2["logloss"], 0.940, places=3)
        self.assertAlmostEqual(sb["brier"], 0.616, places=3)
        self.assertAlmostEqual(sb["logloss"], 1.020, places=3)


if __name__ == "__main__":
    unittest.main()
