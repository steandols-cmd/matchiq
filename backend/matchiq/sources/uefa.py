"""UEFA:s matchdomän – EXPERIMENTELL adapter, AVSTÄNGD som standard.

UEFA är förstahandskälla för Champions League, men matchdomänens endpoints är inte en publicerad
API-produkt, formatet kan ändras och villkoren för automatiserad hämtning är inte granskade.
Adaptern kan bara köras om användaren uttryckligen aktiverat källan med en dokumenterad motivering
(se Källor & licenser). Den rekommenderade vägen är import av exporterade filer.

Tolkningen är defensiv: okända fält ger parserfel i hämtloggen i stället för gissade värden.
"""
from __future__ import annotations

from .base import Adapter

MATCH_URL = "https://match.uefa.com/v5/matches/{id}"
LINEUP_URL = "https://match.uefa.com/v5/matches/{id}/lineups"


class UefaAdapter(Adapter):
    source_id = "uefa"
    label = "UEFA (experimentell)"
    jobs = ("lineups",)

    def run(self, job: str = "lineups", match_id: int | None = None) -> dict:
        if match_id is None:
            return {"skipped": "kräver match_id"}
        m = self.app.db.one("SELECT official_match_id, home_team_id, away_team_id FROM matches WHERE id=?", (match_id,))
        if not m or not m["official_match_id"]:
            return {"skipped": "matchen saknar UEFA-ID"}
        res = self.http.get(self.source_id, LINEUP_URL.format(id=m["official_match_id"]), job=job,
                            respect_robots=True)
        if res.status != 200:
            return {"error": f"HTTP {res.status}"}
        try:
            data = res.json()
            status_txt = str(data.get("lineupStatus") or "")
            confirmed = "CONFIRMED" in status_txt.upper() or "TACTICAL" in status_txt.upper()
            for side, tid in (("homeTeam", m["home_team_id"]), ("awayTeam", m["away_team_id"])):
                blk = data.get(side) or {}
                players = []
                for p in blk.get("field") or blk.get("players") or []:
                    pl = p.get("player") or {}
                    name = (pl.get("translations") or {}).get("shortName", {}).get("EN") or pl.get("internationalName")
                    if not name:
                        continue
                    players.append({"name": name, "number": p.get("jerseyNumber"),
                                    "position": pl.get("fieldPosition"), "is_starter": True,
                                    "player_id": self.repo.resolve_player(name, self.source_id, pl.get("id"))})
                if len(players) >= 11 and confirmed:
                    self.repo.upsert_lineup(match_id, tid, self.source_id, "confirmed", players[:11],
                                            fetched_at=self.now(), fetch_id=res.fetch_id,
                                            source_url=LINEUP_URL.format(id=m["official_match_id"]))
                    self.counts["lineups"] += 1
            self.http.finish(res.fetch_id, "ok" if self.counts.get("lineups") else "partial")
        except Exception as e:  # noqa: BLE001
            self.http.finish(res.fetch_id, "error", error=f"Okänt format: {e!r}")
            return {"error": "okänt format – inga värden gissades"}
        return self.summary()
