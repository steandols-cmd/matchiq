"""Hämta historik från källor med öppen licens via appens egna adaptrar och skriv en täckningsrapport.

    python scripts/hamta_oppen_data.py --data-dir work --sources openfootball,wyscout_public \
        --out rapport --name oppen_data [--export export.zip]

Körs i GitHub Actions (internetåtkomst). Rapporten innehåller bara räknade siffror ur den hämtade
databasen – per tävling, säsong, mått och källa – samt driftstatus och kontroller av lagkopplingen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("MATCHIQ_SECRETS", "memory")

from matchiq import analytics, secrets_store  # noqa: E402
from matchiq.core import init_app  # noqa: E402
from matchiq.sources import sync  # noqa: E402

COMPS = ["UCL", "UCLQ", "SWE1", "ENG1", "ESP1", "GER1", "ITA1", "FRA1"]


def coverage_table(app) -> list[dict]:
    rows = app.db.query("""SELECT c.code comp, COALESCE(s.label,'?') season, COUNT(DISTINCT m.id) matches,
        COUNT(DISTINCT CASE WHEN m.status='finished' THEN m.id END) finished,
        MIN(m.local_date) first, MAX(m.local_date) last
        FROM matches m JOIN competitions c ON c.id=m.competition_id LEFT JOIN seasons s ON s.id=m.season_id
        GROUP BY c.code, s.label ORDER BY c.code, s.label""")
    out = {(r["comp"], r["season"]): dict(r) for r in rows}
    res = app.db.query("""SELECT c.code comp, COALESCE(s.label,'?') season, r.source_id src,
        COUNT(DISTINCT m.id) n FROM matches m JOIN competitions c ON c.id=m.competition_id
        LEFT JOIN seasons s ON s.id=m.season_id JOIN match_results r ON r.match_id=m.id
        WHERE r.home_goals_90 IS NOT NULL GROUP BY 1,2,3""")
    for r in res:
        out[(r["comp"], r["season"])].setdefault("results", {})[r["src"]] = r["n"]
    for col, key in (("corners", "corners"), ("shots", "shots"), ("shots_on_target", "sot")):
        q = app.db.query(f"""SELECT comp, season, src, COUNT(*) n FROM (
            SELECT c.code comp, COALESCE(s.label,'?') season, t.source_id src, m.id
            FROM matches m JOIN competitions c ON c.id=m.competition_id LEFT JOIN seasons s ON s.id=m.season_id
            JOIN team_match_stats t ON t.match_id=m.id WHERE t.{col} IS NOT NULL
            GROUP BY m.id, t.source_id HAVING COUNT(DISTINCT t.is_home)=2) GROUP BY 1,2,3""")
        for r in q:
            out[(r["comp"], r["season"])].setdefault(key, {})[r["src"]] = r["n"]
    pl = app.db.query("""SELECT c.code comp, COALESCE(s.label,'?') season, p.source_id src,
        COUNT(DISTINCT p.match_id) matches, COUNT(DISTINCT p.player_id) players, COUNT(*) n
        FROM player_match_stats p JOIN matches m ON m.id=p.match_id JOIN competitions c ON c.id=m.competition_id
        LEFT JOIN seasons s ON s.id=m.season_id GROUP BY 1,2,3""")
    for r in pl:
        out[(r["comp"], r["season"])].setdefault("players", {})[r["src"]] = {
            "matches": r["matches"], "players": r["players"], "rows": r["n"]}
    return list(out.values())


def link_checks(app) -> dict:
    created = {r["src"]: r["n"] for r in app.db.query(
        "SELECT created_by_source src, COUNT(*) n FROM teams GROUP BY created_by_source")}
    linked = {r["source_id"]: r["n"] for r in app.db.query(
        "SELECT source_id, COUNT(*) n FROM team_source_ids GROUP BY source_id")}
    review = app.db.scalar("SELECT COUNT(*) FROM teams WHERE needs_review=1")
    # Matcher som BARA finns hos en händelsekälla trots att OpenFootball täcker samma tävling och säsong
    orphan = app.db.query("""SELECT c.code comp, COALESCE(se.label,'?') season, s.source_id src, COUNT(*) n
        FROM matches m JOIN competitions c ON c.id=m.competition_id LEFT JOIN seasons se ON se.id=m.season_id
        JOIN match_source_ids s ON s.match_id=m.id
        WHERE s.source_id IN ('wyscout_public','statsbomb_open','api_football')
          AND NOT EXISTS (SELECT 1 FROM match_results r WHERE r.match_id=m.id AND r.source_id='openfootball')
          AND EXISTS (SELECT 1 FROM matches m2 JOIN match_results r2 ON r2.match_id=m2.id
                      WHERE r2.source_id='openfootball' AND m2.competition_id=m.competition_id
                        AND m2.season_id=m.season_id)
        GROUP BY 1,2,3 ORDER BY 1,2""")
    new_teams = app.db.query("""SELECT name, created_by_source src FROM teams
        WHERE created_by_source IN ('wyscout_public','statsbomb_open','api_football') ORDER BY name""")
    conflicts = app.db.query("""SELECT r1.match_id, r1.home_goals_90 h1, r1.away_goals_90 a1, r1.source_id s1,
        r2.home_goals_90 h2, r2.away_goals_90 a2, r2.source_id s2 FROM match_results r1
        JOIN match_results r2 ON r2.match_id=r1.match_id AND r2.source_id>r1.source_id
        WHERE r1.home_goals_90 IS NOT NULL AND r2.home_goals_90 IS NOT NULL
          AND (r1.home_goals_90<>r2.home_goals_90 OR r1.away_goals_90<>r2.away_goals_90)""")
    return {"teams_created_by_source": created, "team_ids_linked_by_source": linked, "teams_needing_review": review,
            "matches_only_in_event_source_where_openfootball_covers_season": [dict(r) for r in orphan],
            "teams_created_by_event_sources": [dict(r) for r in new_teams],
            "result_conflicts_between_sources": [dict(r) for r in conflicts][:200],
            "result_conflicts_total": len(conflicts)}


def evaluate_leagues(app, comps: list[str]) -> dict:
    """Walk-forward per tävling (expanderande fönster per matchdag) för V2, V3 och baslinjen på de
    säsonger där det finns data. Parametrarna är de som finns i databasen (V3: valda på UCL) – detta är
    alltså en kontroll av hur modellerna fungerar i ligorna, inte ett nytt modellval."""
    import json as _json

    from matchiq.catalog import training_source_ids
    from matchiq.models import baseline, v2, v3
    from matchiq.models.data import HistoryStore
    from matchiq.models.evaluate import build_targets, evaluation_source_ids, summarize, walk_forward
    out = {}
    max_age = app.get_setting("counts_max_age_days")
    row = app.db.one("SELECT params_json FROM model_versions WHERE id='V3-3.0'")
    v3_params = _json.loads(row["params_json"]) if row and row["params_json"] else None
    for comp in comps:
        try:
            train = HistoryStore.load(app.db, training_source_ids(app.db), competitions=[comp],
                                      counts_max_age_days=max_age)
            ev = HistoryStore.load(app.db, evaluation_source_ids(app.db), competitions=[comp])
            a = ev.a
            seasons_counts = sorted({str(a.season[i]) for i in range(len(a.match_id))
                                     if not (a.vals_h["corners"][i] != a.vals_h["corners"][i])})
            seasons_all = sorted({str(s) for s in a.season if s})
            # 1X2: de tre senaste säsongerna med resultat; räknemått: alla säsonger med hörndata
            recent = [s for s in seasons_all if s][-4:-1] if len(seasons_all) > 3 else seasons_all[-3:]
            seasons = sorted(set(recent) | set(seasons_counts))
            targets = build_targets(ev, comp, seasons)
            res = {"seasons_1x2": recent, "seasons_counts": seasons_counts, "n_targets": len(targets)}
            v3.clear_cache()
            for name, mod, params in (("V2", v2, None), ("V3", v3, v3_params), ("BASE", baseline, None)):
                rows = walk_forward(train, mod.predict, params, targets, "test")
                summ = summarize(rows)
                res[name] = {"by_season": summ.get("by_season", {}), "all": summ.get("all", {})}
            out[comp] = res
            print(f"Utvärdering {comp}: {len(targets)} matcher", flush=True)
        except Exception as e:  # noqa: BLE001
            out[comp] = {"error": repr(e)[:500]}
    return out


def write_md(rep: dict, path: Path) -> None:
    L = [f"# Hämtad data – {rep['name']} ({rep['finished_utc']})", "",
         "Siffrorna är räknade ur databasen som byggdes av appens egna källadaptrar i GitHub Actions.", "",
         "## Körning per källa", "", "| Källa | Status | Tid (s) | Resultat |", "|---|---|---|---|"]
    for r in rep["runs"]:
        res = {k: v for k, v in (r.get("result") or {}).items() if k != "event_kinds"}
        L.append(f"| {r['source']} | {r['status']}{' – ' + str(r.get('error')) if r.get('error') else ''} | "
                 f"{r.get('seconds', '')} | {json.dumps(res, ensure_ascii=False)[:600]} |")
    for r in rep["runs"]:
        if (r.get("result") or {}).get("event_kinds"):
            L += ["", f"Händelsetyper i {r['source']} (topp 40):", ""]
            L += [f"- {k}: {v}" for k, v in r["result"]["event_kinds"].items()]
    L += ["", "## Driftstatus per tävling och mått", "",
          f"Fönster: {rep['operational']['max_age_days']} dagar. Operativ = minst {rep['operational']['operative_min']} "
          "matcher med värde från en källa som får användas för träning.", "",
          "| Tävling | Mått | Status | Matcher i fönstret | Totalt (tillåtet) | Senaste | Källor |", "|---|---|---|---|---|---|---|"]
    for c in rep["operational"]["competitions"]:
        for _k, m in c["metrics"].items():
            L.append(f"| {c['competition']} | {m['label']} | {m['status']} | {m['recent_allowed']} | "
                     f"{m['total_allowed']} | {(m['last_allowed'] or '–')[:10]} | "
                     f"{', '.join(f'{a}: {b}' for a, b in m['by_source'].items()) or '–'} |")
    L += ["", "## Täckning per tävling och säsong", "",
          "| Tävling | Säsong | Matcher | Spelade | Resultat (källa: n) | Hörnor | Skott | Skott på mål | Spelarrader |",
          "|---|---|---|---|---|---|---|---|---|"]
    fmt = (lambda d: ", ".join(f"{k}: {v}" for k, v in (d or {}).items()) or "–")
    for r in rep["coverage"]:
        pl = ", ".join(f"{k}: {v['players']} spelare/{v['matches']} matcher" for k, v in (r.get("players") or {}).items())
        L.append(f"| {r['comp']} | {r['season']} | {r['matches']} | {r['finished']} | {fmt(r.get('results'))} | "
                 f"{fmt(r.get('corners'))} | {fmt(r.get('shots'))} | {fmt(r.get('sot'))} | {pl or '–'} |")
    lc = rep["links"]
    L += ["", "## Kontroll av lagkoppling", "",
          f"- Lag skapade per källa: {lc['teams_created_by_source']}",
          f"- Källans lag-ID kopplade till befintliga lag: {lc['team_ids_linked_by_source']}",
          f"- Lag flaggade för granskning: {lc['teams_needing_review']}",
          f"- Resultatkonflikter mellan källor (samma match, olika 90-minutersresultat): {lc['result_conflicts_total']}",
          "", "Matcher som bara finns hos en händelsekälla fast OpenFootball täcker säsongen (bör vara 0 om "
          "kopplingen fungerar):", ""]
    L += [f"- {r['comp']} {r['season']} {r['src']}: {r['n']}" for r in lc[
        "matches_only_in_event_source_where_openfootball_covers_season"]] or ["- inga"]
    L += ["", "Lag som skapades av händelsekällor (ej kopplade):", ""]
    L += [f"- {r['name']} ({r['src']})" for r in lc["teams_created_by_event_sources"][:150]] or ["- inga"]
    if rep.get("evaluation"):
        L += ["", "## Walk-forward per tävling (V3-parametrar valda på Champions League)", "",
              "| Tävling | Säsong | Modell | n 1X2 | Brier | Log loss | Hörnor MAE / täckn. 80 % (n) | "
              "Skott MAE / täckn. (n) | Skott på mål MAE / täckn. (n) |", "|---|---|---|---|---|---|---|---|---|"]
        f3 = (lambda v, d=3: "–" if v is None else f"{v:.{d}f}".replace(".", ","))
        pc = (lambda v: "–" if v is None else f"{round(v * 100)} %")
        for comp, r in rep["evaluation"].items():
            if "error" in r:
                L.append(f"| {comp} | – | – | – | – | – | fel: {r['error'][:120]} | | |")
                continue
            for season in sorted(set(r["seasons_1x2"]) | set(r["seasons_counts"])):
                for mname in ("V2", "V3", "BASE"):
                    s_ = r[mname]["by_season"].get(season)
                    if not s_:
                        continue
                    x = s_.get("1x2") or {}
                    cells = []
                    for m in ("corners", "shots", "sot"):
                        y = s_.get(m) or {}
                        cells.append(f"{f3(y.get('mae'), 2)} / {pc(y.get('coverage'))} ({y.get('n', 0)})" if y.get("n") else "–")
                    L.append(f"| {comp} | {season} | {mname} | {x.get('n', 0)} | {f3(x.get('brier'))} | "
                             f"{f3(x.get('logloss'))} | " + " | ".join(cells) + " |")
    if lc["result_conflicts_between_sources"]:
        L += ["", "Resultatkonflikter (första 50):", ""]
        L += [f"- match {r['match_id']}: {r['s1']} {r['h1']}–{r['a1']} / {r['s2']} {r['h2']}–{r['a2']}"
              for r in lc["result_conflicts_between_sources"][:50]]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--sources", default="openfootball,wyscout_public")
    ap.add_argument("--out", default="rapport")
    ap.add_argument("--name", default="oppen_data")
    ap.add_argument("--export")
    ap.add_argument("--evaluate", action="store_true", help="walk-forward per tävling efter hämtningen")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    app = init_app(Path(a.data_dir))
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        secrets_store.set_secret("github_token", tok)
    runs = []
    last = [0.0]

    def progress(msg, done, total):
        if time.time() - last[0] > 20:
            print(f"[{done}/{total}] {msg}", flush=True)
            last[0] = time.time()

    for sid in [x.strip() for x in a.sources.split(",") if x.strip()]:
        t0 = time.time()
        r = sync.run_backfill(app, [sid], None, progress, COMPS)
        # GitHubs anropsgräns: vänta och fortsätt (redan hämtat hoppas över) – högst ~4 timmar
        waits = 0
        while (r and r[-1]["status"] == "blocked" and "anropsgräns" in str(r[-1].get("error"))
               and waits < 24):
            print("GitHubs anropsgräns nådd – väntar 10 minuter och fortsätter", flush=True)
            time.sleep(600)
            waits += 1
            r = sync.run_backfill(app, [sid], None, progress, COMPS)
        for x in r:
            x["seconds"] = round(time.time() - t0)
            print(json.dumps({k: v for k, v in x.items() if k != "result"}, ensure_ascii=False), flush=True)
        runs += r
    rep = {"name": a.name, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": runs,
           "operational": analytics.operational_status(app, ["UCL", "SWE1", "ENG1", "ESP1", "GER1", "ITA1", "FRA1"]),
           "coverage": coverage_table(app), "links": link_checks(app),
           "fetches": {r["source_id"]: {"n": r["n"], "failed": r["failed"], "bytes": r["b"]} for r in app.db.query(
               """SELECT source_id, COUNT(*) n, SUM(CASE WHEN http_status IS NULL OR http_status>=400 THEN 1 ELSE 0 END)
               failed, SUM(COALESCE(bytes,0)) b FROM fetches GROUP BY source_id""")}}
    if a.evaluate:
        rep["evaluation"] = evaluate_leagues(app, ["ENG1", "ESP1", "GER1", "ITA1", "FRA1", "SWE1"])
    (out / f"{a.name}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_md(rep, out / f"{a.name}.md")
    if a.export:
        m = app.db.export_bundle(Path(a.export))
        print("Export:", a.export, m.get("tables", {}).get("matches"))
    bad = [r for r in runs if r["status"] not in ("ok", "skipped")]
    print("Klar.", "Problem: " + json.dumps(bad, ensure_ascii=False, default=str)[:2000] if bad else "Inga fel.")


if __name__ == "__main__":
    main()
