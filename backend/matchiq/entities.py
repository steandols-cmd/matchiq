"""Entiteter och idempotent uppdatering: lag/alias, matcher, resultat, lagstatistik, startelvor.

Regler (från kravspecifikationen):
* Deduplicera först med källans/officiellt match-ID, annars tävling + datum + hemmalag + bortalag.
* Lagalias matchas EXAKT efter normalisering (skiftläge, diakritiska tecken, blanksteg, punkter).
  "Paris" och "Paris FC" är olika strängar och kan därför aldrig förväxlas; likhetsmatchning används
  bara som förslag i granskningsvyn, aldrig automatiskt.
* Saknade värden lagras som NULL. Ett NULL i en uppdatering skriver inte över ett känt värde.
* Varje ändring loggas i change_log med källa och tid.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Iterable

from .db import Database
from .timeutil import Clock, local_date, parse_iso, to_iso

_SPECIAL = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "ß": "ss", "ł": "l", "Ł": "l",
                          "đ": "d", "Đ": "d", "ı": "i", "œ": "oe", "Œ": "oe", "þ": "th", "ð": "d"})


def normalize_name(name: str) -> str:
    """Normalisering för exakt aliasmatchning. Tar INTE bort ord som 'FC' – då skulle Paris/Paris FC krocka."""
    s = unicodedata.normalize("NFKC", str(name)).strip().translate(_SPECIAL)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold().replace(".", "").replace("’", "'").replace("`", "'")
    s = re.sub(r"[‐-―-]", " ", s)  # bindestreck = mellanslag ("Saint-Germain" = "Saint Germain")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


_STOP_TOKENS = {"fc", "cf", "sc", "ac", "afc", "fk", "sk", "bk", "if", "club", "de", "da", "do", "del", "la", "le",
                "the", "sv", "vfl", "vfb", "tsg", "rc", "rcd", "ud", "cd", "us", "ss", "as", "ssc", "kv", "krc",
                "kaa", "sl", "calcio", "football", "futbol", "royal", "real", "city", "united", "athletic",
                "olympique", "racing", "borussia", "dynamo", "dinamo", "pfk", "fotball", "and"}


def _significant_tokens(name: str) -> set[str]:
    toks = re.split(r"[\s/\-']+", normalize_name(name))
    return {t for t in toks if len(t) >= 4 and t not in _STOP_TOKENS and not t.isdigit()}


TEAM_STAT_FIELDS = ("shots", "shots_on_target", "corners", "fouls", "yellow_cards", "red_cards",
                    "offsides", "saves", "possession", "passes", "xg")
RESULT_FIELDS = ("home_goals_90", "away_goals_90", "home_goals_aet", "away_goals_aet", "home_pens",
                 "away_pens", "decided_by", "home_goals_ht", "away_goals_ht")

RESULT_DELAY = timedelta(hours=3)  # resultat/statistik anses kända tidigast 3 h efter avspark


def deterministic_color(name: str) -> tuple[str, str]:
    """Neutral färgsättning för genererade klubbmärken (inga riktiga logotyper bäddas in)."""
    h = int(hashlib.sha256(normalize_name(name).encode()).hexdigest()[:8], 16)
    palette = ["#C8102E", "#1D428A", "#0B6E4F", "#6C1D45", "#F2A900", "#00529F", "#D71920", "#004D98",
               "#7A263A", "#132257", "#FDB913", "#00A650", "#E03A3E", "#5CBFEB", "#241F20", "#EF0107"]
    a = palette[h % len(palette)]
    b = palette[(h // 16) % len(palette)]
    if a == b:
        b = "#FFFFFF"
    return a, b


class Repo:
    def __init__(self, db: Database, clock: Clock):
        self.db = db
        self.clock = clock

    # ------------------------------------------------------------------ hjälp
    def now_iso(self) -> str:
        return to_iso(self.clock.now())  # type: ignore[return-value]

    def log_change(self, c, entity: str, entity_id: Any, field: str | None, old: Any, new: Any,
                   source_id: str | None = None, fetch_id: int | None = None, import_id: int | None = None,
                   actor: str = "system") -> None:
        c.execute("""INSERT INTO change_log (at_utc, entity, entity_id, field, old_value, new_value, source_id,
                     fetch_id, import_id, actor) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (self.now_iso(), entity, str(entity_id), field,
                   None if old is None else str(old), None if new is None else str(new),
                   source_id, fetch_id, import_id, actor))

    # ------------------------------------------------------------ tävlingar
    def competition_id(self, code: str) -> int:
        r = self.db.one("SELECT id FROM competitions WHERE code=?", (code,))
        if r is None:
            raise KeyError(f"Okänd tävlingskod {code}")
        return int(r["id"])

    def season_id(self, competition_id: int, label: str | None) -> int | None:
        if not label:
            return None
        label = str(label).strip()
        with self.db.tx() as c:
            c.execute("INSERT OR IGNORE INTO seasons (competition_id, label) VALUES (?,?)", (competition_id, label))
            return int(c.execute("SELECT id FROM seasons WHERE competition_id=? AND label=?",
                                 (competition_id, label)).fetchone()[0])

    # ------------------------------------------------------------------ lag
    def find_team(self, name: str, source_id: str = "", context: str = "",
                  source_team_id: str | None = None) -> int | None:
        if source_team_id:
            r = self.db.one("SELECT team_id FROM team_source_ids WHERE source_id=? AND source_team_id=?",
                            (source_id, str(source_team_id)))
            if r:
                return int(r["team_id"])
        norm = normalize_name(name)
        # Prioritet: källspecifikt alias i kontext > källspecifikt > globalt i kontext > globalt
        for sid, ctx in ((source_id, context), (source_id, ""), ("", context), ("", "")):
            r = self.db.one("SELECT team_id FROM team_aliases WHERE alias_norm=? AND source_id=? AND context=?",
                            (norm, sid, ctx))
            if r:
                return int(r["team_id"])
        return None

    def resolve_team(self, name: str, source_id: str, context: str = "", source_team_id: str | None = None,
                     country: str | None = None, domestic_code: str | None = None) -> int:
        """Hitta laget via käll-ID eller exakt alias; skapa annars ett nytt lag markerat för granskning."""
        name = str(name).strip()
        if not name:
            raise ValueError("Tomt lagnamn")
        tid = self.find_team(name, source_id, context, source_team_id)
        with self.db.tx() as c:
            if tid is None:
                col_a, col_b = deterministic_color(name)
                # Flagga för granskning endast om ett befintligt lag har ett likartat namn (möjlig dubblett).
                review = 1 if self.possible_duplicates(name) else 0
                cur = c.execute("""INSERT INTO teams (name, country, domestic_competition_code, color_primary,
                    color_secondary, needs_review, created_by_source, created_at_utc) VALUES (?,?,?,?,?,?,?,?)""",
                                (name, country, domestic_code, col_a, col_b, review, source_id, self.now_iso()))
                tid = int(cur.lastrowid)
                # Autoskapade alias gäller bara i den kontext (liga/tävling) där namnet sågs.
                c.execute("""INSERT OR IGNORE INTO team_aliases (team_id, alias, alias_norm, context, source_id,
                    origin, created_at_utc) VALUES (?,?,?,?,?,?,?)""",
                          (tid, name, normalize_name(name), context or "", "", "auto", self.now_iso()))
                self.log_change(c, "team", tid, None, None, name, source_id=source_id)
            else:
                if country or domestic_code:
                    c.execute("""UPDATE teams SET country=COALESCE(country, ?),
                        domestic_competition_code=COALESCE(domestic_competition_code, ?) WHERE id=?""",
                              (country, domestic_code, tid))
            if source_team_id:
                c.execute("""INSERT OR IGNORE INTO team_source_ids (team_id, source_id, source_team_id, name_original)
                             VALUES (?,?,?,?)""", (tid, source_id, str(source_team_id), name))
        return tid

    def possible_duplicates(self, name: str, exclude_id: int | None = None, limit: int = 5) -> list[dict]:
        """Förslag på möjliga dubbletter (delade betydelsebärande ord). Används ENDAST som förslag."""
        toks = _significant_tokens(name)
        if not toks:
            return []
        out = []
        for r in self.db.query("SELECT DISTINCT t.id, t.name FROM teams t JOIN team_aliases a ON a.team_id=t.id"):
            if exclude_id is not None and r["id"] == exclude_id:
                continue
            other = _significant_tokens(r["name"])
            if toks & other:
                out.append({"id": r["id"], "name": r["name"], "shared": sorted(toks & other)})
                if len(out) >= limit:
                    break
        return out

    def add_alias(self, team_id: int, alias: str, context: str = "", source_id: str = "",
                  origin: str = "user") -> None:
        norm = normalize_name(alias)
        with self.db.tx() as c:
            existing = c.execute("SELECT team_id FROM team_aliases WHERE alias_norm=? AND context=? AND source_id=?",
                                 (norm, context, source_id)).fetchone()
            if existing and int(existing[0]) != team_id:
                raise ValueError(f"Aliaset '{alias}' pekar redan på ett annat lag (id {existing[0]}). "
                                 "Ta bort det först om det är fel.")
            c.execute("""INSERT OR IGNORE INTO team_aliases (team_id, alias, alias_norm, context, source_id, origin,
                         created_at_utc) VALUES (?,?,?,?,?,?,?)""",
                      (team_id, alias, norm, context, source_id, origin, self.now_iso()))

    def merge_teams(self, keep_id: int, drop_id: int) -> None:
        """Slå ihop två lagidentiteter (endast på uttrycklig begäran från användaren)."""
        if keep_id == drop_id:
            return
        with self.db.tx() as c:
            for table, col in (("matches", "home_team_id"), ("matches", "away_team_id"),
                               ("team_match_stats", "team_id"), ("player_match_stats", "team_id"),
                               ("lineups", "team_id"), ("availability", "team_id")):
                c.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (keep_id, drop_id))
            c.execute("UPDATE OR IGNORE team_aliases SET team_id=? WHERE team_id=?", (keep_id, drop_id))
            c.execute("DELETE FROM team_aliases WHERE team_id=?", (drop_id,))
            c.execute("UPDATE OR IGNORE team_source_ids SET team_id=? WHERE team_id=?", (keep_id, drop_id))
            c.execute("DELETE FROM team_source_ids WHERE team_id=?", (drop_id,))
            # natural keys innehåller lag-id – räkna om
            for r in c.execute("SELECT m.id, m.local_date, m.home_team_id, m.away_team_id, co.code FROM matches m "
                               "JOIN competitions co ON co.id=m.competition_id WHERE ? IN (m.home_team_id, m.away_team_id)",
                               (keep_id,)).fetchall():
                c.execute("UPDATE matches SET natural_key=? WHERE id=?",
                          (f"{r['code']}|{r['local_date']}|{r['home_team_id']}|{r['away_team_id']}", r["id"]))
            c.execute("DELETE FROM teams WHERE id=?", (drop_id,))
            self.log_change(c, "team", keep_id, "merge", drop_id, keep_id, actor="user")

    # --------------------------------------------------------------- matcher
    def upsert_match(self, *, competition_code: str, kickoff_utc: datetime, home_team_id: int, away_team_id: int,
                     source_id: str, status: str = "scheduled", season_label: str | None = None,
                     source_match_id: str | None = None, official_match_id: str | None = None,
                     kickoff_time_known: bool = True, stage: str | None = None, round_: str | None = None,
                     matchday: str | None = None, venue: str | None = None,
                     fetch_id: int | None = None, import_id: int | None = None) -> tuple[int, str]:
        comp_id = self.competition_id(competition_code)
        season_id = self.season_id(comp_id, season_label)
        ko = to_iso(kickoff_utc)
        ld = local_date(kickoff_utc)
        nk = f"{competition_code}|{ld}|{home_team_id}|{away_team_id}"
        with self.db.tx() as c:
            row = None
            if source_match_id:
                row = c.execute("""SELECT m.* FROM match_source_ids s JOIN matches m ON m.id=s.match_id
                                   WHERE s.source_id=? AND s.source_match_id=?""",
                                (source_id, str(source_match_id))).fetchone()
            if row is None and official_match_id:
                row = c.execute("SELECT * FROM matches WHERE official_match_id=?", (str(official_match_id),)).fetchone()
            if row is None:
                row = c.execute("SELECT * FROM matches WHERE natural_key=?", (nk,)).fetchone()
            if row is None:
                # Tolerans för datumformat (UTC vs lokalt datum): samma tävling och lag ±1 dygn
                for delta in (-1, 1):
                    alt = (datetime.fromisoformat(ld) + timedelta(days=delta)).strftime("%Y-%m-%d")
                    row = c.execute("SELECT * FROM matches WHERE natural_key=?",
                                    (f"{competition_code}|{alt}|{home_team_id}|{away_team_id}",)).fetchone()
                    if row is not None:
                        break
            now = self.now_iso()
            if row is None:
                cur = c.execute("""INSERT INTO matches (competition_id, season_id, stage, round, matchday, kickoff_utc,
                    kickoff_time_known, local_date, home_team_id, away_team_id, venue, status, official_match_id,
                    natural_key, created_at_utc, updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (comp_id, season_id, stage, round_, matchday, ko, 1 if kickoff_time_known else 0, ld,
                                 home_team_id, away_team_id, venue, status,
                                 str(official_match_id) if official_match_id else None, nk, now, now))
                mid = int(cur.lastrowid)
                action = "inserted"
                self.log_change(c, "match", mid, None, None, nk, source_id, fetch_id, import_id)
            else:
                mid = int(row["id"])
                action = "unchanged"
                updates: dict[str, Any] = {}
                # Avsparkstid: en källa med känd klocktid får uppdatera; datum-only får inte skriva över tid.
                if kickoff_time_known and ko != row["kickoff_utc"]:
                    updates["kickoff_utc"] = ko
                    updates["local_date"] = ld
                    updates["kickoff_time_known"] = 1
                    updates["natural_key"] = nk
                if status != row["status"] and status != "unknown":
                    # Avslutad match går inte tillbaka till planerad
                    if not (row["status"] == "finished" and status == "scheduled"):
                        updates["status"] = status
                for col, val in (("stage", stage), ("round", round_), ("matchday", matchday), ("venue", venue),
                                 ("season_id", season_id)):
                    if val is not None and row[col] is None:
                        updates[col] = val
                if official_match_id and row["official_match_id"] is None:
                    clash = c.execute("SELECT id FROM matches WHERE official_match_id=?",
                                      (str(official_match_id),)).fetchone()
                    if clash is None:
                        updates["official_match_id"] = str(official_match_id)
                if updates:
                    if "natural_key" in updates:
                        clash = c.execute("SELECT id FROM matches WHERE natural_key=? AND id<>?",
                                          (updates["natural_key"], mid)).fetchone()
                        if clash:
                            updates.pop("natural_key")
                            updates.pop("local_date", None)
                    sets = ", ".join(f"{k}=?" for k in updates)
                    c.execute(f"UPDATE matches SET {sets}, updated_at_utc=? WHERE id=?",
                              tuple(updates.values()) + (now, mid))
                    for k, v in updates.items():
                        self.log_change(c, "match", mid, k, row[k], v, source_id, fetch_id, import_id)
                    action = "updated"
            if source_match_id:
                c.execute("INSERT OR IGNORE INTO match_source_ids (match_id, source_id, source_match_id) VALUES (?,?,?)",
                          (mid, source_id, str(source_match_id)))
        return mid, action

    # --------------------------------------------------------------- resultat
    def upsert_result(self, match_id: int, source_id: str, values: dict, *, available_at: datetime | None = None,
                      observed_at: datetime | None = None, original_home: str | None = None,
                      original_away: str | None = None, fetch_id: int | None = None,
                      import_id: int | None = None) -> str:
        m = self.db.one("SELECT kickoff_utc FROM matches WHERE id=?", (match_id,))
        if m is None:
            raise KeyError(match_id)
        ko = parse_iso(m["kickoff_utc"])
        avail = to_iso(available_at or (ko + RESULT_DELAY))  # type: ignore[operator]
        obs = to_iso(observed_at or self.clock.now())
        clean = {k: values.get(k) for k in RESULT_FIELDS}
        if clean["decided_by"] is None:
            if clean["home_pens"] is not None:
                clean["decided_by"] = "penalties"
            elif clean["home_goals_aet"] is not None:
                clean["decided_by"] = "extra_time"
            elif clean["home_goals_90"] is not None:
                clean["decided_by"] = "regular"
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM match_results WHERE match_id=? AND source_id=?",
                            (match_id, source_id)).fetchone()
            if row is None:
                c.execute(f"""INSERT INTO match_results (match_id, source_id, fetch_id, import_id, {", ".join(RESULT_FIELDS)},
                    original_home_name, original_away_name, available_at_utc, observed_at_utc)
                    VALUES (?,?,?,?,{",".join("?" * len(RESULT_FIELDS))},?,?,?,?)""",
                          (match_id, source_id, fetch_id, import_id, *clean.values(), original_home, original_away,
                           avail, obs))
                self.log_change(c, "match_result", match_id, None, None, json.dumps(clean), source_id, fetch_id,
                                import_id)
                if clean["home_goals_90"] is not None:
                    c.execute("UPDATE matches SET status='finished', updated_at_utc=? WHERE id=? AND status<>'finished'",
                              (self.now_iso(), match_id))
                return "inserted"
            changed = {k: v for k, v in clean.items() if v is not None and v != row[k]}
            if not changed:
                return "unchanged"
            sets = ", ".join(f"{k}=?" for k in changed)
            c.execute(f"UPDATE match_results SET {sets}, observed_at_utc=?, fetch_id=COALESCE(?, fetch_id), "
                      f"import_id=COALESCE(?, import_id) WHERE id=?",
                      (*changed.values(), obs, fetch_id, import_id, row["id"]))
            for k, v in changed.items():
                self.log_change(c, "match_result", match_id, k, row[k], v, source_id, fetch_id, import_id)
            return "updated"

    def upsert_team_stats(self, match_id: int, team_id: int, is_home: bool, source_id: str, values: dict, *,
                          available_at: datetime | None = None, observed_at: datetime | None = None,
                          fetch_id: int | None = None, import_id: int | None = None) -> str:
        m = self.db.one("SELECT kickoff_utc FROM matches WHERE id=?", (match_id,))
        ko = parse_iso(m["kickoff_utc"])  # type: ignore[index]
        avail = to_iso(available_at or (ko + RESULT_DELAY))  # type: ignore[operator]
        obs = to_iso(observed_at or self.clock.now())
        clean = {k: values.get(k) for k in TEAM_STAT_FIELDS}
        if all(v is None for v in clean.values()):
            return "skipped"
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM team_match_stats WHERE match_id=? AND team_id=? AND source_id=?",
                            (match_id, team_id, source_id)).fetchone()
            if row is None:
                c.execute(f"""INSERT INTO team_match_stats (match_id, team_id, is_home, source_id, fetch_id, import_id,
                    {", ".join(TEAM_STAT_FIELDS)}, available_at_utc, observed_at_utc)
                    VALUES (?,?,?,?,?,?,{",".join("?" * len(TEAM_STAT_FIELDS))},?,?)""",
                          (match_id, team_id, 1 if is_home else 0, source_id, fetch_id, import_id, *clean.values(),
                           avail, obs))
                return "inserted"
            changed = {k: v for k, v in clean.items() if v is not None and v != row[k]}
            if not changed:
                return "unchanged"
            sets = ", ".join(f"{k}=?" for k in changed)
            c.execute(f"UPDATE team_match_stats SET {sets}, observed_at_utc=? WHERE id=?",
                      (*changed.values(), obs, row["id"]))
            for k, v in changed.items():
                self.log_change(c, "team_match_stats", f"{match_id}:{team_id}", k, row[k], v, source_id, fetch_id,
                                import_id)
            return "updated"

    # ---------------------------------------------------------------- spelare
    def resolve_player(self, name: str, source_id: str, source_player_id: str | None = None) -> int | None:
        name = (name or "").strip()
        if not name:
            return None
        if not source_player_id:
            # Utan käll-ID: ett stabilt ID ur namnet inom källan (annars skapas en ny spelare vid varje anrop)
            source_player_id = "namn:" + normalize_name(name)
        with self.db.tx() as c:
            if source_player_id:
                r = c.execute("SELECT player_id FROM player_source_ids WHERE source_id=? AND source_player_id=?",
                              (source_id, str(source_player_id))).fetchone()
                if r:
                    return int(r[0])
            cur = c.execute("INSERT INTO players (name, created_at_utc) VALUES (?,?)", (name, self.now_iso()))
            pid = int(cur.lastrowid)
            if source_player_id:
                c.execute("INSERT INTO player_source_ids (player_id, source_id, source_player_id, name_original) "
                          "VALUES (?,?,?,?)", (pid, source_id, str(source_player_id), name))
            return pid

    # ---------------------------------------------------------------- elvor
    def upsert_lineup(self, match_id: int, team_id: int, source_id: str, status: str,
                      players: Iterable[dict], *, fetched_at: datetime, published_at: datetime | None = None,
                      formation: str | None = None, source_url: str | None = None,
                      fetch_id: int | None = None, import_id: int | None = None) -> str:
        """Spara en elva. Samma innehåll från samma källa skapar ingen dubblett (innehållshash)."""
        if status not in ("confirmed", "expected"):
            raise ValueError("status måste vara confirmed eller expected")
        plist = list(players)
        payload = json.dumps([{k: p.get(k) for k in ("name", "number", "position", "is_starter")} for p in plist],
                             sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(((formation or "") + "|" + payload).encode()).hexdigest()
        with self.db.tx() as c:
            exists = c.execute("""SELECT id FROM lineups WHERE match_id=? AND team_id=? AND source_id=? AND status=?
                                  AND content_hash=?""", (match_id, team_id, source_id, status, h)).fetchone()
            if exists:
                return "unchanged"
            cur = c.execute("""INSERT INTO lineups (match_id, team_id, source_id, status, formation, source_url,
                published_at_utc, fetched_at_utc, fetch_id, import_id, content_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (match_id, team_id, source_id, status, formation, source_url, to_iso(published_at),
                             to_iso(fetched_at), fetch_id, import_id, h))
            lid = int(cur.lastrowid)
            for slot, p in enumerate(plist, start=1):
                c.execute("""INSERT INTO lineup_players (lineup_id, slot, player_id, name_original, shirt_number,
                             position, is_starter) VALUES (?,?,?,?,?,?,?)""",
                          (lid, slot, p.get("player_id"), p["name"], p.get("number"), p.get("position"),
                           1 if p.get("is_starter", True) else 0))
            self.log_change(c, "lineup", f"{match_id}:{team_id}", status, None, f"{len(plist)} spelare",
                            source_id, fetch_id, import_id)
            return "inserted"

    def add_availability(self, *, match_id: int | None, team_id: int, player_name: str, kind: str,
                         reason: str | None, source_id: str, fetched_at: datetime,
                         published_at: datetime | None = None) -> str:
        with self.db.tx() as c:
            cur = c.execute("""INSERT OR IGNORE INTO availability (match_id, team_id, player_name, kind, reason,
                source_id, published_at_utc, fetched_at_utc) VALUES (?,?,?,?,?,?,?,?)""",
                            (match_id, team_id, player_name, kind, reason, source_id, to_iso(published_at),
                             to_iso(fetched_at)))
            return "inserted" if cur.rowcount else "unchanged"

    def add_odds(self, *, match_id: int, source_id: str, bookmaker: str, kind: str, odds: tuple,
                 fetched_at: datetime, published_at: datetime | None = None) -> str:
        with self.db.tx() as c:
            cur = c.execute("""INSERT OR IGNORE INTO market_odds (match_id, source_id, bookmaker, market, kind,
                odds_home, odds_draw, odds_away, published_at_utc, fetched_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (match_id, source_id, bookmaker, "1x2", kind, odds[0], odds[1], odds[2],
                             to_iso(published_at), to_iso(fetched_at)))
            return "inserted" if cur.rowcount else "unchanged"
