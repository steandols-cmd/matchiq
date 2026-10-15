"""Generisk import av Excel/CSV via en mappning som användaren granskar i mappningsvyn.

Flöde: inspect (blad, kolumner, radantal, saknade värden, dubbletter) → preview (tolkade rader,
nya lag, om matchen skulle skapas/uppdateras, fel per rad) → run (skriver, spårbart och idempotent).
Originalfilen ändras aldrig – en kopia sparas i datamappen.
"""
from __future__ import annotations

import json
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..core import App
from ..timeutil import UTC, to_iso
from .reader import excel_serial_to_datetime, inspect_tables, read_any, stash_copy
from . import workbook_ucl

TARGETS = {
    "matches": {
        "label": "Matcher och resultat (+ valfri lagstatistik)",
        "required": ["date", "home", "away"],
        "optional": ["time", "competition", "season", "home_goals", "away_goals", "home_goals_ht", "away_goals_ht",
                     "home_shots", "away_shots", "home_sot", "away_sot", "home_corners", "away_corners",
                     "home_xg", "away_xg", "match_id", "status"],
    },
    "lineups": {
        "label": "Startelvor (en rad per spelare)",
        "required": ["date", "home", "away", "team", "player"],
        "optional": ["competition", "number", "position", "status", "published_at", "fetched_at"],
    },
    "odds": {
        "label": "1X2-odds",
        "required": ["date", "home", "away", "bookmaker", "odds_home", "odds_draw", "odds_away"],
        "optional": ["competition", "kind", "published_at", "fetched_at"],
    },
}
FIELD_LABELS = {
    "date": "Datum", "time": "Avsparkstid (lokal)", "home": "Hemmalag", "away": "Bortalag",
    "competition": "Tävlingskod (kolumn)", "season": "Säsong", "home_goals": "Mål hemma (90 min)",
    "away_goals": "Mål borta (90 min)", "home_goals_ht": "Halvtid hemma", "away_goals_ht": "Halvtid borta",
    "home_shots": "Skott hemma", "away_shots": "Skott borta", "home_sot": "Skott på mål hemma",
    "away_sot": "Skott på mål borta", "home_corners": "Hörnor hemma", "away_corners": "Hörnor borta",
    "home_xg": "xG hemma", "away_xg": "xG borta", "match_id": "Källans match-ID", "status": "Status",
    "team": "Lag", "player": "Spelare", "number": "Tröjnummer", "position": "Position",
    "published_at": "Publicerad (UTC)", "fetched_at": "Hämtad (UTC)", "bookmaker": "Spelbolag",
    "odds_home": "Odds 1", "odds_draw": "Odds X", "odds_away": "Odds 2", "kind": "Oddstyp",
}


def inspect_file(app: App, path: Path, original_name: str | None = None) -> dict:
    stored, digest = stash_copy(path, app.paths.imports)
    tables = read_any(stored)
    sheets = inspect_tables(tables)
    profile = None
    if stored.suffix.lower() in (".xlsx", ".xlsm") and workbook_ucl.detect([t.name for t in tables]):
        tmap = {t.name: t for t in tables}
        profile = {"id": workbook_ucl.PROFILE_ID, "label": "Tidigare UCL-arbetsbok (känd profil)",
                   "inventory": workbook_ucl.verify_inventory(tmap)}
    dup_db = app.db.one("SELECT id, finished_at_utc, status FROM imports WHERE file_sha256=? AND status='done' "
                        "ORDER BY id DESC LIMIT 1", (digest,))
    return {"file": original_name or path.name, "stored_copy": str(stored), "sha256": digest,
            "bytes": stored.stat().st_size, "sheets": sheets, "profile": profile,
            "previously_imported": dict(dup_db) if dup_db else None,
            "targets": {k: {**v, "labels": {f: FIELD_LABELS[f] for f in v["required"] + v["optional"]}}
                        for k, v in TARGETS.items()}}


def _val(rec: dict, mapping: dict, field: str) -> Any:
    col = mapping.get(field)
    if col is None or col == "":
        return None
    if isinstance(col, dict) and "const" in col:
        return col["const"]
    v = rec.get(col)
    if isinstance(v, str):
        v = v.strip()
        if v == "" or v == "-":
            return None
    return v


def _int(v):
    if v is None:
        return None
    try:
        return int(round(float(str(v).replace(",", "."))))
    except ValueError:
        return None


def _float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _kickoff(rec: dict, mapping: dict, tz: ZoneInfo) -> tuple[datetime | None, bool]:
    d = excel_serial_to_datetime(_val(rec, mapping, "date"))
    if d is None:
        return None, False
    t = _val(rec, mapping, "time")
    known = False
    if isinstance(t, datetime):
        d = d.replace(hour=t.hour, minute=t.minute)
        known = True
    elif isinstance(t, dtime):
        d = d.replace(hour=t.hour, minute=t.minute)
        known = True
    elif isinstance(t, str) and ":" in t:
        hh, mm = t.split(":")[:2]
        d = d.replace(hour=int(hh), minute=int(mm[:2]))
        known = True
    elif isinstance(t, (int, float)) and 0 <= float(t) < 1:  # Excel-tid som bråkdel av dygn
        mins = round(float(t) * 1440)
        d = d.replace(hour=mins // 60, minute=mins % 60)
        known = True
    elif d.hour or d.minute:
        known = True
    if not known:
        d = d.replace(hour=12, minute=0)
    return d.replace(tzinfo=tz).astimezone(UTC), known


def _plan(app: App, path: Path, sheet: str | None, header_row: int | None, target: str, mapping: dict,
          options: dict, limit: int | None = None) -> tuple[list[dict], dict]:
    tables = read_any(path, sheet, header_row)
    if not tables:
        raise ValueError("Bladet hittades inte")
    t = tables[0]
    spec = TARGETS[target]
    missing = [f for f in spec["required"] if not mapping.get(f)]
    if missing:
        raise ValueError("Obligatoriska fält saknar mappning: " + ", ".join(FIELD_LABELS[f] for f in missing))
    tz = ZoneInfo(options.get("timezone") or "Europe/Stockholm")
    comp_default = options.get("competition")
    source_id = options.get("source_id") or "user_file"
    rows = []
    stats = {"rows": 0, "ok": 0, "errors": 0, "new_teams": set(), "duplicate_keys": 0}
    seen_keys = set()
    for i, rec in enumerate(t.records()):
        if limit is not None and i >= limit:
            break
        stats["rows"] += 1
        err = []
        ko, known = _kickoff(rec, mapping, tz)
        comp = _val(rec, mapping, "competition") or comp_default
        home, away = _val(rec, mapping, "home"), _val(rec, mapping, "away")
        if ko is None:
            err.append("datum saknas/okänt format")
        if not comp:
            err.append("tävling saknas")
        elif app.db.one("SELECT 1 FROM competitions WHERE code=?", (str(comp),)) is None:
            err.append(f"okänd tävlingskod {comp}")
        if not home or not away:
            err.append("lagnamn saknas")
        hid = app.repo.find_team(str(home), source_id, str(comp or "")) if home else None
        aid = app.repo.find_team(str(away), source_id, str(comp or "")) if away else None
        for nm, tid in ((home, hid), (away, aid)):
            if nm and tid is None:
                stats["new_teams"].add(str(nm))
        key = (str(comp), ko.date().isoformat() if ko else None, str(home), str(away))
        if target == "matches":
            if key in seen_keys:
                stats["duplicate_keys"] += 1
            seen_keys.add(key)
        exists = None
        if hid and aid and ko and comp:
            from ..timeutil import local_date
            exists = app.db.one("SELECT id FROM matches WHERE natural_key=?",
                                (f"{comp}|{local_date(ko)}|{hid}|{aid}",))
        row = {"row": i + t.header_row + 1, "kickoff_utc": to_iso(ko) if ko else None, "time_known": known,
               "competition": comp, "home": home, "away": away, "home_team_id": hid, "away_team_id": aid,
               "match_exists": bool(exists), "errors": err, "rec": rec}
        if target == "matches":
            row["values"] = {f: _val(rec, mapping, f) for f in spec["optional"] if mapping.get(f)}
        elif target == "lineups":
            row["values"] = {f: _val(rec, mapping, f) for f in ("team", "player", "number", "position", "status",
                                                                  "published_at", "fetched_at")}
        else:
            row["values"] = {f: _val(rec, mapping, f) for f in ("bookmaker", "odds_home", "odds_draw", "odds_away",
                                                                  "kind", "published_at", "fetched_at")}
        stats["errors" if err else "ok"] += 1
        rows.append(row)
    stats["new_teams"] = sorted(stats["new_teams"])
    return rows, stats


def preview(app: App, path: Path, sheet: str | None, header_row: int | None, target: str, mapping: dict,
            options: dict, limit: int = 50) -> dict:
    rows, stats = _plan(app, path, sheet, header_row, target, mapping, options, limit=None)
    sample = [{k: v for k, v in r.items() if k != "rec"} for r in rows[:limit]]
    for s in sample:
        s["values"] = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in s["values"].items()}
    return {"stats": stats, "sample": sample, "would_create_matches": sum(1 for r in rows if not r["match_exists"]
                                                                          and not r["errors"]),
            "would_update_matches": sum(1 for r in rows if r["match_exists"] and not r["errors"])}


def run(app: App, path: Path, sheet: str | None, header_row: int | None, target: str, mapping: dict,
        options: dict, original_name: str | None = None) -> dict:
    stored, digest = stash_copy(path, app.paths.imports)
    source_id = options.get("source_id") or "user_file"
    if app.db.one("SELECT 1 FROM sources WHERE id=?", (source_id,)) is None:
        raise ValueError(f"Okänd källa {source_id}")
    cur = app.db.execute("""INSERT INTO imports (file_name, file_sha256, file_bytes, stored_copy_path, profile,
        mapping_json, started_at_utc, status) VALUES (?,?,?,?,?,?,?, 'running')""",
                         (original_name or path.name, digest, stored.stat().st_size, str(stored), f"generic:{target}",
                          json.dumps({"sheet": sheet, "header_row": header_row, "mapping": mapping,
                                      "options": options}, ensure_ascii=False), to_iso(app.clock.now())))
    import_id = int(cur.lastrowid)
    rows, stats = _plan(app, stored, sheet, header_row, target, mapping, options)
    counts: dict[str, int] = {}

    def inc(k):
        counts[k] = counts.get(k, 0) + 1

    with app.db.tx():
        for r in rows:
            if r["errors"]:
                inc("rad_fel")
                continue
            ko = datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
            comp = str(r["competition"])
            h = app.repo.resolve_team(str(r["home"]), source_id, context=comp)
            a = app.repo.resolve_team(str(r["away"]), source_id, context=comp)
            if h == a:
                inc("rad_fel")
                continue
            v = r["values"]
            if target == "matches":
                hg, ag = _int(v.get("home_goals")), _int(v.get("away_goals"))
                mid, act = app.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=h,
                                                 away_team_id=a, source_id=source_id,
                                                 status="finished" if hg is not None and ag is not None else "scheduled",
                                                 season_label=str(v["season"]) if v.get("season") else None,
                                                 source_match_id=str(v["match_id"]) if v.get("match_id") else None,
                                                 kickoff_time_known=r["time_known"], import_id=import_id)
                inc(f"match_{act}")
                if hg is not None and ag is not None:
                    inc("result_" + app.repo.upsert_result(mid, source_id, {
                        "home_goals_90": hg, "away_goals_90": ag, "home_goals_ht": _int(v.get("home_goals_ht")),
                        "away_goals_ht": _int(v.get("away_goals_ht"))}, original_home=str(r["home"]),
                        original_away=str(r["away"]), import_id=import_id))
                for is_home, tid, p in ((True, h, "home"), (False, a, "away")):
                    st = {"shots": _int(v.get(f"{p}_shots")), "shots_on_target": _int(v.get(f"{p}_sot")),
                          "corners": _int(v.get(f"{p}_corners")), "xg": _float(v.get(f"{p}_xg"))}
                    if any(x is not None for x in st.values()):
                        inc("teamstats_" + app.repo.upsert_team_stats(mid, tid, is_home, source_id, st,
                                                                      import_id=import_id))
            elif target == "lineups":
                inc("lineup_rows")
            else:
                mid, _ = app.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                               source_id=source_id, status="unknown", import_id=import_id)
                odds = (_float(v.get("odds_home")), _float(v.get("odds_draw")), _float(v.get("odds_away")))
                if None in odds:
                    inc("odds_incomplete")
                    continue
                fetched = excel_serial_to_datetime(v.get("fetched_at"))
                inc("odds_" + app.repo.add_odds(match_id=mid, source_id=source_id, bookmaker=str(v["bookmaker"]),
                                                kind=str(v.get("kind") or "snapshot"), odds=odds,
                                                fetched_at=fetched.replace(tzinfo=UTC) if fetched else app.clock.now()))
        if target == "lineups":
            _store_lineups(app, rows, source_id, import_id, counts)
    summary = {"profile": f"generic:{target}", "counts": counts, "stats": {**stats, "new_teams": stats["new_teams"]}}
    app.db.execute("UPDATE imports SET status='done', finished_at_utc=?, summary_json=? WHERE id=?",
                   (to_iso(app.clock.now()), json.dumps(summary, ensure_ascii=False, default=str), import_id))
    return {"import_id": import_id, **summary}


def _store_lineups(app: App, rows: list[dict], source_id: str, import_id: int, counts: dict) -> None:
    groups: dict[tuple, list] = {}
    meta: dict[tuple, dict] = {}
    for r in rows:
        if r["errors"]:
            continue
        ko = datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
        comp = str(r["competition"])
        h = app.repo.resolve_team(str(r["home"]), source_id, context=comp)
        a = app.repo.resolve_team(str(r["away"]), source_id, context=comp)
        mid, _ = app.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                       source_id=source_id, status="unknown", import_id=import_id)
        team = app.repo.find_team(str(r["values"]["team"]), source_id, comp)
        if team not in (h, a):
            counts["lineup_team_mismatch"] = counts.get("lineup_team_mismatch", 0) + 1
            continue
        st = str(r["values"].get("status") or "confirmed").lower()
        status = "expected" if st.startswith(("exp", "förv", "forv", "obek")) else "confirmed"
        key = (mid, team, status)
        groups.setdefault(key, []).append({"name": str(r["values"]["player"]), "number": _int(r["values"].get("number")),
                                           "position": r["values"].get("position"), "is_starter": True})
        meta[key] = r["values"]
    for (mid, team, status), players in groups.items():
        fetched = excel_serial_to_datetime(meta[(mid, team, status)].get("fetched_at"))
        res = app.repo.upsert_lineup(mid, team, source_id, status, players,
                                     fetched_at=fetched.replace(tzinfo=UTC) if fetched else app.clock.now(),
                                     import_id=import_id)
        counts[f"lineup_{res}"] = counts.get(f"lineup_{res}", 0) + 1
    _ = timedelta
