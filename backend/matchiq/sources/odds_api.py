"""The Odds API v4 – 1X2-odds för marknadsjämförelse (aldrig träningsdata)."""
from __future__ import annotations

from .. import secrets_store
from ..entities import normalize_name
from ..timeutil import parse_iso
from .base import Adapter
from .http import SourceBlocked

BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
SPORTS = {"UCL": "soccer_uefa_champs_league", "ENG1": "soccer_epl", "ESP1": "soccer_spain_la_liga",
          "GER1": "soccer_germany_bundesliga", "ITA1": "soccer_italy_serie_a", "FRA1": "soccer_france_ligue_one",
          "SWE1": "soccer_sweden_allsvenskan"}


class OddsApiAdapter(Adapter):
    source_id = "the_odds_api"
    label = "The Odds API"
    jobs = ("odds",)

    def run(self, job: str = "odds", competitions: list[str] | None = None) -> dict:
        key = secrets_store.get_secret("the_odds_api")
        if not key:
            raise SourceBlocked("API-nyckel för The Odds API saknas (Inställningar → API-nycklar).")
        for comp in competitions or list(SPORTS):
            res = self.http.get(self.source_id, BASE.format(sport=SPORTS[comp]), job=job,
                                params={"apiKey": key, "regions": "eu,uk", "markets": "h2h", "oddsFormat": "decimal",
                                        "dateFormat": "iso"}, conditional=False, redact=("apiKey",))
            if res.status != 200:
                self.counts["errors"] += 1
                continue
            self.store(res.json() or [], comp, res.fetch_id)
        return self.summary()

    def store(self, events: list[dict], comp: str, fetch_id: int) -> None:
        n = 0
        for ev in events:
            ko = parse_iso(ev.get("commence_time"))
            # Odds kopplas bara till en befintlig match (exakta alias) – inga matcher skapas från oddsdata.
            h = self.repo.find_team(ev.get("home_team", ""), self.source_id, context=comp)
            a = self.repo.find_team(ev.get("away_team", ""), self.source_id, context=comp)
            if h is None or a is None or ko is None:
                self.counts["unmatched_events"] += 1
                continue
            row = self.app.db.one("""SELECT m.id FROM matches m JOIN competitions c ON c.id=m.competition_id
                WHERE c.code=? AND m.home_team_id=? AND m.away_team_id=? AND abs(julianday(m.kickoff_utc)-julianday(?))<1""",
                                  (comp, h, a, ev["commence_time"]))
            if row is None:
                self.counts["unmatched_events"] += 1
                continue
            for bk in ev.get("bookmakers") or []:
                for mk in bk.get("markets") or []:
                    if mk.get("key") != "h2h":
                        continue
                    prices = {normalize_name(o.get("name", "")): o.get("price") for o in mk.get("outcomes") or []}
                    oh = prices.get(normalize_name(ev["home_team"]))
                    oa = prices.get(normalize_name(ev["away_team"]))
                    od = prices.get("draw")
                    if None in (oh, od, oa):
                        continue
                    r = self.repo.add_odds(match_id=row["id"], source_id=self.source_id, bookmaker=bk.get("title"),
                                           kind="snapshot", odds=(oh, od, oa), fetched_at=self.now(),
                                           published_at=parse_iso(bk.get("last_update")))
                    n += r == "inserted"
        self.counts["odds_inserted"] += n
        self.http.finish(fetch_id, "ok", {"inserted": n})
