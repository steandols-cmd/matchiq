"""Generera docs/DATABAS.md och docs/KALLREGISTER.md direkt från koden (håller dokumentationen i synk).

    python scripts/gen_docs.py [--data-dir DATAMAPP]

Med --data-dir skrivs även docs/VALIDERING.md från den senaste valideringskörningen i den databasen.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from matchiq.catalog import COMPETITIONS, SOURCES, MODEL_VERSIONS  # noqa: E402
from matchiq.db import list_migrations  # noqa: E402

USES = {"display": "visning", "training": "träning", "evaluation": "utvärdering", "benchmark": "marknadsjämförelse",
        "sanity_check": "rimlighetskontroll"}
POLICY = {"allowed": "Tillåten (licens)", "conditional": "Spärrad tills villkoren godkänts av användaren",
          "unclear": "Spärrad – rättigheter oklara (kräver dokumenterat beslut)",
          "blocked": "Spärrad – kräver skriftligt tillstånd"}
FETCH = {"allowed": "Automatisk", "api_key": "Automatisk med API-nyckel", "disabled": "Avstängd som standard",
         "manual_only": "Endast import"}


def kallregister() -> str:
    out = ["# Käll- och licensregister", "",
           "Genererat från `backend/matchiq/catalog.py`. Samma register visas i appen under **Data & källor → Källor & "
           "licenser**, där användaren också kan godkänna eller återkalla träningsanvändning (varje beslut loggas).", "",
           "| Källa | Ägare | Licens / villkor | Tillåtna användningar | Träning (standard) | Hämtning | Uppdatering |",
           "|---|---|---|---|---|---|---|"]
    for s in SOURCES:
        out.append(f"| **{s['name']}**<br>{s['url']} | {s['owner']} | {s['license']} | "
                   f"{', '.join(USES.get(u, u) for u in s['allowed_uses']) or '–'} | {POLICY[s['training_policy']]} | "
                   f"{FETCH[s['automated_fetch']]} | {s.get('update_frequency') or '–'} |")
    out += ["", "## Täckning och kända begränsningar", ""]
    for s in SOURCES:
        out.append(f"- **{s['name']}** – {s['coverage']} {s.get('notes') or ''}".rstrip())
    out += ["", "## Regler", "",
            "- En datamängd används **aldrig** för modellträning om rättigheterna saknas eller är oklara. "
            "Spärren gäller per observation (varje värde bär sin källa).",
            "- Football-Data.co.uk: villkoren utesluter AI-/botbaserade träningsprodukter – spärrad tills skriftligt "
            "tillstånd registrerats (referens krävs).",
            "- UEFA: förstahandskälla, men automatisk hämtning är avstängd och träning spärrad tills användaren "
            "dokumenterat ett beslut. Odokumenterade endpoints kan ändras.",
            "- StatsBomb Open Data: täcker ett urval; attribution krävs; träning först efter att villkoren godkänts.",
            "- StatMuse: endast rimlighetskontroll. Sofascore-bilden: endast designförlaga – ingen data samlas in.",
            "- Odds används bara för jämförelse, aldrig som träningsdata.", "",
            "## Tävlingar", "", "| Kod | Namn | Typ | Flik |", "|---|---|---|---|"]
    for c in COMPETITIONS:
        out.append(f"| {c['code']} | {c['name']} | {c['kind']} | {'ja' if c['show_in_tabs'] else 'nej'} |")
    out += ["", "## Modellversioner", "", "| ID | Status vid start | Beskrivning |", "|---|---|---|"]
    for m in MODEL_VERSIONS:
        out.append(f"| {m['id']} | {m['status']} | {m['description']} |")
    return "\n".join(out) + "\n"


def databas() -> str:
    out = ["# Databasmodell", "",
           "SQLite, en fil: `matchiq.sqlite` i datamappen. Genererat från migreringarna i "
           "`backend/matchiq/migrations/`.", "",
           "**Konventioner:** tider i UTC (ISO 8601 med `Z`), saknade värden = `NULL` (aldrig 0), varje observation "
           "bär `source_id` och `fetch_id`/`import_id`. `forecast_snapshots` och `reports` är oföränderliga "
           "(databastriggers stoppar UPDATE/DELETE).", "",
           "## Datamapp", "", "| Plattform | Sökväg |", "|---|---|",
           "| macOS | `~/Library/Application Support/MatchIQ/data` |",
           "| Windows | `%APPDATA%\\MatchIQ\\data` |", "| Linux | `~/.local/share/matchiq/data` |", "",
           "Innehåll: `matchiq.sqlite`, `backups/` (automatiskt före varje migrering), `exports/`, "
           "`reports/ÅÅÅÅ-MM-DD/TÄVLING/*.pdf`, `raw/` (råfiler per källa, namngivna efter SHA-256), `imports/` "
           "(kopior av importerade filer), `logs/`, `crests/`.", "",
           "## Migrering och export", "",
           "- Vid start appliceras väntande migreringar (`schema_migrations` håller version, tid, appversion och "
           "SHA-256 för varje migreringsfil). En säkerhetskopia tas först.",
           "- **Exportera hela databasen** (Inställningar eller `python -m matchiq.cli export --out fil.zip`) ger en zip "
           "med komplett SQLite-fil, en CSV per tabell, `schema.sql` och `manifest.json` (schemaversion, radantal, "
           "SHA-256 per fil).",
           "- **Läs in export** (`python -m matchiq.cli import-db --file fil.zip`) verifierar kontrollsummor, "
           "säkerhetskopierar aktuell databas, ersätter den och migrerar framåt till appens schemaversion.",
           "- Nya schemaändringar läggs som nästa numrerade fil (`0002_….sql`); äldre filer ändras aldrig.", ""]
    for version, name, path in list_migrations():
        sql = path.read_text(encoding="utf-8")
        out.append(f"## Migrering {version:04d} – {name}")
        out.append("")
        for m in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, re.S):
            out.append(f"### `{m.group(1)}`")
            out.append("")
            out.append("| Kolumn / regel | Definition |")
            out.append("|---|---|")
            for line in m.group(2).splitlines():
                line = line.strip().rstrip(",")
                if not line or line.startswith("--"):
                    continue
                comment = ""
                if "--" in line:
                    line, comment = line.split("--", 1)
                    line = line.strip().rstrip(",")
                parts = line.split(None, 1)
                col, rest = (parts[0], parts[1] if len(parts) > 1 else "")
                if col.upper() in ("UNIQUE", "CHECK", "PRIMARY", "FOREIGN"):
                    col, rest = "*(regel)*", line
                rest = rest.replace("|", "\\|")
                out.append(f"| `{col}` | {rest}{' — ' + comment.strip() if comment else ''} |")
            out.append("")
        triggers = re.findall(r"CREATE TRIGGER (\w+)", sql)
        if triggers:
            out.append("**Triggers:** " + ", ".join(f"`{t}`" for t in triggers))
            out.append("")
    return "\n".join(out) + "\n"


def _f(v, d=3):
    return "–" if v is None else f"{v:.{d}f}".replace(".", ",")


def _pct(v):
    return "–" if v is None else f"{round(v * 100)} %"


def validering(data_dir: Path) -> str:
    import json
    import sqlite3

    from matchiq import analytics
    from matchiq.core import init_app

    c = sqlite3.connect(data_dir / "matchiq.sqlite")
    c.row_factory = sqlite3.Row
    runs = {r["model_version_id"]: r for r in c.execute(
        "SELECT * FROM backtest_runs WHERE id IN (SELECT MAX(id) FROM backtest_runs GROUP BY model_version_id)")}
    if not runs:
        return "# Validering\n\nIngen valideringskörning finns i databasen.\n"
    order = [m for m in ("V3-3.0", "V2-2.0", "BASE-1.0") if m in runs]
    cfg = json.loads(runs[order[0]]["config_json"])
    names = {"V3-3.0": "V3 (experimentell)", "V2-2.0": "V2 (baslinje)", "BASE-1.0": "Baslinje"}
    out = ["# Validering av modellerna", "",
           f"Genererad från valideringskörningen {runs[order[0]]['created_at_utc']} (`scripts/gen_docs.py --data-dir …`). "
           "Samma siffror visas live i appen under **Utvärdering**.", "",
           "## Upplägg", "",
           f"- **Tävling:** {cfg['competition']}",
           f"- **Valideringssäsonger (modellval):** {', '.join(cfg['validation'])}",
           f"- **Orörd holdout (test):** {', '.join(cfg['test'])}",
           f"- **Träningskällor:** {', '.join(cfg['train_sources'])}",
           f"- **Datagräns per prognos:** {cfg['cutoff_rule']} – expanderande fönster, endast matcher som spelats och "
           "publicerats före datagränsen; matcher avgjorda i förlängning ingår inte som 90-minutersobservationer.",
           f"- **Modellval låst:** {cfg.get('selection_locked_at_utc')}, före utvärderingen av holdouten.",
           "- **Mått:** Brier (summa över tre klasser), log loss, träffprocent för 1X2; MAE, RMSE, bias och faktisk "
           "täckning för 80 %-intervallet (P10–P90) för mål, skott, skott på mål och hörnor (per lag och match).", ""]
    for split, title in (("test", "Orörd holdout"), ("validation", "Valideringssäsonger (där V3:s parametrar valdes)")):
        out += [f"## {title}", "", "| Modell | n 1X2 | Brier | Log loss | Träff | Mål MAE / bias / täckn. | Skott MAE / bias / täckn. | "
                "Skott på mål MAE / bias / täckn. | Hörnor MAE / bias / täckn. |", "|---|---|---|---|---|---|---|---|---|"]
        for m in order:
            d = json.loads(runs[m]["summary_json"])["by_split"].get(split, {})
            x = d.get("1x2", {})
            cells = [names[m], str(x.get("n", 0)), _f(x.get("brier")), _f(x.get("logloss")), _pct(x.get("hit_rate"))]
            for k in ("goals", "shots", "sot", "corners"):
                y = d.get(k, {})
                cells.append(f"{_f(y.get('mae'), 2)} / {_f(y.get('bias'), 2)} / {_pct(y.get('coverage'))} (n={y.get('n', 0)})")
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
    out += ["## Per säsong (1X2)", "", "| Säsong | " + " | ".join(f"{names[m]} Brier / log loss (n)" for m in order) + " |",
            "|---|" + "---|" * len(order)]
    seasons = sorted({s for m in order for s in json.loads(runs[m]["summary_json"])["by_season"]})
    for se in seasons:
        row = [se]
        for m in order:
            x = json.loads(runs[m]["summary_json"])["by_season"].get(se, {}).get("1x2", {})
            row.append(f"{_f(x.get('brier'))} / {_f(x.get('logloss'))} ({x.get('n', 0)})")
        out.append("| " + " | ".join(row) + " |")
    mv = {r["id"]: r for r in c.execute("SELECT * FROM model_versions")}
    v3 = mv.get("V3-3.0")
    if v3 is not None and v3["gate_report_json"]:
        g = json.loads(v3["gate_report_json"])
        params = json.loads(v3["params_json"] or "{}")
        out += ["", "## V3: valda parametrar", "", "```json", json.dumps(params, ensure_ascii=False, indent=2), "```", "",
                "Sökordning (val på valideringssäsongerna, lägsta log loss för 1X2 respektive negativ log-likelihood för "
                "räknemått; en förändring måste förbättra med minst 0,002 för att väljas):", "",
                "| Steg | Parametrar | Log loss 1X2 | NLL räknemått |", "|---|---|---|---|"]
        for e in g.get("selection_log", []):
            ps = ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("stage", "logloss", "count_nll"))
            out.append(f"| {e['stage']} | {ps} | {_f(e.get('logloss'), 4)} | {_f(e.get('count_nll'), 4)} |")
        for mid in ("V3-3.0", "V2-2.0"):
            r = mv.get(mid)
            if r is None or not r["gate_report_json"]:
                continue
            gg = json.loads(r["gate_report_json"])["gates"]
            out += ["", f"## Grindar – {names[mid]} (status: {r['status']})", ""]
            out += [f"- {'✅' if ch['ok'] else '⚠️'} {ch['text']}" for ch in gg["checks"]]
            if mid == "V3-3.0":
                out.append(f"\nFöreslagen status: **{gg['suggested_status']}** · produktion möjlig: "
                           f"**{'ja' if gg['production_possible'] else 'nej'}**")
            else:
                out.append("\nV2 är jämförelsebaslinje; grindarna visas som information om dess kvalitet.")
    app = init_app(data_dir)
    pe = analytics.prospective_evaluation(app)
    out += ["", "## Frysta prognoser mot faktiskt utfall (prospektivt)", "",
            "Endast ögonblicksbilder som frystes före avspark (förmatchsbehöriga). Prognoserna räknas aldrig om.", "",
            "| Modell | Matcher | Brier | Log loss | Träff |", "|---|---|---|---|---|"]
    for m, d in sorted(pe.items()):
        x = d.get("1x2", {})
        out.append(f"| {m} | {d.get('n_matches', 0)} | {_f(x.get('brier'))} | {_f(x.get('logloss'))} | {_pct(x.get('hit_rate'))} |")
    if not pe:
        out.append("| – | 0 | – | – | – |")
    out += ["", "## Benchmark mot den tidigare arbetsboken", "",
            "Arbetsbokens V2-resultat reproduceras exakt av MatchIQ:s V2 (automatiskt test "
            "`test_v2_benchmark_reproduced`, körs när `MATCHIQ_WORKBOOK` pekar på arbetsboken): **517 matcher, Brier "
            "0,556 mot baslinjens 0,616 och log loss 0,940 mot 1,020.** Arbetsbokens V3 var en skuggprototyp utan "
            "godkännande och importeras som arkiverad (LEGACY-V3). MatchIQ:s V3 är en ny modell som valideras ovan.",
            "", "## Tolkning och förbehåll", "",
            "- V3 klarar alla backtest-grindar men saknar ännu ≥ 200 frysta T−30-prognoser med facit. Status är därför "
            "*kandidat*, och modellen visas som **experimentell** i hela appen. Produktion kan bara sättas manuellt när "
            "alla grindar är gröna.",
            "- V3:s modellstruktur utvecklades med tillgång till hela historiken, även om parametervalet var låst före "
            "holdouten. Kravet på prospektiva T−30-prognoser finns för att fånga sådan överanpassning.",
            "- Om träningskällorna ändras (t.ex. om UEFA-data spärras eller godkänns) ändras underlaget. Kör då om "
            "valideringen.",
            "- LEGACY-ORIG är arbetsbokens egna frysta prognoser (importerade med ursprunglig tidsstämpel).", ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir")
    a = ap.parse_args()
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "KALLREGISTER.md").write_text(kallregister(), encoding="utf-8")
    (docs / "DATABAS.md").write_text(databas(), encoding="utf-8")
    print("docs/KALLREGISTER.md och docs/DATABAS.md uppdaterade")
    if a.data_dir:
        (docs / "VALIDERING.md").write_text(validering(Path(a.data_dir)), encoding="utf-8")
        print("docs/VALIDERING.md uppdaterad")
