"""Källkatalog, tävlingar och modellversioner (seed-data) samt licensspärr för träning.

Varje källa har dokumenterad ägare, URL, licens/villkor, tillåtna användningar,
uppdateringsfrekvens och täckning. En datamängd används ALDRIG för modellträning
om rättigheterna saknas eller är oklara – se ``training_allowed``.
"""
from __future__ import annotations

import json
from datetime import datetime

from .db import Database
from .timeutil import to_iso

# training_policy:
#   allowed     – licensen tillåter träning (t.ex. CC0)
#   conditional – tillåten under villkor som användaren måste granska och godkänna
#   unclear     – rättigheter oklara: spärrad tills användaren dokumenterat ett beslut
#   blocked     – uttryckligen förbjuden: spärrad tills skriftligt tillstånd registrerats
SOURCES: list[dict] = [
    {
        "id": "openfootball",
        "name": "OpenFootball (football.json, champions-league, europe m.fl.)",
        "owner": "OpenFootball-projektet (Gerald Bauer m.fl.)",
        "url": "https://github.com/openfootball",
        "terms_url": "https://github.com/openfootball/football.json",
        "license": "CC0 1.0 / public domain enligt respektive repository",
        "attribution": "Data: OpenFootball (CC0)",
        "allowed_uses": ["display", "training", "evaluation", "benchmark"],
        "training_policy": "allowed",
        "automated_fetch": "allowed",
        "enabled": 1,
        "requires_api_key": 0,
        "update_frequency": "Oregelbunden (frivilligt underhåll); kontrollera dagligen",
        "coverage": "Spelscheman och resultat. Inga kompletta skott-, hörn- eller spelardata. "
                    "CL-arkiv från 2011/12; ligatäckning varierar per land och säsong.",
        "min_interval_seconds": 2.0,
        "daily_quota": 500,
        "data_kinds": ["fixtures", "results"],
        "notes": "Filerna hämtas via GitHubs dokumenterade REST-API (60 anrop/timme utan token). Saknade filer loggas med HTTP-status.",
    },
    {
        "id": "statsbomb_open",
        "name": "StatsBomb Open Data (Hudl)",
        "owner": "Hudl / StatsBomb",
        "url": "https://github.com/statsbomb/open-data",
        "terms_url": "https://github.com/hudl/open-data",
        "license": "StatsBombs användaravtal för öppna data – attribution krävs, logotypvillkor gäller",
        "attribution": "Data: StatsBomb (Hudl) Open Data",
        "allowed_uses": ["display", "training", "evaluation"],
        "training_policy": "conditional",
        "automated_fetch": "allowed",
        "enabled": 1,
        "requires_api_key": 0,
        "update_frequency": "Sällan; nya urval publiceras oregelbundet",
        "coverage": "Händelsedata (passningar, skott, xG, kort, försvarsaktioner) för UTVALDA tävlingar och "
                    "säsonger – inte heltäckande historik.",
        "min_interval_seconds": 1.0,
        "daily_quota": 2000,
        "data_kinds": ["events", "lineups", "team_stats", "player_stats"],
        "notes": "Träning kräver att användaren läst och godkänt villkoren under Källor & licenser.",
    },
    {
        "id": "wyscout_public",
        "name": "Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare)",
        "owner": "Wyscout / L. Pappalardo, P. Cintia, A. Rossi m.fl. (CNR Pisa)",
        "url": "https://figshare.com/collections/Soccer_match_event_dataset/4415000",
        "terms_url": "https://creativecommons.org/licenses/by/4.0/",
        "license": "CC BY 4.0 (angivet på figshare och i artikeln i Scientific Data 6:236, 2019)",
        "attribution": "Data: Wyscout via Pappalardo m.fl. (2019), Scientific Data 6:236, CC BY 4.0",
        "allowed_uses": ["display", "training", "evaluation"],
        "training_policy": "allowed",
        "automated_fetch": "allowed",
        "enabled": 1,
        "requires_api_key": 0,
        "update_frequency": "Statisk datamängd (publicerad 2019)",
        "coverage": "Säsongen 2017/18 i Premier League, La Liga, Bundesliga, Serie A och Ligue 1 (1 826 matcher): "
                    "alla händelser inklusive skott och hörnor, spelare, startelvor och byten. VM 2018 och EM 2016 "
                    "ingår i datamängden men används inte.",
        "min_interval_seconds": 1.0,
        "daily_quota": 50,
        "data_kinds": ["events", "lineups", "team_stats", "player_stats", "players"],
        "notes": "Hämtas via figshares dokumenterade API. Taggarnas betydelse läses ur källans egen tags2name.csv.",
    },
    {
        "id": "uefa",
        "name": "UEFA – officiella tävlings- och matchdata",
        "owner": "UEFA",
        "url": "https://www.uefa.com/uefachampionsleague/",
        "terms_url": "https://www.uefa.com/",
        "license": "UEFA:s innehållsrättigheter. Matchdomänens endpoints är inte en publicerad API-produkt.",
        "attribution": "Källa: UEFA",
        "allowed_uses": ["display", "evaluation"],
        "training_policy": "unclear",
        "automated_fetch": "disabled",
        "enabled": 0,
        "requires_api_key": 0,
        "update_frequency": "Löpande under matchdagar",
        "coverage": "Förstahandskälla för Champions League: fixtures, resultat, startelvor, bänk, målskyttar, "
                    "lagstatistik (skott, skott på mål, hörnor) per match-ID.",
        "min_interval_seconds": 5.0,
        "daily_quota": 300,
        "data_kinds": ["fixtures", "results", "lineups", "team_stats"],
        "notes": "Automatisk hämtning är AVSTÄNGD som standard: villkoren för automatiserad åtkomst och "
                 "vidareanvändning är inte granskade och odokumenterade endpoints kan ändras. Använd "
                 "importvägen (Excel/CSV) eller aktivera först efter egen granskning.",
    },
    {
        "id": "football_data_couk",
        "name": "Football-Data.co.uk",
        "owner": "Football-Data.co.uk",
        "url": "https://www.football-data.co.uk/data.php",
        "terms_url": "https://www.football-data.co.uk/data.php",
        "license": "Privat bruk. Kommersiell användning samt AI-/botbaserade träningsprodukter undantas.",
        "attribution": "Data: Football-Data.co.uk",
        "allowed_uses": ["display", "benchmark"],
        "training_policy": "blocked",
        "automated_fetch": "allowed",
        "enabled": 0,
        "requires_api_key": 0,
        "update_frequency": "Ungefär två gånger per vecka under säsong",
        "coverage": "Resultat, odds och – varierande per liga/säsong – skott, skott på mål, hörnor, fouls, kort.",
        "min_interval_seconds": 5.0,
        "daily_quota": 200,
        "data_kinds": ["results", "team_stats", "odds"],
        "notes": "SPÄRRAD från modellträning tills skriftligt tillstånd som uttryckligen medger det har "
                 "registrerats. Får användas för visning och marknadsjämförelse.",
    },
    {
        "id": "football_data_org",
        "name": "football-data.org (API v4)",
        "owner": "football-data.org",
        "url": "https://www.football-data.org/",
        "terms_url": "https://www.football-data.org/",
        "license": "API-licens enligt valt abonnemang; nyckel krävs",
        "attribution": "Football data provided by the Football-Data.org API",
        "allowed_uses": ["display", "evaluation", "training"],
        "training_policy": "conditional",
        "automated_fetch": "api_key",
        "enabled": 0,
        "requires_api_key": 1,
        "update_frequency": "Löpande; gratisnivå begränsad till 10 anrop/min",
        "coverage": "Fixtures och resultat för större ligor och CL (beroende på abonnemang). "
                    "Allsvenskan ingår inte i gratisnivån.",
        "min_interval_seconds": 6.5,
        "daily_quota": 5000,
        "data_kinds": ["fixtures", "results"],
        "notes": "Ange API-nyckel under Inställningar → API-nycklar (lagras i Nyckelring/Autentiseringshanteraren).",
    },
    {
        "id": "api_football",
        "name": "API-Football (API-Sports v3)",
        "owner": "API-Sports",
        "url": "https://www.api-football.com/",
        "terms_url": "https://www.api-football.com/",
        "license": "Kommersiellt API enligt abonnemangsvillkor; nyckel krävs",
        "attribution": "Data: API-Football",
        "allowed_uses": ["display", "evaluation", "training"],
        "training_policy": "conditional",
        "automated_fetch": "api_key",
        "enabled": 0,
        "requires_api_key": 1,
        "update_frequency": "Löpande; startelvor normalt 20–40 min före avspark",
        "coverage": "Fixtures, resultat, bekräftade startelvor, skador/avstängningar och matchstatistik "
                    "(skott, skott på mål, hörnor) för de flesta ligor inkl. Allsvenskan.",
        "min_interval_seconds": 2.0,
        "daily_quota": 100,
        "data_kinds": ["fixtures", "results", "lineups", "injuries", "team_stats"],
        "notes": "Gratisnivån har 100 anrop/dygn – pollningen anpassas efter kvoten.",
    },
    {
        "id": "the_odds_api",
        "name": "The Odds API (v4)",
        "owner": "The Odds API",
        "url": "https://the-odds-api.com/",
        "terms_url": "https://the-odds-api.com/",
        "license": "API-licens enligt abonnemang; nyckel krävs",
        "attribution": "Odds: The Odds API",
        "allowed_uses": ["display", "benchmark"],
        "training_policy": "blocked",
        "automated_fetch": "api_key",
        "enabled": 0,
        "requires_api_key": 1,
        "update_frequency": "Löpande",
        "coverage": "1X2-odds från flera spelbolag.",
        "min_interval_seconds": 2.0,
        "daily_quota": 15,
        "data_kinds": ["odds"],
        "notes": "Odds används bara för visning och marknadsjämförelse – aldrig för modellträning.",
    },
    {
        "id": "statmuse_legacy",
        "name": "StatMuse (äldre modulkontroller)",
        "owner": "StatMuse",
        "url": "https://www.statmuse.com/",
        "terms_url": "https://www.statmuse.com/",
        "license": "Webbplatsens villkor; inget öppet datalicens",
        "attribution": "StatMuse",
        "allowed_uses": ["sanity_check"],
        "training_policy": "blocked",
        "automated_fetch": "disabled",
        "enabled": 0,
        "requires_api_key": 0,
        "update_frequency": "–",
        "coverage": "Utvalda CL-lagsummor i äldre material. Endast sekundär rimlighetskontroll.",
        "min_interval_seconds": 60.0,
        "daily_quota": 0,
        "data_kinds": [],
        "notes": "Hämtas inte automatiskt. Får inte vara ensam källa eller träningskälla.",
    },
    {
        "id": "sofascore_reference",
        "name": "Sofascore-skärmbild (designreferens)",
        "owner": "Sofascore",
        "url": "https://www.sofascore.com/",
        "terms_url": "https://www.sofascore.com/",
        "license": "Endast visuell förlaga för matchlistans layout",
        "attribution": "–",
        "allowed_uses": [],
        "training_policy": "blocked",
        "automated_fetch": "disabled",
        "enabled": 0,
        "requires_api_key": 0,
        "update_frequency": "–",
        "coverage": "Ingen data samlas in – bilden användes bara som designförlaga.",
        "min_interval_seconds": 60.0,
        "daily_quota": 0,
        "data_kinds": [],
        "notes": "Ingen statistik eller historik hämtas från Sofascore.",
    },
    {
        "id": "workbook_legacy",
        "name": "Tidigare arbetsbok (UCL-modul) – frysta prognoser",
        "owner": "Användaren",
        "url": "lokal fil",
        "terms_url": None,
        "license": "Egna härledda prognoser; underliggande data behåller sin ursprungskälla",
        "attribution": "–",
        "allowed_uses": ["display", "evaluation"],
        "training_policy": "blocked",
        "automated_fetch": "manual_only",
        "enabled": 1,
        "requires_api_key": 0,
        "update_frequency": "Vid import",
        "coverage": "Frysta prognoser (Ursprung, V2, V3-skugga) och prognoslogg från arbetsboken.",
        "min_interval_seconds": 0.0,
        "daily_quota": None,
        "data_kinds": ["forecasts"],
        "notes": "Prognoser används för utvärdering, aldrig som träningsdata.",
    },
    {
        "id": "manual",
        "name": "Manuell inmatning",
        "owner": "Användaren",
        "url": "lokal inmatning",
        "terms_url": None,
        "license": "Användarens egen inmatning",
        "attribution": "–",
        "allowed_uses": ["display", "evaluation", "training"],
        "training_policy": "allowed",
        "automated_fetch": "manual_only",
        "enabled": 1,
        "requires_api_key": 0,
        "update_frequency": "Vid inmatning",
        "coverage": "Facit efter match, startelvor och korrigeringar som användaren matat in.",
        "min_interval_seconds": 0.0,
        "daily_quota": None,
        "data_kinds": ["results", "team_stats", "lineups"],
        "notes": "Varje manuell ändring loggas med tid.",
    },
    {
        "id": "user_file",
        "name": "Egen fil (Excel/CSV) – okänd ursprungskälla",
        "owner": "Användaren",
        "url": "lokal fil",
        "terms_url": None,
        "license": "Okänd – ange ursprungskälla vid import",
        "attribution": "–",
        "allowed_uses": ["display"],
        "training_policy": "unclear",
        "automated_fetch": "manual_only",
        "enabled": 1,
        "requires_api_key": 0,
        "update_frequency": "Vid import",
        "coverage": "Data från filer där ursprunget inte angetts.",
        "min_interval_seconds": 0.0,
        "daily_quota": None,
        "data_kinds": ["fixtures", "results", "team_stats", "lineups", "odds"],
        "notes": "Spärrad från träning tills ursprung och rättigheter dokumenterats.",
    },
]

COMPETITIONS: list[dict] = [
    {"code": "UCL", "name": "Champions League", "country": None, "kind": "international_cup", "show_in_tabs": 1, "tab_order": 1},
    {"code": "SWE1", "name": "Allsvenskan", "country": "SWE", "kind": "league", "show_in_tabs": 1, "tab_order": 2},
    {"code": "ENG1", "name": "Premier League", "country": "ENG", "kind": "league", "show_in_tabs": 1, "tab_order": 3},
    {"code": "ESP1", "name": "La Liga", "country": "ESP", "kind": "league", "show_in_tabs": 1, "tab_order": 4},
    {"code": "GER1", "name": "Bundesliga", "country": "GER", "kind": "league", "show_in_tabs": 1, "tab_order": 5},
    {"code": "ITA1", "name": "Serie A", "country": "ITA", "kind": "league", "show_in_tabs": 1, "tab_order": 6},
    {"code": "FRA1", "name": "Ligue 1", "country": "FRA", "kind": "league", "show_in_tabs": 1, "tab_order": 7},
    {"code": "UCLQ", "name": "Champions League – kval", "country": None, "kind": "international_cup", "show_in_tabs": 0, "tab_order": None},
    {"code": "NED1", "name": "Eredivisie", "country": "NED", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "POR1", "name": "Primeira Liga", "country": "POR", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "BEL1", "name": "Pro League (Belgien)", "country": "BEL", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "TUR1", "name": "Süper Lig", "country": "TUR", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "CZE1", "name": "Tjeckiska förstaligan", "country": "CZE", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "NOR1", "name": "Eliteserien", "country": "NOR", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "AZE1", "name": "Premyer Liqa (Azerbajdzjan)", "country": "AZE", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "AUT1", "name": "Bundesliga (Österrike)", "country": "AUT", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "SCO1", "name": "Premiership (Skottland)", "country": "SCO", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "UKR1", "name": "Premjer-liha (Ukraina)", "country": "UKR", "kind": "league", "show_in_tabs": 0, "tab_order": None},
    {"code": "SVK1", "name": "Niké liga (Slovakien)", "country": "SVK", "kind": "league", "show_in_tabs": 0, "tab_order": None},
]

MODEL_VERSIONS: list[dict] = [
    {"id": "BASE-1.0", "family": "BASE", "version": "1.0", "status": "baslinje",
     "description": "Enkel baslinje: expanderande klassfrekvens för 1X2 och tävlingsmedel för antal.",
     "params": {"window": "all_before_cutoff"}},
    {"id": "V2-2.0", "family": "V2", "version": "2.0", "status": "baslinje",
     "description": "V2.0 | senaste 15 CL-matcher per lag | k=8 tävlingsprior | oberoende Poisson. "
                    "Jämförelsebaslinje enligt den tidigare arbetsbokens metod.",
     "params": {"last_n": 15, "k": 8, "max_goals": 10}},
    {"id": "V3-3.0", "family": "V3", "version": "3.0-exp", "status": "experimentell",
     "description": "V3 experimentell: tidsviktad attack/försvar, empirisk-Bayes-shrinkage med validerad styrka, "
                    "separat inhemsk styrka med ligafaktor från tidigare europeiska möten (aktiveras bara om "
                    "den förbättrar valideringen), negativ binomial för räknevariabler vid överspridning.",
     "params": {}},
    {"id": "LEGACY-ORIG", "family": "LEGACY", "version": "arbetsbok-ursprung", "status": "arkiverad",
     "description": "Ursprungliga prognoser från den tidigare arbetsboken (importerade, frysta).", "params": {}},
    {"id": "LEGACY-V2", "family": "LEGACY", "version": "arbetsbok-V2.0", "status": "arkiverad",
     "description": "V2-prognoser beräknade i den tidigare arbetsboken (importerade, frysta).", "params": {}},
    {"id": "LEGACY-V3", "family": "LEGACY", "version": "arbetsbok-V3-shadow-0.3", "status": "arkiverad",
     "description": "V3-skuggprognoser från den tidigare arbetsboken (importerade, frysta).", "params": {}},
]


def seed(db: Database, now: datetime) -> None:
    """Fyll i katalogen. Idempotent: befintliga användarbeslut (godkännanden, aktivering) bevaras."""
    ts = to_iso(now)
    with db.tx() as c:
        for s in SOURCES:
            existing = c.execute("SELECT id FROM sources WHERE id=?", (s["id"],)).fetchone()
            values = (
                s["name"], s["owner"], s["url"], s.get("terms_url"), s["license"], s.get("attribution"),
                json.dumps(s["allowed_uses"]), s["training_policy"], s["automated_fetch"],
                s["requires_api_key"], s.get("update_frequency"), s.get("coverage"),
                s.get("min_interval_seconds", 1.0), s.get("daily_quota"), json.dumps(s.get("data_kinds", [])),
                s.get("notes"), ts,
            )
            if existing:
                c.execute("""UPDATE sources SET name=?, owner=?, url=?, terms_url=?, license=?, attribution=?,
                    allowed_uses=?, training_policy=?, automated_fetch=?, requires_api_key=?, update_frequency=?,
                    coverage=?, min_interval_seconds=?, daily_quota=?, data_kinds=?, notes=?, updated_at_utc=?
                    WHERE id=?""", values + (s["id"],))
            else:
                c.execute("""INSERT INTO sources (name, owner, url, terms_url, license, attribution, allowed_uses,
                    training_policy, automated_fetch, requires_api_key, update_frequency, coverage,
                    min_interval_seconds, daily_quota, data_kinds, notes, updated_at_utc, id, enabled)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values + (s["id"], s["enabled"]))
                c.execute("INSERT INTO source_audit (source_id, action, detail, at_utc) VALUES (?,?,?,?)",
                          (s["id"], "skapad", "Katalogpost skapad", ts))
        for comp in COMPETITIONS:
            c.execute("""INSERT INTO competitions (code, name, country, kind, show_in_tabs, tab_order)
                VALUES (:code,:name,:country,:kind,:show_in_tabs,:tab_order)
                ON CONFLICT(code) DO UPDATE SET name=excluded.name, show_in_tabs=excluded.show_in_tabs,
                tab_order=excluded.tab_order""", comp)
        for mv in MODEL_VERSIONS:
            c.execute("""INSERT INTO model_versions (id, family, version, description, params_json, status,
                status_reason, created_at_utc, status_changed_at_utc) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET description=excluded.description""",
                      (mv["id"], mv["family"], mv["version"], mv["description"], json.dumps(mv["params"]),
                       mv["status"], "Initial status", ts, ts))


def training_allowed(source: dict) -> bool:
    """Får data från källan användas för modellträning?"""
    approval = source.get("training_approval")
    if approval == "revoked":
        return False
    policy = source["training_policy"]
    if policy == "allowed":
        return True
    if policy in ("conditional", "unclear"):
        return approval == "approved"
    if policy == "blocked":
        return approval == "approved" and bool((source.get("training_approval_note") or "").strip())
    return False


TRAINING_TEXT_OVERRIDE = {
    "workbook_legacy": "Prognoser – används aldrig som träningsdata",
    "sofascore_reference": "Ingen data samlas in",
    "the_odds_api": "Odds används aldrig för modellträning",
    "statmuse_legacy": "Endast rimlighetskontroll – aldrig träningsdata",
}


def training_status_text(source: dict) -> str:
    if source.get("id") in TRAINING_TEXT_OVERRIDE and not training_allowed(source):
        return TRAINING_TEXT_OVERRIDE[source["id"]]
    if training_allowed(source):
        if source["training_policy"] == "allowed":
            return "Tillåten (licens)"
        return "Tillåten efter dokumenterat godkännande"
    return {
        "conditional": "Spärrad – villkoren måste godkännas",
        "unclear": "Spärrad – rättigheter oklara",
        "blocked": "Spärrad – uttryckligen förbjuden utan skriftligt tillstånd",
        "allowed": "Spärrad (återkallad av användare)",
    }[source["training_policy"]]


def training_source_ids(db: Database) -> set[str]:
    rows = db.query("SELECT * FROM sources")
    return {r["id"] for r in rows if training_allowed(dict(r))}


def set_training_approval(db: Database, source_id: str, approve: bool, note: str, now: datetime) -> dict:
    src = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if src is None:
        raise KeyError(source_id)
    note = (note or "").strip()
    if approve and src["training_policy"] in ("unclear", "blocked") and len(note) < 10:
        raise ValueError("Ett godkännande av en oklar eller spärrad källa kräver en dokumenterad motivering "
                         "(t.ex. referens till skriftligt tillstånd), minst 10 tecken.")
    if approve and src["training_policy"] == "conditional" and not note:
        note = "Användaren har läst och godkänt villkoren"
    ts = to_iso(now)
    with db.tx() as c:
        c.execute("""UPDATE sources SET training_approval=?, training_approval_note=?, training_approval_at_utc=?
                     WHERE id=?""", ("approved" if approve else "revoked", note, ts, source_id))
        c.execute("INSERT INTO source_audit (source_id, action, detail, at_utc) VALUES (?,?,?,?)",
                  (source_id, "träning godkänd" if approve else "träning återkallad", note, ts))
    return dict(db.one("SELECT * FROM sources WHERE id=?", (source_id,)))


def set_source_enabled(db: Database, source_id: str, enabled: bool, now: datetime, note: str = "") -> None:
    src = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if src is None:
        raise KeyError(source_id)
    if enabled and src["automated_fetch"] in ("manual_only",):
        raise ValueError("Källan kan inte hämtas automatiskt – använd importvägen.")
    if enabled and src["automated_fetch"] == "disabled" and len(note.strip()) < 10:
        raise ValueError("Automatisk hämtning är avstängd för källan. Aktivering kräver en dokumenterad "
                         "motivering om att villkoren granskats (minst 10 tecken).")
    ts = to_iso(now)
    with db.tx() as c:
        c.execute("UPDATE sources SET enabled=? WHERE id=?", (1 if enabled else 0, source_id))
        c.execute("INSERT INTO source_audit (source_id, action, detail, at_utc) VALUES (?,?,?,?)",
                  (source_id, "aktiverad" if enabled else "avaktiverad", note, ts))
