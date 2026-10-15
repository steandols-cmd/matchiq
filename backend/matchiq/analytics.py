"""Härledda vyer: datatäckning, tabell, lagform, eftermatchsutvärdering av frysta prognoser."""
from __future__ import annotations

import json
from collections import defaultdict

import numpy as np

from .catalog import training_source_ids
from .core import App
from .models.metrics import calibration_bins, outcome_label, summarize_1x2, summarize_counts

METRIC_COLS = {"shots": "shots", "sot": "shots_on_target", "corners": "corners", "xg": "xg"}


def coverage(app: App, comp: str) -> dict:
    """Täckning per säsong och mått: andel avslutade matcher med värde (alla källor) och med träningsbar källa."""
    train = training_source_ids(app.db)
    ph = ",".join("?" * len(train)) or "''"
    seasons = app.db.query("""SELECT COALESCE(s.label,'okänd') AS season, COUNT(*) AS n,
        SUM(m.status='finished') AS finished FROM matches m JOIN competitions c ON c.id=m.competition_id
        LEFT JOIN seasons s ON s.id=m.season_id WHERE c.code=? GROUP BY season ORDER BY season""", (comp,))
    out = []
    for srow in seasons:
        season = srow["season"]
        base = """FROM matches m JOIN competitions c ON c.id=m.competition_id LEFT JOIN seasons s ON s.id=m.season_id
                  WHERE c.code=? AND COALESCE(s.label,'okänd')=? AND m.status='finished'"""
        res_any = app.db.scalar(f"SELECT COUNT(DISTINCT m.id) {base} AND EXISTS (SELECT 1 FROM match_results r "
                                f"WHERE r.match_id=m.id AND r.home_goals_90 IS NOT NULL)", (comp, season))
        res_tr = app.db.scalar(f"SELECT COUNT(DISTINCT m.id) {base} AND EXISTS (SELECT 1 FROM match_results r "
                               f"WHERE r.match_id=m.id AND r.home_goals_90 IS NOT NULL AND r.source_id IN ({ph}))",
                               (comp, season, *train))
        metrics = {"goals": {"any": res_any, "training": res_tr}}
        for m, col in METRIC_COLS.items():
            # en match räknas som täckt om BÅDA lagens värde finns
            q_any = f"""SELECT COUNT(*) FROM (SELECT m.id {base} AND (SELECT COUNT(DISTINCT t.team_id) FROM team_match_stats t
                        WHERE t.match_id=m.id AND t.{col} IS NOT NULL)=2)"""
            q_tr = f"""SELECT COUNT(*) FROM (SELECT m.id {base} AND (SELECT COUNT(DISTINCT t.team_id) FROM team_match_stats t
                        WHERE t.match_id=m.id AND t.{col} IS NOT NULL AND t.source_id IN ({ph}))=2)"""
            metrics[m] = {"any": app.db.scalar(q_any, (comp, season)),
                          "training": app.db.scalar(q_tr, (comp, season, *train))}
        fin = srow["finished"] or 0
        for v in metrics.values():
            v["pct_any"] = (v["any"] / fin) if fin else None
            v["pct_training"] = (v["training"] / fin) if fin else None
            v["missing"] = fin - v["any"]
        out.append({"season": season, "matches": srow["n"], "finished": fin, "metrics": metrics})
    return {"competition": comp, "seasons": out, "training_sources": sorted(train)}


def team_coverage(app: App, comp: str, season: str | None = None) -> list[dict]:
    """Per lag: antal matcher och hur många som har respektive mått – visar ojämn input mellan lag."""
    params: list = [comp]
    sfilter = ""
    if season:
        sfilter = " AND s.label=?"
        params.append(season)
    rows = app.db.query(f"""SELECT t.id, t.name, COUNT(DISTINCT m.id) AS matches,
        COUNT(DISTINCT CASE WHEN st.shots IS NOT NULL THEN m.id END) AS shots,
        COUNT(DISTINCT CASE WHEN st.shots_on_target IS NOT NULL THEN m.id END) AS sot,
        COUNT(DISTINCT CASE WHEN st.corners IS NOT NULL THEN m.id END) AS corners,
        COUNT(DISTINCT CASE WHEN st.xg IS NOT NULL THEN m.id END) AS xg
        FROM matches m JOIN competitions c ON c.id=m.competition_id LEFT JOIN seasons s ON s.id=m.season_id
        JOIN teams t ON t.id IN (m.home_team_id, m.away_team_id)
        LEFT JOIN team_match_stats st ON st.match_id=m.id AND st.team_id=t.id
        WHERE c.code=? AND m.status='finished' {sfilter} GROUP BY t.id ORDER BY matches DESC, t.name""", params)
    return [dict(r) for r in rows]


def standings(app: App, comp: str, season: str | None = None) -> list[dict]:
    if season is None:
        r = app.db.one("""SELECT s.label FROM matches m JOIN competitions c ON c.id=m.competition_id
            JOIN seasons s ON s.id=m.season_id WHERE c.code=? ORDER BY m.kickoff_utc DESC LIMIT 1""", (comp,))
        season = r["label"] if r else None
    rows = app.db.query("""SELECT m.id, m.home_team_id h, m.away_team_id a, r.home_goals_90 hg, r.away_goals_90 ag
        FROM matches m JOIN competitions c ON c.id=m.competition_id JOIN seasons s ON s.id=m.season_id
        JOIN match_results r ON r.id=(SELECT id FROM match_results WHERE match_id=m.id AND home_goals_90 IS NOT NULL
             ORDER BY CASE source_id WHEN 'manual' THEN 0 WHEN 'uefa' THEN 1 ELSE 2 END LIMIT 1)
        WHERE c.code=? AND s.label=? AND m.status='finished'""", (comp, season))
    tab: dict[int, dict] = defaultdict(lambda: {"p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0,
                                                "form": []})
    for r in rows:
        for tid, gf, ga in ((r["h"], r["hg"], r["ag"]), (r["a"], r["ag"], r["hg"])):
            t = tab[tid]
            t["p"] += 1
            t["gf"] += gf
            t["ga"] += ga
            res = "V" if gf > ga else ("O" if gf == ga else "F")
            t["w" if res == "V" else ("d" if res == "O" else "l")] += 1
            t["pts"] += 3 if res == "V" else (1 if res == "O" else 0)
    names = {r["id"]: r["name"] for r in app.db.query("SELECT id, name FROM teams")}
    out = [{"team_id": tid, "team": names.get(tid), **v, "gd": v["gf"] - v["ga"]} for tid, v in tab.items()]
    out.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"], x["team"] or ""))
    for i, r in enumerate(out, 1):
        r["pos"] = i
    return out


def recent_form(app: App, team_id: int, before_utc: str, n: int = 5) -> list[dict]:
    rows = app.db.query("""SELECT m.id, m.kickoff_utc, c.code comp, m.home_team_id, m.away_team_id, h.name home, a.name away,
        r.home_goals_90 hg, r.away_goals_90 ag FROM matches m JOIN competitions c ON c.id=m.competition_id
        JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
        JOIN match_results r ON r.id=(SELECT id FROM match_results WHERE match_id=m.id AND home_goals_90 IS NOT NULL
            ORDER BY CASE source_id WHEN 'manual' THEN 0 WHEN 'uefa' THEN 1 ELSE 2 END LIMIT 1)
        WHERE ? IN (m.home_team_id, m.away_team_id) AND m.kickoff_utc < ? ORDER BY m.kickoff_utc DESC LIMIT ?""",
                        (team_id, before_utc, n))
    out = []
    for r in rows:
        home = r["home_team_id"] == team_id
        gf, ga = (r["hg"], r["ag"]) if home else (r["ag"], r["hg"])
        out.append({"match_id": r["id"], "kickoff_utc": r["kickoff_utc"], "competition": r["comp"],
                    "opponent": r["away"] if home else r["home"], "home": home, "gf": gf, "ga": ga,
                    "result": "V" if gf > ga else ("O" if gf == ga else "F")})
    return out


def team_metric_averages(app: App, team_id: int, before_utc: str, comp: str | None = None, n: int = 10) -> dict:
    """Snitt för/emot per mått över senaste n matcher MED värde (saknade värden räknas inte som 0)."""
    out = {}
    cfilter = " AND c.code=?" if comp else ""
    for metric, col in {"goals": None, **METRIC_COLS}.items():
        if metric == "goals":
            rows = app.db.query(f"""SELECT CASE WHEN m.home_team_id=? THEN r.home_goals_90 ELSE r.away_goals_90 END f,
                CASE WHEN m.home_team_id=? THEN r.away_goals_90 ELSE r.home_goals_90 END a
                FROM matches m JOIN competitions c ON c.id=m.competition_id
                JOIN match_results r ON r.id=(SELECT id FROM match_results WHERE match_id=m.id AND home_goals_90 IS NOT NULL LIMIT 1)
                WHERE ? IN (m.home_team_id, m.away_team_id) AND m.kickoff_utc<? {cfilter}
                ORDER BY m.kickoff_utc DESC LIMIT ?""", (team_id, team_id, team_id, before_utc,
                                                         *([comp] if comp else []), n))
        else:
            rows = app.db.query(f"""SELECT f.{col} f, o.{col} a FROM matches m JOIN competitions c ON c.id=m.competition_id
                JOIN team_match_stats f ON f.match_id=m.id AND f.team_id=?
                JOIN team_match_stats o ON o.match_id=m.id AND o.team_id<>? AND o.source_id=f.source_id
                WHERE ? IN (m.home_team_id, m.away_team_id) AND m.kickoff_utc<? AND f.{col} IS NOT NULL
                AND o.{col} IS NOT NULL {cfilter} GROUP BY m.id ORDER BY m.kickoff_utc DESC LIMIT ?""",
                                (team_id, team_id, team_id, before_utc, *([comp] if comp else []), n))
        vals = [(r["f"], r["a"]) for r in rows if r["f"] is not None]
        out[metric] = {"n": len(vals), "for": float(np.mean([v[0] for v in vals])) if vals else None,
                       "against": float(np.mean([v[1] for v in vals])) if vals else None}
    return out


def prospective_evaluation(app: App, eligible_only: bool = True, competition: str | None = None) -> dict:
    """Utvärdera frysta prognoser mot faktiska utfall (eftermatch). Prognoserna räknas aldrig om."""
    q = """SELECT s.*, o.home_goals ohg, o.away_goals oag, o.home_corners ohc, o.away_corners oac, o.home_shots ohs,
        o.away_shots oas, o.home_sot ohst, o.away_sot oast, o.entered_by, m.kickoff_utc, c.code comp,
        COALESCE(se.label,'') season, h.name home, a.name away, mv.version mv_version
        FROM forecast_snapshots s JOIN match_outcomes o ON o.match_id=s.match_id JOIN matches m ON m.id=s.match_id
        JOIN competitions c ON c.id=m.competition_id LEFT JOIN seasons se ON se.id=m.season_id
        JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
        JOIN model_versions mv ON mv.id=s.model_version_id WHERE s.kind <> 'test'"""
    params: list = []
    if eligible_only:
        q += " AND s.prematch_eligible=1"
    if competition:
        q += " AND c.code=?"
        params.append(competition)
    rows = app.db.query(q + " ORDER BY m.kickoff_utc", params)
    # en prognos per match och modell: den senaste frysta före avspark (T−30 har företräde)
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["match_id"], r["model_version_id"])
        prio = {"T-30": 0, "manual": 1, "legacy": 2, "late": 3}.get(r["kind"], 4)
        if key not in best or prio < best[key]["_prio"] or (prio == best[key]["_prio"] and r["created_at_utc"] >
                                                             best[key]["created_at_utc"]):
            best[key] = {**dict(r), "_prio": prio}
    by_model: dict[str, list] = defaultdict(list)
    for r in best.values():
        by_model[r["model_version_id"]].append(r)
    out = {}
    for model, rs in by_model.items():
        one_x_two = []
        counts = defaultdict(list)
        table = []
        for r in rs:
            if r["ohg"] is None:
                continue
            outcome = outcome_label(r["ohg"], r["oag"])
            payload = json.loads(r["payload_json"])
            mets = (payload.get("model") or {}).get("metrics") or {}
            ivals = payload.get("intervals") or {}
            if r["p_home"] is not None:
                one_x_two.append(((r["p_home"], r["p_draw"], r["p_away"]), outcome))
            row = {"match_id": r["match_id"], "kickoff_utc": r["kickoff_utc"], "home": r["home"], "away": r["away"],
                   "competition": r["comp"], "season": r["season"], "kind": r["kind"],
                   "created_at_utc": r["created_at_utc"], "prematch_eligible": bool(r["prematch_eligible"]),
                   "p": [r["p_home"], r["p_draw"], r["p_away"]], "outcome": outcome,
                   "actual": {"goals": [r["ohg"], r["oag"]], "corners": [r["ohc"], r["oac"]],
                              "shots": [r["ohs"], r["oas"]], "sot": [r["ohst"], r["oast"]]},
                   "pred": {"goals": [r["goals_home"], r["goals_away"]], "corners": [r["corners_home"], r["corners_away"]],
                            "shots": [r["shots_home"], r["shots_away"]], "sot": [r["sot_home"], r["sot_away"]]}}
            for metric, (ph, pa, ah, aa) in {
                    "goals": (r["goals_home"], r["goals_away"], r["ohg"], r["oag"]),
                    "corners": (r["corners_home"], r["corners_away"], r["ohc"], r["oac"]),
                    "shots": (r["shots_home"], r["shots_away"], r["ohs"], r["oas"]),
                    "sot": (r["sot_home"], r["sot_away"], r["ohst"], r["oast"])}.items():
                blk = mets.get(metric) or {}
                lo_h = (blk.get("home") or {}).get("lo")
                hi_h = (blk.get("home") or {}).get("hi")
                lo_a = (blk.get("away") or {}).get("lo")
                hi_a = (blk.get("away") or {}).get("hi")
                if metric == "goals" and lo_h is None and ivals.get("goals_home"):
                    lo_h, hi_h = ivals["goals_home"]
                    lo_a, hi_a = ivals["goals_away"]
                if ph is not None and ah is not None:
                    counts[metric].append((ph, ah, lo_h, hi_h))
                if pa is not None and aa is not None:
                    counts[metric].append((pa, aa, lo_a, hi_a))
            table.append(row)
        series = []
        for row in sorted(table, key=lambda x: x["kickoff_utc"]):
            if row["p"][0] is not None:
                from .models.metrics import brier
                series.append({"date": row["kickoff_utc"][:10],
                               "brier": brier(tuple(row["p"]), row["outcome"])})
        out[model] = {"n_matches": len(table), "1x2": summarize_1x2(one_x_two),
                      "calibration": calibration_bins(one_x_two, 5),
                      **{m: summarize_counts(v) for m, v in counts.items()}, "rows": table, "series": series}
    return out


# ---------------------------------------------------------------------------------------------- driftstatus
METRIC_LABELS = {"goals": "Mål / 1X2", "corners": "Hörnor", "shots": "Skott", "sot": "Skott på mål"}
STAT_COL = {"corners": "corners", "shots": "shots", "sot": "shots_on_target"}
OPERATIVE_MIN = 100   # matcher med värde inom tidsfönstret
LIMITED_MIN = 20      # V2/V3 kräver minst 20 ligamatcher med värde


def _metric_rows(app: App, comp: str, metric: str) -> list:
    """(kickoff, källa) för varje avslutad match i tävlingen som har måttet för BÅDA lagen från en källa."""
    if metric == "goals":
        return app.db.query("""SELECT m.id i, m.kickoff_utc k, r.source_id s FROM matches m
            JOIN competitions c ON c.id = m.competition_id JOIN match_results r ON r.match_id = m.id
            WHERE c.code = ? AND m.status = 'finished' AND r.home_goals_90 IS NOT NULL
              AND r.away_goals_90 IS NOT NULL AND COALESCE(r.decided_by, '') NOT IN ('extra_time', 'penalties')""",
                            (comp,))
    col = STAT_COL[metric]
    return app.db.query(f"""SELECT m.id i, m.kickoff_utc k, t.source_id s FROM matches m
        JOIN competitions c ON c.id = m.competition_id JOIN team_match_stats t ON t.match_id = m.id
        WHERE c.code = ? AND m.status = 'finished' AND t.{col} IS NOT NULL
        GROUP BY m.id, t.source_id HAVING COUNT(DISTINCT t.is_home) = 2""", (comp,))


def operational_status(app: App, competitions: list[str] | None = None) -> dict:
    """Är prognosmodulen operativ per tävling och mått? Bedöms enbart på faktiska data i databasen:
    antal avslutade matcher med värde från källor som får användas för träning, inom samma tidsfönster
    som modellerna använder (inställningen counts_max_age_days)."""
    from datetime import timedelta

    from .timeutil import parse_iso, to_iso
    now = app.clock.now()
    max_age = int(app.get_setting("counts_max_age_days") or 450)
    since = to_iso(now - timedelta(days=max_age))
    allowed = training_source_ids(app.db)
    names = {r["id"]: r["name"] for r in app.db.query("SELECT id, name FROM sources")}
    comps = competitions or [r["code"] for r in app.db.query(
        "SELECT code FROM competitions WHERE show_in_tabs = 1 ORDER BY tab_order")]
    out = []
    for comp in comps:
        row = {"competition": comp, "metrics": {}}
        for metric in ("goals", "corners", "shots", "sot"):
            rows = _metric_rows(app, comp, metric)
            total_allowed_ids, recent_allowed_ids, recent_any_ids = set(), set(), set()
            last_allowed = last_any = None
            by_source: dict[str, set] = defaultdict(set)
            blocked_recent: set = set()
            for r in rows:
                i, k, s = r["i"], r["k"], r["s"]
                by_source[s].add(i)
                last_any = max(last_any or k, k)
                if k >= since:
                    recent_any_ids.add(i)
                if s in allowed:
                    total_allowed_ids.add(i)
                    last_allowed = max(last_allowed or k, k)
                    if k >= since:
                        recent_allowed_ids.add(i)
                elif k >= since:
                    blocked_recent.add(s)
            matches_recent_allowed, matches_recent_any = recent_allowed_ids, recent_any_ids
            total_allowed = len(total_allowed_ids)
            recent_allowed, recent_any = len(matches_recent_allowed), len(matches_recent_any)
            if recent_allowed >= OPERATIVE_MIN:
                status, reason = "operativ", f"{recent_allowed} matcher med värde de senaste {max_age} dagarna."
            elif recent_allowed >= LIMITED_MIN:
                status, reason = "begränsad", (f"Bara {recent_allowed} matcher med värde de senaste {max_age} "
                                               "dagarna – prognosen bygger mest på ligasnittet.")
            elif recent_any >= LIMITED_MIN:
                blocked = sorted(names.get(x, x) for x in blocked_recent)
                status, reason = "spärrad", ("Aktuell data finns men källan är spärrad från träning: "
                                             + ", ".join(blocked) + ". Godkänn villkoren under Källor & licenser.")
            elif total_allowed:
                status, reason = "inaktuell", (f"Senaste tillåtna data är från {last_allowed[:10]} – äldre än "
                                               f"{max_age} dagar och används därför inte.")
            else:
                status, reason = "saknas", "Ingen data för måttet i någon tillåten källa."
            needs = []
            if status != "operativ":
                if metric == "goals":
                    needs.append("Kör historikhämtningen (OpenFootball, CC0) under Data & källor → Hämta historik.")
                else:
                    needs.append("API-Football med API-nyckel: lagstatistik per match (skott, skott på mål, hörnor). "
                                 "Vilka säsonger abonnemanget omfattar visas efter första hämtningen.")
                    if comp == "UCL":
                        needs.append("UEFA-data från arbetsboken kan användas efter ditt beslut under "
                                     "Källor & licenser.")
            row["metrics"][metric] = {
                "label": METRIC_LABELS[metric], "status": status, "reason": reason, "needs": needs,
                "recent_allowed": recent_allowed, "recent_any": recent_any, "total_allowed": total_allowed,
                "last_allowed": last_allowed, "last_any": last_any,
                "by_source": {names.get(k, k): len(v) for k, v in sorted(by_source.items(), key=lambda x: -len(x[1]))}}
        out.append(row)
    _ = parse_iso
    return {"max_age_days": max_age, "operative_min": OPERATIVE_MIN, "limited_min": LIMITED_MIN,
            "as_of_utc": to_iso(now), "competitions": out}
