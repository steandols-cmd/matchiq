"""Importprofil för den tidigare UCL-arbetsboken ("UCL_officiella_18_startelvor_och_verifiering*.xlsx").

Arbetsboken är INTE ett krav för att appen ska starta – den kan importeras som historiskt underlag.
Importen är spårbar (imports-tabellen, fil-hash, källa per rad), idempotent (kan köras om utan
dubbletter) och skriver aldrig till originalfilen. Frysta prognoser från arbetsboken importeras som
oföränderliga 'legacy'-snapshots och kopplas till rätt match.
"""
from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from ..aliases_seed import WORKBOOK_LEAGUES
from ..core import App
from ..entities import normalize_name
from ..timeutil import STOCKHOLM, UTC, local_to_utc, to_iso
from .reader import Table, excel_serial_to_datetime, file_sha256, read_xlsx, stash_copy

PROFILE_ID = "ucl-arbetsbok"

# Kontrollvärden från tidigare inventering. Verifieras mot filen – inte bevis på fullständig täckning.
CONTROLS: list[dict] = [
    {"key": "cl_matches", "label": "Champions League-matcher (UEFA)", "expected": 2024, "sheets": ["CL HISTORIK"]},
    {"key": "uefa_squad_rows", "label": "UEFA spelar-/trupposter", "expected": 79742,
     "sheets": ["UEFA TRUPPER", "TRUPPER", "UEFA SPELARE", "TRUPPPOSTER"]},
    {"key": "uefa_scorers", "label": "UEFA målskyttsposter", "expected": 6183,
     "sheets": ["MÅLSKYTTAR", "UEFA MÅLSKYTTAR", "MALSKYTTAR"]},
    {"key": "domestic_legacy", "label": "Äldre inhemska matcher (OpenFootball)", "expected": 15340,
     "sheets": ["INHEMSK HISTORIK"]},
    {"key": "football_data", "label": "Football-Data-rader", "expected": 105156,
     "sheets": ["FOOTBALL-DATA", "FOOTBALL DATA", "FOOTBALLDATA"]},
    {"key": "football_json", "label": "OpenFootball football.json-rader", "expected": 37259,
     "sheets": ["FOOTBALL.JSON", "FOOTBALL JSON"]},
    {"key": "europe", "label": "OpenFootball Europe-rader", "expected": 2985,
     "sheets": ["EUROPE", "OPENFOOTBALL EUROPE"]},
    {"key": "sb_matches", "label": "StatsBomb-matcher", "expected": 386, "sheets": ["STATSBOMB MATCHER", "STATSBOMB"]},
    {"key": "sb_player_rows", "label": "StatsBomb spelarrader", "expected": 10836,
     "sheets": ["STATSBOMB SPELARE", "STATSBOMB SPELARSTATISTIK"]},
    {"key": "sb_team_rows", "label": "StatsBomb lagmatchrader", "expected": 772,
     "sheets": ["STATSBOMB LAG", "STATSBOMB LAGSTATISTIK"]},
    {"key": "sb_lineups", "label": "StatsBomb eventbaserade startelvor", "expected": 8492,
     "sheets": ["STATSBOMB ELVOR", "STATSBOMB STARTELVOR"]},
    {"key": "failed_fetches", "label": "Misslyckade eller saknade filhämtningar (manifest)", "expected": 66,
     "sheets": ["NEDLADDNINGAR"]},
]
EXPECTED_MISSING_CL = {"Skott H": 6, "Skott B": 6, "Skott på mål H": 9, "Skott på mål B": 11,
                       "Hörnor H": 11, "Hörnor B": 21}

_TIME_PREFIX = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s+(.*\S)\s*$")


def detect(sheet_names: list[str]) -> bool:
    names = {s.upper() for s in sheet_names}
    return "CL HISTORIK" in names and bool(names & {"INHEMSK HISTORIK", "PROGNOSLOGG", "MD3 SKUGGTEST"})


def _find_table(tables: dict[str, Table], candidates: list[str]) -> Table | None:
    norm = {normalize_name(k): v for k, v in tables.items()}
    for c in candidates:
        t = norm.get(normalize_name(c))
        if t is not None:
            return t
    return None


def verify_inventory(tables: dict[str, Table]) -> list[dict]:
    out = []
    for ctl in CONTROLS:
        t = _find_table(tables, ctl["sheets"])
        if t is None:
            out.append({**{k: ctl[k] for k in ("key", "label", "expected")}, "found": None, "sheet": None,
                        "status": "saknas i filen",
                        "note": "Bladet finns inte i den här arbetsboken – datamängden kan inte verifieras och "
                                "redovisas som saknad."})
            continue
        if ctl["key"] == "failed_fetches":
            status_col = next((c for c in t.columns if "status" in c.lower()), None)
            found = sum(1 for r in t.records() if status_col and str(r.get(status_col)) not in ("200", "OK", "ok"))
        else:
            found = len(t.rows)
        st = "stämmer" if found == ctl["expected"] else "avviker"
        out.append({**{k: ctl[k] for k in ("key", "label", "expected")}, "found": found, "sheet": t.name,
                    "status": st, "note": "" if st == "stämmer" else f"Skillnad {found - ctl['expected']:+d} rader"})
    cl = tables.get("CL HISTORIK")
    if cl is not None:
        for col, exp in EXPECTED_MISSING_CL.items():
            if col in cl.columns:
                n = sum(1 for r in cl.records() if r.get(col) is None)
                out.append({"key": f"cl_missing_{col}", "label": f"CL-rader där '{col}' saknas (lagras som tomt)",
                            "expected": exp, "found": n, "sheet": cl.name,
                            "status": "stämmer" if n == exp else "avviker", "note": ""})
    return out


def _int(v: Any) -> int | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _season_label(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{4})[-/](\d{2,4})$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)[-2:]}"
    return s


def _cl_season_for(dt: datetime) -> str:
    y = dt.year if dt.month >= 7 else dt.year - 1
    return f"{y}/{str(y + 1)[-2:]}"


class WorkbookImporter:
    def __init__(self, app: App, progress: Callable[[str, int, int], None] | None = None):
        self.app = app
        self.repo = app.repo
        self.db = app.db
        self.progress = progress or (lambda stage, done, total: None)
        self.team_cache: dict[tuple, int] = {}
        self.counts: dict[str, Counter] = defaultdict(Counter)
        self.warnings: list[str] = []
        self.import_id: int | None = None

    # ---------------------------------------------------------------- helpers
    def team(self, name: str, source: str, context: str = "", source_team_id: str | None = None,
             domestic: str | None = None) -> int:
        key = (name, source, context, source_team_id)
        if key not in self.team_cache:
            self.team_cache[key] = self.repo.resolve_team(name, source, context=context,
                                                          source_team_id=source_team_id, domestic_code=domestic)
        return self.team_cache[key]

    def match_by_source(self, source_id: str, source_match_id: str) -> int | None:
        r = self.db.one("SELECT match_id FROM match_source_ids WHERE source_id=? AND source_match_id=?",
                        (source_id, str(source_match_id)))
        return int(r["match_id"]) if r else None

    def match_by_official(self, official: str) -> int | None:
        r = self.db.one("SELECT id FROM matches WHERE official_match_id=?", (str(official),))
        return int(r["id"]) if r else None

    def match_by_teams_date(self, comp: str, local_date: str, home_id: int, away_id: int) -> int | None:
        r = self.db.one("SELECT id FROM matches WHERE natural_key=?", (f"{comp}|{local_date}|{home_id}|{away_id}",))
        return int(r["id"]) if r else None

    # ------------------------------------------------------------------- run
    def run(self, path: Path, *, original_name: str | None = None) -> dict:
        app = self.app
        stored, digest = stash_copy(path, app.paths.imports)
        now = to_iso(app.clock.now())
        cur = self.db.execute("""INSERT INTO imports (file_name, file_sha256, file_bytes, stored_copy_path, profile,
            started_at_utc, status) VALUES (?,?,?,?,?,?, 'running')""",
                              (original_name or path.name, digest, stored.stat().st_size, str(stored), PROFILE_ID, now))
        self.import_id = int(cur.lastrowid)
        try:
            self.progress("Läser arbetsboken", 0, 1)
            tables = {t.name: t for t in read_xlsx(stored)}
            inventory = verify_inventory(tables)
            steps = [
                ("CL HISTORIK", self._cl_history),
                ("HISTORISKA MATCHER", self._openfootball_cl),
                ("INHEMSK HISTORIK", self._domestic),
                ("9 MATCHER", self._nine_matches),
                ("PROGNOSLOGG", self._forecast_log),
                ("ELVOR – INMATNING", self._lineups_md2_day1),
                ("MD2 SKUGGTEST", self._md2_shadow),
                ("MD2 SPELARHISTORIK", self._md2_expected_xi),
                ("MD2 STARTELVOR", self._md2_confirmed_xi),
                ("MD3 SKUGGTEST", self._md3_fixtures),
            ]
            for i, (sheet, fn) in enumerate(steps):
                self.progress(f"Importerar {sheet}", i, len(steps))
                t = tables.get(sheet)
                if t is None:
                    self.warnings.append(f"Bladet '{sheet}' saknas – hoppas över.")
                    continue
                with self.db.tx():
                    fn(t, tables)
            review = self.db.query("SELECT id, name FROM teams WHERE needs_review=1 ORDER BY name")
            summary = {
                "profile": PROFILE_ID,
                "file": original_name or path.name,
                "sha256": digest,
                "inventory": inventory,
                "counts": {k: dict(v) for k, v in self.counts.items()},
                "warnings": self.warnings,
                "teams_needing_review": len(review),
                "sheets_in_file": list(tables.keys()),
            }
            self.db.execute("UPDATE imports SET status='done', finished_at_utc=?, summary_json=? WHERE id=?",
                            (to_iso(app.clock.now()), json.dumps(summary, ensure_ascii=False), self.import_id))
            self.progress("Klar", 1, 1)
            return {"import_id": self.import_id, **summary}
        except Exception as e:  # pragma: no cover - loggas och visas för användaren
            self.db.execute("UPDATE imports SET status='error', finished_at_utc=?, error=? WHERE id=?",
                            (to_iso(app.clock.now()), repr(e), self.import_id))
            raise

    # ------------------------------------------------------------ CL HISTORIK
    def _cl_history(self, t: Table, tables: dict) -> None:
        c = self.counts["cl_historik"]
        for r in t.records():
            mid_src = r.get("Match-ID")
            if mid_src is None:
                continue
            ko = r.get("Avspark UTC")
            if isinstance(ko, datetime):
                ko_utc = ko.replace(tzinfo=UTC)
                time_known = True
            else:
                d = excel_serial_to_datetime(r.get("Datum"))
                if d is None:
                    self.warnings.append(f"CL HISTORIK: saknar datum för match {mid_src}")
                    continue
                ko_utc = local_to_utc(d.replace(hour=20, minute=0))
                time_known = False
            home = self.team(str(r["Hemmalag"]), "uefa", source_team_id=_s(r.get("Hem-ID")))
            away = self.team(str(r["Bortalag"]), "uefa", source_team_id=_s(r.get("Borta-ID")))
            hg90, ag90 = _int(r.get("Mål H 90")), _int(r.get("Mål B 90"))
            status = "finished" if hg90 is not None else "scheduled"
            match_id, action = self.repo.upsert_match(
                competition_code="UCL", kickoff_utc=ko_utc, home_team_id=home, away_team_id=away,
                source_id="uefa", status=status, season_label=_season_label(r.get("Säsong")),
                source_match_id=str(mid_src), official_match_id=str(mid_src), kickoff_time_known=time_known,
                stage=_s(r.get("Fas")), round_=_s(r.get("Omgång")), matchday=_s(r.get("Matchdag")),
                import_id=self.import_id)
            c[f"match_{action}"] += 1
            if hg90 is not None:
                et = _int(r.get("Förlängning/straff")) == 1
                vals = {"home_goals_90": hg90, "away_goals_90": ag90}
                if et:
                    vals.update({"home_goals_aet": _int(r.get("Mål H totalt")),
                                 "away_goals_aet": _int(r.get("Mål B totalt")), "decided_by": "extra_time"})
                res = self.repo.upsert_result(match_id, "uefa", vals, original_home=str(r["Hemmalag"]),
                                              original_away=str(r["Bortalag"]), import_id=self.import_id)
                c[f"result_{res}"] += 1
                for is_home, team_id, sfx in ((True, home, "H"), (False, away, "B")):
                    st = self.repo.upsert_team_stats(match_id, team_id, is_home, "uefa", {
                        "shots": _int(r.get(f"Skott {sfx}")),
                        "shots_on_target": _int(r.get(f"Skott på mål {sfx}")),
                        "corners": _int(r.get(f"Hörnor {sfx}")),
                    }, import_id=self.import_id)
                    c[f"teamstats_{st}"] += 1

    # ----------------------------------------------------- HISTORISKA MATCHER
    def _openfootball_cl(self, t: Table, tables: dict) -> None:
        """CL-resultat från OpenFootball (CC0) – ger en träningsbar resultatkälla för samma matcher."""
        c = self.counts["openfootball_cl"]
        for r in t.records():
            d = excel_serial_to_datetime(r.get("Datum"))
            if d is None:
                continue
            home = self.team(str(r["Hemmalag"]), "openfootball", context="UCL")
            away = self.team(str(r["Bortalag"]), "openfootball", context="UCL")
            ld = d.strftime("%Y-%m-%d")
            existing = self.match_by_teams_date("UCL", ld, home, away)
            if existing is None:
                ko = local_to_utc(d.replace(hour=21, minute=0))
                existing, action = self.repo.upsert_match(
                    competition_code="UCL", kickoff_utc=ko, home_team_id=home, away_team_id=away,
                    source_id="openfootball", status="finished", season_label=_season_label(r.get("Säsong")),
                    kickoff_time_known=False, import_id=self.import_id)
                c[f"match_{action}"] += 1
            else:
                c["match_matched_existing"] += 1
            if r.get("Match-ID"):
                with self.db.tx() as cx:
                    cx.execute("INSERT OR IGNORE INTO match_source_ids VALUES (?,?,?)",
                               (existing, "workbook_legacy", str(r["Match-ID"])))
            hg, ag = _int(r.get("Mål hemma")), _int(r.get("Mål borta"))
            if hg is not None and ag is not None:
                res = self.repo.upsert_result(existing, "openfootball", {"home_goals_90": hg, "away_goals_90": ag},
                                              original_home=str(r["Hemmalag"]), original_away=str(r["Bortalag"]),
                                              import_id=self.import_id)
                c[f"result_{res}"] += 1

    # ------------------------------------------------------- INHEMSK HISTORIK
    def _domestic(self, t: Table, tables: dict) -> None:
        c = self.counts["inhemsk"]
        total = len(t.rows)
        for i, r in enumerate(t.records()):
            if i % 1000 == 0:
                self.progress("Importerar INHEMSK HISTORIK", i, total)
            lg = str(r.get("Liga") or "").strip()
            if lg not in WORKBOOK_LEAGUES:
                c["skipped_unknown_league"] += 1
                continue
            comp, tzname = WORKBOOK_LEAGUES[lg]
            d = excel_serial_to_datetime(r.get("Datum"))
            if d is None:
                c["skipped_no_date"] += 1
                continue
            home_raw, away_raw = str(r.get("Hemmalag") or ""), str(r.get("Bortalag") or "")
            m = _TIME_PREFIX.match(home_raw)
            if m:
                hh, mm, home_name = int(m.group(1)), int(m.group(2)), m.group(3)
                ko = d.replace(hour=hh, minute=mm).replace(tzinfo=ZoneInfo(tzname)).astimezone(UTC)
                known = True
            else:
                home_name = home_raw.strip()
                ko = d.replace(hour=15, minute=0).replace(tzinfo=ZoneInfo(tzname)).astimezone(UTC)
                known = False
            away_name = away_raw.strip()
            if not home_name or not away_name:
                c["skipped_no_team"] += 1
                continue
            home = self.team(home_name, "openfootball", context=comp, domestic=comp)
            away = self.team(away_name, "openfootball", context=comp, domestic=comp)
            if home == away:
                c["skipped_same_team"] += 1
                continue
            hg, ag = _int(r.get("Mål H")), _int(r.get("Mål B"))
            match_id, action = self.repo.upsert_match(
                competition_code=comp, kickoff_utc=ko, home_team_id=home, away_team_id=away,
                source_id="openfootball", status="finished" if hg is not None else "scheduled",
                season_label=_season_label(r.get("Säsong")), kickoff_time_known=known, import_id=self.import_id)
            c[f"match_{action}"] += 1
            if hg is not None and ag is not None:
                res = self.repo.upsert_result(match_id, "openfootball", {"home_goals_90": hg, "away_goals_90": ag},
                                              original_home=home_raw, original_away=away_raw,
                                              import_id=self.import_id)
                c[f"result_{res}"] += 1

    # -------------------------------------------------------------- 9 MATCHER
    def _nine_matches(self, t: Table, tables: dict) -> None:
        """Registrera arbetsbokens match-ID:n (CL-20261013-…) så att elvor kan kopplas rätt."""
        c = self.counts["nio_matcher"]
        for r in t.records():
            if not r.get("Match-ID") or not r.get("Hemmalag"):
                continue
            d = r.get("Matchdatum (Stockholm)")
            # Arkets lagnamn följer UEFA:s namngivning (kolumnen Källa = UEFA)
            home = self.team(str(r["Hemmalag"]), "uefa")
            away = self.team(str(r["Bortalag"]), "uefa")
            mid = self.match_by_teams_date("UCL", str(d), home, away)
            if mid is None:
                self.warnings.append(f"9 MATCHER: hittade ingen match för {r['Hemmalag']}–{r['Bortalag']} {d}")
                continue
            with self.db.tx() as cx:
                cx.execute("INSERT OR IGNORE INTO match_source_ids VALUES (?,?,?)",
                           (mid, "workbook_legacy", str(r["Match-ID"])))
            c["linked"] += 1

    # ------------------------------------------------------------ PROGNOSLOGG
    def _forecast_log(self, t: Table, tables: dict) -> None:
        c = self.counts["prognoslogg"]
        for r in t.records():
            uefa_id = r.get("Match-ID")
            if not uefa_id or not str(uefa_id).isdigit():
                continue
            mid = self.match_by_official(str(uefa_id))
            if mid is None:
                self.warnings.append(f"PROGNOSLOGG: match {uefa_id} saknas i CL-historiken")
                continue
            m = self.db.one("SELECT kickoff_utc FROM matches WHERE id=?", (mid,))
            ko = datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00"))
            saved = excel_serial_to_datetime(str(r.get("Original sparad UTC") or "").replace(" UTC", ""))
            if saved is not None:
                saved = saved.replace(tzinfo=UTC)
                eligible = str(r.get("Pre-match behörig?") or "").upper().startswith("JA")
                self._legacy_snapshot(mid, "LEGACY-ORIG", created=saved, cutoff=saved, kickoff=ko, eligible=eligible,
                                      probs=(r.get("Original P(1)"), r.get("Original P(X)"), r.get("Original P(2)")),
                                      counts={"goals": (r.get("Original mål H"), r.get("Original mål B")),
                                              "corners": (r.get("Original hörn H"), r.get("Original hörn B")),
                                              "shots": (r.get("Original skott H"), r.get("Original skott B")),
                                              "sot": (r.get("Original SOT H"), r.get("Original SOT B"))},
                                      note=str(r.get("Tidsstatus / källa") or ""), key=f"orig:{uefa_id}")
                c["legacy_original"] += 1
            v2_cut = excel_serial_to_datetime(r.get("V2 datagräns"))
            if v2_cut is not None and r.get("V2 P(1)") is not None:
                v2_created = excel_serial_to_datetime(str(r.get("V2 beräknad") or "")[:10]) or v2_cut
                self._legacy_snapshot(mid, "LEGACY-V2", created=v2_created.replace(tzinfo=UTC),
                                      cutoff=(v2_cut + timedelta(hours=23, minutes=59, seconds=59)).replace(tzinfo=UTC),
                                      kickoff=ko, eligible=False,
                                      probs=(r.get("V2 P(1)"), r.get("V2 P(X)"), r.get("V2 P(2)")),
                                      counts={"goals": (r.get("V2 mål H"), r.get("V2 mål B")),
                                              "corners": (r.get("V2 hörn H"), r.get("V2 hörn B")),
                                              "shots": (r.get("V2 skott H"), r.get("V2 skott B")),
                                              "sot": (r.get("V2 SOT H"), r.get("V2 SOT B"))},
                                      note="Retrospektiv V2 (beräknad efter avspark, CL-data t.o.m. 12 okt) – "
                                           "ej behörig för förmatchsutvärdering", key=f"v2:{uefa_id}")
                c["legacy_v2"] += 1
            if r.get("Utfall mål H") is not None:
                self._outcome(mid, r, "Utfall mål H", "Utfall mål B", "Utfall hörn H", "Utfall hörn B",
                              "Utfall skott H", "Utfall skott B", "Utfall SOT H", "Utfall SOT B", "uefa")
                c["outcomes"] += 1

    def _outcome(self, mid: int, r: dict, hg: str, ag: str, hc: str, ac: str, hs: str, as_: str, hst: str,
                 ast: str, source: str) -> None:
        with self.db.tx() as cx:
            cx.execute("""INSERT INTO match_outcomes (match_id, home_goals, away_goals, home_corners, away_corners,
                home_shots, away_shots, home_sot, away_sot, source_id, entered_by, recorded_at_utc, note)
                VALUES (?,?,?,?,?,?,?,?,?,?,'import',?,?)
                ON CONFLICT(match_id) DO NOTHING""",
                       (mid, _int(r.get(hg)), _int(r.get(ag)), _int(r.get(hc)), _int(r.get(ac)), _int(r.get(hs)),
                        _int(r.get(as_)), _int(r.get(hst)), _int(r.get(ast)), source,
                        to_iso(self.app.clock.now()), "Importerat från arbetsbokens prognoslogg"))

    def _legacy_snapshot(self, match_id: int, model: str, *, created: datetime, cutoff: datetime, kickoff: datetime,
                         eligible: bool, probs: tuple, counts: dict, note: str, key: str,
                         intervals: dict | None = None, extra: dict | None = None) -> None:
        """Importera en fryst prognos. Deterministiskt ID gör importen idempotent."""
        sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"matchiq-legacy:{model}:{match_id}:{key}"))
        if self.db.one("SELECT 1 FROM forecast_snapshots WHERE id=?", (sid,)):
            self.counts["legacy"]["snapshot_unchanged"] += 1
            return
        p = [_float(x) for x in probs]
        if any(x is None for x in p):
            p_norm = [None, None, None]
        else:
            s = sum(p)  # type: ignore[arg-type]
            p_norm = [x / s for x in p]  # type: ignore[operator]
            p_norm[2] = 1.0 - p_norm[0] - p_norm[1]
        vals = {k: (_float(v[0]), _float(v[1])) for k, v in counts.items()}
        payload = {"source": "workbook_legacy", "note": note, "intervals": intervals or {}, "imported": True,
                   "import_id": self.import_id, **(extra or {})}
        mins = (kickoff - created).total_seconds() / 60
        with self.db.tx() as cx:
            cx.execute("""INSERT INTO forecast_snapshots (id, match_id, model_version_id, model_family, kind,
                scheduled_for_utc, created_at_utc, data_cutoff_utc, kickoff_utc_at_creation, minutes_before_kickoff,
                is_late, prematch_eligible, clock, created_by, p_home, p_draw, p_away, goals_home, goals_away,
                corners_home, corners_away, shots_home, shots_away, sot_home, sot_away, payload_json, inputs_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (sid, match_id, model, "LEGACY", "legacy", None, to_iso(created), to_iso(cutoff),
                        to_iso(kickoff), mins, 0, 1 if (eligible and mins > 0) else 0, "system", "import",
                        p_norm[0], p_norm[1], p_norm[2], vals["goals"][0], vals["goals"][1], vals["corners"][0],
                        vals["corners"][1], vals["shots"][0], vals["shots"][1], vals["sot"][0], vals["sot"][1],
                        json.dumps(payload, ensure_ascii=False), f"legacy:{key}"))
        self.counts["legacy"]["snapshot_inserted"] += 1

    # ---------------------------------------------------------- ELVOR (13 okt)
    def _lineups_md2_day1(self, t: Table, tables: dict) -> None:
        c = self.counts["elvor_13okt"]
        groups: dict[tuple, list[dict]] = defaultdict(list)
        meta: dict[tuple, dict] = {}
        for r in t.records():
            if not r.get("Match-ID") or not r.get("Namn"):
                continue
            key = (str(r["Match-ID"]), str(r["Klubb"]))
            groups[key].append({"name": str(r["Namn"]).strip(), "number": None,
                                "position": _s(r.get("Position")), "is_starter": True,
                                "slot": _int(r.get("Startplats"))})
            meta[key] = r
        for (wb_id, club), players in groups.items():
            mid = self.match_by_source("workbook_legacy", wb_id)
            if mid is None:
                self.warnings.append(f"ELVOR: okänt match-ID {wb_id}")
                continue
            r = meta[(wb_id, club)]
            m = self.db.one("SELECT home_team_id, away_team_id FROM matches WHERE id=?", (mid,))
            team_id = m["home_team_id"] if str(r.get("Hemma/borta")).lower().startswith("hem") else m["away_team_id"]
            fetched = excel_serial_to_datetime(r.get("Kontrollerad tid UTC"))
            players.sort(key=lambda p: p.get("slot") or 99)
            res = self.repo.upsert_lineup(mid, team_id, "uefa", "confirmed", players,
                                          fetched_at=fetched.replace(tzinfo=UTC) if fetched else self.app.clock.now(),
                                          source_url=_s(r.get("Källa")), import_id=self.import_id)
            c[res] += 1

    # ------------------------------------------------------------ MD2 (14 okt)
    def _md2_shadow(self, t: Table, tables: dict) -> None:
        c = self.counts["md2"]
        # rubrikraden ligger längre ned i bladet – läs om med rätt rubrikrad
        raw = _reheader(t, "Match-ID")
        if raw is None:
            self.warnings.append("MD2 SKUGGTEST: hittade ingen rubrikrad")
            return
        for r in raw.records():
            wid = r.get("Match-ID")
            if not wid or not str(wid).startswith("MD2-"):
                continue
            d = excel_serial_to_datetime(r.get("Datum"))
            hhmm = str(r.get("Avspark Sverige") or "21:00")
            hh, mm = (int(x) for x in hhmm.split(":")[:2])
            ko = local_to_utc(d.replace(hour=hh, minute=mm))  # type: ignore[union-attr]
            home = self.team(str(r["Hemmalag"]), "workbook_legacy")
            away = self.team(str(r["Bortalag"]), "workbook_legacy")
            mid, action = self.repo.upsert_match(competition_code="UCL", kickoff_utc=ko, home_team_id=home,
                                                 away_team_id=away, source_id="workbook_legacy", status="scheduled",
                                                 season_label=_cl_season_for(ko), source_match_id=str(wid),
                                                 matchday="MD2", stage="LEAGUE_PHASE", import_id=self.import_id)
            c[f"match_{action}"] += 1
            locked = r.get("Prognos låst UTC")
            cutoff = r.get("Historikgräns UTC") or locked
            if isinstance(locked, datetime):
                locked = locked.replace(tzinfo=UTC)
                cutoff = cutoff.replace(tzinfo=UTC) if isinstance(cutoff, datetime) else locked
                common = dict(created=locked, cutoff=cutoff, kickoff=ko, eligible=True)
                self._legacy_snapshot(mid, "LEGACY-V2", **common,
                                      probs=(r.get("V2 P(1)"), r.get("V2 P(X)"), r.get("V2 P(2)")),
                                      counts={"goals": (r.get("V2 mål H"), r.get("V2 mål B")),
                                              "corners": (r.get("V2 hörnor H"), r.get("V2 hörnor B")),
                                              "shots": (r.get("V2 skott H"), r.get("V2 skott B")),
                                              "sot": (r.get("V2 SOT H"), r.get("V2 SOT B"))},
                                      note=f"MD2 skuggtest, låst {locked:%Y-%m-%d %H:%M} UTC ({r.get('V2 version')})",
                                      key=f"md2:{wid}",
                                      extra={"lineup_status": str(r.get("Officiell startelva?") or ""),
                                             "team_news": str(r.get("Skador, tveksamheter och avstängningar") or "")})
                self._legacy_snapshot(mid, "LEGACY-V3", **common,
                                      probs=(r.get("V3 P(1)"), r.get("V3 P(X)"), r.get("V3 P(2)")),
                                      counts={"goals": (r.get("V3 mål H"), r.get("V3 mål B")),
                                              "corners": (r.get("V3 hörnor H"), r.get("V3 hörnor B")),
                                              "shots": (r.get("V3 skott H"), r.get("V3 skott B")),
                                              "sot": (r.get("V3 SOT H"), r.get("V3 SOT B"))},
                                      intervals={"goals_home": [_float(r.get("V3 mål P10 H")),
                                                                _float(r.get("V3 mål P90 H"))],
                                                 "goals_away": [_float(r.get("V3 mål P10 B")),
                                                                _float(r.get("V3 mål P90 B"))]},
                                      note=f"MD2 skuggtest, låst {locked:%Y-%m-%d %H:%M} UTC ({r.get('V3 version')}) – "
                                           "V3 var ej kalibrerad", key=f"md2:{wid}")
                c["snapshots"] += 2
            news = str(r.get("Skador, tveksamheter och avstängningar") or "")
            if news:
                self._team_news(mid, home, away, news, fetched=locked if isinstance(locked, datetime) else ko)
            if r.get("Faktiskt mål H") is not None:
                self._outcome(mid, r, "Faktiskt mål H", "Faktiskt mål B", "Faktiskt hörn H", "Faktiskt hörn B",
                              "Faktiskt skott H", "Faktiskt skott B", "Faktiskt SOT H", "Faktiskt SOT B", "manual")

    def _team_news(self, match_id: int, home: int, away: int, text: str, fetched: datetime) -> None:
        """Tolka UEFA:s lagnyheter ('Lag: A, B ute; C tveksam.') till frånvaroposter."""
        names = {home: self.db.one("SELECT name FROM teams WHERE id=?", (home,))["name"],
                 away: self.db.one("SELECT name FROM teams WHERE id=?", (away,))["name"]}
        for seg in re.split(r"\.\s+|\.$", text):
            if ":" not in seg:
                continue
            team_txt, rest = seg.split(":", 1)
            tn = normalize_name(team_txt)
            cands = [tid for tid, nm in names.items() if tn and (tn in normalize_name(nm) or normalize_name(nm) in tn)]
            if len(cands) != 1:
                continue
            team_id = cands[0]
            for part in rest.split(";"):
                part = part.strip()
                kind = None
                low = part.lower()
                if low.endswith(" ute"):
                    kind, part = "injury", part[:-4]
                elif low.endswith("avstängd") or low.endswith("avstängda"):
                    kind, part = "suspension", re.sub(r"\s+avstängda?$", "", part)
                elif low.endswith("tveksam") or low.endswith("tveksamma"):
                    kind, part = "doubtful", re.sub(r"\s+tveksamma?$", "", part)
                if kind is None or "inga frånvarande" in low:
                    continue
                for nm in re.split(r",\s*|\s+och\s+", part):
                    nm = nm.strip()
                    if nm:
                        self.repo.add_availability(match_id=match_id, team_id=team_id, player_name=nm, kind=kind,
                                                   reason="UEFA lagnyheter (via arbetsbok)", source_id="uefa",
                                                   fetched_at=fetched)
                        self.counts["md2"]["availability"] += 1

    def _md2_expected_xi(self, t: Table, tables: dict) -> None:
        raw = _reheader(t, "Match-ID")
        if raw is None:
            return
        groups: dict[tuple, list[dict]] = defaultdict(list)
        meta = {}
        for r in raw.records():
            if not str(r.get("Match-ID") or "").startswith("MD2-") or not r.get("Spelare"):
                continue
            key = (str(r["Match-ID"]), str(r["H/B"]))
            groups[key].append({"name": str(r["Spelare"]).strip(), "position": None, "number": None,
                                "is_starter": True, "slot": _int(r.get("XI-ordning"))})
            meta[key] = r
        for (wid, hb), players in groups.items():
            mid = self.match_by_source("workbook_legacy", wid)
            if mid is None:
                continue
            m = self.db.one("SELECT home_team_id, away_team_id, kickoff_utc FROM matches WHERE id=?", (mid,))
            team_id = m["home_team_id"] if hb.lower().startswith("hem") else m["away_team_id"]
            players.sort(key=lambda p: p.get("slot") or 99)
            # förväntad elva sågs senast vid grundsnapshot (14 okt 16:02 UTC)
            fetched = datetime(2026, 10, 14, 16, 2, 43, tzinfo=UTC)
            res = self.repo.upsert_lineup(mid, team_id, "uefa", "expected", players, fetched_at=fetched,
                                          source_url=_s(meta[(wid, hb)].get("Laguppställningskälla")),
                                          import_id=self.import_id)
            self.counts["md2_forvantade_elvor"][res] += 1

    def _md2_confirmed_xi(self, t: Table, tables: dict) -> None:
        raw = _reheader(t, "Match-ID")
        if raw is None:
            return
        groups: dict[tuple, list[dict]] = defaultdict(list)
        meta = {}
        for r in raw.records():
            if not str(r.get("Match-ID") or "").startswith("MD2-") or not r.get("Spelare"):
                continue
            key = (str(r["Match-ID"]), str(r["Lag"]))
            groups[key].append({"name": str(r["Spelare"]).strip(), "number": _int(r.get("Tröjnummer")),
                                "position": None, "is_starter": True})
            meta[key] = r
        fetched = datetime(2026, 10, 14, 18, 33, 23, tzinfo=STOCKHOLM).astimezone(UTC)
        for (wid, club), players in groups.items():
            mid = self.match_by_source("workbook_legacy", wid)
            if mid is None:
                continue
            m = self.db.one("SELECT home_team_id, away_team_id FROM matches WHERE id=?", (mid,))
            tid = self.team(club, "workbook_legacy")
            if tid not in (m["home_team_id"], m["away_team_id"]):
                self.warnings.append(f"MD2 STARTELVOR: laget {club} hör inte till match {wid}")
                continue
            r = meta[(wid, club)]
            # Elvan kommer från tredjepartsflöden (lineup feed/FotMob/Guardian) – ursprung 'user_file'.
            res = self.repo.upsert_lineup(mid, tid, "user_file", "confirmed", players, fetched_at=fetched,
                                          formation=_s(r.get("Formation")), source_url=_s(r.get("Källa startelva")),
                                          import_id=self.import_id)
            self.counts["md2_bekraftade_elvor"][res] += 1

    # ------------------------------------------------------------ MD3-schema
    def _md3_fixtures(self, t: Table, tables: dict) -> None:
        c = self.counts["md3"]
        raw = _reheader(t, "Match-ID")
        if raw is None:
            return
        seen = set()
        for r in raw.records():
            wid = r.get("Match-ID")
            if not wid or not str(wid).startswith("MD3-") or wid in seen:
                continue
            seen.add(wid)
            d = excel_serial_to_datetime(r.get("Matchdatum"))
            hhmm = str(r.get("Avspark UEFA") or "21:00")
            hh, mm = (int(x) for x in hhmm.split(":")[:2])
            ko = local_to_utc(d.replace(hour=hh, minute=mm))  # type: ignore[union-attr]
            home = self.team(str(r["Hemmalag"]), "workbook_legacy")
            away = self.team(str(r["Bortalag"]), "workbook_legacy")
            mid, action = self.repo.upsert_match(competition_code="UCL", kickoff_utc=ko, home_team_id=home,
                                                 away_team_id=away, source_id="workbook_legacy", status="scheduled",
                                                 season_label=_cl_season_for(ko), source_match_id=str(wid),
                                                 matchday="MD3", stage="LEAGUE_PHASE", import_id=self.import_id)
            c[f"match_{action}"] += 1


def _s(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _reheader(t: Table, first_col: str) -> Table | None:
    """Vissa blad har förklaringstext överst. Hitta raden där första kolumnen heter first_col."""
    if t.columns and t.columns[0] == first_col:
        return t
    for i, row in enumerate(t.rows):
        if row and row[0] == first_col:
            cols = [str(c) if c is not None else f"Kolumn {j + 1}" for j, c in enumerate(row)]
            seen: Counter = Counter()
            uniq = []
            for col in cols:
                seen[col] += 1
                uniq.append(col if seen[col] == 1 else f"{col} ({seen[col]})")
            width = max((j for j, c in enumerate(row) if c is not None), default=0) + 1
            return Table(t.name, t.header_row + i + 1, uniq[:width], [r[:width] for r in t.rows[i + 1:]])
    return None


def import_workbook(app: App, path: Path, progress=None, original_name: str | None = None) -> dict:
    return WorkbookImporter(app, progress).run(path, original_name=original_name)


def preview_workbook(path: Path) -> dict:
    tables = {t.name: t for t in read_xlsx(path)}
    return {"profile": PROFILE_ID, "detected": detect(list(tables)), "sha256": file_sha256(path),
            "inventory": verify_inventory(tables)}
