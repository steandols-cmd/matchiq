"""Football-Data.co.uk – CSV-filer med resultat, matchstatistik och odds.

SPÄRRAD FRÅN MODELLTRÄNING (villkoren utesluter AI-/botbaserade träningsprodukter). Data används
för visning och marknadsjämförelse. robots.txt respekteras.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..timeutil import UTC
from .base import Adapter

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
NEW_BASE = "https://www.football-data.co.uk/new/{country}.csv"
DIVS = {"ENG1": "E0", "ESP1": "SP1", "GER1": "D1", "ITA1": "I1", "FRA1": "F1", "NED1": "N1", "POR1": "P1",
        "BEL1": "B1", "TUR1": "T1", "SCO1": "SC0"}
NEW_LEAGUES = {"SWE1": "SWE", "NOR1": "NOR"}


def _i(v):
    try:
        return None if v in (None, "") else int(float(v))
    except ValueError:
        return None


def _f(v):
    try:
        return None if v in (None, "") else float(v)
    except ValueError:
        return None


def parse_csv(text: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        home = r.get("HomeTeam") or r.get("Home")
        away = r.get("AwayTeam") or r.get("Away")
        date = r.get("Date")
        if not home or not away or not date:
            continue
        d = None
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                d = datetime.strptime(date.strip(), fmt)
                break
            except ValueError:
                continue
        if d is None:
            continue
        rows.append({
            "date": d, "time": (r.get("Time") or "").strip() or None, "home": home.strip(), "away": away.strip(),
            "season": r.get("Season"),
            "hg": _i(r.get("FTHG") or r.get("HG")), "ag": _i(r.get("FTAG") or r.get("AG")),
            "hgh": _i(r.get("HTHG")), "agh": _i(r.get("HTAG")),
            "hs": _i(r.get("HS")), "as": _i(r.get("AS")), "hst": _i(r.get("HST")), "ast": _i(r.get("AST")),
            "hc": _i(r.get("HC")), "ac": _i(r.get("AC")), "hf": _i(r.get("HF")), "af": _i(r.get("AF")),
            "hy": _i(r.get("HY")), "ay": _i(r.get("AY")), "hr": _i(r.get("HR")), "ar": _i(r.get("AR")),
            "odds": {
                "Bet365": (_f(r.get("B365H")), _f(r.get("B365D")), _f(r.get("B365A"))),
                "Pinnacle": (_f(r.get("PSH")), _f(r.get("PSD")), _f(r.get("PSA"))),
                "Marknadssnitt": (_f(r.get("AvgH")), _f(r.get("AvgD")), _f(r.get("AvgA"))),
                "Pinnacle (stängning)": (_f(r.get("PSCH")), _f(r.get("PSCD")), _f(r.get("PSCA"))),
            },
        })
    return rows


class FootballDataCoUkAdapter(Adapter):
    source_id = "football_data_couk"
    label = "Football-Data.co.uk"
    jobs = ("results",)

    def run(self, job: str = "results", competitions: list[str] | None = None, season: str | None = None) -> dict:
        now = self.now()
        sy = now.year if now.month >= 7 else now.year - 1
        season = season or f"{str(sy)[-2:]}{str(sy + 1)[-2:]}"
        for comp in competitions or list(DIVS) + list(NEW_LEAGUES):
            if comp in DIVS:
                url = BASE.format(season=season, div=DIVS[comp])
            elif comp in NEW_LEAGUES:
                url = NEW_BASE.format(country=NEW_LEAGUES[comp])
            else:
                continue
            res = self.http.get(self.source_id, url, job=job, respect_robots=True)
            if res.status != 200:
                self.counts["missing_files"] += 1
                continue
            self._store(parse_csv(res.text()), comp, res.fetch_id)
        return self.summary()

    def _store(self, rows: list[dict], comp: str, fetch_id: int) -> None:
        c = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        tz = ZoneInfo("Europe/London") if comp in DIVS else ZoneInfo("Europe/Stockholm")
        for r in rows:
            d = r["date"]
            if r["time"]:
                hh, mm = (int(x) for x in r["time"].split(":")[:2])
                ko = d.replace(hour=hh, minute=mm, tzinfo=tz).astimezone(UTC)
                known = True
            else:
                ko = d.replace(hour=15, tzinfo=tz).astimezone(UTC)
                known = False
            h = self.team(r["home"], context=comp)
            a = self.team(r["away"], context=comp)
            if h == a:
                c["skipped"] += 1
                continue
            finished = r["hg"] is not None
            mid, act = self.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                              source_id=self.source_id, status="finished" if finished else "scheduled",
                                              kickoff_time_known=known, fetch_id=fetch_id)
            c[act if act in c else "updated"] += 1
            avail = ko + timedelta(hours=3)
            if finished:
                self.repo.upsert_result(mid, self.source_id, {"home_goals_90": r["hg"], "away_goals_90": r["ag"],
                                                              "home_goals_ht": r["hgh"], "away_goals_ht": r["agh"]},
                                        fetch_id=fetch_id, available_at=avail, original_home=r["home"],
                                        original_away=r["away"])
                for is_home, tid, p in ((True, h, "h"), (False, a, "a")):
                    self.repo.upsert_team_stats(mid, tid, is_home, self.source_id, {
                        "shots": r[f"{p}s"], "shots_on_target": r[f"{p}st"], "corners": r[f"{p}c"],
                        "fouls": r[f"{p}f"], "yellow_cards": r[f"{p}y"], "red_cards": r[f"{p}r"]},
                        fetch_id=fetch_id, available_at=avail)
            for book, odds in r["odds"].items():
                if all(o is not None for o in odds):
                    self.repo.add_odds(match_id=mid, source_id=self.source_id, bookmaker=book,
                                       kind="closing" if "stängning" in book else "snapshot", odds=odds,
                                       fetched_at=self.now())
        self.http.finish(fetch_id, "ok", c)
        for k, v in c.items():
            self.counts[k] += v
