# Käll- och licensregister

Genererat från `backend/matchiq/catalog.py`. Samma register visas i appen under **Data & källor → Källor & licenser**, där användaren också kan godkänna eller återkalla träningsanvändning (varje beslut loggas).

| Källa | Ägare | Licens / villkor | Tillåtna användningar | Träning (standard) | Hämtning | Uppdatering |
|---|---|---|---|---|---|---|
| **OpenFootball (football.json, champions-league, europe m.fl.)**<br>https://github.com/openfootball | OpenFootball-projektet (Gerald Bauer m.fl.) | CC0 1.0 / public domain enligt respektive repository | visning, träning, utvärdering, marknadsjämförelse | Tillåten (licens) | Automatisk | Oregelbunden (frivilligt underhåll); kontrollera dagligen |
| **StatsBomb Open Data (Hudl)**<br>https://github.com/statsbomb/open-data | Hudl / StatsBomb | StatsBombs användaravtal för öppna data – attribution krävs, logotypvillkor gäller | visning, träning, utvärdering | Spärrad tills villkoren godkänts av användaren | Automatisk | Sällan; nya urval publiceras oregelbundet |
| **Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare)**<br>https://figshare.com/collections/Soccer_match_event_dataset/4415000 | Wyscout / L. Pappalardo, P. Cintia, A. Rossi m.fl. (CNR Pisa) | CC BY 4.0 (angivet på figshare och i artikeln i Scientific Data 6:236, 2019) | visning, träning, utvärdering | Tillåten (licens) | Automatisk | Statisk datamängd (publicerad 2019) |
| **UEFA – officiella tävlings- och matchdata**<br>https://www.uefa.com/uefachampionsleague/ | UEFA | UEFA:s innehållsrättigheter. Matchdomänens endpoints är inte en publicerad API-produkt. | visning, utvärdering | Spärrad – rättigheter oklara (kräver dokumenterat beslut) | Avstängd som standard | Löpande under matchdagar |
| **Football-Data.co.uk**<br>https://www.football-data.co.uk/data.php | Football-Data.co.uk | Privat bruk. Kommersiell användning samt AI-/botbaserade träningsprodukter undantas. | visning, marknadsjämförelse | Spärrad – kräver skriftligt tillstånd | Automatisk | Ungefär två gånger per vecka under säsong |
| **football-data.org (API v4)**<br>https://www.football-data.org/ | football-data.org | API-licens enligt valt abonnemang; nyckel krävs | visning, utvärdering, träning | Spärrad tills villkoren godkänts av användaren | Automatisk med API-nyckel | Löpande; gratisnivå begränsad till 10 anrop/min |
| **API-Football (API-Sports v3)**<br>https://www.api-football.com/ | API-Sports | Kommersiellt API enligt abonnemangsvillkor; nyckel krävs | visning, utvärdering, träning | Spärrad tills villkoren godkänts av användaren | Automatisk med API-nyckel | Löpande; startelvor normalt 20–40 min före avspark |
| **The Odds API (v4)**<br>https://the-odds-api.com/ | The Odds API | API-licens enligt abonnemang; nyckel krävs | visning, marknadsjämförelse | Spärrad – kräver skriftligt tillstånd | Automatisk med API-nyckel | Löpande |
| **StatMuse (äldre modulkontroller)**<br>https://www.statmuse.com/ | StatMuse | Webbplatsens villkor; inget öppet datalicens | rimlighetskontroll | Spärrad – kräver skriftligt tillstånd | Avstängd som standard | – |
| **Sofascore-skärmbild (designreferens)**<br>https://www.sofascore.com/ | Sofascore | Endast visuell förlaga för matchlistans layout | – | Spärrad – kräver skriftligt tillstånd | Avstängd som standard | – |
| **Tidigare arbetsbok (UCL-modul) – frysta prognoser**<br>lokal fil | Användaren | Egna härledda prognoser; underliggande data behåller sin ursprungskälla | visning, utvärdering | Spärrad – kräver skriftligt tillstånd | Endast import | Vid import |
| **Manuell inmatning**<br>lokal inmatning | Användaren | Användarens egen inmatning | visning, utvärdering, träning | Tillåten (licens) | Endast import | Vid inmatning |
| **Egen fil (Excel/CSV) – okänd ursprungskälla**<br>lokal fil | Användaren | Okänd – ange ursprungskälla vid import | visning | Spärrad – rättigheter oklara (kräver dokumenterat beslut) | Endast import | Vid import |

## Täckning och kända begränsningar

- **OpenFootball (football.json, champions-league, europe m.fl.)** – Spelscheman och resultat. Inga kompletta skott-, hörn- eller spelardata. CL-arkiv från 2011/12; ligatäckning varierar per land och säsong. Filerna hämtas via GitHubs dokumenterade REST-API (60 anrop/timme utan token). Saknade filer loggas med HTTP-status.
- **StatsBomb Open Data (Hudl)** – Händelsedata (passningar, skott, xG, kort, försvarsaktioner) för UTVALDA tävlingar och säsonger – inte heltäckande historik. Träning kräver att användaren läst och godkänt villkoren under Källor & licenser.
- **Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare)** – Säsongen 2017/18 i Premier League, La Liga, Bundesliga, Serie A och Ligue 1 (1 826 matcher): alla händelser inklusive skott och hörnor, spelare, startelvor och byten. VM 2018 och EM 2016 ingår i datamängden men används inte. Hämtas via figshares dokumenterade API. Taggarnas betydelse läses ur källans egen tags2name.csv.
- **UEFA – officiella tävlings- och matchdata** – Förstahandskälla för Champions League: fixtures, resultat, startelvor, bänk, målskyttar, lagstatistik (skott, skott på mål, hörnor) per match-ID. Automatisk hämtning är AVSTÄNGD som standard: villkoren för automatiserad åtkomst och vidareanvändning är inte granskade och odokumenterade endpoints kan ändras. Använd importvägen (Excel/CSV) eller aktivera först efter egen granskning.
- **Football-Data.co.uk** – Resultat, odds och – varierande per liga/säsong – skott, skott på mål, hörnor, fouls, kort. SPÄRRAD från modellträning tills skriftligt tillstånd som uttryckligen medger det har registrerats. Får användas för visning och marknadsjämförelse.
- **football-data.org (API v4)** – Fixtures och resultat för större ligor och CL (beroende på abonnemang). Allsvenskan ingår inte i gratisnivån. Ange API-nyckel under Inställningar → API-nycklar (lagras i Nyckelring/Autentiseringshanteraren).
- **API-Football (API-Sports v3)** – Fixtures, resultat, bekräftade startelvor, skador/avstängningar och matchstatistik (skott, skott på mål, hörnor) för de flesta ligor inkl. Allsvenskan. Gratisnivån har 100 anrop/dygn – pollningen anpassas efter kvoten.
- **The Odds API (v4)** – 1X2-odds från flera spelbolag. Odds används bara för visning och marknadsjämförelse – aldrig för modellträning.
- **StatMuse (äldre modulkontroller)** – Utvalda CL-lagsummor i äldre material. Endast sekundär rimlighetskontroll. Hämtas inte automatiskt. Får inte vara ensam källa eller träningskälla.
- **Sofascore-skärmbild (designreferens)** – Ingen data samlas in – bilden användes bara som designförlaga. Ingen statistik eller historik hämtas från Sofascore.
- **Tidigare arbetsbok (UCL-modul) – frysta prognoser** – Frysta prognoser (Ursprung, V2, V3-skugga) och prognoslogg från arbetsboken. Prognoser används för utvärdering, aldrig som träningsdata.
- **Manuell inmatning** – Facit efter match, startelvor och korrigeringar som användaren matat in. Varje manuell ändring loggas med tid.
- **Egen fil (Excel/CSV) – okänd ursprungskälla** – Data från filer där ursprunget inte angetts. Spärrad från träning tills ursprung och rättigheter dokumenterats.

## Regler

- En datamängd används **aldrig** för modellträning om rättigheterna saknas eller är oklara. Spärren gäller per observation (varje värde bär sin källa).
- Football-Data.co.uk: villkoren utesluter AI-/botbaserade träningsprodukter – spärrad tills skriftligt tillstånd registrerats (referens krävs).
- UEFA: förstahandskälla, men automatisk hämtning är avstängd och träning spärrad tills användaren dokumenterat ett beslut. Odokumenterade endpoints kan ändras.
- StatsBomb Open Data: täcker ett urval; attribution krävs; träning först efter att villkoren godkänts.
- StatMuse: endast rimlighetskontroll. Sofascore-bilden: endast designförlaga – ingen data samlas in.
- Odds används bara för jämförelse, aldrig som träningsdata.

## Tävlingar

| Kod | Namn | Typ | Flik |
|---|---|---|---|
| UCL | Champions League | international_cup | ja |
| SWE1 | Allsvenskan | league | ja |
| ENG1 | Premier League | league | ja |
| ESP1 | La Liga | league | ja |
| GER1 | Bundesliga | league | ja |
| ITA1 | Serie A | league | ja |
| FRA1 | Ligue 1 | league | ja |
| UCLQ | Champions League – kval | international_cup | nej |
| NED1 | Eredivisie | league | nej |
| POR1 | Primeira Liga | league | nej |
| BEL1 | Pro League (Belgien) | league | nej |
| TUR1 | Süper Lig | league | nej |
| CZE1 | Tjeckiska förstaligan | league | nej |
| NOR1 | Eliteserien | league | nej |
| AZE1 | Premyer Liqa (Azerbajdzjan) | league | nej |
| AUT1 | Bundesliga (Österrike) | league | nej |
| SCO1 | Premiership (Skottland) | league | nej |
| UKR1 | Premjer-liha (Ukraina) | league | nej |
| SVK1 | Niké liga (Slovakien) | league | nej |

## Modellversioner

| ID | Status vid start | Beskrivning |
|---|---|---|
| BASE-1.0 | baslinje | Enkel baslinje: expanderande klassfrekvens för 1X2 och tävlingsmedel för antal. |
| V2-2.0 | baslinje | V2.0 | senaste 15 CL-matcher per lag | k=8 tävlingsprior | oberoende Poisson. Jämförelsebaslinje enligt den tidigare arbetsbokens metod. |
| V3-3.0 | experimentell | V3 experimentell: tidsviktad attack/försvar, empirisk-Bayes-shrinkage med validerad styrka, separat inhemsk styrka med ligafaktor från tidigare europeiska möten (aktiveras bara om den förbättrar valideringen), negativ binomial för räknevariabler vid överspridning. |
| LEGACY-ORIG | arkiverad | Ursprungliga prognoser från den tidigare arbetsboken (importerade, frysta). |
| LEGACY-V2 | arkiverad | V2-prognoser beräknade i den tidigare arbetsboken (importerade, frysta). |
| LEGACY-V3 | arkiverad | V3-skuggprognoser från den tidigare arbetsboken (importerade, frysta). |
