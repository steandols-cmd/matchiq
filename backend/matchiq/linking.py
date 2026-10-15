"""Koppla en källas lag-ID:n till befintliga lag med hjälp av matcher som redan finns i databasen.

Problemet: källor skriver lagnamn olika ("Manchester City" / "Manchester City FC" / "Man City"). Att
gissa på namnlikhet ger fel (Paris ≠ Paris FC). I stället används matcherna som bevis: om källans match
"lag 1646 – lag 1659, 1–2, 13 maj 2018" motsvarar exakt en befintlig match i samma tävling (±1 dygn,
samma resultat efter 90 minuter) får källans lag-ID en röst för respektive befintligt lag. Ett ID kopplas
först när rösterna är tillräckligt många och entydiga, och ingen annan av källans ID:n gör anspråk på samma
lag. Varje koppling loggas i ändringsloggen. Okopplade ID:n hanteras som vanligt (exakta alias, annars
nytt lag som flaggas för granskning).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from .core import App
from .entities import _significant_tokens


def _team_tokens(app: App, team_id: int) -> set[str]:
    toks: set[str] = set()
    for r in app.db.query("SELECT alias FROM team_aliases WHERE team_id=? UNION SELECT name FROM teams WHERE id=?",
                          (team_id, team_id)):
        toks |= _significant_tokens(r[0])
    return toks


def link_source_teams(app: App, source_id: str, competition_code: str, fixtures: list[dict], *,
                      min_votes: int = 2, min_share: float = 0.8, day_tolerance: int = 1) -> dict:
    """fixtures: [{date: 'ÅÅÅÅ-MM-DD', home_sid, away_sid, home_name, away_name, hg, ag}] (resultat efter 90 min).

    Returnerar {"linked": {sid: team_id}, "already": n, "conflicts": [...], "unlinked": [sid, ...]}.
    """
    comp = app.db.one("SELECT id FROM competitions WHERE code=?", (competition_code,))
    if comp is None:
        return {"linked": {}, "already": 0, "conflicts": [], "unlinked": []}
    known = {r["source_team_id"]: r["team_id"] for r in app.db.query(
        "SELECT source_team_id, team_id FROM team_source_ids WHERE source_id=?", (source_id,))}
    names: dict[str, str] = {}
    sids: set[str] = set()
    for f in fixtures:
        for side in ("home", "away"):
            sid = str(f[f"{side}_sid"])
            sids.add(sid)
            names.setdefault(sid, f.get(f"{side}_name") or "")
    tok_cache: dict[int, set[str]] = {}

    def toks(tid: int) -> set[str]:
        if tid not in tok_cache:
            tok_cache[tid] = _team_tokens(app, tid)
        return tok_cache[tid]

    def candidates(f: dict) -> list:
        if f.get("hg") is None or f.get("ag") is None:
            return []
        d = date.fromisoformat(str(f["date"])[:10])
        lo, hi = (d - timedelta(days=day_tolerance)).isoformat(), (d + timedelta(days=day_tolerance)).isoformat()
        return app.db.query("""SELECT DISTINCT m.id, m.home_team_id, m.away_team_id FROM matches m
            JOIN match_results r ON r.match_id = m.id
            WHERE m.competition_id=? AND m.local_date BETWEEN ? AND ? AND r.source_id<>?
              AND r.home_goals_90=? AND r.away_goals_90=?""",
                            (comp["id"], lo, hi, source_id, int(f["hg"]), int(f["ag"])))

    mapping = dict(known)
    votes: dict[str, Counter] = defaultdict(Counter)
    for _pass in (1, 2):
        votes.clear()
        for f in fixtures:
            hs, as_ = str(f["home_sid"]), str(f["away_sid"])
            cands = candidates(f)
            # Redan kopplade ID:n begränsar kandidaterna (andra varvet)
            if hs in mapping:
                cands = [c for c in cands if c["home_team_id"] == mapping[hs]]
            if as_ in mapping:
                cands = [c for c in cands if c["away_team_id"] == mapping[as_]]
            if len(cands) > 1:
                ht, at = _significant_tokens(f.get("home_name") or ""), _significant_tokens(f.get("away_name") or "")
                narrowed = [c for c in cands if (ht & toks(c["home_team_id"])) and (at & toks(c["away_team_id"]))]
                cands = narrowed
            if len(cands) != 1:
                continue
            c = cands[0]
            votes[hs][c["home_team_id"]] += 1
            votes[as_][c["away_team_id"]] += 1
        proposed: dict[str, int] = {}
        for sid, cnt in votes.items():
            if sid in mapping:
                continue
            (tid, n), total = cnt.most_common(1)[0], sum(cnt.values())
            if n >= min_votes and n / total >= min_share:
                proposed[sid] = tid
        claimed = Counter(proposed.values())
        taken = set(mapping.values())
        conflicts = []
        for sid, tid in list(proposed.items()):
            if claimed[tid] > 1 or tid in taken:
                conflicts.append({"source_team_id": sid, "name": names.get(sid), "team_id": tid})
                proposed.pop(sid)
        mapping.update(proposed)

    new = {sid: tid for sid, tid in mapping.items() if sid not in known and sid in sids}
    if new:
        with app.db.tx() as c:
            for sid, tid in new.items():
                c.execute("""INSERT OR IGNORE INTO team_source_ids (team_id, source_id, source_team_id, name_original)
                             VALUES (?,?,?,?)""", (tid, source_id, sid, names.get(sid)))
                app.repo.log_change(c, "team_link", tid, f"{source_id}:{sid}", None,
                                    f"{names.get(sid)} → lag {tid} (kopplat via {sum(votes[sid].values())} "
                                    f"gemensamma matcher)", source_id=source_id)
    return {"linked": new, "already": len([s for s in sids if s in known]), "conflicts": conflicts,
            "unlinked": sorted(s for s in sids if s not in mapping)}
