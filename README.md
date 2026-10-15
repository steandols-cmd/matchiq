# MatchIQ – prognosmotor för fotboll

MatchIQ är en skrivbordsapp för macOS och Windows som samlar in tillåten match-, lag-, spelar- och startelvedata,
räknar fram statistiska prognoser före avspark och **fryser** prognosen som en PDF exakt 30 minuter före avspark
(T−30). Frysta prognoser jämförs sedan med det faktiska utfallet, så att modellernas träffsäkerhet kan följas
över tid. Täckning, källor, licenser, osäkerhet och modellstatus visas öppet i appen.

> MatchIQ ger statistiska prognoser, inte löften om utfall.

---

## Innehåll

1. [Vad appen gör](#vad-appen-gör)
2. [Första uppstart](#första-uppstart)
3. [Installationspaket – bygga för macOS och Windows](#installationspaket--bygga-för-macos-och-windows)
4. [Arkitektur](#arkitektur)
5. [Data, källor och licenser](#data-källor-och-licenser)
6. [Modeller och validering](#modeller-och-validering)
7. [T−30-schemaläggning och PDF-arkiv](#t30-schemaläggning-och-pdf-arkiv)
8. [Eftermatch och kalibrering](#eftermatch-och-kalibrering)
9. [Databasen – åtkomst, export och migrering](#databasen--åtkomst-export-och-migrering)
10. [Säkerhet](#säkerhet)
11. [Tester och vad som är verifierat](#tester-och-vad-som-är-verifierat)
12. [Det här behöver du konfigurera](#det-här-behöver-du-konfigurera)
13. [Utvecklingsläge](#utvecklingsläge)
14. [Kända begränsningar](#kända-begränsningar)

---

## Vad appen gör

| Område | Innehåll |
|---|---|
| **Matchlista** | Kommande och spelade matcher per tävling (flikar: Champions League, Allsvenskan, Premier League, La Liga, Bundesliga, Serie A, Ligue 1). Fullständiga lagnamn och klubbmärke på varje rad, avsparkstid till vänster, filter för datum, status och lag. |
| **Matchprognos** | 1X2 i procent (summerar alltid till exakt 100), förväntade mål, hörnor, skott och skott på mål med 80 %-intervall (P10–P90), BTTS och över 2,5. V2 (baslinje, **bärnsten**) och V3 (**ljusgrön**, märkt *experimentell* tills den klarat alla grindar) sida vid sida. |
| **Lag, spelare och startelvor** | Form, snitt för/emot (saknade värden räknas inte som 0), startelvor med status *bekräftad / förväntad / ej publicerad*, frånvaro, alias och källornas ID. Möjliga dubbletter granskas manuellt – inget slås ihop automatiskt. |
| **Data och källor** | Käll- och licensregister, träningsspärrar, täckning per tävling/säsong/lag/mått, importvy med mappning, hämtlogg och ändringslogg. |
| **Utfall och kalibrering** | Tidsordnad walk-forward-validering, kalibreringsdiagram, Brier, log loss, MAE, RMSE, bias och intervalltäckning per säsong – samt frysta T−30-prognoser mot faktiskt utfall. |
| **T−30-rapporter** | PDF skapas automatiskt 30 minuter före avspark, arkiveras per datum och tävling och kan öppnas från matchen. Avisering i appen och i operativsystemet. |
| **Bakgrundskörning** | Valfri autostart vid inloggning (macOS och Windows) och ikon i menyraden/systemfältet så att schemaläggaren arbetar även när fönstret är stängt. |

Tider visas i **Europe/Stockholm** och lagras i **UTC**.

---

## Första uppstart

### 1. Installera

* **macOS:** öppna `MatchIQ-<version>-mac-arm64.dmg` och dra MatchIQ till *Program*.
  Bygger du appen själv på din Mac (se nedan) startar den direkt. Laddar du ned en osignerad build från
  GitHub Actions blockerar Gatekeeper första starten: öppna *Systeminställningar → Integritet och säkerhet* och
  klicka **Öppna ändå** (eller kör `xattr -dr com.apple.quarantine /Applications/MatchIQ.app` i Terminal).
  Med ett Developer ID-certifikat i CI signeras och notariseras appen och varningen försvinner.
* **Windows:** kör `MatchIQ-<version>-win-x64.exe` (installation per användare, valbar mapp) eller `.msi`.
  En osignerad installerare visar SmartScreen – välj *Mer information → Kör ändå*.

### 2. Starta

Vid första starten skapar appen datamappen och databasen och startar schemaläggaren:

| Plattform | Datamapp |
|---|---|
| macOS | `~/Library/Application Support/MatchIQ/data` |
| Windows | `%APPDATA%\MatchIQ\data` |

Innehåll: `matchiq.sqlite` (databasen), `reports/` (PDF-arkiv), `backups/`, `exports/`, `imports/` (kopior av
importerade filer), `raw/` (råfiler från källor, namngivna efter SHA-256), `logs/` och `crests/`.

OpenFootball (CC0) hämtas automatiskt i bakgrunden, så tävlingar, matcher och resultat fylls på utan
konfiguration. Tomma vyer visar alltid *varför* de är tomma och vad som kan aktiveras.

### 3. Importera den tidigare arbetsboken (valfritt)

*Data & källor → Import → Välj fil* och välj `UCL_officiella_18_startelvor_och_verifiering_V3.xlsx`.

1. Mappningsvyn visar alla blad, kolumner, antal rader, saknade värden och dubbletter **innan** något sparas,
   samt arbetsbokens kontrollvärden (t.ex. 2 024 CL-matcher, 15 340 inhemska matcher). Kontrollvärden vars blad
   inte finns i filen redovisas som *saknas i filen* – inget döljs.
2. Klicka **Importera**. Originalfilen öppnas bara för läsning; en kopia sparas i `imports/` med sin SHA-256.
3. Importen kan köras flera gånger utan dubbletter. Frysta prognoser från arbetsboken sparas som oföränderliga
   ögonblicksbilder med sin ursprungliga tidsstämpel (LEGACY-ORIG/V2/V3) och skrivs aldrig över.

Appen startar och fungerar utan arbetsboken.

### 4. Gå igenom källor och träningsrättigheter

*Data & källor → Källor & licenser.* Källor med oklara eller villkorade rättigheter är **spärrade från
modellträning** tills du dokumenterar ett beslut (anteckning krävs och loggas).

> **Viktigt om arbetsbokens CL-historik:** de 2 024 CL-matcherna kommer från UEFA. UEFA-data är spärrad från
> träning i en ny installation. Utan ditt beslut tränas V2/V3 bara på tillåtna källor (OpenFootball m.fl.) och
> UEFA-data används endast för visning och utvärdering. Läs UEFA:s villkor innan du godkänner.

### 5. Kör modellval och validering

*Utvärdering → Kör modellval & validering.* Väljer V3:s parametrar på valideringssäsongerna, låser valet och
utvärderar därefter på orörda slutsäsonger. Tar några minuter.

### 6. Slå på bakgrundskörning (rekommenderas)

*Inställningar → Bakgrundskörning och schemaläggare.* Appen startar då vid inloggning utan fönster och T−30-rapporterna skapas även
när fönstret är stängt. Schemaläggarens status syns alltid uppe till höger.

### 7. API-nycklar (valfritt)

*Inställningar → API-nycklar.* Nycklarna sparas i macOS Nyckelring respektive Windows Autentiseringshanteraren
och kan aldrig läsas tillbaka av gränssnittet. Se [Det här behöver du konfigurera](#det-här-behöver-du-konfigurera).

---

## Installationspaket – bygga för macOS och Windows

Installationspaketen byggs på respektive operativsystem (Electron och PyInstaller kan inte korskompilera).

### Alternativ A – GitHub Actions (rekommenderas)

Arbetsflödet `.github/workflows/build.yml` körs vid push till `main` eller manuellt (*Actions → Run workflow*):

| Jobb | Plattform | Innehåll |
|---|---|---|
| Backend-tester | Linux, macOS, Windows | Hela testsviten |
| Gränssnitt | Linux | Vite-bygge (+ separat typkontroll) |
| UI-kontroll | Linux | Skärmbilder av de fem vyerna i stående och liggande format + jämförelse mot mockuperna |
| Sidecar-test | Linux, macOS, Windows | Electron-kodens typkontroll; startar backend som sidecar och verifierar tokenskyddet |
| Installationspaket | macOS (Apple Silicon), Windows, Linux | PyInstaller-backend + röktest, sedan `.dmg`/`.zip`, `.exe`/`.msi`, `.AppImage` |

Färdiga paket hämtas under *Artifacts* i körningen. Kodsignering är valfri – lägg in secrets
`CSC_LINK`, `CSC_KEY_PASSWORD` (samt `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` för notarisering).
Utan certifikat signeras macOS-appen ad hoc så att den startar på Apple Silicon.

### Alternativ B – bygg lokalt

Kräver Python 3.11+ och Node.js 20+.

```bash
# macOS (kräver även Xcode Command Line Tools: xcode-select --install)
./scripts/build-mac.sh
# → apps/desktop/release/MatchIQ-1.0.0-mac-arm64.dmg
```

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
# → apps\desktop\release\MatchIQ-1.0.0-win-x64.exe och .msi
```

Skripten skapar en virtuell Python-miljö, kör testerna, paketerar backend med PyInstaller, bygger gränssnittet
med Vite och paketerar appen med electron-builder.

---

## Arkitektur

```
┌──────────────────────────── Electron (apps/desktop) ────────────────────────────┐
│ huvudprocess: app://-protokoll, fönster, systemfält, autostart, OS-aviseringar  │
│ preload: minimalt IPC-API (contextIsolation + sandbox, ingen Node i renderer)   │
│ renderer: React + TypeScript (apps/web, byggs med Vite)                          │
└──────────────┬──────────────────────────────────────────────────────────────────┘
               │ startar sidecar med slumpad token (256 bitar) via miljövariabel
               ▼
┌──────────────────────── Backend-sidecar (backend/matchiq) ──────────────────────┐
│ Starlette/ASGI + uvicorn, binder ENDAST 127.0.0.1, slumpad port                 │
│ API (Bearer-token + Host-kontroll + CORS bara för app://matchiq)                 │
│ Schemaläggare (T−30) · Synkronisering (adaptiv polling) · Jobbhanterare         │
│ Källadaptrar · Import · Modeller (BASE/V2/V3) · PDF (ReportLab) · Nyckelförråd  │
└──────────────┬──────────────────────────────────────────────────────────────────┘
               ▼
        SQLite (WAL) + numrerade migreringar + automatiska säkerhetskopior
```

Backend är byggd på **Starlette**, samma ASGI-ramverk som FastAPI bygger på. Valet gjordes för att hålla
sidecaren liten och beroendena få; API:t är rena JSON-endpoints under `/api/` och kan flyttas till FastAPI
utan ändringar i gränssnittet om ni vill ha automatisk OpenAPI-dokumentation.

```
backend/
  matchiq/
    api/app.py            REST-API och säkerhetsmellanlager
    server.py             sidecar-start (token, port, föräldervakt, trådar)
    cli.py                kommandorad: migrate, backup, export, import-db, import-workbook, select-models, …
    db.py                 databas, migreringar, säkerhetskopior, export/import
    migrations/0001_initial.sql
    catalog.py            käll- och licensregister, tävlingar, modellversioner, träningsspärrar
    entities.py           lag/spelare/matcher: exakta alias, dedup, idempotenta upserts
    aliases_seed.py       kanoniska klubbnamn, UEFA-ID, källspecifika alias
    sources/              adaptrar: openfootball, statsbomb, api_football, football_data_org,
                          football_data_couk, odds_api, uefa + http.py (robots, kvoter, retry, ETag, rålogg)
    importers/            Excel/CSV-läsare, generisk import med mappning, arbetsboksimport
    models/               data (cutoff-säker vy), baseline, v2, v3, metrics, evaluate, selection
    forecast.py           beräkning, frysning och laddning av prognoser
    scheduler.py          T−30-jobb, sena rapporter, utfallshämtning
    reports/pdf.py        PDF-rapporten
    secrets_store.py      Nyckelring / Autentiseringshanteraren
  tests/                  automatiska tester (unittest)
apps/web/                 React-gränssnittet
apps/desktop/             Electron-skalet och electron-builder-konfiguration
scripts/                  byggskript, UI-kontroll, demo, simulering, dokumentationsgenerator
docs/                     källregister, databasmodell, validering, visuell jämförelse, mockuper
```

---

## Data, källor och licenser

Fullständigt register: **[docs/KALLREGISTER.md](docs/KALLREGISTER.md)** (genereras från koden och visas i appen).

| Källa | Användning | Träning som standard |
|---|---|---|
| OpenFootball (CC0) | Fixturer och resultat för alla säsonger i källan, hämtas via GitHubs API | Tillåten |
| Wyscout öppna händelsedata (CC BY 4.0) | Skott, skott på mål, hörnor, spelare och startelvor 2017/18 i de fem stora ligorna | Tillåten |
| Manuell inmatning | Utfall, startelvor | Tillåten |
| StatsBomb Open Data | Urval av matcher med händelsedata (attribution krävs) | Spärrad tills villkoren godkänts |
| UEFA | Förstahandskälla; automatisk hämtning avstängd (odokumenterade endpoints) | Spärrad tills dokumenterat beslut |
| API-Football, football-data.org | Fixturer, startelvor, frånvaro, statistik (API-nyckel) | Spärrad tills villkoren godkänts |
| Football-Data.co.uk | Endast visning/jämförelse; villkoren utesluter AI-träning | Spärrad – kräver skriftligt tillstånd |
| The Odds API | Odds för jämförelse | Aldrig träning |
| StatMuse, Sofascore-bilden | Rimlighetskontroll respektive designförlaga – ingen insamling | Aldrig |

Principer som är inbyggda i koden:

* **Spärr per observation.** Varje värde bär sin källa; modellernas datavy laddar bara källor vars träning är
  tillåten. Odds används aldrig som träningsdata.
* **Hämtning följer reglerna.** robots.txt respekteras, anropsgränser och dygnskvoter per källa, retry med
  exponentiell backoff och `Retry-After`, villkorliga anrop (ETag/Last-Modified). Inga inloggningar, betalväggar
  eller tekniska spärrar kringgås. Källor som inte får hämtas automatiskt har en importväg i stället.
* **Spårbarhet.** Varje hämtning loggas med URL, tid, HTTP-status, filens SHA-256, tolkningsstatus och antal rader.
  Råfiler arkiveras. API-nycklar maskeras i loggen.
* **Saknat är NULL, aldrig 0.** Saknade värden visas som *saknas* i appen och i PDF:en.
* **Exakta alias.** `Paris` ≠ `Paris FC`, `Slovan` ≠ `Slovan Liberec`. Alias kan vara knutna till en viss källa
  eller liga. Nya namn som liknar befintliga lag flaggas för granskning – inget slås ihop automatiskt.
* **90 min, förlängning och straffar lagras separat.** Matcher som avgjorts i förlängning används inte som
  90-minutersobservationer i träningen.

### Historikhämtning och driftstatus

*Data & källor → Hämta historik* hämtar historik från de valda källorna i ordningen OpenFootball, Wyscout,
StatsBomb och API-Football. Samma vy visar driftstatus per serie och mått. *Operativ* betyder minst 100 spelade
matcher med värde de senaste 450 dagarna från en källa som får användas för träning.

* **Lagkoppling via matcher.** En källas lag-ID kopplas till ett befintligt lag när källans matcher motsvarar
  befintliga matcher, alltså samma tävling, datum ±1 dygn och samma 90-minutersresultat. Namnlikhet används inte.
* **Oförändrade filer hämtas inte igen.** Det avgör blob-SHA från GitHub.
* **Avbruten hämtning återupptas av sig själv.** Det gäller när en anropsgräns eller dygnskvot stoppar
  hämtningen.
* **API-Footballs abonnemang styr säsongerna.** Säsonger som abonnemanget inte omfattar markeras med källans eget
  meddelande. Matchdetaljer hämtas för upp till 20 matcher per anrop.
* **Gammal data för räknemått används inte.** Skott, skott på mål och hörnor äldre än 450 dagar ingår inte
  (inställbart). Värdet visas då som saknat, med orsak.

Täckningen i siffror finns på grenen
[`datarapport`](https://github.com/steandols-cmd/matchiq/tree/datarapport/rapport). Den uppdateras av
GitHub Actions (*Datakällor – inventering och nedladdning*) vid ändringar och varje måndag:

* **Öppna källor ger 1X2.** Det blir operativt för CL och de fem stora ligorna (OpenFootball 2010/11–2026/27,
  CL 2011/12–2025/26).
* **Allsvenskan finns bara delvis.** Den finns för 2023–2025, och 2025 bara till och med maj.
* **Hörnor och skott finns bara för äldre säsonger.** Det gäller Wyscout 2017/18 och StatsBomb för valda
  matcher, och den datan är äldre än 450 dagar. För aktuella säsonger krävs API-Football. För CL krävs ditt
  beslut om UEFA-datan i arbetsboken.

---

## Modeller och validering

| Modell | Beskrivning | Status |
|---|---|---|
| **BASE-1.0** | Klassfrekvenser (Laplace-utjämnade) och tävlingsmedel | Jämförelsenivå |
| **V2-2.0** | Arbetsbokens metod: senaste 15 matcher per lag, k = 8 krympning mot tävlingsmedel, oberoende Poisson | **Baslinje** (bärnsten) |
| **V3-3.0** | Tidsviktade anfalls-/försvarsstyrkor med empirisk-Bayes-krympning, inhemsk styrka bryggad till Europa via tidigare inbördes möten, negativ binomial för räknevariabler | **Experimentell** (ljusgrön) tills alla grindar passerats |

Varje mått (mål, hörnor, skott, skott på mål) har egen modell. Ingen data som publicerats efter prognosens
datagräns används – det kontrolleras med assertioner i datavyn och med ett eget läckagetest.

### Validering (detaljer i [docs/VALIDERING.md](docs/VALIDERING.md))

Expanderande fönster per matchdag. V3:s parametrar valdes på **2023/24–2024/25** och låstes innan den orörda
holdouten **2025/26–2026/27** utvärderades. Resultat på holdouten (Champions League, n = 214 matcher):

| Modell | Brier ↓ | Log loss ↓ | Mål MAE | Skott MAE | Hörnor MAE | 80 %-intervall skott |
|---|---|---|---|---|---|---|
| V3 (exp.) | **0,543** | **0,920** | **1,10** | **3,94** | **2,07** | 80 % |
| V2 | 0,552 | 0,935 | 1,11 | 4,21 | 2,13 | 66 % |
| Baslinje | 0,614 | 1,018 | 1,18 | 4,71 | 2,27 | 62 % |

Arbetsbokens V2-benchmark reproduceras exakt: **517 matcher, Brier 0,556 mot baslinjens 0,616, log loss 0,940
mot 1,020** (automatiskt test).

**Grindar för produktion** (visas i appen): ≥ 200 tidsordnade testobservationer per mått, ≥ 2 säsonger,
låst modellval före orörd slutsäsong, bättre än V2 och baslinjen på holdout, 80 %-intervallens faktiska täckning
70–90 % och **≥ 200 frysta T−30-prognoser med facit**. V3 klarar alla backtest-grindar och har status
*kandidat*, men saknar ännu prospektiva T−30-prognoser. V3 kan därför inte sättas i produktion och visas som
**experimentell** överallt. Produktion kan bara sättas manuellt, och bara när alla grindar är gröna.

> Siffrorna ovan kommer från demodatabasen, där UEFA-data godkänts för träning med en dokumenterad anteckning.
> I en ny installation, där UEFA är spärrad, blir underlaget ett annat. Kör då om valideringen under
> *Utvärdering*.

---

## T−30-schemaläggning och PDF-arkiv

* Varje kommande match får ett jobb med förfallotid **avspark − 30 min** (UTC). Ändrad avsparkstid ersätter
  väntande jobb.
* Inför T−30 synkas matchens källor (startelvor, frånvaro). Vid T−30 beräknas V2, V3 och baslinjen med
  **datagräns = T−30**, ögonblicksbilderna sparas oföränderligt (match-ID, källor och hämttider, datagräns,
  modellversion, startelvans status) och PDF:en skapas och arkiveras. Avisering skickas.
* **Startelvor:** *bekräftad*, *förväntad* eller *ej publicerad* vid datagränsen. Rapporten skapas även utan elva
  men märks tydligt. Spelarstatus hittas aldrig på.
* **Missad tidpunkt** (dator avstängd, appen stängd, nätverket nere): T−30-tidpunkten markeras som *missad* och
  en tydligt märkt **SEN rapport** skapas med faktisk data, faktisk skapandetid och en datagräns som aldrig
  ligger efter avspark. Den räknas inte som en förmatchsprognos i utvärderingen.
* Senare uppdateringar skriver aldrig över en fryst T−30-prognos. Databastriggers stoppar UPDATE/DELETE på
  `forecast_snapshots` och `reports`.

**Arkiv:** `reports/ÅÅÅÅ-MM-DD/TÄVLING/ÅÅÅÅ-MM-DD_HHMM_TÄVLING_Hemma_vs_Borta_m<id>_T-30.pdf`
(ändelsen är `SEN` för sena, `MANUELL` för manuella och `TEST` för testrapporter).

PDF:en innehåller match, tävling, lokal avsparkstid (och UTC), skapandetid, T−30-datagräns, 1X2 i procent,
förväntade värden med intervall, startelvornas status, täckning, källor och träningsbeslut, modellversioner med
ögonblicksbildernas ID, osäkerhetsflaggor och texten *”statistisk prognos, inte ett löfte om utfall”*. Saknade
värden skrivs som *saknas*, aldrig som 0.

Simulera en hel matchdag utan att vänta (på en kopia av databasen, rapporterna märks *SIMULERAD KLOCKA*):

```bash
python scripts/simulate_matchday.py --data-dir DATAMAPP --copy-to /tmp/sim \
  --start 2026-10-20T16:00:00Z --end 2026-10-21T19:00:00Z
```

---

## Eftermatch och kalibrering

Utfall (mål, hörnor, skott, skott på mål) hämtas automatiskt från aktiva källor eller matas in manuellt under
matchens flik *Eftermatch*. Utfallen sparas separat, länkas till den frysta ögonblicksbilden och gamla prognoser
räknas aldrig om. *Utvärdering* visar fel per mått över tid för V2, V3 och baslinjen, kalibreringsdiagram och n.

---

## Databasen – åtkomst, export och migrering

Detaljerad modell: **[docs/DATABAS.md](docs/DATABAS.md)**.

* Databasen är **en vanlig SQLite-fil** (`matchiq.sqlite` i datamappen) och kan öppnas med valfritt
  SQLite-verktyg, t.ex. *DB Browser for SQLite* eller `sqlite3`. Stäng appen först om du ska skriva i den.
* **Exportera allt** (*Inställningar → Databas → Exportera hela databasen*, eller
  `python -m matchiq.cli export --out matchiq-export.zip`): zip med komplett SQLite-fil, en CSV per tabell,
  `schema.sql` och `manifest.json` (app- och schemaversion, radantal och SHA-256 per fil).
* **Läsa in en export** (*Inställningar → Databas → Läs in export…*, eller `python -m matchiq.cli import-db --file …`):
  kontrollsummorna verifieras, nuvarande databas säkerhetskopieras och exporten migreras fram till appens
  schemaversion.
* **Migreringar** är numrerade SQL-filer i `backend/matchiq/migrations/`. Vid start tas en säkerhetskopia och
  väntande migreringar körs. `schema_migrations` lagrar version, tid, appversion och filens SHA-256. Nya ändringar
  läggs som nästa fil (`0002_….sql`) och gamla filer ändras aldrig. Exporten är därmed formatet för att flytta
  data till en ny version eller ett annat system.
* Säkerhetskopior: automatiskt före varje migrering och manuellt med en knapp. Säkerhetskopiorna ligger i
  `backups/`.

---

## Säkerhet

* Backend binder bara till `127.0.0.1` på en slumpad port och exponeras aldrig på nätverket.
* Varje start får en ny slumpad token (256 bitar) som bara Electron-processen känner till. Varje anrop kräver
  `Authorization: Bearer`. Felaktig `Host` ger 421 (skydd mot DNS-rebinding) och CORS är begränsat till appens
  eget ursprung.
* Gränssnittet körs med `contextIsolation`, `sandbox` och utan Node-integration. IPC-anrop kontrollerar
  avsändarens ursprung, och filöppning tillåts bara inom datamappen.
* API-nycklar lagras i macOS Nyckelring respektive Windows Autentiseringshanteraren och returneras aldrig till
  gränssnittet. Inga hemligheter finns i källkoden. Se `config.example.env`.
* Backend avslutas automatiskt om Electron-processen försvinner.
* Backend paketeras som en fristående sidecar (PyInstaller) som kan signeras och notariseras tillsammans med
  appen.

---

## Tester och vad som är verifierat

```bash
cd backend && MATCHIQ_SECRETS=memory PYTHONPATH=. python -m unittest discover -s tests -p "test_*.py"
# Med arbetsboken: MATCHIQ_WORKBOOK=/sökväg/UCL_…V3.xlsx (aktiverar import- och benchmarktesterna)
```

| Acceptanstest | Verifiering | Var |
|---|---|---|
| 1. Appen startar och kan navigeras | Gränssnitt och backend i Chromium (alla vyer, stående + liggande, inga JS-fel). Electron-starten och `.dmg`/`.exe` byggs och röktestas i CI | Lokalt + CI |
| 2. Import två gånger ger inga dubbletter | `test_preview_then_import_twice_no_duplicates`, `test_idempotent_and_original_untouched`, `test_sync_twice_no_duplicates_and_logged` | Lokalt |
| 3. Saknade värden förblir NULL och visas som saknade | `test_upserts_idempotent_and_null_preserved`, `test_missing_metric_is_none_not_zero`, `test_missing_stats_null`, `test_parse_and_null_corners` | Lokalt |
| 4. Ingen data efter datagränsen används | `test_no_leakage_after_cutoff`, `test_view_asserts_on_cutoff`, `test_late_after_kickoff_never_uses_post_kickoff_data` | Lokalt |
| 5. T−30 med simulerad klocka | `test_t30_job_runs_exactly_with_simulated_clock`, `test_simulated_tick_creates_t30_report`, simulering av MD3 (15 rapporter) | Lokalt |
| 6. PDF med rätt ögonblicksbild, 100 % och rätt tider | `test_pdf_contains_snapshot_probabilities_and_times` (läser PDF-texten) | Lokalt |
| 7. Saknad/sen startelva visas öppet | `test_lineup_states_and_no_fabrication`, `test_late_lineup_flagged_in_report` | Lokalt |
| 8. V2/V3-status, källvillkor och täckning syns i UI | `scripts/ui_check.py` kontrollerar obligatoriska texter i varje vy | Lokalt + CI |
| 9. UI jämfört med mockuperna, stående + liggande | Sida-vid-sida-montage och mått i [docs/VISUELL-JAMFORELSE.md](docs/VISUELL-JAMFORELSE.md) | Lokalt + CI |

**Testat i utvecklingsmiljön (Linux):** alla backendtester (78 st), arbetsboksimporten med kontrollvärden,
V2-benchmarken, modellvalet, MD3-simuleringen med 15 PDF:er, databasexport och -import, sidecar-protokollet
(Node-test), gränssnittet i Chromium och en typkontroll av gränssnittskoden mot förenklade React-typer.

**Testat i GitHub Actions:** backendtesterna på Linux, macOS och Windows, typkontroll och bygge av gränssnittet,
UI-kontrollen och sidecar-testet på alla tre plattformarna. Dessutom byggs PyInstaller-backend med röktest och
installationspaketen `.dmg`/`.zip` (Apple Silicon), `.exe`/`.msi` och `.AppImage`.

**Inte testat automatiskt:** att Electron-fönstret startar och fungerar på en riktig Mac eller Windows-dator,
alltså fönster, systemfält, autostart och aviseringar. Det prövas först vid installationen.

---

## Det här behöver du konfigurera

Allt fungerar utan nycklar. Det här låser upp mer data:

| Vad | Varför | Var |
|---|---|---|
| **API-Football-nyckel** (api-football.com) | Bekräftade startelvor, frånvaro och matchstatistik (hörnor och skott) för alla sju tävlingar, plus Allsvenskans spelschema. Krävs för att hörnor och skott ska bli operativa i ligorna. Gratisnivån har 100 anrop/dygn och ett begränsat urval säsonger. Appen visar vilka säsonger ditt abonnemang omfattar | Inställningar → API-nycklar, sedan Data & källor → Hämta historik |
| **GitHub-token** (gratis, inga behörigheter behövs) | Höjer GitHubs gräns från 60 till 5 000 anrop/timme, så att OpenFootball- och StatsBomb-hämtningen går på minuter i stället för timmar | Inställningar → API-nycklar |
| **football-data.org-nyckel** | Fler fixturer och resultat | Som ovan |
| **The Odds API-nyckel** | Oddsjämförelse (aldrig träning) | Som ovan |
| **Beslut om UEFA-data** | Arbetsbokens CL-historik får användas för träning först efter ditt dokumenterade beslut | Data & källor → UEFA → Godkänn för träning |
| **Beslut om StatsBomb Open Data** | Kräver att du godkänner StatsBombs användarvillkor | Data & källor → StatsBomb |
| **Skriftligt tillstånd från Football-Data.co.uk** | Endast om du vill använda deras data för träning | Data & källor (referens krävs) |
| **Kodsigneringscertifikat** (Apple Developer ID / Windows) | Inga Gatekeeper-/SmartScreen-varningar | GitHub-secrets, se ovan |

---

## Utvecklingsläge

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m matchiq --dev-token --port 8765          # skriver ut en utvecklingstoken

# Gränssnitt (i ett annat fönster)
npm install
npm --workspace apps/web run dev   # öppna http://localhost:5173/?token=<token>&api=http://127.0.0.1:8765

# Hela skrivbordsappen (bygger gränssnittet och startar Electron med Python-backend)
npm run desktop:start
```

Kommandoraden (`python -m matchiq.cli …`): `migrate`, `backup`, `export`, `import-db`, `import-workbook`,
`select-models`, `simulate-t30`, `tick`. Kör `python -m matchiq.cli --help` för detaljer.

Demodatabas och skärmbilder:

```bash
python scripts/make_demo.py --data-dir /tmp/demo --workbook UCL_…V3.xlsx --approve-uefa
python scripts/ui_check.py --out ui-check --data-dir /tmp/demo --mockups docs/mockups [--theme light]
python scripts/gen_docs.py                         # uppdaterar docs/KALLREGISTER.md och docs/DATABAS.md
```

---

## Kända begränsningar

* **Tema:** mockuperna är mörka medan kravtexten beskriver en ljus arbetsyta med marinblå rubriker. Appen startar
  i mörkt tema (som mockuperna). Det ljusa temat finns under *Inställningar → Utseende → Ljus arbetsyta*, med vit arbetsyta,
  marinblå rubriker med vit text och ljusblå tabellränder. Skärmbilder finns i båda teman.
* **Klubbmärken:** officiella klubbmärken är varumärkesskyddade och följer inte med. Appen ritar en sköld i
  klubbens färger med initialer. Du kan ladda upp ett märke per lag under *Lag & spelare*.
* **Odds:** oddsfliken är tom tills en oddskälla med nyckel aktiverats. Inga odds hittas på.
* **UEFA:** automatisk hämtning är avstängd eftersom endpoints är odokumenterade och villkoren oklara. Data
  importeras via arbetsboken eller en fil.
* **Arbetsboken V3** innehåller inte bladen för trupp/målskyttar, Football-Data, football.json, Europe, StatsBomb
  och manifestet över misslyckade hämtningar. De kontrollvärdena redovisas som *saknas i filen*. De som finns
  stämmer exakt (2 024 CL-matcher, 15 340 inhemska matcher och alla kontrollerade saknade värden).
* **Startelvor från arbetsboken** saknar exakta positioner för utespelare. De visas som *”Utespelare – exakt
  position ej verifierad”* i stället för att gissas.

Teckensnitt i PDF: DejaVu Sans (fri licens, `backend/matchiq/assets/fonts/DejaVu-LICENSE.txt`).
