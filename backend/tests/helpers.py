"""Gemensamma testhjälpare: temporär app, syntetisk historik och falsk HTTP-session."""
from __future__ import annotations

import json
import os
import random
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("MATCHIQ_SECRETS", "memory")

from matchiq.core import init_app  # noqa: E402
from matchiq.timeutil import UTC, FakeClock  # noqa: E402


def make_app(now: datetime | None = None):
    tmp = Path(tempfile.mkdtemp(prefix="matchiq-test-"))
    clock = FakeClock(now or datetime(2026, 10, 15, 8, 0, tzinfo=UTC))
    return init_app(tmp, clock), clock, tmp


def seed_history(app, comp: str = "UCL", seasons=(2021, 2022, 2023, 2024, 2025), n_teams: int = 24, seed: int = 7,
                 source: str = "openfootball", with_stats: bool = True, stats_source: str = "manual"):
    """Syntetisk, deterministisk historik med varierande lagstyrka. Returnerar lag-id:n."""
    rng = random.Random(seed)
    teams = [app.repo.resolve_team(f"Testlag {i:02d}", source, context=comp) for i in range(n_teams)]
    strength = {t: rng.uniform(0.6, 1.6) for t in teams}
    defence = {t: rng.uniform(0.7, 1.4) for t in teams}
    for sy in seasons:
        start = datetime(sy, 9, 10, 19, 0, tzinfo=UTC)
        day = 0
        for r in range(8):
            rng.shuffle(teams)
            for i in range(0, n_teams, 2):
                h, a = teams[i], teams[i + 1]
                ko = start + timedelta(days=day + (i // 8))
                lh = 1.45 * strength[h] * defence[a]
                la = 1.15 * strength[a] * defence[h]
                hg, ag = _pois(rng, lh), _pois(rng, la)
                mid, _ = app.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                               source_id=source, status="finished", season_label=f"{sy}/{str(sy + 1)[-2:]}")
                app.repo.upsert_result(mid, source, {"home_goals_90": hg, "away_goals_90": ag})
                if with_stats:
                    for is_home, t, lam in ((True, h, lh), (False, a, la)):
                        app.repo.upsert_team_stats(mid, t, is_home, stats_source, {
                            "shots": _pois(rng, 9 * lam), "shots_on_target": _pois(rng, 3.4 * lam),
                            "corners": _pois(rng, 3.5 + lam)})
            day += 14
    return teams


def _pois(rng, lam):
    import math
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


class FakeResponse:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = headers or {}
        self.text = self.content.decode("utf-8", "replace")


class FakeSession:
    """Svarar enligt en tabell url->svar och loggar anrop. Används i stället för nätet i tester."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple] = []
        self.headers: dict = {}

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        resp = self.routes.get(url)
        if callable(resp):
            resp = resp(url, params, headers)
        if isinstance(resp, list):
            return resp.pop(0) if len(resp) > 1 else resp[0]
        return resp or FakeResponse(404, b"")
