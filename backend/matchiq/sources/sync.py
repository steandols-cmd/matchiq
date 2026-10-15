"""Synkorkestrering med adaptiv pollning efter avstånd till avspark och källornas villkor."""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timedelta

from ..core import App
from ..timeutil import parse_iso, to_iso
from .api_football import ApiFootballAdapter
from .base import Adapter
from .football_data_couk import FootballDataCoUkAdapter
from .football_data_org import FootballDataOrgAdapter
from .http import HttpClient, SourceBlocked
from .odds_api import OddsApiAdapter
from .openfootball import OpenFootballAdapter
from .statsbomb import StatsBombAdapter
from .uefa import UefaAdapter
from .wyscout import WyscoutAdapter

log = logging.getLogger("matchiq.sync")
ADAPTERS: dict[str, type[Adapter]] = {
    "openfootball": OpenFootballAdapter, "statsbomb_open": StatsBombAdapter,
    "football_data_couk": FootballDataCoUkAdapter, "football_data_org": FootballDataOrgAdapter,
    "api_football": ApiFootballAdapter, "the_odds_api": OddsApiAdapter, "uefa": UefaAdapter,
    "wyscout_public": WyscoutAdapter,
}
# Historikhämtning: OpenFootball först (spelscheman och resultat som övriga källors lag kopplas mot).
BACKFILL_ORDER = ["openfootball", "wyscout_public", "statsbomb_open", "api_football"]
GLOBAL_JOBS = [("openfootball", "fixtures_results"), ("football_data_org", "fixtures"), ("api_football", "fixtures"),
               ("the_odds_api", "odds"), ("statsbomb_open", "matches"), ("football_data_couk", "results")]


def nearest_kickoff_delta(app: App) -> timedelta | None:
    now = app.clock.now()
    r = app.db.one("""SELECT MIN(kickoff_utc) AS k FROM matches WHERE status IN ('scheduled','live')
                      AND kickoff_utc >= ?""", (to_iso(now - timedelta(hours=3)),))
    if not r or not r["k"]:
        return None
    return parse_iso(r["k"]) - now  # type: ignore[operator]


def interval_for(source_id: str, job: str, delta: timedelta | None) -> timedelta:
    """Pollningsintervall: tätare nära avspark, glesare annars. Källans minsta intervall gäller alltid."""
    if job == "matches":            # StatsBomb – sällan uppdaterat
        return timedelta(days=7)
    if job == "results" and source_id == "football_data_couk":
        return timedelta(days=3)
    if delta is None:
        return timedelta(hours=24)
    h = delta.total_seconds() / 3600
    if source_id == "the_odds_api":
        return timedelta(hours=1) if h < 6 else (timedelta(hours=6) if h < 48 else timedelta(hours=24))
    if h < -0:                      # pågående/nyss spelade matcher: resultat och statistik
        return timedelta(hours=1)
    if h < 3:
        return timedelta(minutes=15)
    if h < 24:
        return timedelta(hours=3)
    if h < 24 * 7:
        return timedelta(hours=12)
    return timedelta(hours=24)


def _state(app: App, source_id: str, job: str, scope: str = "") -> dict:
    r = app.db.one("SELECT * FROM sync_state WHERE source_id=? AND job=? AND scope=?", (source_id, job, scope))
    return dict(r) if r else {}


def _save_state(app: App, source_id: str, job: str, scope: str, status: str, error: str | None,
                next_run: datetime) -> None:
    app.db.execute("""INSERT INTO sync_state (source_id, job, scope, last_run_utc, next_run_utc, last_status, last_error)
        VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_id, job, scope) DO UPDATE SET last_run_utc=excluded.last_run_utc,
        next_run_utc=excluded.next_run_utc, last_status=excluded.last_status, last_error=excluded.last_error""",
                   (source_id, job, scope, to_iso(app.clock.now()), to_iso(next_run), status, error))


def run_source(app: App, source_id: str, job: str | None = None, http: HttpClient | None = None, **scope) -> dict:
    cls = ADAPTERS.get(source_id)
    if cls is None:
        return {"status": "error", "error": f"Ingen adapter för {source_id}"}
    ad = cls(app, http)
    job = job or ad.jobs[0]
    try:
        res = ad.run(job, **scope)
        status, err = "ok", None
    except SourceBlocked as e:
        res, status, err = ad.summary(), "blocked", str(e)
    except Exception as e:  # noqa: BLE001
        log.error("Synk %s/%s misslyckades: %s", source_id, job, traceback.format_exc())
        res, status, err = ad.summary(), "error", repr(e)
    nxt = app.clock.now() + interval_for(source_id, job, nearest_kickoff_delta(app))
    _save_state(app, source_id, job, str(scope.get("match_id") or ""), status, err, nxt)
    return {"status": status, "error": err, "result": res, "next_run_utc": to_iso(nxt)}


def run_backfill(app: App, source_ids: list[str] | None = None, http: HttpClient | None = None, progress=None,
                 competitions: list[str] | None = None, seasons: list[int] | None = None) -> list[dict]:
    """Hämta historik från de valda källorna i rätt ordning. Avstängda källor och källor utan nyckel
    redovisas med orsak i stället för att hoppas över tyst."""
    enabled = {r["id"] for r in app.db.query("SELECT id FROM sources WHERE enabled=1")}
    out = []
    for sid in [s for s in BACKFILL_ORDER if source_ids is None or s in source_ids]:
        if sid not in enabled:
            out.append({"source": sid, "status": "skipped", "error": "Källan är inte aktiverad"})
            continue
        scope: dict = {"progress": progress}
        if competitions:
            scope["competitions"] = competitions
        if seasons and sid in ("openfootball", "api_football"):
            scope["seasons"] = seasons
        out.append({"source": sid, **run_source(app, sid, "backfill", http, **scope)})
    return out


def sync_cycle(app: App, http: HttpClient | None = None) -> list[dict]:
    """Kör de globala synkjobb som har förfallit. Avstängda källor och källor utan nyckel hoppas över."""
    now = app.clock.now()
    out = []
    enabled = {r["id"] for r in app.db.query("SELECT id FROM sources WHERE enabled=1")}
    for source_id, job in GLOBAL_JOBS:
        if source_id not in enabled:
            continue
        st = _state(app, source_id, job)
        if st.get("next_run_utc") and parse_iso(st["next_run_utc"]) > now:  # type: ignore[operator]
            continue
        out.append({"source": source_id, "job": job, **run_source(app, source_id, job, http)})
    return out


def sync_match(app: App, match_id: int, http: HttpClient | None = None) -> list[dict]:
    """Riktad uppdatering inför T−30: elvor och frånvaro från källor som är aktiverade."""
    enabled = {r["id"] for r in app.db.query("SELECT id FROM sources WHERE enabled=1")}
    out = []
    for source_id, job in (("api_football", "lineups"), ("api_football", "injuries"), ("uefa", "lineups")):
        if source_id in enabled:
            out.append({"source": source_id, "job": job,
                        **run_source(app, source_id, job, http, match_id=match_id)})
    return out


def sources_overview(app: App) -> list[dict]:
    rows = app.db.query("""SELECT s.id, s.name, s.enabled, (SELECT MAX(started_at_utc) FROM fetches f WHERE f.source_id=s.id)
        AS last_fetch, (SELECT COUNT(*) FROM fetches f WHERE f.source_id=s.id) AS fetches,
        (SELECT COUNT(*) FROM fetches f WHERE f.source_id=s.id AND (f.parser_status='error' OR f.http_status>=400))
        AS failed FROM sources s ORDER BY s.id""")
    out = []
    for r in rows:
        states = [dict(x) for x in app.db.query("SELECT job, scope, last_run_utc, next_run_utc, last_status, last_error "
                                                "FROM sync_state WHERE source_id=? AND job NOT LIKE '\\_%' ESCAPE '\\'",
                                                (r["id"],))]
        out.append({**dict(r), "jobs": states})
    return out
