"""Startpunkt för backend-sidecaren.

Electron startar processen med miljövariablerna:
    MATCHIQ_TOKEN      – slumpad bearer-token (krävs)
    MATCHIQ_DATA_DIR   – datamapp (valfri; standard per OS)
    MATCHIQ_PARENT_PID – Electron-processens PID; backend avslutas om föräldern försvinner

Servern binds alltid till 127.0.0.1. Port 0 ger en ledig port som skrivs ut som
``MATCHIQ_READY port=<port>`` på stdout när servern tar emot anrop.
"""
from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from . import __version__, scheduler
from .api.app import create_app
from .core import init_app
from .sources import sync
from .timeutil import FakeClock, SystemClock, parse_iso


def _parent_watchdog(pid: int) -> None:
    def alive(p: int) -> bool:
        if sys.platform.startswith("win"):
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x100000, False, p)  # SYNCHRONIZE
            if not h:
                return False
            r = ctypes.windll.kernel32.WaitForSingleObject(h, 0)
            ctypes.windll.kernel32.CloseHandle(h)
            return r == 0x102  # WAIT_TIMEOUT => lever
        try:
            os.kill(p, 0)
            return True
        except OSError:
            return False

    while True:
        time.sleep(3)
        if not alive(pid):
            logging.getLogger("matchiq").info("Föräldraprocessen är borta – avslutar backend.")
            os._exit(0)


class SyncThread(threading.Thread):
    def __init__(self, app, interval_s: float = 300.0):
        super().__init__(name="matchiq-sync", daemon=True)
        self.app, self.interval_s = app, interval_s
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                sync.sync_cycle(self.app)
            except Exception:  # noqa: BLE001
                logging.getLogger("matchiq.sync").exception("Synkfel")
            self._stop.wait(self.interval_s)


def main(argv: list[str] | None = None) -> None:
    from matchiq.config import ensure_utf8_stdio
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(prog="matchiq-backend")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MATCHIQ_PORT", "0")))
    ap.add_argument("--data-dir", default=os.environ.get("MATCHIQ_DATA_DIR"))
    ap.add_argument("--dev-token", action="store_true", help="skriv ut en genererad token (endast utveckling)")
    ap.add_argument("--no-scheduler", action="store_true")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--web-dir", default=os.environ.get("MATCHIQ_WEB_DIR"),
                    help="servera byggt gränssnitt från samma port (webbläsarläge)")
    ap.add_argument("--simulated-now", help="starta med simulerad klocka (UTC ISO), kräver MATCHIQ_ALLOW_SIMULATION=1")
    args = ap.parse_args(argv)

    token = os.environ.get("MATCHIQ_TOKEN")
    if not token:
        if not args.dev_token:
            print("MATCHIQ_TOKEN saknas", file=sys.stderr)
            sys.exit(2)
        token = secrets.token_urlsafe(32)
        print(f"MATCHIQ_DEV_TOKEN {token}", flush=True)
    allow_sim = os.environ.get("MATCHIQ_ALLOW_SIMULATION") == "1"
    clock = SystemClock()
    if args.simulated_now:
        if not allow_sim:
            print("Simulerad klocka kräver MATCHIQ_ALLOW_SIMULATION=1", file=sys.stderr)
            sys.exit(2)
        clock = FakeClock(parse_iso(args.simulated_now))  # type: ignore[arg-type]

    app = init_app(Path(args.data_dir) if args.data_dir else None, clock)
    handler = RotatingFileHandler(app.paths.logs / "backend.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler(sys.stderr)],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("matchiq").info("MatchIQ backend %s startar, data: %s", __version__, app.paths.root)

    ppid = os.environ.get("MATCHIQ_PARENT_PID")
    if ppid and ppid.isdigit():
        threading.Thread(target=_parent_watchdog, args=(int(ppid),), daemon=True).start()

    sync_fn = None if args.no_sync else (lambda match_id: sync.sync_match(app, match_id))
    app.extras["sync_fn"] = sync_fn
    if not args.no_scheduler:
        th = scheduler.SchedulerThread(app, sync_fn)
        app.extras["scheduler_thread"] = th
        th.start()
    if not args.no_sync and not clock.simulated:
        SyncThread(app).start()

    asgi = create_app(app, token, allow_simulation=allow_sim, web_dir=args.web_dir)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    config = uvicorn.Config(asgi, log_level="warning", access_log=False, lifespan="off")
    server = uvicorn.Server(config)

    def announce() -> None:
        while not server.started:
            time.sleep(0.05)
        print(f"MATCHIQ_READY port={port}", flush=True)

    threading.Thread(target=announce, daemon=True).start()
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
