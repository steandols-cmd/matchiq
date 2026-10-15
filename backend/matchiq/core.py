"""Applikationskontext: datamapp, databas, klocka, repository och inställningar."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import catalog
from .aliases_seed import seed_aliases
from .config import Paths, get_paths
from .db import Database
from .entities import Repo
from .timeutil import Clock, SystemClock, to_iso

log = logging.getLogger("matchiq")

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "matchiq-dark",
    "background_mode": False,
    "autostart": False,
    "report_offset_minutes": 30,
    "notify_os": True,
    "default_competition": "UCL",
    "first_run_done": False,
}


@dataclass
class App:
    paths: Paths
    db: Database
    clock: Clock
    repo: Repo
    extras: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- settings
    def get_setting(self, key: str) -> Any:
        r = self.db.one("SELECT value_json FROM settings WHERE key=?", (key,))
        if r is None:
            return DEFAULT_SETTINGS.get(key)
        return json.loads(r["value_json"])

    def all_settings(self) -> dict:
        out = dict(DEFAULT_SETTINGS)
        for r in self.db.query("SELECT key, value_json FROM settings"):
            out[r["key"]] = json.loads(r["value_json"])
        return out

    def set_setting(self, key: str, value: Any) -> None:
        self.db.execute("""INSERT INTO settings (key, value_json, updated_at_utc) VALUES (?,?,?)
                           ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                           updated_at_utc=excluded.updated_at_utc""",
                        (key, json.dumps(value), to_iso(self.clock.now())))

    def notify(self, title: str, body: str = "", level: str = "info", match_id: int | None = None,
               report_id: int | None = None) -> int:
        cur = self.db.execute("""INSERT INTO notifications (created_at_utc, level, title, body, match_id, report_id)
                                 VALUES (?,?,?,?,?,?)""",
                              (to_iso(self.clock.now()), level, title, body, match_id, report_id))
        return int(cur.lastrowid)


def init_app(data_dir: Path | None = None, clock: Clock | None = None) -> App:
    paths = get_paths(data_dir)
    clock = clock or SystemClock()
    db = Database(paths.db, paths.backups)
    applied = db.migrate()
    if applied:
        log.info("Migreringar applicerade: %s", applied)
    catalog.seed(db, clock.now())
    repo = Repo(db, clock)
    seed_aliases(repo, to_iso(clock.now()))  # type: ignore[arg-type]
    return App(paths=paths, db=db, clock=clock, repo=repo)
