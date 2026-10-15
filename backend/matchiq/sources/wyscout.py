"""Wyscouts öppna händelsedata (Pappalardo m.fl. 2019, Scientific Data 6:236), licens CC BY 4.0.

Innehåll som används: säsongen 2017/18 i Premier League, La Liga, Bundesliga, Serie A och Ligue 1 –
matcher, lag, spelare, startelvor/byten och alla händelser. Ur händelserna räknas per lag och match
skott, skott på mål, hörnor, fouls och kort för ordinarie speltid (1H/2H); per spelare skott, skott på
mål, mål, passningar och nyckelpassningar samt uppskattade minuter ur startelva och byten.

Taggarnas betydelse (t.ex. "Goal", "accurate") läses ur källans egen tags2name.csv – inga ID:n
antas. Filerna hämtas via figshares dokumenterade API (api.figshare.com).
"""
from __future__ import annotations

import csv
import io
import re
import json
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from ..linking import link_source_teams
from ..timeutil import UTC, to_iso
from .base import Adapter
from .jsonstream import iter_json_array

COLLECTION = "https://api.figshare.com/v2/collections/4415000/articles?page_size=100"
ARTICLE = "https://api.figshare.com/v2/articles/{id}"
AREA_TO_COMP = {"England": "ENG1", "Spain": "ESP1", "Italy": "ITA1", "Germany": "GER1", "France": "FRA1"}
NEEDED = ("competitions.json", "teams.json", "players.json", "matches.zip", "events.zip", "tags2name.csv")
SHOT_SUBEVENTS = {"free kick shot", "penalty"}


def _norm_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.lower())


def tag_ids(csv_text: str) -> dict[str, int]:
    """{normaliserad etikett: tagg-ID} ur källans tags2name.csv (gemener, utan mellanslag och tecken)."""
    sample = csv_text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(csv_text), delimiter=delim))
    if not rows:
        raise ValueError("tags2name.csv är tom")
    head = [h.strip().lower() for h in rows[0]]
    try:
        i_id = next(i for i, h in enumerate(head) if h in ("tag", "id", "tagid", "tag_id", "wyid"))
        i_lab = next(i for i, h in enumerate(head) if h in ("label", "name", "tagname", "tag_name", "description"))
    except StopIteration:
        raise ValueError(f"Okända kolumner i tags2name.csv: {rows[0]}") from None
    out = {}
    for r in rows[1:]:
        if len(r) > max(i_id, i_lab) and r[i_id].strip().isdigit():
            out[_norm_label(r[i_lab])] = int(r[i_id])
    return out


def required_tags(tags: dict[str, int]) -> dict[str, int | None]:
    """Taggar som behövs. "goal" och "accurate" är nödvändiga (skott på mål); saknas de avbryts importen.
    Övriga är valfria – saknas de lagras värdet som NULL, aldrig som 0."""
    def find(*labels: str, required: bool = False) -> int | None:
        for lab in labels:
            if _norm_label(lab) in tags:
                return tags[_norm_label(lab)]
        if required:
            raise ValueError(f"Taggen {labels[0]!r} finns inte i tags2name.csv – importen avbryts. "
                             f"Etiketter i filen: {sorted(tags)[:60]}")
        return None
    return {"goal": find("goal", required=True), "accurate": find("accurate", required=True),
            "key_pass": find("key_pass", "keypass", "key pass"),
            "yellow": find("yellow_card", "yellow"), "red": find("red_card", "red"),
            "second_yellow": find("second_yellow_card", "second_yellow", "2nd yellow")}


def aggregate_events(events, tag: dict[str, int], match_ids: set[int]):
    """Lag- och spelarstatistik per match ur en ström av Wyscout-händelser (endast 1H/2H)."""
    cards0 = 0 if tag["yellow"] is not None and tag["red"] is not None else None  # okänd tagg => NULL
    kp0 = 0 if tag["key_pass"] is not None else None
    team = defaultdict(lambda: {"shots": 0, "shots_on_target": 0, "corners": 0, "fouls": 0, "yellow_cards": cards0,
                                "red_cards": cards0, "passes": 0})
    player = defaultdict(lambda: {"shots": 0, "shots_on_target": 0, "goals": 0, "passes": 0, "key_passes": kp0,
                                  "fouls": 0})
    seen = set()
    kinds: Counter = Counter()
    for ev in events:
        mid = ev.get("matchId")
        if mid not in match_ids or ev.get("matchPeriod") not in ("1H", "2H"):
            continue
        seen.add(mid)
        tid, pid = ev.get("teamId"), ev.get("playerId")
        tags = {t.get("id") for t in ev.get("tags") or []}
        name, sub = (ev.get("eventName") or "").lower(), (ev.get("subEventName") or "").lower()
        kinds[(ev.get("eventName"), ev.get("subEventName"))] += 1
        t = team[(mid, tid)]
        p = player[(mid, tid, pid)] if pid else None
        if name == "shot" or (name == "free kick" and sub in SHOT_SUBEVENTS):
            t["shots"] += 1
            on = tag["accurate"] in tags or tag["goal"] in tags
            if on:
                t["shots_on_target"] += 1
            if p is not None:
                p["shots"] += 1
                p["shots_on_target"] += int(on)
                p["goals"] += int(tag["goal"] in tags)
        elif name == "free kick" and sub == "corner":
            t["corners"] += 1
        elif name == "pass":
            t["passes"] += 1
            if p is not None:
                p["passes"] += 1
                if kp0 is not None:
                    p["key_passes"] += int(tag["key_pass"] in tags)
        elif name == "foul":
            t["fouls"] += 1
            if p is not None:
                p["fouls"] += 1
            if cards0 is not None:
                if tag["yellow"] in tags:
                    t["yellow_cards"] += 1
                if tag["red"] in tags or (tag["second_yellow"] is not None and tag["second_yellow"] in tags):
                    t["red_cards"] += 1
    return dict(team), dict(player), seen, kinds


def minutes_from_formation(form: dict, end_minute: float = 90.0) -> dict[int, dict]:
    """Uppskattade minuter per spelare ur startelva och byten (Wyscout anger bytesminut)."""
    out: dict[int, dict] = {}
    for e in form.get("lineup") or []:
        out[e["playerId"]] = {"started": 1, "on": 0.0, "off": None}
    for s in form.get("substitutions") or []:
        if not isinstance(s, dict):
            continue
        minute = float(s.get("minute") or 0)
        if s.get("playerOut") in out:
            out[s["playerOut"]]["off"] = minute
        if s.get("playerIn"):
            out[s["playerIn"]] = {"started": 0, "on": minute, "off": None}
    for v in out.values():
        v["minutes"] = round((v["off"] if v["off"] is not None else end_minute) - v["on"], 1)
    return out


class WyscoutAdapter(Adapter):
    source_id = "wyscout_public"
    label = "Wyscout öppna data"
    jobs = ("backfill",)

    def _files(self, job: str) -> dict[str, str]:
        res = self.http.get(self.source_id, COLLECTION, job=job, conditional=False)
        if res.status != 200:
            raise RuntimeError(f"figshare-samlingen svarade HTTP {res.status}")
        self.http.finish(res.fetch_id, "ok")
        urls = {}
        for art in res.json() or []:
            d = self.http.get(self.source_id, ARTICLE.format(id=art["id"]), job=job, conditional=False)
            if d.status != 200:
                continue
            self.http.finish(d.fetch_id, "ok")
            for f in (d.json() or {}).get("files", []):
                urls[f["name"]] = f["download_url"]
        missing = [n for n in NEEDED if n not in urls]
        if missing:
            raise RuntimeError(f"Filer saknas i figshare-samlingen: {missing}")
        return urls

    def _download(self, url: str, job: str, archive: str = "full"):
        res = self.http.get(self.source_id, url, job=job, conditional=False, archive=archive, timeout=600)
        if res.status != 200 or not res.content:
            raise RuntimeError(f"Nedladdning misslyckades: {url} (HTTP {res.status})")
        return res

    def run(self, job: str = "backfill", competitions: list[str] | None = None, progress=None) -> dict:
        wanted = set(competitions or AREA_TO_COMP.values())
        step = (lambda msg, i, n: progress(msg, i, n)) if progress else (lambda *a: None)
        step("Wyscout: läser filförteckning på figshare", 0, 6)
        urls = self._files(job)
        dl = {}
        for i, name in enumerate(("tags2name.csv", "competitions.json", "teams.json", "players.json", "matches.zip"), 1):
            step(f"Wyscout: hämtar {name}", i, 6)
            dl[name] = self._download(urls[name], job)
        tag = required_tags(tag_ids(dl["tags2name.csv"].text()))
        self._kp_known = tag["key_pass"] is not None
        comps = {c["wyId"]: AREA_TO_COMP.get((c.get("area") or {}).get("name")) for c in dl["competitions.json"].json()
                 if c.get("type") == "club"}
        teams = {t["wyId"]: t for t in dl["teams.json"].json()}
        players = {p["wyId"]: p for p in dl["players.json"].json()}
        for n in ("tags2name.csv", "competitions.json", "teams.json", "players.json"):
            self.http.finish(dl[n].fetch_id, "ok")
        matches = []
        with zipfile.ZipFile(io.BytesIO(dl["matches.zip"].content)) as z:
            for member in z.namelist():
                if not member.endswith(".json"):
                    continue
                for m in json.loads(z.read(member).decode("utf-8")):
                    code = comps.get(m.get("competitionId"))
                    if code in wanted and m.get("status", "Played") == "Played":
                        matches.append((code, m))
        self.counts["matches_in_source"] = len(matches)
        # 1) koppla lag-ID:n till befintliga lag via gemensamma matcher
        by_comp = defaultdict(list)
        for code, m in matches:
            td = m["teamsData"]
            sides = {v["side"]: v for v in td.values()}
            if "home" not in sides or "away" not in sides:
                continue
            h, a = sides["home"], sides["away"]
            by_comp[code].append({"date": m["dateutc"][:10], "home_sid": h["teamId"], "away_sid": a["teamId"],
                                  "home_name": (teams.get(h["teamId"]) or {}).get("officialName"),
                                  "away_name": (teams.get(a["teamId"]) or {}).get("officialName"),
                                  "hg": h.get("score"), "ag": a.get("score")})
        for code, fx in by_comp.items():
            r = link_source_teams(self.app, self.source_id, code, fx)
            self.counts[f"teams_linked_{code}"] += len(r["linked"])
            self.counts["teams_unlinked"] += len(r["unlinked"])
            self.counts["link_conflicts"] += len(r["conflicts"])
        # 2) matcher och resultat
        ours: dict[int, tuple] = {}
        for code, m in matches:
            sides = {v["side"]: v for v in m["teamsData"].values()}
            if "home" not in sides or "away" not in sides:
                self.counts["skipped"] += 1
                continue
            h, a = sides["home"], sides["away"]
            ko = datetime.strptime(m["dateutc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            hid = self._team(teams, h["teamId"], code)
            aid = self._team(teams, a["teamId"], code)
            sy = int(m["dateutc"][:4]) if int(m["dateutc"][5:7]) >= 7 else int(m["dateutc"][:4]) - 1
            mid, act = self.repo.upsert_match(competition_code=code, kickoff_utc=ko, home_team_id=hid,
                                              away_team_id=aid, source_id=self.source_id, status="finished",
                                              season_label=f"{sy}/{str(sy + 1)[-2:]}", source_match_id=str(m["wyId"]),
                                              round_=f"Omgång {m.get('gameweek')}" if m.get("gameweek") else None,
                                              fetch_id=dl["matches.zip"].fetch_id)
            self.counts[f"match_{act}"] += 1
            avail = ko + timedelta(hours=3)
            self.repo.upsert_result(mid, self.source_id, {"home_goals_90": h.get("score"),
                                                          "away_goals_90": a.get("score"),
                                                          "home_goals_ht": h.get("scoreHT"),
                                                          "away_goals_ht": a.get("scoreHT")},
                                    fetch_id=dl["matches.zip"].fetch_id, available_at=avail,
                                    original_home=(teams.get(h["teamId"]) or {}).get("name"),
                                    original_away=(teams.get(a["teamId"]) or {}).get("name"))
            ours[m["wyId"]] = (mid, ko, {h["teamId"]: hid, a["teamId"]: aid}, h["teamId"], m)
        self.http.finish(dl["matches.zip"].fetch_id, "ok", {"inserted": self.counts.get("match_inserted", 0),
                                                            "unchanged": self.counts.get("match_unchanged", 0)})
        # 3) händelser (stor fil) – strömmas, aggregeras per match
        step("Wyscout: hämtar events.zip (cirka 77 MB)", 5, 6)
        ev = self._download(urls["events.zip"], job, archive="none")
        team_stats: dict = {}
        player_stats: dict = {}
        seen: set = set()
        kinds: Counter = Counter()
        with zipfile.ZipFile(io.BytesIO(ev.content)) as z:
            for member in z.namelist():
                if not member.endswith(".json"):
                    continue
                step(f"Wyscout: räknar händelser i {member}", 5, 6)
                with z.open(member) as raw:
                    ts, ps, s, k = aggregate_events(iter_json_array(io.TextIOWrapper(raw, encoding="utf-8")),
                                                    tag, set(ours))
                kinds.update(k)
                team_stats.update(ts)
                player_stats.update(ps)
                seen |= s
        step("Wyscout: sparar lag- och spelarstatistik", 6, 6)
        for wy_mid, (mid, ko, tmap, home_sid, m) in ours.items():
            if wy_mid not in seen:
                self.counts["events_missing"] += 1
                continue
            avail = ko + timedelta(hours=3)
            for sid, tid in tmap.items():
                st = team_stats.get((wy_mid, sid))
                if st is None:
                    continue
                r = self.repo.upsert_team_stats(mid, tid, sid == home_sid, self.source_id, dict(st),
                                                fetch_id=ev.fetch_id, available_at=avail)
                self.counts[f"teamstats_{r}"] += 1
            self._players(m, mid, tmap, wy_mid, players, player_stats, ev.fetch_id, avail)
        self.http.finish(ev.fetch_id, "ok", {"inserted": len(seen)})
        out = self.summary()
        # Händelsetyper i källan (för kontroll av att skott/hörnor räknas på rätt händelser)
        out["event_kinds"] = {f"{a} / {b}": n for (a, b), n in kinds.most_common(40)}
        return out

    def _team(self, teams: dict, wy_id: int, code: str) -> int:
        t = teams.get(wy_id) or {}
        return self.team(t.get("officialName") or t.get("name") or str(wy_id), context=code, source_team_id=wy_id)

    def _players(self, m: dict, mid: int, tmap: dict, wy_mid: int, players: dict, pstats: dict, fetch_id: int,
                 avail: datetime) -> None:
        with self.app.db.tx() as c:
            for side in m["teamsData"].values():
                sid = side["teamId"]
                tid = tmap.get(sid)
                form = side.get("formation") or {}
                if tid is None or not side.get("hasFormation"):
                    continue
                mins = minutes_from_formation(form)
                starters = []
                for pid, mv in mins.items():
                    pl = players.get(pid) or {}
                    name = " ".join(x for x in (pl.get("firstName"), pl.get("lastName")) if x) or pl.get("shortName")
                    if not name:
                        continue
                    our = self.repo.resolve_player(name, self.source_id, str(pid))
                    st = pstats.get((wy_mid, sid, pid), {})
                    c.execute("""INSERT OR IGNORE INTO player_match_stats (match_id, player_id, team_id, source_id,
                        fetch_id, started, minutes, minutes_estimated, goals, shots, shots_on_target, passes,
                        key_passes, fouls, available_at_utc, observed_at_utc) VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?)""",
                              (mid, our, tid, self.source_id, fetch_id, mv["started"], mv["minutes"], st.get("goals", 0),
                               st.get("shots", 0), st.get("shots_on_target", 0), st.get("passes", 0),
                               st.get("key_passes", 0 if self._kp_known else None), st.get("fouls", 0), to_iso(avail), to_iso(self.now())))
                    if mv["started"]:
                        starters.append({"name": name, "player_id": our, "is_starter": True,
                                         "position": (pl.get("role") or {}).get("name")})
                if starters:
                    self.repo.upsert_lineup(mid, tid, self.source_id, "confirmed", starters, fetched_at=avail,
                                            fetch_id=fetch_id)
                    self.counts["lineups"] += 1
