"""Prognostjänst: beräknar V2/V3/baslinje för en match vid en given datagräns och fryser snapshots.

En snapshot skrivs en gång och kan aldrig ändras (databastrigger). Senare uppdateringar skapar nya
snapshots; den frysta T−30-prognosen skrivs aldrig över.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime

from . import catalog
from .core import App
from .models import baseline, v2, v3
from .models.data import HistoryStore
from .models.selection import team_league_map
from .timeutil import parse_iso, to_iso

MODELS = {"V2": (v2, "V2-2.0"), "V3": (v3, "V3-3.0"), "BASE": (baseline, "BASE-1.0")}
_store_lock = threading.Lock()


def _data_version(app: App) -> tuple:
    return (app.db.scalar("SELECT MAX(id) FROM change_log") or 0,
            tuple(sorted(catalog.training_source_ids(app.db))))


def get_store(app: App, comp: str) -> HistoryStore:
    """HistoryStore med cache som invalideras när data eller licensbeslut ändras."""
    with _store_lock:
        key = (comp, _data_version(app))
        cache = app.extras.setdefault("store_cache", {})
        st = cache.get(key)
        if st is None:
            leagues = sorted(set(team_league_map(app).values()))
            st = HistoryStore.load(app.db, None, competitions=sorted({comp, *leagues}))
            v3.set_team_leagues(st, team_league_map(app))
            cache.clear()
            cache[key] = st
        return st


def match_info(app: App, match_id: int) -> dict:
    r = app.db.one("""SELECT m.*, co.code AS comp_code, co.name AS comp_name, h.name AS home_name, a.name AS away_name,
        h.color_primary AS home_c1, h.color_secondary AS home_c2, h.crest_path AS home_crest,
        a.color_primary AS away_c1, a.color_secondary AS away_c2, a.crest_path AS away_crest,
        s.label AS season FROM matches m JOIN competitions co ON co.id=m.competition_id
        JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
        LEFT JOIN seasons s ON s.id=m.season_id WHERE m.id=?""", (match_id,))
    if r is None:
        raise KeyError(f"Match {match_id} finns inte")
    return dict(r)


def lineup_state(app: App, match_id: int, team_id: int, cutoff: datetime) -> dict:
    """Startelvans status vid datagränsen. Hittar aldrig på spelare – saknas elva så sägs det."""
    rows = app.db.query("""SELECT l.*, s.name AS source_name FROM lineups l JOIN sources s ON s.id=l.source_id
        WHERE l.match_id=? AND l.team_id=? AND l.fetched_at_utc<=? ORDER BY
        CASE l.status WHEN 'confirmed' THEN 0 ELSE 1 END, l.fetched_at_utc DESC LIMIT 1""",
                        (match_id, team_id, to_iso(cutoff)))
    if not rows:
        later = app.db.one("SELECT MIN(fetched_at_utc) AS t FROM lineups WHERE match_id=? AND team_id=?",
                           (match_id, team_id))
        return {"status": "unpublished", "label": "Opublicerad", "players": [], "source": None,
                "fetched_at_utc": None, "published_at_utc": None, "formation": None,
                "note": ("Ingen elva fanns tillgänglig vid datagränsen." +
                         (f" (En elva registrerades senare, {later['t']}, och används inte.)" if later and later["t"]
                          else ""))}
    lu = rows[0]
    players = [dict(p) for p in app.db.query(
        "SELECT slot, name_original AS name, shirt_number AS number, position, is_starter FROM lineup_players "
        "WHERE lineup_id=? ORDER BY slot", (lu["id"],))]
    return {"status": lu["status"], "label": "Bekräftad" if lu["status"] == "confirmed" else "Obekräftad (förväntad)",
            "players": players, "source": lu["source_name"], "source_id": lu["source_id"],
            "source_url": lu["source_url"], "fetched_at_utc": lu["fetched_at_utc"],
            "published_at_utc": lu["published_at_utc"], "formation": lu["formation"], "note": ""}


def availability_state(app: App, match_id: int, team_id: int, cutoff: datetime) -> list[dict]:
    return [dict(r) for r in app.db.query(
        """SELECT player_name, kind, reason, source_id, fetched_at_utc FROM availability
           WHERE (match_id=? OR match_id IS NULL) AND team_id=? AND fetched_at_utc<=? ORDER BY kind, player_name""",
        (match_id, team_id, to_iso(cutoff)))]


def compute(app: App, match_id: int, cutoff: datetime, families: tuple[str, ...] = ("V2", "V3", "BASE")) -> dict:
    info = match_info(app, match_id)
    store = get_store(app, info["comp_code"])
    view = store.view(cutoff, exclude_match_ids={match_id})
    results = {}
    for fam in families:
        mod, mid = MODELS[fam]
        row = app.db.one("SELECT params_json, status, version FROM model_versions WHERE id=?", (mid,))
        params = json.loads(row["params_json"]) if row and row["params_json"] else {}
        res = mod.predict(view, info["comp_code"], info["home_team_id"], info["away_team_id"],
                          params if fam == "V3" else None)
        res["status"] = row["status"] if row else None
        res["version"] = row["version"] if row else None
        results[fam] = res
    sources_rows = [dict(r) for r in app.db.query("SELECT * FROM sources")]
    training = [s["id"] for s in sources_rows if catalog.training_allowed(s)]
    training_detail = [{"id": s["id"], "name": s["name"], "policy": s["training_policy"],
                        "approval_note": s["training_approval_note"], "approved_at_utc": s["training_approval_at_utc"]}
                       for s in sources_rows if catalog.training_allowed(s)]
    blocked = [{"id": s["id"], "name": s["name"], "reason": catalog.training_status_text(s)}
               for s in sources_rows if not catalog.training_allowed(s)
               and any(k in (s["data_kinds"] or "") for k in ("results", "team_stats", "events"))]
    used = {m: view.sources_used(m, (info["comp_code"],)) for m in ("goals", "shots", "sot", "corners")}
    lineups = {"home": lineup_state(app, match_id, info["home_team_id"], cutoff),
               "away": lineup_state(app, match_id, info["away_team_id"], cutoff)}
    absences = {"home": availability_state(app, match_id, info["home_team_id"], cutoff),
                "away": availability_state(app, match_id, info["away_team_id"], cutoff)}
    flags = []
    for side in ("home", "away"):
        st = lineups[side]["status"]
        if st != "confirmed":
            flags.append({"level": "warning", "code": f"lineup_{side}",
                          "text": f"Startelva {('hemma' if side == 'home' else 'borta')}: {lineups[side]['label'].lower()}. "
                                  "Modellerna använder inga spelareffekter (ingen validerad spelarvikt finns), så "
                                  "siffrorna ändras inte – men sena frånvaron och rotation fångas inte och den verkliga "
                                  "osäkerheten är större än intervallen visar."})
    names = {"home": info["home_name"], "away": info["away_name"]}
    for fam in ("V2", "V3"):
        res = results.get(fam)
        if not res:
            continue
        for side in ("home", "away"):
            thin = [(m, c.get(f"{side}_n")) for m, c in res.get("coverage", {}).items()
                    if c.get(f"{side}_n") is not None and c.get("status") not in ("spärrad", "otillräcklig")
                    and c.get(f"{side}_n") < 5]
            if thin:
                ns = sorted({n for _, n in thin})
                flags.append({"level": "warning", "code": f"thin_{fam}_{side}",
                              "text": f"{fam}: tunn historik för {names[side]} – {'/'.join(map(str, ns))} "
                                      f"{info['comp_name']}-matcher i träningsdata ({', '.join(m for m, _ in thin)}). "
                                      "Skattningen domineras av priorn och osäkerheten är större än vanligt."})
    for fam, res in results.items():
        for w in res.get("warnings", []):
            flags.append({"level": "info", "code": f"{fam}_warning", "text": f"{fam}: {w}"})
        for metric, cov in res.get("coverage", {}).items():
            if cov.get("status") in ("spärrad", "otillräcklig"):
                flags.append({"level": "warning", "code": f"{fam}_{metric}_missing",
                              "text": f"{fam}: {metric} saknas – {cov['league_n']} matcher med tillåten träningsdata "
                                      f"(kräver ≥ 20). Värdet visas som saknat, aldrig som 0."})
    return {
        "match": {k: info[k] for k in ("id", "comp_code", "comp_name", "home_team_id", "away_team_id", "home_name",
                                       "away_name", "kickoff_utc", "season", "matchday", "stage", "status")},
        "data_cutoff_utc": to_iso(cutoff),
        "models": results,
        "lineups": lineups,
        "absences": absences,
        "training_sources": training,
        "training_detail": training_detail,
        "blocked_sources": blocked,
        "sources_used": used,
        "flags": flags,
        "data_version": list(_data_version(app)),
    }


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def freeze(app: App, match_id: int, cutoff: datetime, *, kind: str, created_by: str,
           scheduled_for: datetime | None = None, job_id: int | None = None, payload: dict | None = None) -> dict:
    """Beräkna (om inte payload ges) och skriv oföränderliga snapshots för V2, V3 och baslinje."""
    payload = payload or compute(app, match_id, cutoff)
    created = app.clock.now()
    ko = parse_iso(payload["match"]["kickoff_utc"])
    mins = (ko - created).total_seconds() / 60.0  # type: ignore[operator]
    eligible = 1 if (created < ko and cutoff < ko and kind in ("T-30", "manual")) else 0  # type: ignore[operator]
    is_late = 1 if kind == "late" else 0
    ids = {}
    with app.db.tx() as c:
        for fam, res in payload["models"].items():
            _, mid = MODELS[fam]
            sid = str(uuid.uuid4())
            mets = res.get("metrics") or {}

            def mean(metric: str, side: str):
                blk = mets.get(metric)
                return None if blk is None else blk[side]["mean"]

            probs = res.get("probs") or {}
            body = {**{k: v for k, v in payload.items() if k != "models"}, "model": res}
            c.execute("""INSERT INTO forecast_snapshots (id, match_id, model_version_id, model_family, kind,
                scheduled_for_utc, created_at_utc, data_cutoff_utc, kickoff_utc_at_creation, minutes_before_kickoff,
                is_late, prematch_eligible, clock, created_by, report_job_id, p_home, p_draw, p_away, goals_home,
                goals_away, corners_home, corners_away, shots_home, shots_away, sot_home, sot_away, payload_json,
                inputs_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (sid, match_id, mid, fam, kind, to_iso(scheduled_for), to_iso(created), to_iso(cutoff),
                       payload["match"]["kickoff_utc"], mins, is_late, eligible,
                       "simulated" if app.clock.simulated else "system", created_by, job_id,
                       probs.get("p_home"), probs.get("p_draw"), probs.get("p_away"),
                       mean("goals", "home"), mean("goals", "away"), mean("corners", "home"), mean("corners", "away"),
                       mean("shots", "home"), mean("shots", "away"), mean("sot", "home"), mean("sot", "away"),
                       json.dumps(body, ensure_ascii=False, default=str),
                       _hash({"match": match_id, "cutoff": to_iso(cutoff), "params": res.get("params"),
                              "data": payload["data_version"]})))
            ids[fam] = sid
    return {"snapshot_ids": ids, "created_at_utc": to_iso(created), "prematch_eligible": bool(eligible),
            "payload": payload}


def load_snapshot(app: App, snapshot_id: str) -> dict:
    r = app.db.one("SELECT * FROM forecast_snapshots WHERE id=?", (snapshot_id,))
    if r is None:
        raise KeyError(snapshot_id)
    d = dict(r)
    d["payload"] = json.loads(d.pop("payload_json"))
    return d
