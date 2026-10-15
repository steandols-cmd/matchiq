"""SQLite-åtkomst, migreringar, säkerhetskopior samt export/import av hela databasen.

Databasen är en enda fil (``matchiq.sqlite``) i datamappen. Inför varje migrering
tas en säkerhetskopia. ``export_bundle`` skapar en portabel zip (SQLite-kopia,
CSV per tabell, schema och manifest med kontrollsummor) som kan läsas in i en ny
version av appen med ``import_bundle`` – vilket gör uppgraderingar och flytt
mellan datorer okomplicerade.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import sqlite3
import threading
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import __version__
from .config import resource_dir
from .timeutil import UTC, to_iso

MIGRATIONS_DIR = resource_dir() / "migrations"
_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


def list_migrations() -> list[tuple[int, str, Path]]:
    out = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _MIGRATION_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), m.group(2), p))
    return out


def latest_schema_version() -> int:
    migs = list_migrations()
    return migs[-1][0] if migs else 0


def _now_iso() -> str:
    return to_iso(datetime.now(UTC))  # type: ignore[return-value]


class Database:
    """Trådsäker wrapper: en anslutning per tråd, skrivningar serialiseras med lås."""

    def __init__(self, path: Path | str, backups_dir: Path | None = None):
        self.path = Path(path)
        self.backups_dir = backups_dir or self.path.parent / "backups"
        self._local = threading.local()
        self.write_lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- anslutningar ---------------------------------------------------------
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.path), timeout=30, isolation_level=None,
                                check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA busy_timeout = 30000")
            c.execute("PRAGMA synchronous = NORMAL")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Skrivtransaktion (BEGIN IMMEDIATE) – serialiserad mellan trådar."""
        with self.write_lock:
            c = self.conn()
            if c.in_transaction:  # nästlad användning: återanvänd yttre transaktion
                yield c
                return
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
            except BaseException:
                c.execute("ROLLBACK")
                raise
            else:
                c.execute("COMMIT")

    # -- hjälpare ---------------------------------------------------------------
    def query(self, sql: str, params: Iterable[Any] | dict = ()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, params).fetchall()

    def one(self, sql: str, params: Iterable[Any] | dict = ()) -> sqlite3.Row | None:
        return self.conn().execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Iterable[Any] | dict = ()) -> Any:
        r = self.conn().execute(sql, params).fetchone()
        return None if r is None else r[0]

    def execute(self, sql: str, params: Iterable[Any] | dict = ()) -> sqlite3.Cursor:
        with self.tx() as c:
            return c.execute(sql, params)

    # -- migreringar -----------------------------------------------------------
    def schema_version(self) -> int:
        c = self.conn()
        c.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at_utc TEXT NOT NULL,
            app_version TEXT NOT NULL, sha256 TEXT NOT NULL)""")
        v = c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        return int(v or 0)

    def migrate(self) -> list[int]:
        """Applicera alla väntande migreringar. Tar säkerhetskopia först om databasen har data."""
        current = self.schema_version()
        pending = [m for m in list_migrations() if m[0] > current]
        if not pending:
            return []
        if current > 0:
            self.backup(reason=f"före-migrering-v{current}-till-v{pending[-1][0]}")
        applied = []
        for version, name, path in pending:
            sql = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode()).hexdigest()
            with self.write_lock:
                c = self.conn()
                c.execute("BEGIN IMMEDIATE")
                try:
                    for stmt in _split_sql(sql):
                        c.execute(stmt)
                    c.execute("INSERT INTO schema_migrations VALUES (?,?,?,?,?)",
                              (version, name, _now_iso(), __version__, digest))
                    c.execute("COMMIT")
                except BaseException:
                    c.execute("ROLLBACK")
                    raise
            applied.append(version)
        if latest_schema_version() > 0 and self.schema_version() > latest_schema_version():
            raise RuntimeError("Databasen har nyare schema än appen – uppdatera appen")
        return applied

    # -- säkerhetskopior --------------------------------------------------------
    def backup(self, reason: str = "manuell", dest: Path | None = None) -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", reason)[:60]
        target = dest or self.backups_dir / f"matchiq-{stamp}-{safe}.sqlite"
        src = self.conn()
        with sqlite3.connect(str(target)) as dst:
            src.backup(dst)
        return target

    # -- export/import ----------------------------------------------------------
    def table_names(self) -> list[str]:
        return [r[0] for r in self.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    def export_bundle(self, out_path: Path) -> dict:
        """Skapa en portabel exportfil (zip) med SQLite-kopia + CSV per tabell + manifest."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_db = out_path.with_suffix(".tmp.sqlite")
        self.backup(dest=tmp_db)
        manifest: dict[str, Any] = {
            "format": "matchiq-export",
            "format_version": 1,
            "app_version": __version__,
            "schema_version": self.schema_version(),
            "created_at_utc": _now_iso(),
            "tables": {},
            "files": {},
        }
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            db_bytes = tmp_db.read_bytes()
            z.writestr("matchiq.sqlite", db_bytes)
            manifest["files"]["matchiq.sqlite"] = hashlib.sha256(db_bytes).hexdigest()
            schema = "\n;\n".join(r[0] for r in self.query(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC, name"))
            z.writestr("schema.sql", schema)
            for t in self.table_names():
                cur = self.conn().execute(f'SELECT * FROM "{t}"')
                cols = [d[0] for d in cur.description]
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(cols)
                n = 0
                for row in cur:
                    w.writerow(["" if v is None else v for v in row])
                    n += 1
                data = buf.getvalue().encode("utf-8")
                name = f"csv/{t}.csv"
                z.writestr(name, data)
                manifest["tables"][t] = {"rows": n, "columns": cols}
                manifest["files"][name] = hashlib.sha256(data).hexdigest()
            z.writestr("README.txt", (
                "MatchIQ databasexport\n"
                "matchiq.sqlite  – komplett databas (öppnas med valfri SQLite-klient)\n"
                "csv/*.csv       – en CSV per tabell (tomt fält = NULL/saknas, aldrig 0)\n"
                "schema.sql      – tabelldefinitioner\n"
                "manifest.json   – schemaversion, radantal och SHA-256 per fil\n"))
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        tmp_db.unlink(missing_ok=True)
        return manifest

    @staticmethod
    def verify_bundle(bundle: Path) -> dict:
        with zipfile.ZipFile(bundle) as z:
            manifest = json.loads(z.read("manifest.json"))
            if manifest.get("format") != "matchiq-export":
                raise ValueError("Filen är ingen MatchIQ-export")
            for name, digest in manifest["files"].items():
                if hashlib.sha256(z.read(name)).hexdigest() != digest:
                    raise ValueError(f"Kontrollsumman stämmer inte för {name}")
        return manifest

    def import_bundle(self, bundle: Path) -> dict:
        """Ersätt aktuell databas med en export. Aktuell databas säkerhetskopieras först."""
        manifest = self.verify_bundle(bundle)
        if manifest["schema_version"] > latest_schema_version():
            raise ValueError("Exporten kommer från en nyare appversion – uppdatera appen först")
        backup = self.backup(reason="före-import-av-export")
        self.close()
        with zipfile.ZipFile(bundle) as z:
            data = z.read("matchiq.sqlite")
        tmp = self.path.with_suffix(".incoming")
        tmp.write_bytes(data)
        for suffix in ("-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)
        shutil.move(str(tmp), str(self.path))
        applied = self.migrate()  # migrera framåt till appens schemaversion
        return {"manifest": manifest, "backup": str(backup), "migrations_applied": applied}


def _split_sql(sql: str) -> list[str]:
    """Dela upp ett SQL-skript i satser (hanterar triggers via sqlite3.complete_statement)."""
    statements: list[str] = []
    buf = ""
    for line in sql.splitlines():
        if line.strip().startswith("--") or not line.strip():
            continue
        buf += line + "\n"
        if sqlite3.complete_statement(buf):
            statements.append(buf.strip())
            buf = ""
    if buf.strip():
        raise ValueError(f"Ofullständig SQL-sats i migrering: {buf[:80]}")
    return statements


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
