"""Tidshantering: UTC i lagring, Europe/Stockholm i gränssnitt och rapporter.

All lagring sker som ISO 8601-strängar i UTC med suffix ``Z`` (sekundupplösning).
Klockan är injicerbar så att schemaläggning och T−30 kan testas med simulerad tid.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
STOCKHOLM = ZoneInfo("Europe/Stockholm")


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError("Naiva datetime-objekt får inte lagras – ange tidszon")
    return dt.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def local_to_utc(naive_local: datetime, tz: ZoneInfo = STOCKHOLM) -> datetime:
    """Tolka en naiv lokal tid (t.ex. 'Avspark Sverige') i angiven zon och returnera UTC."""
    if naive_local.tzinfo is not None:
        return naive_local.astimezone(UTC)
    return naive_local.replace(tzinfo=tz).astimezone(UTC)


def to_stockholm(dt: datetime | str | None) -> datetime | None:
    if isinstance(dt, str):
        dt = parse_iso(dt)
    if dt is None:
        return None
    return dt.astimezone(STOCKHOLM)


def fmt_local(dt: datetime | str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    loc = to_stockholm(dt)
    return loc.strftime(fmt) if loc else "saknas"


def local_date(dt: datetime | str) -> str:
    loc = to_stockholm(dt)
    assert loc is not None
    return loc.strftime("%Y-%m-%d")


class Clock:
    """Gränssnitt för klocka. Alla tidsberoende komponenter tar emot en Clock."""

    simulated = False

    def now(self) -> datetime:  # pragma: no cover - interface
        raise NotImplementedError


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)


class FakeClock(Clock):
    """Simulerad klocka för tester och demonstrationer (T−30 utan att vänta på match)."""

    simulated = True

    def __init__(self, start: datetime):
        if start.tzinfo is None:
            raise ValueError("FakeClock kräver tidszonsmedveten starttid")
        self._now = start.astimezone(UTC)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def set(self, when: datetime) -> None:
        with self._lock:
            self._now = when.astimezone(UTC)

    def advance(self, **kwargs) -> datetime:
        with self._lock:
            self._now = self._now + timedelta(**kwargs)
            return self._now
