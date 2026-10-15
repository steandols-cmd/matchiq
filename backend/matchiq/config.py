"""Konfiguration och sökvägar.

Datamappen är avsiktligt lätt att hitta och kopiera ut (t.ex. inför en
systemuppdatering eller migrering):

* macOS:   ~/Library/Application Support/MatchIQ/data
* Windows: %APPDATA%\\MatchIQ\\data
* Linux:   ~/.local/share/matchiq/data

Mappen kan pekas om med miljövariabeln ``MATCHIQ_DATA_DIR``.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def default_data_dir() -> Path:
    env = os.environ.get("MATCHIQ_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "MatchIQ" / "data"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / "MatchIQ" / "data"
    xdg = os.environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(xdg) / "matchiq" / "data"


def resource_dir() -> Path:
    """Katalog med paketresurser (fonter, migreringar). Fungerar även i PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "matchiq"
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def db(self) -> Path:
        return self.root / "matchiq.sqlite"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def imports(self) -> Path:
        return self.root / "imports"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def crests(self) -> Path:
        return self.root / "crests"

    def ensure(self) -> "Paths":
        for p in (self.root, self.backups, self.reports, self.raw, self.imports,
                  self.exports, self.logs, self.crests):
            p.mkdir(parents=True, exist_ok=True)
        return self


def get_paths(root: Path | None = None) -> Paths:
    return Paths(root or default_data_dir()).ensure()
