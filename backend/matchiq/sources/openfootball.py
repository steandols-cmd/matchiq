"""OpenFootball (CC0): spelscheman och resultat.

Filerna hämtas via GitHubs dokumenterade REST-API (api.github.com, contents-endpointen med
``Accept: application/vnd.github.raw``) i stället för att skrapa webbsidor. Anropsgränsen för
oautentiserade anrop är 60/timme; en valfri GitHub-token (Inställningar → API-nycklar) höjer den.

Två format stöds:
* football.json (JSON, en fil per liga och säsong)
* Football.TXT (text) – används av champions-league-repot
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..timeutil import UTC, to_iso
from .base import CALENDAR_LEAGUES, Adapter, season_label
from .http import SourceBlocked


JSON_LEAGUES = {  # tävlingskod -> (football.json-kod, tidszon)
    "ENG1": ("en.1", "Europe/London"), "ESP1": ("es.1", "Europe/Madrid"), "GER1": ("de.1", "Europe/Berlin"),
    "ITA1": ("it.1", "Europe/Rome"), "FRA1": ("fr.1", "Europe/Paris"), "NED1": ("nl.1", "Europe/Amsterdam"),
    "POR1": ("pt.1", "Europe/Lisbon"), "BEL1": ("be.1", "Europe/Brussels"), "TUR1": ("tr.1", "Europe/Istanbul"),
    "AUT1": ("at.1", "Europe/Vienna"), "SCO1": ("sco.1", "Europe/London"), "SWE1": ("se.1", "Europe/Stockholm"),
}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], start=1)}
_SCORE = r"(\d+)\s*[-:]\s*(\d+)"
_DATE_LINE = re.compile(r"^\s*\[?(?:[A-Za-z]{3}\.?\s+)?([A-Za-z]{3})\.?[\s/]+(\d{1,2})(?:[\s,]+(\d{4}))?\]?\s*$")
_ISO_DATE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_ROUND = re.compile(r"^\s*(?:»|▪|::|=+|#+)?\s*(.*(?:Matchday|Round|Final|League|Group|Play-?off|Knockout|"
                    r"Quarter|Semi|Spieltag|Jornada).*)$", re.I)
_LEAD_TIME = re.compile(r"^\s*(\d{1,2})[.:](\d{2})\s+")
_SCORE_RE = re.compile(r"(?<![\w])(\d+)\s*-\s*(\d+)(?![\w])")
_HT_RE = re.compile(r"\(\s*(\d+)\s*-\s*(\d+)\s*\)")
_MIDDLE = re.compile(r"^(?P<t1>.+?)\s+(?P<g1>\d+)\s*-\s*(?P<g2>\d+)(?P<ht>\s*\(\s*\d+\s*-\s*\d+\s*\))?\s+"
                     r"(?P<t2>[^\d(].*?)(?P<tail>\s+(?:a\.?e\.?t|\d+\s*-\s*\d+\s*pen|pen).*)?$", re.I)
_AET = re.compile(r"a\.?e\.?t\.?\s*" + _SCORE + r"|" + _SCORE + r"\s*a\.?e\.?t\.?", re.I)
_PEN = re.compile(r"(\d+)\s*-\s*(\d+)\s*(?:pen|p\b)|pen\.?\s*(\d+)\s*-\s*(\d+)", re.I)
_COUNTRY = re.compile(r"\s*\(([A-Z]{3})\)\s*$")


def season_path(start_year: int, calendar: bool) -> str:
    return str(start_year) if calendar else f"{start_year}-{str(start_year + 1)[-2:]}"


def parse_football_json(data: dict) -> list[dict]:
    """Stöder både nya (matches[]) och äldre (rounds[].matches[]) football.json-format."""
    out = []
    rounds = data.get("rounds")
    items = []
    if rounds:
        for rd in rounds:
            for m in rd.get("matches", []):
                items.append((rd.get("name"), m))
    for m in data.get("matches", []):
        items.append((m.get("round"), m))
    for rnd, m in items:
        t1 = m.get("team1")
        t2 = m.get("team2")
        t1 = t1.get("name") if isinstance(t1, dict) else t1
        t2 = t2.get("name") if isinstance(t2, dict) else t2
        if not t1 or not t2 or not m.get("date"):
            continue
        sc = m.get("score") or {}
        ft = sc.get("ft") if isinstance(sc, dict) else None
        if ft is None and m.get("score1") is not None:
            ft = [m.get("score1"), m.get("score2")]
        ht = sc.get("ht") if isinstance(sc, dict) else None
        et = sc.get("et") if isinstance(sc, dict) else None
        p = sc.get("p") if isinstance(sc, dict) else None
        out.append({"round": rnd, "date": m["date"], "time": m.get("time"), "team1": t1, "team2": t2,
                    "ft": ft, "ht": ht, "et": et, "pens": p})
    return out


def parse_football_txt(text: str, default_year: int, calendar: bool = False) -> list[dict]:
    """Tolerant tolkning av Football.TXT. Rader som inte kan tolkas räknas och rapporteras.

    calendar=True för ligor som spelas inom ett kalenderår (t.ex. Allsvenskan): då byts aldrig år
    när månaden "går bakåt" (uppskjutna matcher listas ibland i annan ordning)."""
    out: list[dict] = []
    cur_date: tuple[int, int, int] | None = None
    cur_round = None
    year = default_year
    last_month = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("="):
            continue
        m = _ISO_DATE.match(line)
        if m:
            cur_date = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            continue
        m = _DATE_LINE.match(line)
        if m and m.group(1).lower()[:3] in MONTHS:
            mon = MONTHS[m.group(1).lower()[:3]]
            if m.group(3):
                year = int(m.group(3))
            elif not calendar and last_month and mon < last_month and last_month >= 7 and mon <= 6:
                year += 1  # säsongen passerar nyår
            last_month = mon
            cur_date = (year, mon, int(m.group(2)))
            continue
        body = line
        tm = _LEAD_TIME.match(body)
        hh = mi = None
        if tm:
            hh, mi = int(tm.group(1)), int(tm.group(2))
            body = body[tm.end():]
        vs = re.search(r"\s+(?:v|vs\.?)\s+", body)
        if vs is None and not _MIDDLE.match(body.strip()):
            r = _ROUND.match(line)
            if r:
                cur_round = r.group(1).strip()
            continue
        if cur_date is None:
            continue
        ft = ht = et = pens = None
        if vs is not None:
            t1 = body[:vs.start()].strip()
            right = body[vs.end():]
            sm = _SCORE_RE.search(right)
            if sm:
                t2 = right[:sm.start()].strip()
                ft = [int(sm.group(1)), int(sm.group(2))]
                tail = right[sm.end():]
            else:
                t2, tail = right.strip(), ""
        else:
            mm = _MIDDLE.match(body.strip())
            t1, t2 = mm.group("t1").strip(), mm.group("t2").strip()
            ft = [int(mm.group("g1")), int(mm.group("g2"))]
            tail = (mm.group("ht") or "") + (mm.group("tail") or "")
        hm = _HT_RE.search(tail)
        if hm:
            ht = [int(hm.group(1)), int(hm.group(2))]
        a = _AET.search(tail)
        if a:
            vals = [x for x in a.groups() if x is not None]
            et = [int(vals[0]), int(vals[1])]
        p = _PEN.search(tail)
        if p:
            vals = [x for x in p.groups() if x is not None]
            pens = [int(vals[0]), int(vals[1])]
        if not t1 or not t2:
            out.append({"unparsed": line})
            continue
        c1 = _COUNTRY.search(t1)
        c2 = _COUNTRY.search(t2)
        t1c, t2c = _COUNTRY.sub("", t1).strip(), _COUNTRY.sub("", t2).strip()
        out.append({"round": cur_round, "date": "%04d-%02d-%02d" % cur_date,
                    "time": None if hh is None else f"{hh:02d}:{mi:02d}", "team1": t1c, "team2": t2c,
                    "country1": c1.group(1) if c1 else None, "country2": c2.group(1) if c2 else None,
                    "ft": ft, "ht": ht, "et": et, "pens": pens, "line": line.strip()})
    return out


# (repo, mönster) -> (tävlingskod, tidszon, kalenderår?)
TARGETS = [
    ("football.json", re.compile(r"^(\d{4})(?:-(\d{2}))?/([a-z]+\.1)\.json$")),
    ("champions-league", re.compile(r"^(\d{4})-(\d{2})/(cl|clq)\.txt$")),
    ("europe", re.compile(r"^sweden/(\d{4})_(se1)\.txt$")),
]
JSON_CODE_TO_COMP = {code: comp for comp, (code, _tz) in JSON_LEAGUES.items()}


def classify(repo: str, path: str) -> dict | None:
    """Vilken tävling och säsong en fil i ett OpenFootball-repo avser (None = inte relevant)."""
    for r, rx in TARGETS:
        if r != repo:
            continue
        m = rx.match(path)
        if not m:
            return None
        if repo == "football.json":
            comp = JSON_CODE_TO_COMP.get(m.group(3))
            if comp is None:
                return None
            cal = m.group(2) is None
            return {"comp": comp, "tz": JSON_LEAGUES[comp][1], "start": int(m.group(1)), "calendar": cal,
                    "format": "json"}
        if repo == "champions-league":
            return {"comp": "UCL" if m.group(3) == "cl" else "UCLQ", "tz": "Europe/Paris", "start": int(m.group(1)),
                    "calendar": False, "format": "txt"}
        if repo == "europe":
            return {"comp": "SWE1", "tz": "Europe/Stockholm", "start": int(m.group(1)), "calendar": True,
                    "format": "txt"}
    return None


class OpenFootballAdapter(Adapter):
    """Två jobb:

    * ``fixtures_results`` – innevarande och föregående säsong (körs dagligen av synken).
    * ``backfill`` – samtliga säsonger som finns i repona (historik).

    Filträdet hämtas med ett anrop per repo; varje fils blob-SHA sparas, så en fil laddas bara ner
    igen när den faktiskt har ändrats i källan.
    """
    source_id = "openfootball"
    label = "OpenFootball"
    jobs = ("fixtures_results", "backfill")

    def run(self, job: str = "fixtures_results", competitions: list[str] | None = None,
            seasons: list[int] | None = None, progress=None) -> dict:
        from .github import GitHubRepo
        now = self.now()
        comps = set(competitions or ["UCL", "UCLQ", "ENG1", "ESP1", "GER1", "ITA1", "FRA1", "SWE1"])
        plan = []
        for repo in ("football.json", "champions-league", "europe"):
            gh = GitHubRepo(self.http, self.source_id, "openfootball", repo)
            for path, sha in sorted(gh.tree(job).items()):
                info = classify(repo, path)
                if not info or info["comp"] not in comps:
                    continue
                cur = now.year if info["calendar"] else (now.year if now.month >= 7 else now.year - 1)
                if seasons is not None and info["start"] not in seasons:
                    continue
                if job == "fixtures_results" and seasons is None and info["start"] < cur - 1:
                    continue
                plan.append((gh, path, sha, info))
        self.counts["files_in_scope"] = len(plan)
        for i, (gh, path, sha, info) in enumerate(plan, 1):
            if progress:
                progress(f"OpenFootball {info['comp']} {path}", i, len(plan))
            key = f"{gh.repo}/{path}"
            st = self.app.db.one("SELECT etag FROM sync_state WHERE source_id=? AND job='_blob' AND scope=?",
                                 (self.source_id, key))
            if st and st["etag"] == sha:
                self.counts["files_unchanged"] += 1
                continue
            res = gh.file(path, job)
            if res.status != 200:
                self.counts["missing_files"] += 1
                continue
            try:
                if info["format"] == "json":
                    rows = parse_football_json(res.json())
                else:
                    rows = parse_football_txt(res.text(), info["start"], calendar=info["calendar"])
                label = season_label(info["start"], info["calendar"])
                self._store(rows, info["comp"], info["tz"], label, res.fetch_id,
                            context="UCL" if info["comp"] in ("UCL", "UCLQ") else info["comp"])
                self.app.db.execute("""INSERT INTO sync_state (source_id, job, scope, etag, last_run_utc)
                    VALUES (?,?,?,?,?) ON CONFLICT(source_id, job, scope) DO UPDATE SET etag=excluded.etag,
                    last_run_utc=excluded.last_run_utc""", (self.source_id, "_blob", key, sha, to_iso(now)))
                self.counts["files_imported"] += 1
            except SourceBlocked:
                raise
            except Exception as e:  # noqa: BLE001 - parserfel loggas per fil
                self.counts["parse_errors"] += 1
                self.http.finish(res.fetch_id, "error", error=repr(e))
        return self.summary()

    def _store(self, rows: list[dict], comp: str, tz: str, season: str, fetch_id: int, context: str) -> None:
        c = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        zone = ZoneInfo(tz)
        for r in rows:
            if "unparsed" in r:
                c["skipped"] += 1
                continue
            d = datetime.strptime(r["date"], "%Y-%m-%d")
            if r.get("time"):
                hh, mm = (int(x) for x in r["time"].split(":")[:2])
                ko = d.replace(hour=hh, minute=mm, tzinfo=zone).astimezone(UTC)
                known = True
            else:
                ko = d.replace(hour=12, tzinfo=zone).astimezone(UTC)
                known = False
            h = self.team(r["team1"], context=context)
            a = self.team(r["team2"], context=context)
            if h == a:
                c["skipped"] += 1
                continue
            ft = r.get("ft")
            mid, act = self.repo.upsert_match(competition_code=comp, kickoff_utc=ko, home_team_id=h, away_team_id=a,
                                              source_id=self.source_id, status="finished" if ft else "scheduled",
                                              season_label=season, kickoff_time_known=known, round_=r.get("round"),
                                              fetch_id=fetch_id)
            c[act if act in c else "updated"] += 1
            if ft:
                vals = {"home_goals_90": ft[0], "away_goals_90": ft[1]}
                if r.get("ht"):
                    vals.update({"home_goals_ht": r["ht"][0], "away_goals_ht": r["ht"][1]})
                if r.get("et"):
                    # Med förlängning är 'ft' ställningen efter 90 min i football.json
                    vals.update({"home_goals_aet": r["et"][0], "away_goals_aet": r["et"][1]})
                if r.get("pens"):
                    vals.update({"home_pens": r["pens"][0], "away_pens": r["pens"][1]})
                self.repo.upsert_result(mid, self.source_id, vals, original_home=r["team1"],
                                        original_away=r["team2"], fetch_id=fetch_id,
                                        available_at=ko + timedelta(hours=3))
        self.http.finish(fetch_id, "ok" if c["skipped"] == 0 else "partial", c)
        for k, v in c.items():
            self.counts[k] += v
        _ = to_iso
