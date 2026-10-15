"""Simulera en hel matchdag med T−30-schemaläggaren på en KOPIA av databasen (simulerad klocka).

    python scripts/simulate_matchday.py --data-dir DEMO --copy-to SIM --start 2026-10-20T16:00:00Z --end 2026-10-21T19:00:00Z

Visar att T−30-jobben körs exakt vid rätt tid utan att vänta på riktiga matcher. Originaldatabasen
påverkas inte. Rapporterna märks "SIMULERAD KLOCKA".
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from matchiq import scheduler  # noqa: E402
from matchiq.core import init_app  # noqa: E402
from matchiq.timeutil import FakeClock, parse_iso, to_iso  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--copy-to", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    a = ap.parse_args()
    src, dst = Path(a.data_dir), Path(a.copy_to)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    from matchiq.db import Database
    Database(src / "matchiq.sqlite").backup(dest=dst / "matchiq.sqlite")
    clock = FakeClock(parse_iso(a.start))  # type: ignore[arg-type]
    app = init_app(dst, clock)
    end = parse_iso(a.end)
    print(scheduler.tick(app))
    while True:
        nxt = app.db.one("SELECT MIN(due_at_utc) AS d FROM report_jobs WHERE status='pending' AND due_at_utc<=?",
                         (to_iso(end),))
        if not nxt or not nxt["d"]:
            break
        clock.set(parse_iso(nxt["d"]) + timedelta(seconds=5))  # type: ignore[operator]
        st = scheduler.tick(app)
        print(f"{to_iso(clock.now())}: {st['reports']} rapport(er)")
    for r in app.db.query("""SELECT r.kind, r.created_at_utc, r.data_cutoff_utc, r.path, h.name h, a.name a
                             FROM reports r JOIN matches m ON m.id=r.match_id JOIN teams h ON h.id=m.home_team_id
                             JOIN teams a ON a.id=m.away_team_id ORDER BY r.created_at_utc"""):
        print(f"  {r['kind']:5} {r['h']} – {r['a']}: skapad {r['created_at_utc']}, datagräns {r['data_cutoff_utc']}")
        print(f"        {r['path']}")


if __name__ == "__main__":
    main()
