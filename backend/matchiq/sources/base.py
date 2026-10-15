"""Gemensam bas för källadaptrar."""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from ..core import App
from .http import HttpClient, SourceBlocked  # noqa: F401  (återexport)


class Adapter:
    source_id: str = ""
    label: str = ""
    jobs: tuple[str, ...] = ()
    #: tävlingskod -> källans egen kod/ID
    competitions: dict[str, str] = {}

    def __init__(self, app: App, http: HttpClient | None = None):
        self.app = app
        self.http = http or HttpClient(app)
        self.repo = app.repo
        self.counts: Counter = Counter()

    def now(self) -> datetime:
        return self.app.clock.now()

    def team(self, name: str, context: str = "", source_team_id=None) -> int:
        return self.repo.resolve_team(name, self.source_id, context=context,
                                      source_team_id=None if source_team_id is None else str(source_team_id))

    def run(self, job: str, **scope) -> dict:  # pragma: no cover - implementeras av adaptrarna
        raise NotImplementedError

    def summary(self) -> dict:
        return dict(self.counts)


def season_start_year(dt: datetime, calendar_year_league: bool = False) -> int:
    if calendar_year_league:
        return dt.year
    return dt.year if dt.month >= 7 else dt.year - 1


def season_label(start_year: int, calendar_year_league: bool = False) -> str:
    return str(start_year) if calendar_year_league else f"{start_year}/{str(start_year + 1)[-2:]}"


CALENDAR_LEAGUES = {"SWE1", "NOR1"}
