"""Schemaläggning: T−30-rapporter, adaptiv datasynk, missade deadlines och utfallsinsamling.

* Varje kommande match får ett jobb med förfallotid = officiell avspark − 30 min (UTC).
* Vid T−30 fryses V2/V3/baslinje med datagräns exakt T−30 och en PDF arkiveras.
  Startelvor hämtas från T−40 (kontrollpunkter T−40, T−36, T−32) tills båda är bekräftade, så att elvor
  publicerade fram till T−30 kommer med.
* Om appen eller nätet var nere vid T−30 låtsas appen aldrig att rapporten skapades i tid:
  jobbet markeras som missat och en tydligt märkt SEN rapport skapas vid återhämtning med faktisk
  skapandetid och faktisk datagräns (aldrig senare än avspark).
* Klockan är injicerbar (FakeClock) så att hela flödet kan testas utan att vänta på en riktig match.
"""
from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from .core import App
from .db import sha256_file
from .forecast import freeze, load_snapshot, match_info
from .reports.pdf import build_report, report_filename
from .timeutil import parse_iso, to_iso, to_stockholm

log = logging.getLogger("matchiq.scheduler")
GRACE = timedelta(minutes=3)            # jobbet räknas som "i tid" om det startar inom 3 min efter T−30
HORIZON = timedelta(days=21)             # schemalägg rapporter för matcher inom 3 veckor


def offset(app: App) -> timedelta:
    return timedelta(minutes=int(app.get_setting("report_offset_minutes") or 30))


# ------------------------------------------------------------------------------ jobb
def ensure_jobs(app: App) -> dict:
    now = app.clock.now()
    off = offset(app)
    created = superseded = 0
    # Endast matcher som var kända FÖRE sin T−30 får ett T−30-jobb. En match som registreras efter sin
    # deadline (t.ex. historisk import) får ingen automatisk "sen" rapport – den kan skapas manuellt.
    rows = app.db.query("""SELECT id, kickoff_utc, created_at_utc FROM matches WHERE status='scheduled'
                           AND kickoff_time_known=1 AND kickoff_utc > ? AND kickoff_utc <= ?""",
                        (to_iso(now - timedelta(days=7)), to_iso(now + HORIZON)))
    with app.db.tx() as c:
        for r in rows:
            ko = parse_iso(r["kickoff_utc"])
            due = to_iso(ko - off)  # type: ignore[operator]
            if r["created_at_utc"] > due:  # type: ignore[operator]
                continue
            jobs = c.execute("SELECT * FROM report_jobs WHERE match_id=? AND kind='T-30'", (r["id"],)).fetchall()
            if any(j["due_at_utc"] == due for j in jobs):
                continue
            for j in jobs:
                if j["status"] == "pending":
                    c.execute("UPDATE report_jobs SET status='superseded', last_error=? WHERE id=?",
                              (f"Avsparkstiden ändrades till {r['kickoff_utc']}", j["id"]))
                    superseded += 1
            if any(j["status"] in ("done", "late_done", "running") for j in jobs) and ko < now:  # type: ignore[operator]
                continue
            c.execute("""INSERT OR IGNORE INTO report_jobs (match_id, kind, due_at_utc, kickoff_utc, status,
                         created_at_utc) VALUES (?,?,?,?, 'pending', ?)""",
                      (r["id"], "T-30", due, r["kickoff_utc"], to_iso(now)))
            created += 1
    return {"created": created, "superseded": superseded}


def _report_dir(app: App, kickoff_utc: str, comp: str) -> Path:
    loc = to_stockholm(kickoff_utc)
    return app.paths.reports / f"{loc:%Y-%m-%d}" / comp


def create_report(app: App, match_id: int, *, kind: str, cutoff: datetime, created_by: str,
                  scheduled_for: datetime | None = None, job_id: int | None = None,
                  notes: list[str] | None = None) -> dict:
    """Frys snapshots och arkivera en PDF. Returnerar rapportraden."""
    info = match_info(app, match_id)
    snap_kind = "late" if kind == "late" else ("test" if kind == "test" else ("T-30" if kind == "T-30" else "manual"))
    fr = freeze(app, match_id, cutoff, kind=snap_kind, created_by=created_by, scheduled_for=scheduled_for,
                job_id=job_id)
    snaps = [load_snapshot(app, sid) for sid in fr["snapshot_ids"].values()]
    created_at = parse_iso(fr["created_at_utc"])
    folder = _report_dir(app, info["kickoff_utc"], info["comp_code"])
    fname = report_filename({"id": match_id, "comp_code": info["comp_code"], "home_name": info["home_name"],
                             "away_name": info["away_name"]}, kind, info["kickoff_utc"])
    path = folder / fname
    n = 2
    while path.exists():  # rapporter skrivs aldrig över
        path = folder / fname.replace(".pdf", f"_{n}.pdf")
        n += 1
    build_report(snaps, path, kind=kind, created_at=created_at, extra_notes=notes)  # type: ignore[arg-type]
    digest = sha256_file(path)
    with app.db.tx() as c:
        cur = c.execute("""INSERT INTO reports (match_id, job_id, kind, is_late, created_at_utc, data_cutoff_utc, path,
            sha256, bytes, snapshot_ids_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (match_id, job_id, kind, 1 if kind == "late" else 0, fr["created_at_utc"], to_iso(cutoff),
                         str(path), digest, path.stat().st_size, __import__("json").dumps(fr["snapshot_ids"])))
        rid = int(cur.lastrowid)
    title = {"T-30": "T−30-rapport klar", "late": "Sen rapport skapad (missad deadline)", "test": "Testrapport klar",
             "manual": "Manuell prognos sparad"}[kind]
    app.notify(f"{title}: {info['home_name']} – {info['away_name']}",
               f"Datagräns {to_stockholm(cutoff):%Y-%m-%d %H:%M}. PDF: {path.name}",
               level="warning" if kind == "late" else "success", match_id=match_id, report_id=rid)
    return {"report_id": rid, "path": str(path), "sha256": digest, "snapshot_ids": fr["snapshot_ids"],
            "created_at_utc": fr["created_at_utc"], "data_cutoff_utc": to_iso(cutoff), "kind": kind}


def lineup_checkpoints(app: App) -> list[int]:
    """Minuter före avspark då startelvor hämtas, t.ex. [40, 36, 32] med T−30-rapport och startpunkt T−40.
    API-Football publicerar elvor 20–40 minuter före avspark, så flera försök behövs före datagränsen."""
    off = int(offset(app).total_seconds() // 60)
    lead = max(int(app.get_setting("lineup_fetch_minutes") or 40), off + 2)
    return sorted({p for p in (lead, lead - 4, off + 2) if p >= off + 2}, reverse=True)


def _lineups_confirmed(app: App, match_id: int) -> bool:
    r = app.db.one("""SELECT COUNT(DISTINCT l.team_id) AS n FROM lineups l JOIN matches m ON m.id=l.match_id
        WHERE l.match_id=? AND l.status='confirmed' AND l.team_id IN (m.home_team_id, m.away_team_id)""", (match_id,))
    return bool(r and r["n"] >= 2)


def lineup_window(app: App, sync_fn) -> int:
    """Hämta startelvor vid kontrollpunkterna (standard T−40, T−36, T−32) för matcher med väntande T−30-jobb.
    Varje kontrollpunkt ger högst ett anrop per match, och hämtningen slutar när båda elvorna är bekräftade.
    Startar appen sent tas de passerade kontrollpunkterna igen med ett enda anrop."""
    now = app.clock.now()
    points = lineup_checkpoints(app)
    off = offset(app)
    rows = app.db.query("""SELECT match_id, kickoff_utc FROM report_jobs WHERE status='pending' AND kind='T-30'
        AND kickoff_utc>? AND kickoff_utc<=?""", (to_iso(now + off), to_iso(now + timedelta(minutes=points[0]))))
    n = 0
    for r in rows:
        mins = (parse_iso(r["kickoff_utc"]) - now).total_seconds() / 60  # type: ignore[operator]
        passed = sum(1 for p in points if mins <= p)
        st = app.db.one("SELECT calls_today FROM sync_state WHERE source_id='scheduler' AND job='lineups' AND scope=?",
                        (str(r["match_id"]),))
        done = int(st["calls_today"]) if st else 0
        if passed <= done:
            continue
        app.db.execute("""INSERT INTO sync_state (source_id, job, scope, last_run_utc, last_status, calls_today)
            VALUES ('scheduler','lineups',?,?,?,?) ON CONFLICT(source_id, job, scope) DO UPDATE SET
            last_run_utc=excluded.last_run_utc, last_status=excluded.last_status, calls_today=excluded.calls_today""",
                       (str(r["match_id"]), to_iso(now), "confirmed" if _lineups_confirmed(app, r["match_id"])
                        else "fetching", passed))
        if _lineups_confirmed(app, r["match_id"]):
            continue
        try:
            sync_fn(r["match_id"])
            n += 1
        except Exception as e:  # noqa: BLE001
            log.warning("Hämtning av startelvor misslyckades: %s", e)
    return n


def run_due_jobs(app: App, sync_fn=None) -> list[dict]:
    """Kör förfallna jobb. sync_fn(match_id) anropas för sista datasynk när den behövs."""
    now = app.clock.now()
    out = []
    jobs = app.db.query("SELECT * FROM report_jobs WHERE status='pending' AND due_at_utc<=? ORDER BY due_at_utc",
                        (to_iso(now),))
    for j in jobs:
        due = parse_iso(j["due_at_utc"])
        ko = parse_iso(j["kickoff_utc"])
        app.db.execute("UPDATE report_jobs SET status='running', started_at_utc=?, attempts=attempts+1 WHERE id=?",
                       (to_iso(now), j["id"]))
        try:
            if now - due <= GRACE:  # type: ignore[operator]
                rep = create_report(app, j["match_id"], kind="T-30", cutoff=due, created_by="scheduler",  # type: ignore[arg-type]
                                    scheduled_for=due, job_id=j["id"])
                app.db.execute("UPDATE report_jobs SET status='done', completed_at_utc=?, report_id=? WHERE id=?",
                               (to_iso(app.clock.now()), rep["report_id"], j["id"]))
            else:
                late_by = int((now - due).total_seconds())  # type: ignore[operator]
                app.db.execute("UPDATE report_jobs SET status='missed', late_by_seconds=? WHERE id=?",
                               (late_by, j["id"]))
                if sync_fn:
                    try:
                        sync_fn(j["match_id"])
                    except Exception as e:  # noqa: BLE001 - sen rapport skapas ändå med befintliga data
                        log.warning("Synk före sen rapport misslyckades: %s", e)
                now2 = app.clock.now()
                cutoff = min(now2, ko)  # type: ignore[type-var]
                notes = [f"Deadline T−30 ({to_stockholm(due):%Y-%m-%d %H:%M}) missades med {late_by // 60} min – appen "
                         "eller nätverket var inte igång. Rapporten är skapad i efterhand med det dataunderlag som "
                         "fanns vid angiven datagräns och ersätter inte en T−30-rapport."]
                if now2 >= ko:  # type: ignore[operator]
                    notes.append("Rapporten skapades efter avspark. Datagränsen är satt till avsparkstiden och "
                                 "matchens egna data används inte, men prognosen räknas inte som förmatchsprognos.")
                rep = create_report(app, j["match_id"], kind="late", cutoff=cutoff, created_by="scheduler",
                                    scheduled_for=due, job_id=j["id"], notes=notes)
                app.db.execute("UPDATE report_jobs SET status='late_done', completed_at_utc=?, report_id=? WHERE id=?",
                               (to_iso(app.clock.now()), rep["report_id"], j["id"]))
            out.append(rep)
        except Exception as e:  # noqa: BLE001
            log.error("Rapportjobb %s misslyckades: %s", j["id"], traceback.format_exc())
            app.db.execute("UPDATE report_jobs SET status='failed', last_error=? WHERE id=?", (repr(e), j["id"]))
            app.notify("Rapportjobb misslyckades", f"Match {j['match_id']}: {e}", level="error",
                       match_id=j["match_id"])
    return out


def refresh_outcomes(app: App) -> int:
    """Fyll i facit (automatiskt) för avslutade matcher som har snapshots men saknar utfall."""
    rows = app.db.query("""SELECT DISTINCT m.id, m.home_team_id, m.away_team_id FROM matches m
        JOIN forecast_snapshots s ON s.match_id=m.id LEFT JOIN match_outcomes o ON o.match_id=m.id
        WHERE m.status='finished' AND o.match_id IS NULL""")
    n = 0
    for r in rows:
        res = app.db.one("""SELECT * FROM match_results WHERE match_id=? AND home_goals_90 IS NOT NULL
            ORDER BY CASE source_id WHEN 'manual' THEN 0 WHEN 'uefa' THEN 1 WHEN 'api_football' THEN 2 ELSE 5 END
            LIMIT 1""", (r["id"],))
        if res is None:
            continue
        st = {}
        for side, tid in (("home", r["home_team_id"]), ("away", r["away_team_id"])):
            s = app.db.one("""SELECT * FROM team_match_stats WHERE match_id=? AND team_id=? ORDER BY
                CASE source_id WHEN 'manual' THEN 0 WHEN 'uefa' THEN 1 WHEN 'api_football' THEN 2 ELSE 5 END LIMIT 1""",
                           (r["id"], tid))
            st[side] = dict(s) if s else {}
        app.db.execute("""INSERT OR IGNORE INTO match_outcomes (match_id, home_goals, away_goals, home_corners,
            away_corners, home_shots, away_shots, home_sot, away_sot, source_id, entered_by, recorded_at_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,'auto',?)""",
                       (r["id"], res["home_goals_90"], res["away_goals_90"], st["home"].get("corners"),
                        st["away"].get("corners"), st["home"].get("shots"), st["away"].get("shots"),
                        st["home"].get("shots_on_target"), st["away"].get("shots_on_target"), res["source_id"],
                        to_iso(app.clock.now())))
        n += 1
    return n


def tick(app: App, sync_fn=None) -> dict:
    """Ett varv i schemaläggaren. Säker att anropa när som helst (idempotent)."""
    j = ensure_jobs(app)
    lineup_syncs = lineup_window(app, sync_fn) if sync_fn else 0
    reports = run_due_jobs(app, sync_fn)
    outcomes = refresh_outcomes(app)
    state = {"last_tick_utc": to_iso(app.clock.now()), "jobs": j, "reports": len(reports), "outcomes": outcomes,
             "lineup_syncs": lineup_syncs}
    app.extras["scheduler_state"] = state
    return state


def status(app: App) -> dict:
    nxt = app.db.one("""SELECT j.*, h.name AS home, a.name AS away FROM report_jobs j JOIN matches m ON m.id=j.match_id
        JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
        WHERE j.status='pending' ORDER BY j.due_at_utc LIMIT 1""")
    counts = {r["status"]: r["n"] for r in app.db.query("SELECT status, COUNT(*) AS n FROM report_jobs GROUP BY status")}
    thread = app.extras.get("scheduler_thread")
    return {
        "running": bool(thread and thread.is_alive()),
        "background_mode": bool(app.get_setting("background_mode")),
        "clock": "simulerad" if app.clock.simulated else "system",
        "now_utc": to_iso(app.clock.now()),
        "next_job": dict(nxt) if nxt else None,
        "job_counts": counts,
        "last": app.extras.get("scheduler_state"),
        "offset_minutes": int(offset(app).total_seconds() // 60),
        "lineup_checkpoints": lineup_checkpoints(app),
    }


class SchedulerThread(threading.Thread):
    """Bakgrundstråd som kör tick() regelbundet. Sover kort så att T−30 träffas med sekundprecision."""

    def __init__(self, app: App, sync_fn=None, interval_s: float = 15.0):
        super().__init__(name="matchiq-scheduler", daemon=True)
        self.app, self.sync_fn, self.interval_s = app, sync_fn, interval_s
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                tick(self.app, self.sync_fn)
            except Exception:  # noqa: BLE001
                log.error("Schemaläggarfel: %s", traceback.format_exc())
            nxt = self.app.db.one("SELECT MIN(due_at_utc) AS d FROM report_jobs WHERE status='pending'")
            wait = self.interval_s
            if nxt and nxt["d"]:
                secs = (parse_iso(nxt["d"]) - self.app.clock.now()).total_seconds()  # type: ignore[operator]
                if 0 < secs < wait:
                    wait = max(secs, 0.5)
            self._stop.wait(wait)
