"""Bygg en demodatabas från den tidigare arbetsboken (för skärmbilder och test-PDF).

    python scripts/make_demo.py --data-dir ./demo-data --workbook UCL_….xlsx [--approve-uefa]

--approve-uefa registrerar ett DOKUMENTERAT användarbeslut (via samma flöde som i appen) om att UEFA-data
får användas för träning i demomiljön. I en ny installation är UEFA-data spärrad tills användaren själv beslutar.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from matchiq import catalog  # noqa: E402
from matchiq.core import init_app  # noqa: E402
from matchiq.importers.workbook_ucl import import_workbook  # noqa: E402
from matchiq.models.selection import run_selection  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--workbook", required=True)
    ap.add_argument("--approve-uefa", action="store_true")
    ap.add_argument("--skip-selection", action="store_true")
    a = ap.parse_args()
    app = init_app(Path(a.data_dir))
    t = time.time()
    s = import_workbook(app, Path(a.workbook), original_name=Path(a.workbook).name)
    print(f"Import klar på {time.time() - t:.1f} s; lag att granska: {s['teams_needing_review']}")
    for row in s["inventory"]:
        print(f"  {row['status']:<15} {row['label']}: förväntat {row['expected']}, i filen {row['found']}")
    if a.approve_uefa:
        catalog.set_training_approval(
            app.db, "uefa", True,
            "Demomiljö: godkänt för lokal, privat analys så att alla mått kan visas. Granska UEFA:s villkor "
            "innan skarp användning.", app.clock.now())
        print("UEFA godkänd för träning i demomiljön (dokumenterat beslut).")
    if not a.skip_selection:
        t = time.time()
        r = run_selection(app, "UCL", progress=lambda m, d, n: print(f"  [{d}/{n}] {m}", flush=True))
        print(f"Modellval klart på {time.time() - t:.1f} s: {r['params']} -> {r['gates']['suggested_status']}")


if __name__ == "__main__":
    main()
