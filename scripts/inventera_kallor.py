"""Inventera vad de öppna källorna faktiskt innehåller (täckning per tävling, säsong och mått) och vilka
villkor de anger. Inga siffror hittas på: allt i rapporten är räknat ur källornas egna filer.

    python scripts/inventera_kallor.py --out rapport

Körs i GitHub Actions (som har internetåtkomst) och skriver kallinventering.json och kallinventering.md.
Miljövariabeln GITHUB_TOKEN höjer anropsgränsen mot GitHubs API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from matchiq.sources.openfootball import parse_football_json, parse_football_txt  # noqa: E402

UA = {"User-Agent": "MatchIQ-kallinventering/1.0 (+https://github.com/steandols-cmd/matchiq)"}
GH = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
OUR_LEAGUES = {"en.1": "ENG1", "es.1": "ESP1", "de.1": "GER1", "it.1": "ITA1", "fr.1": "FRA1", "se.1": "SWE1"}
SB_COMPS = {"Champions League": "UCL", "Premier League": "ENG1", "La Liga": "ESP1", "1. Bundesliga": "GER1",
            "Serie A": "ITA1", "Ligue 1": "FRA1"}


class Net:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(UA)
        tok = os.environ.get("GITHUB_TOKEN")
        self.gh_headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if tok:
            self.gh_headers["Authorization"] = f"Bearer {tok}"
        self.log: list[dict] = []

    def get(self, url: str, headers: dict | None = None, tries: int = 3):
        for i in range(tries):
            try:
                r = self.s.get(url, headers=headers or {}, timeout=60)
                self.log.append({"url": url, "status": r.status_code, "bytes": len(r.content)})
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** i * 3)
                    continue
                return r
            except requests.RequestException as e:
                self.log.append({"url": url, "status": None, "error": repr(e)})
                time.sleep(2 ** i * 3)
        return None

    def gh(self, path: str):
        r = self.get(GH + path, self.gh_headers)
        return r.json() if r is not None and r.status_code == 200 else None


def openfootball(net: Net) -> dict:
    out: dict = {"repos": {}, "files": [], "errors": []}
    repos = []
    page = 1
    while True:
        data = net.gh(f"/orgs/openfootball/repos?per_page=100&page={page}")
        if not data:
            break
        repos += data
        if len(data) < 100:
            break
        page += 1
    out["repos"] = {r["name"]: {"default_branch": r["default_branch"], "pushed_at": r["pushed_at"],
                                "license": (r.get("license") or {}).get("spdx_id")} for r in repos}
    wanted = [n for n in out["repos"] if n in ("football.json", "champions-league", "europe")
              or "swe" in n.lower() or n.lower() in ("sweden", "se")]
    for name in wanted:
        br = out["repos"][name]["default_branch"]
        tree = net.gh(f"/repos/openfootball/{name}/git/trees/{br}?recursive=1")
        if not tree:
            out["errors"].append(f"{name}: kunde inte läsa filträdet")
            continue
        paths = [t["path"] for t in tree.get("tree", []) if t["type"] == "blob"]
        out["repos"][name]["n_files"] = len(paths)
        out["repos"][name]["truncated"] = tree.get("truncated", False)
        for p in paths:
            comp = None
            if name == "football.json":
                m = re.match(r"^(\d{4}(?:-\d{2})?)/([a-z]+\.\d)\.json$", p)
                if m and m.group(2) in OUR_LEAGUES:
                    comp, season = OUR_LEAGUES[m.group(2)], m.group(1)
            elif name == "champions-league":
                m = re.match(r"^(\d{4}-\d{2})/(cl|champs|championsleague)[^/]*\.txt$", p)
                if m:
                    comp, season = "UCL", m.group(1)
            elif "swe" in p.lower() or "/se" in p.lower():
                m = re.search(r"(\d{4}(?:-\d{2})?)", p)
                if p.endswith(".txt") and m:
                    comp, season = "SWE1?", m.group(1)
            if comp:
                out["files"].append({"repo": name, "branch": br, "path": p, "competition": comp, "season": season})
    # Räkna matcher och resultat i varje relevant fil
    for f in out["files"]:
        r = net.get(f"{RAW}/openfootball/{f['repo']}/{f['branch']}/{f['path']}")
        if r is None or r.status_code != 200:
            f["status"] = None if r is None else r.status_code
            continue
        try:
            if f["path"].endswith(".json"):
                rows = parse_football_json(r.json())
            else:
                rows = parse_football_txt(r.text, int(f["season"][:4]))
            ok = [x for x in rows if "unparsed" not in x]
            today = datetime.now(timezone.utc).date()
            soon = [{"date": x["date"], "time": x.get("time"), "home": x["team1"], "away": x["team2"],
                     "round": x.get("round"), "competition": f["competition"]}
                    for x in ok if today.isoformat() <= x["date"] <= (today + timedelta(days=7)).isoformat()]
            if soon:
                out.setdefault("upcoming", []).extend(soon)
            f.update({"status": 200, "matches": len(ok), "with_score": sum(1 for x in ok if x.get("ft")),
                      "unparsed_lines": len(rows) - len(ok),
                      "first_date": min((x["date"] for x in ok), default=None),
                      "last_date": max((x["date"] for x in ok), default=None),
                      "teams": len({x["team1"] for x in ok} | {x["team2"] for x in ok})})
        except Exception as e:  # noqa: BLE001
            f.update({"status": "parse_error", "error": repr(e)[:300]})
    return out


def statsbomb(net: Net) -> dict:
    out: dict = {"competitions": [], "terms_excerpt": None}
    base = f"{RAW}/statsbomb/open-data/master"
    rd = net.get(f"{base}/README.md")
    if rd is not None and rd.status_code == 200:
        lines = [ln.strip() for ln in rd.text.splitlines()
                 if re.search(r"licen|terms|agreement|attribut|commercial|credit|logo", ln, re.I)]
        out["terms_excerpt"] = lines[:25]
    r = net.get(f"{base}/data/competitions.json")
    if r is None or r.status_code != 200:
        out["error"] = "competitions.json kunde inte läsas"
        return out
    for c in r.json():
        code = SB_COMPS.get(c.get("competition_name"))
        if not code or c.get("competition_gender", "male") != "male":
            continue
        ml = net.get(f"{base}/data/matches/{c['competition_id']}/{c['season_id']}.json")
        matches = ml.json() if ml is not None and ml.status_code == 200 else []
        teams = Counter()
        for m in matches:
            teams[m["home_team"]["home_team_name"]] += 1
            teams[m["away_team"]["away_team_name"]] += 1
        out["competitions"].append({
            "competition": code, "name": c["competition_name"], "season": c["season_name"],
            "competition_id": c["competition_id"], "season_id": c["season_id"], "matches": len(matches),
            "teams": len(teams), "first_date": min((m["match_date"] for m in matches), default=None),
            "last_date": max((m["match_date"] for m in matches), default=None),
            "match_updated": c.get("match_updated"), "data_version": c.get("match_available"),
            "full_season_guess": len(matches) >= 300})
    return out


def wyscout(net: Net) -> dict:
    out: dict = {"articles": []}
    arts = net.get("https://api.figshare.com/v2/collections/4415000/articles?page_size=100")
    if arts is None or arts.status_code != 200:
        out["error"] = f"figshare: {None if arts is None else arts.status_code}"
        return out
    for a in arts.json():
        d = net.get(f"https://api.figshare.com/v2/articles/{a['id']}")
        if d is None or d.status_code != 200:
            continue
        j = d.json()
        out["articles"].append({"id": a["id"], "title": j.get("title"), "doi": j.get("doi"),
                                "license": (j.get("license") or {}).get("name"),
                                "license_url": (j.get("license") or {}).get("url"),
                                "files": [{"name": f["name"], "size": f["size"], "url": f["download_url"]}
                                          for f in j.get("files", [])]})
    return out


def robots(net: Net) -> dict:
    """robots.txt för värdarna som adaptrarna använder (för att visa att reglerna följs)."""
    import urllib.robotparser
    hosts = {"https://api.github.com": "/repos/openfootball/football.json/contents/2024-25/en.1.json",
             "https://raw.githubusercontent.com": "/openfootball/football.json/master/2024-25/en.1.json",
             "https://api.figshare.com": "/v2/collections/4415000/articles",
             "https://ndownloader.figshare.com": "/files/14464685",
             "https://v3.football.api-sports.io": "/fixtures"}
    out = {}
    for base, path in hosts.items():
        r = net.get(base + "/robots.txt")
        txt = r.text if r is not None and r.status_code == 200 else ""
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(txt.splitlines())
        out[base] = {"status": None if r is None else r.status_code, "robots_txt": txt[:800],
                     "matchiq_allowed": rp.can_fetch("MatchIQ", base + path)}
    return out


def write_md(rep: dict, path: Path) -> None:
    L = [f"# Källinventering ({rep['generated_utc']})", "",
         "Allt nedan är räknat ur källornas egna filer av `scripts/inventera_kallor.py` i GitHub Actions.", ""]
    of = rep["openfootball"]
    L += ["## OpenFootball (CC0)", "", "| Tävling | Repo | Säsong | Matcher | Med resultat | Första | Sista | Lag | Otolkade rader |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(of["files"], key=lambda x: (x["competition"], x["season"], x["repo"])):
        L.append(f"| {f['competition']} | {f['repo']} | {f['season']} | {f.get('matches', '–')} | "
                 f"{f.get('with_score', '–')} | {f.get('first_date') or '–'} | {f.get('last_date') or '–'} | "
                 f"{f.get('teams', '–')} | {f.get('unparsed_lines', f.get('status'))} |")
    L += ["", f"Repon i organisationen: {len(of['repos'])}. Fel: {of['errors'] or 'inga'}", ""]
    up = sorted(of.get("upcoming", []), key=lambda x: (x["date"], x.get("time") or "", x["competition"]))
    L += [f"### Matcher idag och kommande 7 dagar enligt OpenFootball ({len(up)} st)", "",
          "| Datum | Tid (lokal) | Tävling | Hemma | Borta | Omgång |", "|---|---|---|---|---|---|"]
    L += [f"| {x['date']} | {x.get('time') or '–'} | {x['competition']} | {x['home']} | {x['away']} | "
          f"{x.get('round') or '–'} |" for x in up] or ["| – | – | – | inga matcher | | |"]
    L += [""]
    sb = rep["statsbomb"]
    L += ["## StatsBomb Open Data", "", "| Tävling | Säsong | Matcher | Lag | Första | Sista |", "|---|---|---|---|---|---|"]
    for c in sorted(sb.get("competitions", []), key=lambda x: (x["competition"], x["season"])):
        L.append(f"| {c['competition']} | {c['season']} | {c['matches']} | {c['teams']} | {c['first_date']} | "
                 f"{c['last_date']} |")
    L += ["", "Villkor (utdrag ur README):", ""] + [f"> {t}" for t in (sb.get("terms_excerpt") or [])] + [""]
    wy = rep["wyscout"]
    L += ["## Wyscout/figshare (Pappalardo m.fl. 2019)", ""]
    for a in wy.get("articles", []):
        L.append(f"- **{a['title']}** – licens {a['license']} – " +
                 ", ".join(f"{f['name']} ({f['size'] / 1e6:.1f} MB)" for f in a["files"]))
    if wy.get("error"):
        L.append(f"- Fel: {wy['error']}")
    L += ["", "## robots.txt för värdar som används", ""]
    for host, r in rep.get("robots", {}).items():
        L.append(f"- **{host}** – HTTP {r['status']}, MatchIQ tillåten: {'ja' if r['matchiq_allowed'] else 'NEJ'}"
                 + (f" – `{r['robots_txt'][:200].strip()}`".replace("\n", " ⏎ ") if r["robots_txt"] else ""))
    fails = [x for x in rep["http_log"] if x.get("status") != 200]
    L += ["", f"## Anrop: {len(rep['http_log'])} totalt, {len(fails)} utan HTTP 200", ""]
    L += [f"- {x.get('status')} {x['url']}" for x in fails[:60]]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="rapport")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    net = Net()
    rep = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    rep["openfootball"] = openfootball(net)
    rep["statsbomb"] = statsbomb(net)
    rep["wyscout"] = wyscout(net)
    rep["robots"] = robots(net)
    rep["http_log"] = net.log
    (out / "kallinventering.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(rep, out / "kallinventering.md")
    per = defaultdict(int)
    for f in rep["openfootball"]["files"]:
        per[f["competition"]] += f.get("matches") or 0
    print("OpenFootball matcher per tävling:", dict(per))
    print("StatsBomb tävlingssäsonger:", len(rep["statsbomb"].get("competitions", [])))
    print("Wyscout-artiklar:", len(rep["wyscout"].get("articles", [])))


if __name__ == "__main__":
    main()
