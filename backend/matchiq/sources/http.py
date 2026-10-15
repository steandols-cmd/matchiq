"""Hämtningslager för källadaptrar: anropsgränser, dygnskvot, robots.txt, återförsök med backoff,
villkorliga anrop (ETag/Last-Modified), råfilsarkiv med SHA-256 och en loggrad per hämtning.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests

from .. import __version__
from ..core import App
from ..timeutil import to_iso

log = logging.getLogger("matchiq.http")
USER_AGENT = f"MatchIQ/{__version__} (lokal desktopapp för egen analys)"


class SourceBlocked(Exception):
    """Källan får inte hämtas (avstängd, saknar nyckel, robots.txt eller kvot slut)."""


@dataclass
class FetchResult:
    fetch_id: int
    status: int | None
    content: bytes | None
    not_modified: bool
    headers: dict

    def json(self) -> Any:
        return json.loads(self.content or b"null")

    def text(self) -> str:
        data = self.content or b""
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", "replace")


class HttpClient:
    _last_call: dict[str, float] = {}
    _robots: dict[str, urllib.robotparser.RobotFileParser] = {}
    _lock = threading.Lock()

    def __init__(self, app: App, session: requests.Session | None = None, sleep=time.sleep, max_attempts: int = 3):
        self.app = app
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.sleep = sleep
        self.max_attempts = max_attempts

    # ---------------------------------------------------------------- policy
    def _source(self, source_id: str) -> dict:
        r = self.app.db.one("SELECT * FROM sources WHERE id=?", (source_id,))
        if r is None:
            raise SourceBlocked(f"Okänd källa {source_id}")
        return dict(r)

    def check_allowed(self, source_id: str) -> dict:
        src = self._source(source_id)
        if not src["enabled"]:
            raise SourceBlocked(f"{src['name']} är inte aktiverad.")
        if src["automated_fetch"] in ("disabled", "manual_only"):
            # 'disabled' kan aktiveras av användaren efter granskning (enabled=1 + revisionspost)
            if src["automated_fetch"] == "manual_only":
                raise SourceBlocked(f"{src['name']} kan bara importeras manuellt.")
        return src

    def _quota(self, source_id: str, src: dict) -> None:
        day = self.app.clock.now().strftime("%Y-%m-%d")
        row = self.app.db.one("SELECT calls_today, calls_day FROM sync_state WHERE source_id=? AND job='_quota'",
                              (source_id,))
        calls = row["calls_today"] if row and row["calls_day"] == day else 0
        if src["daily_quota"] is not None and calls >= src["daily_quota"]:
            raise SourceBlocked(f"Dygnskvoten för {src['name']} ({src['daily_quota']} anrop) är förbrukad.")
        self.app.db.execute("""INSERT INTO sync_state (source_id, job, scope, calls_today, calls_day) VALUES (?,?,?,?,?)
            ON CONFLICT(source_id, job, scope) DO UPDATE SET calls_today=excluded.calls_today, calls_day=excluded.calls_day""",
                            (source_id, "_quota", "", calls + 1, day))

    def _rate_limit(self, source_id: str, min_interval: float) -> None:
        with self._lock:
            last = self._last_call.get(source_id, 0.0)
            wait = last + min_interval - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last_call[source_id] = time.monotonic()

    def robots_allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self.session.get(base + "/robots.txt", timeout=15)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.parse([])  # ingen robots.txt => inga begränsningar
            except requests.RequestException:
                rp.parse([])
            self._robots[base] = rp
        return rp.can_fetch(USER_AGENT, url)

    # ---------------------------------------------------------------- fetch
    def get(self, source_id: str, url: str, *, job: str, params: dict | None = None, headers: dict | None = None,
            respect_robots: bool = False, conditional: bool = True, redact: tuple[str, ...] = ()) -> FetchResult:
        src = self.check_allowed(source_id)
        if respect_robots and not self.robots_allowed(url):
            self._log_fetch(source_id, job, url, None, None, "skipped", error="Blockerad av robots.txt")
            raise SourceBlocked(f"robots.txt tillåter inte hämtning av {url}")
        self._quota(source_id, src)
        shown_url = url + ("?" + "&".join(f"{k}={'***' if k in redact else v}" for k, v in (params or {}).items())
                           if params else "")
        hdrs = dict(headers or {})
        state = self.app.db.one("SELECT etag, last_modified FROM sync_state WHERE source_id=? AND job='_url' AND scope=?",
                                (source_id, shown_url))
        if conditional and state:
            if state["etag"]:
                hdrs["If-None-Match"] = state["etag"]
            if state["last_modified"]:
                hdrs["If-Modified-Since"] = state["last_modified"]
        started = to_iso(self.app.clock.now())
        attempt = 0
        delay = 2.0
        last_err = None
        while attempt < self.max_attempts:
            attempt += 1
            self._rate_limit(source_id, float(src["min_interval_seconds"] or 0))
            try:
                resp = self.session.get(url, params=params, headers=hdrs, timeout=30)
            except requests.RequestException as e:
                last_err = repr(e)
                self.sleep(delay)
                delay *= 2
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = f"HTTP {resp.status_code}"
                ra = resp.headers.get("Retry-After")
                self.sleep(float(ra) if ra and ra.isdigit() else delay)
                delay *= 2
                continue
            if resp.status_code == 304:
                fid = self._log_fetch(source_id, job, shown_url, 304, None, "not_modified", started=started,
                                      attempt=attempt)
                return FetchResult(fid, 304, None, True, dict(resp.headers))
            content = resp.content if resp.status_code == 200 else None
            fid = self._log_fetch(source_id, job, shown_url, resp.status_code, content,
                                  "pending" if resp.status_code == 200 else "error", started=started, attempt=attempt,
                                  error=None if resp.status_code == 200 else f"HTTP {resp.status_code}")
            if resp.status_code == 200 and conditional:
                self.app.db.execute("""INSERT INTO sync_state (source_id, job, scope, etag, last_modified) VALUES
                    (?,?,?,?,?) ON CONFLICT(source_id, job, scope) DO UPDATE SET etag=excluded.etag,
                    last_modified=excluded.last_modified""",
                                    (source_id, "_url", shown_url, resp.headers.get("ETag"),
                                     resp.headers.get("Last-Modified")))
            return FetchResult(fid, resp.status_code, content, False, dict(resp.headers))
        fid = self._log_fetch(source_id, job, shown_url, None, None, "error", started=started, attempt=attempt,
                              error=last_err)
        return FetchResult(fid, None, None, False, {})

    def _log_fetch(self, source_id, job, url, status, content, parser_status, *, started=None, attempt=1,
                   error=None) -> int:
        sha = hashlib.sha256(content).hexdigest() if content else None
        raw_path = None
        if content:
            d = self.app.paths.raw / source_id / sha[:2]  # type: ignore[index]
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{sha}.bin"
            if not p.exists():
                p.write_bytes(content)
            raw_path = str(p)
        cur = self.app.db.execute("""INSERT INTO fetches (source_id, job, url, started_at_utc, finished_at_utc,
            http_status, sha256, bytes, parser_status, attempt, error, raw_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                  (source_id, job, url, started or to_iso(self.app.clock.now()),
                                   to_iso(self.app.clock.now()), status, sha, len(content) if content else None,
                                   parser_status, attempt, error, raw_path))
        return int(cur.lastrowid)

    def finish(self, fetch_id: int, parser_status: str, counts: dict | None = None, error: str | None = None) -> None:
        c = counts or {}
        self.app.db.execute("""UPDATE fetches SET parser_status=?, rows_imported=?, rows_updated=?, rows_unchanged=?,
            rows_skipped=?, error=COALESCE(?, error) WHERE id=?""",
                            (parser_status, c.get("inserted", 0), c.get("updated", 0), c.get("unchanged", 0),
                             c.get("skipped", 0), error, fetch_id))


def utcnow_iso(app: App) -> str:
    return to_iso(app.clock.now())  # type: ignore[return-value]


def parse_dt(value: str | None) -> datetime | None:
    from ..timeutil import parse_iso
    return parse_iso(value) if value else None
