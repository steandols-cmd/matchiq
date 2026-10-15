"""Lokalt HTTP-API (Starlette/ASGI) för desktopappen.

Säkerhet:
* Servern binds ENDAST till 127.0.0.1 (se server.py) och exponeras aldrig på nätverket.
* Alla /api-anrop (utom /api/health) kräver en slumpad bearer-token som Electron-skalet skapar vid
  start och lämnar till backend via miljövariabel och till gränssnittet via preload-bryggan.
* Host-huvudet måste vara localhost/127.0.0.1 (skydd mot DNS-rebinding).
* CORS tillåts bara för appens eget ursprung.
"""
from __future__ import annotations

import hmac
import json
import math
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from .. import __version__, analytics, catalog, forecast, scheduler, secrets_store
from ..core import App
from ..db import latest_schema_version, rows_to_dicts
from ..importers import generic, workbook_ucl
from ..jobs import JobManager
from ..models import selection
from ..sources import sync
from ..timeutil import parse_iso, to_iso

ALLOWED_ORIGINS = {"app://matchiq", "http://localhost:5173", "http://127.0.0.1:5173", "null"}


def _clean(o: Any) -> Any:
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "keys") and hasattr(o, "__getitem__"):  # sqlite3.Row
        return {k: _clean(o[k]) for k in o.keys()}
    if isinstance(o, (datetime,)):
        return to_iso(o)
    if isinstance(o, set):
        return sorted(_clean(v) for v in o)
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return _clean(o.item())
    except Exception:  # noqa: BLE001
        pass
    return o


class JSON(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(_clean(content), ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


def err(msg: str, status: int = 400) -> JSON:
    return JSON({"error": msg}, status_code=status)


class SecurityMiddleware:
    def __init__(self, app, token: str, extra_hosts: set[str] | None = None):
        self.app = app
        self.token = token.encode()
        self.hosts = {"127.0.0.1", "localhost"} | (extra_hosts or set())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        host = headers.get("host", "").rsplit(":", 1)[0].strip("[]")
        origin = headers.get("origin")
        cors = {}
        if origin and origin in ALLOWED_ORIGINS:
            cors = {"access-control-allow-origin": origin, "vary": "Origin",
                    "access-control-allow-headers": "authorization, content-type, x-filename",
                    "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS"}
        if host not in self.hosts:
            return await JSON({"error": "Otillåten värd"}, status_code=421)(scope, receive, send)
        if scope["method"] == "OPTIONS":
            return await Response(status_code=204, headers=cors)(scope, receive, send)
        path = scope.get("path", "")
        if path.startswith("/api") and path != "/api/health":
            auth = headers.get("authorization", "")
            tok = auth[7:].encode() if auth.lower().startswith("bearer ") else b""
            if not hmac.compare_digest(tok, self.token):
                return await JSON({"error": "Ej behörig"}, status_code=401, headers=cors)(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and cors:
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(k.encode(), v.encode()) for k, v in cors.items()]
            await send(message)

        return await self.app(scope, receive, send_wrapper)


def create_app(ctx: App, token: str, *, extra_hosts: set[str] | None = None, allow_simulation: bool = False):
    jobs = JobManager(ctx)
    ctx.extras["jobs"] = jobs

    async def body(request: Request) -> dict:
        try:
            raw = await request.body()
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------------ meta
    async def health(request: Request):
        return JSON({"ok": True})

    async def meta(request: Request):
        db = ctx.db
        return JSON({
            "app": "MatchIQ", "version": __version__, "data_dir": str(ctx.paths.root), "db_path": str(ctx.paths.db),
            "db_bytes": ctx.paths.db.stat().st_size if ctx.paths.db.exists() else None,
            "schema_version": db.schema_version(), "schema_latest": latest_schema_version(),
            "reports_dir": str(ctx.paths.reports), "clock": "simulerad" if ctx.clock.simulated else "system",
            "now_utc": to_iso(ctx.clock.now()), "secrets_backend": secrets_store.backend_name(),
            "counts": {t: db.scalar(f"SELECT COUNT(*) FROM {t}") for t in
                       ("matches", "teams", "match_results", "team_match_stats", "lineups", "forecast_snapshots",
                        "reports", "fetches", "imports")},
            "teams_needing_review": db.scalar("SELECT COUNT(*) FROM teams WHERE needs_review=1"),
            "allow_simulation": allow_simulation,
        })

    # ------------------------------------------------------------------ tävlingar och matcher
    async def competitions(request: Request):
        rows = ctx.db.query("""SELECT c.*, (SELECT COUNT(*) FROM matches m WHERE m.competition_id=c.id) AS matches,
            (SELECT COUNT(*) FROM matches m WHERE m.competition_id=c.id AND m.status='scheduled' AND m.kickoff_utc>=?)
            AS upcoming FROM competitions c ORDER BY COALESCE(c.tab_order, 99), c.name""", (to_iso(ctx.clock.now()),))
        return JSON(rows_to_dicts(rows))

    def _latest_snaps(match_ids: list[int]) -> dict:
        if not match_ids:
            return {}
        ph = ",".join("?" * len(match_ids))
        rows = ctx.db.query(f"""SELECT s.match_id, s.model_family, s.kind, s.p_home, s.p_draw, s.p_away, s.created_at_utc,
            s.goals_home, s.goals_away, s.id FROM forecast_snapshots s WHERE s.match_id IN ({ph})
            AND s.model_family IN ('V2','V3') AND s.kind IN ('T-30','manual','late')
            ORDER BY CASE s.kind WHEN 'T-30' THEN 0 WHEN 'late' THEN 1 ELSE 2 END, s.created_at_utc DESC""", match_ids)
        out: dict = {}
        for r in rows:
            d = out.setdefault(r["match_id"], {})
            d.setdefault(r["model_family"], dict(r))
        return out

    async def matches(request: Request):
        qp = request.query_params
        where, params = ["1=1"], []
        if qp.get("competition"):
            where.append("c.code=?")
            params.append(qp["competition"])
        if qp.get("from"):
            where.append("m.kickoff_utc>=?")
            params.append(qp["from"])
        if qp.get("to"):
            where.append("m.kickoff_utc<=?")
            params.append(qp["to"])
        if qp.get("status"):
            st = qp["status"].split(",")
            where.append(f"m.status IN ({','.join('?' * len(st))})")
            params += st
        if qp.get("team"):
            where.append("(h.name LIKE ? OR a.name LIKE ?)")
            params += [f"%{qp['team']}%"] * 2
        order = "DESC" if qp.get("order") == "desc" else "ASC"
        limit = min(int(qp.get("limit", 200)), 1000)
        rows = ctx.db.query(f"""SELECT m.id, m.kickoff_utc, m.kickoff_time_known, m.status, m.stage, m.round, m.matchday,
            m.venue, c.code AS competition, c.name AS competition_name, s.label AS season,
            m.home_team_id, h.name AS home, h.color_primary AS home_c1, h.color_secondary AS home_c2,
            h.crest_path AS home_crest, m.away_team_id, a.name AS away, a.color_primary AS away_c1,
            a.color_secondary AS away_c2, a.crest_path AS away_crest,
            (SELECT home_goals_90 FROM match_results r WHERE r.match_id=m.id AND home_goals_90 IS NOT NULL
             ORDER BY CASE source_id WHEN 'manual' THEN 0 WHEN 'uefa' THEN 1 ELSE 2 END LIMIT 1) AS home_goals,
            (SELECT away_goals_90 FROM match_results r WHERE r.match_id=m.id AND away_goals_90 IS NOT NULL
             ORDER BY CASE source_id WHEN 'manual' THEN 0 WHEN 'uefa' THEN 1 ELSE 2 END LIMIT 1) AS away_goals,
            (SELECT status FROM report_jobs j WHERE j.match_id=m.id ORDER BY j.id DESC LIMIT 1) AS job_status,
            (SELECT due_at_utc FROM report_jobs j WHERE j.match_id=m.id ORDER BY j.id DESC LIMIT 1) AS job_due,
            (SELECT COUNT(*) FROM reports r WHERE r.match_id=m.id) AS reports,
            (SELECT GROUP_CONCAT(DISTINCT l.status) FROM lineups l WHERE l.match_id=m.id) AS lineup_status
            FROM matches m JOIN competitions c ON c.id=m.competition_id LEFT JOIN seasons s ON s.id=m.season_id
            JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
            WHERE {' AND '.join(where)} ORDER BY m.kickoff_utc {order} LIMIT ?""", params + [limit])
        data = rows_to_dicts(rows)
        snaps = _latest_snaps([r["id"] for r in data])
        for r in data:
            r["snapshots"] = snaps.get(r["id"], {})
        return JSON(data)

    def _preview_cache_key(mid: int) -> tuple:
        return (mid, forecast._data_version(ctx))

    async def match_detail(request: Request):
        mid = int(request.path_params["mid"])
        try:
            info = forecast.match_info(ctx, mid)
        except KeyError:
            return err("Matchen finns inte", 404)
        now = ctx.clock.now()
        ko = parse_iso(info["kickoff_utc"])
        snaps = [dict(r) for r in ctx.db.query(
            """SELECT id, model_version_id, model_family, kind, created_at_utc, data_cutoff_utc, minutes_before_kickoff,
               is_late, prematch_eligible, p_home, p_draw, p_away, goals_home, goals_away, corners_home, corners_away,
               shots_home, shots_away, sot_home, sot_away, created_by, clock FROM forecast_snapshots WHERE match_id=?
               ORDER BY created_at_utc DESC""", (mid,))]
        frozen = None
        for kind in ("T-30", "late", "manual", "legacy"):
            fam = {}
            for s in snaps:
                if s["kind"] == kind and s["model_family"] not in fam:
                    fam[s["model_family"]] = s["id"]
            if fam:
                frozen = {"kind": kind, "snapshots": {f: forecast.load_snapshot(ctx, sid) for f, sid in fam.items()}}
                break
        preview = None
        if info["status"] in ("scheduled", "live", "unknown") or frozen is None:
            cutoff = min(now, ko) if ko else now  # type: ignore[type-var]
            cache = ctx.extras.setdefault("preview_cache", {})
            key = (_preview_cache_key(mid), to_iso(cutoff)[:15])
            preview = cache.get(key)
            if preview is None:
                preview = forecast.compute(ctx, mid, cutoff)
                cache.clear() if len(cache) > 200 else None
                cache[key] = preview
        reports = rows_to_dicts(ctx.db.query("SELECT * FROM reports WHERE match_id=? ORDER BY id DESC", (mid,)))
        jobs_ = rows_to_dicts(ctx.db.query("SELECT * FROM report_jobs WHERE match_id=? ORDER BY id DESC", (mid,)))
        outcome = ctx.db.one("SELECT * FROM match_outcomes WHERE match_id=?", (mid,))
        results = rows_to_dicts(ctx.db.query("SELECT * FROM match_results WHERE match_id=?", (mid,)))
        stats = rows_to_dicts(ctx.db.query("SELECT * FROM team_match_stats WHERE match_id=?", (mid,)))
        odds = rows_to_dicts(ctx.db.query("""SELECT bookmaker, kind, odds_home, odds_draw, odds_away, fetched_at_utc,
            published_at_utc, source_id FROM market_odds WHERE match_id=? ORDER BY fetched_at_utc DESC""", (mid,)))
        before = info["kickoff_utc"]
        deep = {
            "form": {"home": analytics.recent_form(ctx, info["home_team_id"], before),
                     "away": analytics.recent_form(ctx, info["away_team_id"], before)},
            "averages": {"home": analytics.team_metric_averages(ctx, info["home_team_id"], before, info["comp_code"]),
                         "away": analytics.team_metric_averages(ctx, info["away_team_id"], before, info["comp_code"])},
            "h2h": rows_to_dicts(ctx.db.query("""SELECT m.id, m.kickoff_utc, c.code comp, h.name home, a.name away,
                r.home_goals_90 hg, r.away_goals_90 ag FROM matches m JOIN competitions c ON c.id=m.competition_id
                JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
                JOIN match_results r ON r.match_id=m.id AND r.home_goals_90 IS NOT NULL
                WHERE ((m.home_team_id=? AND m.away_team_id=?) OR (m.home_team_id=? AND m.away_team_id=?))
                AND m.kickoff_utc<? GROUP BY m.id ORDER BY m.kickoff_utc DESC LIMIT 6""",
                                              (info["home_team_id"], info["away_team_id"], info["away_team_id"],
                                               info["home_team_id"], before))),
        }
        return JSON({"match": info, "frozen": frozen, "preview": preview, "snapshots": snaps, "reports": reports,
                     "jobs": jobs_, "outcome": dict(outcome) if outcome else None, "results": results,
                     "team_stats": stats, "odds": odds, "deep": deep, "now_utc": to_iso(now)})

    async def match_freeze(request: Request):
        """Frys en manuell prognos nu (datagräns = nu, aldrig efter avspark)."""
        mid = int(request.path_params["mid"])
        b = await body(request)
        info = forecast.match_info(ctx, mid)
        now = ctx.clock.now()
        ko = parse_iso(info["kickoff_utc"])
        if now >= ko:  # type: ignore[operator]
            return err("Avspark har passerat – en förmatchsprognos kan inte skapas i efterhand.", 409)
        if b.get("pdf", True):
            rep = scheduler.create_report(ctx, mid, kind="manual", cutoff=now, created_by="user")
            return JSON(rep)
        fr = forecast.freeze(ctx, mid, now, kind="manual", created_by="user")
        return JSON({k: v for k, v in fr.items() if k != "payload"})

    async def match_outcome(request: Request):
        """Eftermatch: spara faktiska värden (skilda från prognoser) och logga ändringen."""
        mid = int(request.path_params["mid"])
        b = await body(request)
        fields = ("home_goals", "away_goals", "home_corners", "away_corners", "home_shots", "away_shots",
                  "home_sot", "away_sot")
        vals = {}
        for f in fields:
            v = b.get(f)
            if v in (None, ""):
                vals[f] = None
            else:
                try:
                    vals[f] = int(v)
                except (TypeError, ValueError):
                    return err(f"Ogiltigt värde för {f}")
                if vals[f] < 0:
                    return err(f"Negativt värde för {f}")
        info = forecast.match_info(ctx, mid)
        if parse_iso(info["kickoff_utc"]) > ctx.clock.now():  # type: ignore[operator]
            return err("Matchen har inte spelats ännu.", 409)
        old = ctx.db.one("SELECT * FROM match_outcomes WHERE match_id=?", (mid,))
        now = to_iso(ctx.clock.now())
        with ctx.db.tx() as c:
            c.execute("""INSERT INTO match_outcomes (match_id, home_goals, away_goals, home_corners, away_corners,
                home_shots, away_shots, home_sot, away_sot, source_id, entered_by, recorded_at_utc, note)
                VALUES (?,?,?,?,?,?,?,?,?,'manual','manual',?,?) ON CONFLICT(match_id) DO UPDATE SET
                home_goals=excluded.home_goals, away_goals=excluded.away_goals, home_corners=excluded.home_corners,
                away_corners=excluded.away_corners, home_shots=excluded.home_shots, away_shots=excluded.away_shots,
                home_sot=excluded.home_sot, away_sot=excluded.away_sot, source_id='manual', entered_by='manual',
                recorded_at_utc=excluded.recorded_at_utc, note=excluded.note""",
                      (mid, *[vals[f] for f in fields], now, b.get("note")))
            for f in fields:
                if old is None or old[f] != vals[f]:
                    ctx.repo.log_change(c, "match_outcome", mid, f, None if old is None else old[f], vals[f],
                                        source_id="manual", actor="user")
        # Facit blir också manuell observation (träningsbar) – prognoser påverkas inte retroaktivt.
        if vals["home_goals"] is not None and vals["away_goals"] is not None:
            ctx.repo.upsert_result(mid, "manual", {"home_goals_90": vals["home_goals"],
                                                   "away_goals_90": vals["away_goals"]})
        for is_home, tid, p in ((True, info["home_team_id"], "home"), (False, info["away_team_id"], "away")):
            ctx.repo.upsert_team_stats(mid, tid, is_home, "manual", {"shots": vals[f"{p}_shots"],
                                                                     "shots_on_target": vals[f"{p}_sot"],
                                                                     "corners": vals[f"{p}_corners"]})
        return JSON({"ok": True, "outcome": dict(ctx.db.one("SELECT * FROM match_outcomes WHERE match_id=?", (mid,)))})

    # ------------------------------------------------------------------ lag
    async def teams(request: Request):
        q = request.query_params.get("q", "")
        rows = ctx.db.query("""SELECT t.*, (SELECT COUNT(*) FROM matches m WHERE t.id IN (m.home_team_id, m.away_team_id))
            AS matches FROM teams t WHERE t.name LIKE ? OR t.id IN (SELECT team_id FROM team_aliases WHERE alias LIKE ?)
            ORDER BY needs_review DESC, matches DESC LIMIT 300""", (f"%{q}%", f"%{q}%"))
        return JSON(rows_to_dicts(rows))

    async def team_detail(request: Request):
        tid = int(request.path_params["tid"])
        t = ctx.db.one("SELECT * FROM teams WHERE id=?", (tid,))
        if t is None:
            return err("Laget finns inte", 404)
        now = to_iso(ctx.clock.now())
        lineups = rows_to_dicts(ctx.db.query("""SELECT l.id, l.match_id, l.status, l.formation, l.fetched_at_utc,
            l.source_id, m.kickoff_utc, h.name home, a.name away FROM lineups l JOIN matches m ON m.id=l.match_id
            JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id WHERE l.team_id=?
            ORDER BY m.kickoff_utc DESC, l.fetched_at_utc DESC LIMIT 10""", (tid,)))
        for lu in lineups:
            lu["players"] = rows_to_dicts(ctx.db.query(
                "SELECT slot, name_original name, shirt_number number, position FROM lineup_players WHERE lineup_id=? "
                "ORDER BY slot", (lu["id"],)))
        players = rows_to_dicts(ctx.db.query("""SELECT p.name, COUNT(*) apps, SUM(ps.minutes) minutes,
            SUM(ps.minutes_estimated) est, SUM(ps.goals) goals, SUM(ps.shots) shots, SUM(ps.xg) xg, ps.source_id
            FROM player_match_stats ps JOIN players p ON p.id=ps.player_id WHERE ps.team_id=?
            GROUP BY p.id ORDER BY apps DESC LIMIT 40""", (tid,)))
        return JSON({
            "team": dict(t),
            "aliases": rows_to_dicts(ctx.db.query("SELECT * FROM team_aliases WHERE team_id=? ORDER BY alias", (tid,))),
            "source_ids": rows_to_dicts(ctx.db.query("SELECT * FROM team_source_ids WHERE team_id=?", (tid,))),
            "possible_duplicates": ctx.repo.possible_duplicates(t["name"], exclude_id=tid),
            "form": analytics.recent_form(ctx, tid, now, 10),
            "averages": analytics.team_metric_averages(ctx, tid, now, None, 10),
            "lineups": lineups, "players": players,
            "absences": rows_to_dicts(ctx.db.query("""SELECT a.*, m.kickoff_utc FROM availability a LEFT JOIN matches m
                ON m.id=a.match_id WHERE a.team_id=? ORDER BY a.fetched_at_utc DESC LIMIT 30""", (tid,))),
            "upcoming": rows_to_dicts(ctx.db.query("""SELECT m.id, m.kickoff_utc, c.code comp, h.name home, a.name away
                FROM matches m JOIN competitions c ON c.id=m.competition_id JOIN teams h ON h.id=m.home_team_id
                JOIN teams a ON a.id=m.away_team_id WHERE ? IN (m.home_team_id, m.away_team_id) AND m.kickoff_utc>=?
                ORDER BY m.kickoff_utc LIMIT 5""", (tid, now))),
        })

    async def team_update(request: Request):
        tid = int(request.path_params["tid"])
        b = await body(request)
        allowed = {k: b[k] for k in ("name", "short_name", "color_primary", "color_secondary", "country",
                                     "domestic_competition_code") if k in b}
        if b.get("review_done"):
            allowed["needs_review"] = 0
        if not allowed:
            return err("Inget att uppdatera")
        with ctx.db.tx() as c:
            old = c.execute("SELECT * FROM teams WHERE id=?", (tid,)).fetchone()
            c.execute(f"UPDATE teams SET {', '.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), tid))
            for k, v in allowed.items():
                ctx.repo.log_change(c, "team", tid, k, old[k], v, actor="user")
        return JSON({"ok": True})

    async def team_alias(request: Request):
        tid = int(request.path_params["tid"])
        b = await body(request)
        try:
            ctx.repo.add_alias(tid, b["alias"], b.get("context", ""), b.get("source_id", ""), "user")
        except (KeyError, ValueError) as e:
            return err(str(e))
        return JSON({"ok": True})

    async def team_merge(request: Request):
        b = await body(request)
        try:
            ctx.repo.merge_teams(int(b["keep_id"]), int(b["drop_id"]))
        except Exception as e:  # noqa: BLE001
            return err(str(e))
        return JSON({"ok": True})

    async def team_crest(request: Request):
        tid = int(request.path_params["tid"])
        data = await request.body()
        if not data or len(data) > 2_000_000:
            return err("Bildfilen saknas eller är större än 2 MB")
        ext = (request.headers.get("x-filename", "crest.png").rsplit(".", 1)[-1] or "png").lower()
        if ext not in ("png", "svg", "jpg", "jpeg", "webp"):
            return err("Endast png, svg, jpg eller webp")
        p = ctx.paths.crests / f"team_{tid}.{ext}"
        p.write_bytes(data)
        ctx.db.execute("UPDATE teams SET crest_path=? WHERE id=?", (p.name, tid))
        return JSON({"ok": True, "crest_path": p.name})

    async def crest_file(request: Request):
        name = Path(request.path_params["name"]).name
        p = ctx.paths.crests / name
        if not p.exists():
            return err("Saknas", 404)
        return FileResponse(p)

    # ------------------------------------------------------------------ källor
    async def sources(request: Request):
        rows = [dict(r) for r in ctx.db.query("SELECT * FROM sources ORDER BY id")]
        over = {o["id"]: o for o in sync.sources_overview(ctx)}
        sec = {k["name"]: k["configured"] for k in secrets_store.status()["keys"]}
        key_for = {"api_football": "api_football", "football_data_org": "football_data_org",
                   "the_odds_api": "the_odds_api"}
        for r in rows:
            r["allowed_uses"] = json.loads(r["allowed_uses"] or "[]")
            r["data_kinds"] = json.loads(r["data_kinds"] or "[]")
            r["training_allowed"] = catalog.training_allowed(r)
            r["training_status"] = catalog.training_status_text(r)
            r["api_key_configured"] = sec.get(key_for.get(r["id"], ""), None) if r["requires_api_key"] else None
            r["overview"] = over.get(r["id"])
            r["audit"] = rows_to_dicts(ctx.db.query(
                "SELECT action, detail, at_utc FROM source_audit WHERE source_id=? ORDER BY id DESC LIMIT 5", (r["id"],)))
        return JSON(rows)

    async def source_training(request: Request):
        b = await body(request)
        try:
            r = catalog.set_training_approval(ctx.db, request.path_params["sid"], bool(b.get("approve")),
                                              b.get("note", ""), ctx.clock.now())
        except (KeyError, ValueError) as e:
            return err(str(e))
        return JSON({"ok": True, "training_allowed": catalog.training_allowed(r)})

    async def source_enabled(request: Request):
        b = await body(request)
        try:
            catalog.set_source_enabled(ctx.db, request.path_params["sid"], bool(b.get("enabled")), ctx.clock.now(),
                                       b.get("note", ""))
        except (KeyError, ValueError) as e:
            return err(str(e))
        return JSON({"ok": True})

    async def source_sync(request: Request):
        sid = request.path_params["sid"]
        b = await body(request)
        jid = jobs.start(f"sync:{sid}", lambda progress: sync.run_source(ctx, sid, b.get("job")))
        return JSON({"job_id": jid})

    async def fetches(request: Request):
        qp = request.query_params
        params: list = []
        where = ""
        if qp.get("source"):
            where = "WHERE source_id=?"
            params.append(qp["source"])
        rows = ctx.db.query(f"SELECT * FROM fetches {where} ORDER BY id DESC LIMIT ?", params + [int(qp.get("limit", 100))])
        return JSON(rows_to_dicts(rows))

    async def coverage(request: Request):
        comp = request.query_params.get("competition", "UCL")
        season = request.query_params.get("season")
        return JSON({**analytics.coverage(ctx, comp), "teams": analytics.team_coverage(ctx, comp, season)})

    async def standings(request: Request):
        comp = request.query_params.get("competition", "UCL")
        return JSON(analytics.standings(ctx, comp, request.query_params.get("season")))

    async def changelog(request: Request):
        qp = request.query_params
        rows = ctx.db.query("SELECT * FROM change_log ORDER BY id DESC LIMIT ?", (int(qp.get("limit", 200)),))
        return JSON(rows_to_dicts(rows))

    # ------------------------------------------------------------------ import
    def _upload_path(name: str) -> Path:
        d = Path(tempfile.mkdtemp(prefix="matchiq-upload-"))
        return d / Path(name).name

    async def import_inspect(request: Request):
        name = request.headers.get("x-filename", "fil.xlsx")
        data = await request.body()
        if not data:
            return err("Ingen fil mottogs")
        p = _upload_path(name)
        p.write_bytes(data)
        try:
            res = generic.inspect_file(ctx, p, original_name=name)
        except Exception as e:  # noqa: BLE001
            return err(f"Kunde inte läsa filen: {e}")
        return JSON(res)

    async def import_preview(request: Request):
        b = await body(request)
        try:
            res = generic.preview(ctx, Path(b["stored_copy"]), b.get("sheet"), b.get("header_row"), b["target"],
                                  b.get("mapping", {}), b.get("options", {}))
        except Exception as e:  # noqa: BLE001
            return err(str(e))
        return JSON(res)

    async def import_run(request: Request):
        b = await body(request)
        stored = Path(b["stored_copy"])
        if not stored.exists() or ctx.paths.imports not in stored.parents:
            return err("Okänd importfil")
        if b.get("profile") == workbook_ucl.PROFILE_ID:
            jid = jobs.start("import", lambda progress: workbook_ucl.import_workbook(
                ctx, stored, progress, original_name=b.get("file_name")))
        else:
            jid = jobs.start("import", lambda progress: generic.run(
                ctx, stored, b.get("sheet"), b.get("header_row"), b["target"], b.get("mapping", {}),
                b.get("options", {}), original_name=b.get("file_name")))
        return JSON({"job_id": jid})

    async def imports(request: Request):
        rows = rows_to_dicts(ctx.db.query("SELECT * FROM imports ORDER BY id DESC LIMIT 50"))
        for r in rows:
            r["summary"] = json.loads(r.pop("summary_json") or "null")
            r.pop("mapping_json", None)
        return JSON(rows)

    # ------------------------------------------------------------------ modeller och utvärdering
    async def models(request: Request):
        rows = rows_to_dicts(ctx.db.query("SELECT * FROM model_versions ORDER BY family, id"))
        for r in rows:
            r["params"] = json.loads(r.pop("params_json") or "{}")
            g = json.loads(r.pop("gate_report_json") or "null")
            r["gates"] = (g or {}).get("gates")
            r["selection_log"] = (g or {}).get("selection_log")
            r["history"] = rows_to_dicts(ctx.db.query(
                "SELECT * FROM model_status_history WHERE model_version_id=? ORDER BY id DESC", (r["id"],)))
        return JSON(rows)

    async def model_status(request: Request):
        mid = request.path_params["mid"]
        b = await body(request)
        new = b.get("status")
        row = ctx.db.one("SELECT * FROM model_versions WHERE id=?", (mid,))
        if row is None:
            return err("Okänd modell", 404)
        if new == "produktion":
            g = json.loads(row["gate_report_json"] or "{}").get("gates") or {}
            if not g.get("production_possible"):
                return err("Produktionsstatus kräver att alla statusgrindar är uppfyllda: tidsordnad validering "
                           "på orörd holdout och minst 200 frysta förmatchsprognoser per mått.", 409)
        if new not in ("experimentell", "kandidat", "produktion", "arkiverad", "baslinje"):
            return err("Ogiltig status")
        now = to_iso(ctx.clock.now())
        with ctx.db.tx() as c:
            c.execute("UPDATE model_versions SET status=?, status_reason=?, status_changed_at_utc=? WHERE id=?",
                      (new, b.get("reason", "Ändrad av användare"), now, mid))
            c.execute("INSERT INTO model_status_history (model_version_id, old_status, new_status, reason, at_utc) "
                      "VALUES (?,?,?,?,?)", (mid, row["status"], new, b.get("reason", "Användare"), now))
        return JSON({"ok": True})

    async def run_selection(request: Request):
        b = await body(request)
        jid = jobs.start("selection", lambda progress: _strip_summaries(
            selection.run_selection(ctx, b.get("competition", "UCL"), b.get("validation"), b.get("test"), progress)))
        return JSON({"job_id": jid})

    def _strip_summaries(res: dict) -> dict:
        return {k: v for k, v in res.items() if k not in ("summaries",)}

    async def evaluation(request: Request):
        qp = request.query_params
        comp = qp.get("competition")
        runs = {}
        for mid in ("V2-2.0", "V3-3.0", "BASE-1.0"):
            r = ctx.db.one("""SELECT * FROM backtest_runs WHERE model_version_id=? ORDER BY id DESC LIMIT 1""", (mid,))
            if r:
                runs[mid] = {"run_id": r["id"], "created_at_utc": r["created_at_utc"],
                             "config": json.loads(r["config_json"]), "summary": json.loads(r["summary_json"])}
        prospective = analytics.prospective_evaluation(ctx, eligible_only=qp.get("eligible", "1") == "1",
                                                       competition=comp)
        return JSON({"backtest": runs, "prospective": prospective,
                     "gate_min_obs": 200, "now_utc": to_iso(ctx.clock.now())})

    # ------------------------------------------------------------------ rapporter och schemaläggning
    async def reports(request: Request):
        rows = rows_to_dicts(ctx.db.query("""SELECT r.*, h.name home, a.name away, c.code competition, m.kickoff_utc
            FROM reports r JOIN matches m ON m.id=r.match_id JOIN teams h ON h.id=m.home_team_id
            JOIN teams a ON a.id=m.away_team_id JOIN competitions c ON c.id=m.competition_id
            ORDER BY r.created_at_utc DESC LIMIT 300"""))
        for r in rows:
            r["exists"] = Path(r["path"]).exists()
        return JSON(rows)

    async def report_file(request: Request):
        r = ctx.db.one("SELECT * FROM reports WHERE id=?", (int(request.path_params["rid"]),))
        if r is None or not Path(r["path"]).exists():
            return err("Rapportfilen saknas", 404)
        return FileResponse(r["path"], media_type="application/pdf", filename=Path(r["path"]).name)

    async def report_test(request: Request):
        """Skapa en tydligt märkt testrapport för valfri match utan att vänta på T−30."""
        b = await body(request)
        mid = int(b["match_id"])
        info = forecast.match_info(ctx, mid)
        now = ctx.clock.now()
        ko = parse_iso(info["kickoff_utc"])
        cutoff = min(now, ko - timedelta(minutes=30))  # type: ignore[operator]
        rep = scheduler.create_report(ctx, mid, kind="test", cutoff=cutoff, created_by="user",
                                      notes=["TESTRAPPORT – skapad manuellt för att verifiera PDF-flödet. Ingår inte i "
                                             "utvärderingen."])
        return JSON(rep)

    async def scheduler_status(request: Request):
        return JSON(scheduler.status(ctx))

    async def scheduler_tick(request: Request):
        return JSON(scheduler.tick(ctx, ctx.extras.get("sync_fn")))

    async def scheduler_jobs(request: Request):
        rows = ctx.db.query("""SELECT j.*, h.name home, a.name away, c.code competition FROM report_jobs j
            JOIN matches m ON m.id=j.match_id JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
            JOIN competitions c ON c.id=m.competition_id ORDER BY j.due_at_utc DESC LIMIT 200""")
        return JSON(rows_to_dicts(rows))

    async def simulate(request: Request):
        if not allow_simulation:
            return err("Simulerad klocka är avstängd (starta med MATCHIQ_ALLOW_SIMULATION=1).", 403)
        b = await body(request)
        from ..timeutil import FakeClock
        if not isinstance(ctx.clock, FakeClock):
            return err("Backend kör med systemklocka.", 409)
        ctx.clock.set(parse_iso(b["now_utc"]))  # type: ignore[arg-type]
        ctx.repo.clock = ctx.clock
        return JSON(scheduler.tick(ctx, None))

    # ------------------------------------------------------------------ drift
    async def notifications(request: Request):
        unread = request.query_params.get("unread") == "1"
        undelivered = request.query_params.get("undelivered") == "1"
        q = "SELECT * FROM notifications WHERE 1=1"
        if unread:
            q += " AND read=0"
        if undelivered:
            q += " AND delivered_os=0"
        rows = rows_to_dicts(ctx.db.query(q + " ORDER BY id DESC LIMIT 100"))
        return JSON(rows)

    async def notifications_mark(request: Request):
        b = await body(request)
        ids = [int(i) for i in b.get("ids", [])]
        field = "delivered_os" if b.get("delivered") else "read"
        if ids:
            ctx.db.execute(f"UPDATE notifications SET {field}=1 WHERE id IN ({','.join('?' * len(ids))})", ids)
        elif b.get("all"):
            ctx.db.execute(f"UPDATE notifications SET {field}=1")
        return JSON({"ok": True})

    async def settings_get(request: Request):
        return JSON(ctx.all_settings())

    async def settings_put(request: Request):
        b = await body(request)
        allowed = {"theme", "background_mode", "autostart", "report_offset_minutes", "notify_os",
                   "default_competition", "first_run_done"}
        for k, v in b.items():
            if k in allowed:
                if k == "report_offset_minutes" and int(v) != 30:
                    return err("Rapporttiden är låst till T−30 enligt kravspecifikationen.")
                ctx.set_setting(k, v)
        return JSON(ctx.all_settings())

    async def secrets_get(request: Request):
        return JSON(secrets_store.status())

    async def secrets_put(request: Request):
        b = await body(request)
        try:
            secrets_store.set_secret(request.path_params["name"], b.get("value", ""))
        except (KeyError, ValueError) as e:
            return err(str(e))
        except Exception as e:  # noqa: BLE001
            return err(f"Kunde inte spara i nyckelförrådet: {e}", 500)
        return JSON({"ok": True})

    async def secrets_delete(request: Request):
        secrets_store.delete_secret(request.path_params["name"])
        return JSON({"ok": True})

    async def db_info(request: Request):
        backups = sorted(ctx.paths.backups.glob("*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
        exports = sorted(ctx.paths.exports.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        return JSON({"path": str(ctx.paths.db), "data_dir": str(ctx.paths.root),
                     "bytes": ctx.paths.db.stat().st_size, "schema_version": ctx.db.schema_version(),
                     "migrations": rows_to_dicts(ctx.db.query("SELECT * FROM schema_migrations ORDER BY version")),
                     "backups": [{"path": str(p), "bytes": p.stat().st_size} for p in backups[:20]],
                     "exports": [{"path": str(p), "bytes": p.stat().st_size} for p in exports[:20]],
                     "tables": {t: ctx.db.scalar(f'SELECT COUNT(*) FROM "{t}"') for t in ctx.db.table_names()}})

    async def db_backup(request: Request):
        p = ctx.db.backup("manuell")
        return JSON({"path": str(p)})

    async def db_export(request: Request):
        stamp = ctx.clock.now().strftime("%Y%m%d-%H%M")
        out = ctx.paths.exports / f"matchiq-export-{stamp}.zip"
        manifest = ctx.db.export_bundle(out)
        return JSON({"path": str(out), "manifest": {k: v for k, v in manifest.items() if k != "files"}})

    async def db_import(request: Request):
        b = await body(request)
        p = Path(b.get("path", ""))
        if not p.exists():
            return err("Filen finns inte")
        try:
            res = ctx.db.import_bundle(p)
        except ValueError as e:
            return err(str(e))
        ctx.extras.pop("store_cache", None)
        return JSON(res)

    async def job_get(request: Request):
        j = jobs.get(request.path_params["jid"])
        return JSON(j) if j else err("Okänt jobb", 404)

    async def jobs_list(request: Request):
        return JSON(jobs.list())

    async def sync_now(request: Request):
        jid = jobs.start("sync", lambda progress: sync.sync_cycle(ctx))
        return JSON({"job_id": jid})

    routes = [
        Route("/api/health", health), Route("/api/meta", meta),
        Route("/api/competitions", competitions), Route("/api/matches", matches),
        Route("/api/matches/{mid:int}", match_detail),
        Route("/api/matches/{mid:int}/freeze", match_freeze, methods=["POST"]),
        Route("/api/matches/{mid:int}/outcome", match_outcome, methods=["POST", "PUT"]),
        Route("/api/teams", teams), Route("/api/teams/merge", team_merge, methods=["POST"]),
        Route("/api/teams/{tid:int}", team_detail), Route("/api/teams/{tid:int}", team_update, methods=["PATCH"]),
        Route("/api/teams/{tid:int}/aliases", team_alias, methods=["POST"]),
        Route("/api/teams/{tid:int}/crest", team_crest, methods=["POST"]),
        Route("/api/crests/{name}", crest_file),
        Route("/api/sources", sources), Route("/api/sources/{sid}/training", source_training, methods=["POST"]),
        Route("/api/sources/{sid}/enabled", source_enabled, methods=["POST"]),
        Route("/api/sources/{sid}/sync", source_sync, methods=["POST"]),
        Route("/api/sync", sync_now, methods=["POST"]),
        Route("/api/fetches", fetches), Route("/api/coverage", coverage), Route("/api/standings", standings),
        Route("/api/changelog", changelog),
        Route("/api/imports", imports), Route("/api/imports/inspect", import_inspect, methods=["POST"]),
        Route("/api/imports/preview", import_preview, methods=["POST"]),
        Route("/api/imports/run", import_run, methods=["POST"]),
        Route("/api/models", models), Route("/api/models/{mid}/status", model_status, methods=["POST"]),
        Route("/api/models/selection", run_selection, methods=["POST"]),
        Route("/api/evaluation", evaluation),
        Route("/api/reports", reports), Route("/api/reports/{rid:int}/file", report_file),
        Route("/api/reports/test", report_test, methods=["POST"]),
        Route("/api/scheduler", scheduler_status), Route("/api/scheduler/tick", scheduler_tick, methods=["POST"]),
        Route("/api/scheduler/jobs", scheduler_jobs),
        Route("/api/scheduler/simulate", simulate, methods=["POST"]),
        Route("/api/notifications", notifications),
        Route("/api/notifications/mark", notifications_mark, methods=["POST"]),
        Route("/api/settings", settings_get), Route("/api/settings", settings_put, methods=["PUT"]),
        Route("/api/secrets", secrets_get), Route("/api/secrets/{name}", secrets_put, methods=["PUT"]),
        Route("/api/secrets/{name}", secrets_delete, methods=["DELETE"]),
        Route("/api/db", db_info), Route("/api/db/backup", db_backup, methods=["POST"]),
        Route("/api/db/export", db_export, methods=["POST"]), Route("/api/db/import", db_import, methods=["POST"]),
        Route("/api/jobs", jobs_list), Route("/api/jobs/{jid}", job_get),
    ]
    star = Starlette(routes=routes)
    return SecurityMiddleware(star, token, extra_hosts)
