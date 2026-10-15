"""Kommandoradsverktyg för drift: migrering, säkerhetskopia, export/import, modellval, testrapport.

Exempel:
    python -m matchiq.cli migrate
    python -m matchiq.cli export --out ~/Desktop/matchiq-export.zip
    python -m matchiq.cli import-db --file ~/Desktop/matchiq-export.zip
    python -m matchiq.cli import-workbook --file UCL_….xlsx
    python -m matchiq.cli select-models
    python -m matchiq.cli simulate-t30 --match 123
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from . import scheduler
from .core import init_app
from .forecast import match_info
from .importers.workbook_ucl import import_workbook
from .models.selection import run_selection
from .timeutil import FakeClock, parse_iso


def main(argv: list[str] | None = None) -> None:
    from matchiq.config import ensure_utf8_stdio
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(prog="matchiq")
    ap.add_argument("--data-dir")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("backup")
    e = sub.add_parser("export")
    e.add_argument("--out", required=True)
    i = sub.add_parser("import-db")
    i.add_argument("--file", required=True)
    w = sub.add_parser("import-workbook")
    w.add_argument("--file", required=True)
    s = sub.add_parser("select-models")
    s.add_argument("--competition", default="UCL")
    t = sub.add_parser("simulate-t30", help="kör T−30-flödet för en match med simulerad klocka")
    t.add_argument("--match", type=int, required=True)
    sub.add_parser("tick")
    args = ap.parse_args(argv)
    data_dir = Path(args.data_dir) if args.data_dir else None

    if args.cmd == "simulate-t30":
        base = init_app(data_dir)
        ko = parse_iso(match_info(base, args.match)["kickoff_utc"])
        clock = FakeClock(ko - timedelta(minutes=31))  # type: ignore[operator]
        app = init_app(data_dir, clock)
        app.db.execute("UPDATE matches SET created_at_utc=MIN(created_at_utc, ?) WHERE id=?",
                       (clock.now().strftime("%Y-%m-%dT%H:%M:%SZ"), args.match))
        scheduler.ensure_jobs(app)
        clock.advance(minutes=1, seconds=5)
        print(json.dumps(scheduler.run_due_jobs(app), ensure_ascii=False, indent=2))
        return
    app = init_app(data_dir)
    if args.cmd == "migrate":
        print(f"Schemaversion: {app.db.schema_version()}")
    elif args.cmd == "backup":
        print(app.db.backup("cli"))
    elif args.cmd == "export":
        m = app.db.export_bundle(Path(args.out).expanduser())
        print(json.dumps({k: v for k, v in m.items() if k != "files"}, ensure_ascii=False, indent=2))
    elif args.cmd == "import-db":
        print(json.dumps(app.db.import_bundle(Path(args.file).expanduser()), ensure_ascii=False, indent=2,
                         default=str))
    elif args.cmd == "import-workbook":
        res = import_workbook(app, Path(args.file).expanduser())
        print(json.dumps({k: v for k, v in res.items() if k != "inventory"}, ensure_ascii=False, indent=2))
        for row in res["inventory"]:
            print(f"  {row['status']:<15} {row['label']}: förväntat {row['expected']}, hittat {row['found']}")
    elif args.cmd == "select-models":
        res = run_selection(app, args.competition, progress=lambda m, d, t: print(f"[{d}/{t}] {m}"))
        print(json.dumps({"params": res["params"], "gates": res["gates"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "tick":
        print(json.dumps(scheduler.tick(app), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
