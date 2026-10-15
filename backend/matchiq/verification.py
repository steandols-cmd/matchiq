"""Verifiering mellan källor: samma match jämförs över alla källor som har värden för den.

* Resultat (90 min), hörnor, skott och skott på mål jämförs som par (hemma, borta) per källa.
* Startelvor jämförs på tröjnummer när båda källorna har nummer, annars på efternamn.
* Status per del: ``bekraftad`` (minst två källor och alla lika), ``avvikelse`` (källorna skiljer sig),
  ``en_kalla`` (bara en källa har värdet) eller ``saknas``. Matchens status är den sämsta delens.
* Ingenting räknas om eller justeras: avvikelser visas med varje källas värde så att du kan avgöra vilket
  som stämmer (t.ex. med Eftermatch). Nya avvikelser aviseras en gång per match.
"""
from __future__ import annotations

import unicodedata
from datetime import timedelta

from .core import App
from .timeutil import to_iso

METRICS = [("result", "Resultat"), ("corners", "Hörnor"), ("shots", "Skott"), ("sot", "Skott på mål"),
           ("lineups", "Startelvor")]
RANK = {"avvikelse": 3, "en_kalla": 2, "bekraftad": 1, "saknas": 0}
STATUS_LABEL = {"bekraftad": "Bekräftad", "avvikelse": "Avvikelse", "en_kalla": "En källa", "saknas": "Saknas"}
STAT_COL = {"corners": "corners", "shots": "shots", "sot": "shots_on_target"}
SHORT = {"uefa": "UEFA (din import)", "api_football": "API-Football", "openfootball": "OpenFootball",
         "football_data_org": "football-data.org", "football_data_couk": "Football-Data.co.uk", "manual": "Eftermatch",
         "statsbomb_open": "StatsBomb", "wyscout_public": "Wyscout"}


def _surname(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    parts = [p for p in s.replace("-", " ").replace(".", " ").split() if p]
    return parts[-1] if parts else ""


def _pair_status(values: dict[str, tuple]) -> str:
    vals = {k: v for k, v in values.items() if v is not None and None not in v}
    if not vals:
        return "saknas"
    if len(set(vals.values())) > 1:
        return "avvikelse"
    return "bekraftad" if len(vals) >= 2 else "en_kalla"


def _lineup_compare(a: list[dict], b: list[dict]) -> int:
    """Antal startspelare i ``a`` som inte finns i ``b`` (nummer om båda har nummer, annars efternamn)."""
    if all(p["number"] is not None for p in a + b):
        return len({p["number"] for p in a} - {p["number"] for p in b})
    return len({_surname(p["name"]) for p in a} - {_surname(p["name"]) for p in b})


def _names(app: App) -> dict[str, str]:
    return {r["id"]: SHORT.get(r["id"], r["name"]) for r in app.db.query("SELECT id, name FROM sources")}


def verify_match(app: App, match_id: int, names: dict[str, str] | None = None) -> dict:
    m = app.db.one("SELECT home_team_id, away_team_id FROM matches WHERE id=?", (match_id,))
    names = names or _names(app)
    parts: dict[str, dict] = {}
    res = {r["source_id"]: (r["home_goals_90"], r["away_goals_90"]) for r in app.db.query(
        "SELECT source_id, home_goals_90, away_goals_90 FROM match_results WHERE match_id=?", (match_id,))}
    parts["result"] = {"values": res}
    stats: dict[str, dict[str, dict]] = {}
    for r in app.db.query("SELECT * FROM team_match_stats WHERE match_id=?", (match_id,)):
        side = "home" if r["team_id"] == m["home_team_id"] else ("away" if r["team_id"] == m["away_team_id"] else None)
        if side:
            stats.setdefault(r["source_id"], {})[side] = dict(r)
    for key, col in STAT_COL.items():
        parts[key] = {"values": {sid: ((s.get("home") or {}).get(col), (s.get("away") or {}).get(col))
                                 for sid, s in stats.items()}}
    # Ditt eget facit under Eftermatch räknas som en egen källa (automatiskt ifyllda facit räknas inte två gånger)
    mo = app.db.one("SELECT * FROM match_outcomes WHERE match_id=? AND entered_by='manual'", (match_id,))
    if mo:
        res.setdefault("manual", (mo["home_goals"], mo["away_goals"]))
        for key, (hk, ak) in {"corners": ("home_corners", "away_corners"), "shots": ("home_shots", "away_shots"),
                              "sot": ("home_sot", "away_sot")}.items():
            parts[key]["values"].setdefault("manual", (mo[hk], mo[ak]))
    for p in parts.values():
        p["status"] = _pair_status(p["values"])
    # startelvor: senaste bekräftade elva per källa och lag
    lu: dict[str, dict[str, list[dict]]] = {}
    for r in app.db.query("""SELECT l.id, l.source_id, l.team_id FROM lineups l WHERE l.match_id=? AND l.status='confirmed'
            ORDER BY l.fetched_at_utc""", (match_id,)):
        side = "home" if r["team_id"] == m["home_team_id"] else ("away" if r["team_id"] == m["away_team_id"] else None)
        if side:
            lu.setdefault(r["source_id"], {})[side] = [dict(p) for p in app.db.query(
                "SELECT name_original AS name, shirt_number AS number FROM lineup_players "
                "WHERE lineup_id=? AND is_starter=1", (r["id"],))]
    diffs: dict[str, int] = {}
    srcs = sorted(lu)
    for side in ("home", "away"):
        have = [s for s in srcs if side in lu[s]]
        for i, s1 in enumerate(have):
            for s2 in have[i + 1:]:
                diffs[f"{side}:{s1}:{s2}"] = _lineup_compare(lu[s1][side], lu[s2][side])
    if not lu:
        lst = "saknas"
    elif diffs:
        lst = "avvikelse" if any(v > 0 for v in diffs.values()) else "bekraftad"
    else:
        lst = "en_kalla"
    parts["lineups"] = {"status": lst, "sources": srcs, "differences": diffs}
    overall = max((p["status"] for p in parts.values()), key=lambda s: RANK[s])
    out_parts = []
    for key, label in METRICS:
        p = parts[key]
        item = {"key": key, "label": label, "status": p["status"], "status_label": STATUS_LABEL[p["status"]]}
        if key == "lineups":
            item["sources"] = [{"id": s, "name": names.get(s, s)} for s in p["sources"]]
            item["differences"] = [{"side": k.split(":")[0], "a": names.get(k.split(":")[1], k.split(":")[1]),
                                    "b": names.get(k.split(":")[2], k.split(":")[2]), "players": v}
                                   for k, v in p["differences"].items()]
        else:
            item["values"] = [{"source_id": s, "source": names.get(s, s), "home": v[0], "away": v[1]}
                              for s, v in sorted(p["values"].items()) if v is not None and None not in v]
        out_parts.append(item)
    return {"match_id": match_id, "status": overall, "status_label": STATUS_LABEL[overall], "parts": out_parts}


def verify(app: App, *, competition: str | None = None, days: int = 30, only: str | None = None,
           limit: int = 1000) -> dict:
    now = app.clock.now()
    q = """SELECT m.id, m.kickoff_utc, c.code comp, c.name comp_name, h.name home, a.name away FROM matches m
        JOIN competitions c ON c.id=m.competition_id JOIN teams h ON h.id=m.home_team_id
        JOIN teams a ON a.id=m.away_team_id WHERE m.status='finished' AND m.kickoff_utc>=? AND m.kickoff_utc<=?"""
    args: list = [to_iso(now - timedelta(days=days)), to_iso(now)]
    if competition:
        q += " AND c.code=?"
        args.append(competition)
    q += " ORDER BY m.kickoff_utc DESC LIMIT ?"
    args.append(limit)
    names = _names(app)
    rows = []
    counts = {k: 0 for k in STATUS_LABEL}
    for r in app.db.query(q, tuple(args)):
        v = verify_match(app, r["id"], names)
        counts[v["status"]] += 1
        if only and v["status"] != only:
            continue
        rows.append({**dict(r), **v})
    return {"days": days, "competition": competition, "counts": counts, "matches": rows}


def notify_new_discrepancies(app: App, days: int = 7) -> int:
    """Avisera en gång per match när källorna skiljer sig åt (körs efter synken)."""
    n = 0
    for r in verify(app, days=days, only="avvikelse")["matches"]:
        seen = app.db.one("SELECT 1 FROM sync_state WHERE source_id='verification' AND job='_notified' AND scope=?",
                          (str(r["id"]),))
        if seen:
            continue
        bad = [p["label"].lower() for p in r["parts"] if p["status"] == "avvikelse"]
        app.notify(f"Källorna skiljer sig: {r['home']} – {r['away']}",
                   f"Avvikelse i {', '.join(bad)}. Se Data & källor → Verifiering och rätta vid behov under Eftermatch.",
                   level="warning", match_id=r["id"])
        app.db.execute("""INSERT OR IGNORE INTO sync_state (source_id, job, scope, last_run_utc, last_status)
            VALUES ('verification','_notified',?,?,'avvikelse')""", (str(r["id"]), to_iso(app.clock.now())))
        n += 1
    return n
