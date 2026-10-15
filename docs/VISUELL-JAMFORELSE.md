# Visuell jämförelse mot mockuperna

Skapad med `scripts/ui_check.py`, som startar backend och det byggda gränssnittet. Skriptet tar skärmbilder i
**stående (941 × 1672)** och **liggande (1672 × 941)** format med enhetsskala 2, dvs. 1882 × 3344 respektive
3344 × 1882 pixlar. Det kontrollerar också att obligatoriska element syns och lägger varje mockup sida vid sida
med motsvarande vy. CI-jobbet *UI-kontroll* gör samma sak vid varje bygge och laddar upp bilderna som artefakt.

```bash
python scripts/ui_check.py --out ui-check --data-dir DEMO --mockups docs/mockups            # mörkt tema
python scripts/ui_check.py --out ui-check-ljus --data-dir DEMO --theme light                # ljust tema
```

## De fem huvudvyerna (obligatoriska texter kontrolleras automatiskt)

| Vy | Route | Kontrollerade element | Resultat |
|---|---|---|---|
| Matchlista | `#/matcher?c=UCL` | Tävlingsflikar, *Kommande*, matchanalyspanel | ✅ |
| Matchprognos | `#/match/<id>` | Hemma/X/Borta, rättvisa odds, V2-*BASLINJE*, startelvor, hörnor, skott på mål | ✅ |
| Lag, spelare och startelva | `#/lag/<id>` | Startelvor, snitt för/emot, identitet och alias | ✅ |
| Datakällor och täckning | `#/data?tab=kallor` | Källregister, licens, *Spärrad från träning* och *Träning tillåten* | ✅ |
| Utfall och kalibrering | `#/utvardering` | Walk-forward, *EXPERIMENTELL*, *BASLINJE*, frysta prognoser mot utfall | ✅ |

Inga JavaScript-fel i någon vy och inga laddningsindikatorer kvar vid fotograferingen (båda teman).

## Mockup för mockup

Måtten är grova och används bara som indikatorer. *Palett* är histogramöverlapp i HSV (0–1) och *layout* är
korrelationen mellan nedskalade gråskalebilder (−1–1). Mockuperna visar andra matcher och lag än demodatan,
så layoutkorrelationen kan inte bli hög ens när strukturen är densamma. Bedömningen görs i sida-vid-sida-bilderna.

| Mockup | MatchIQ-vy | Format | Palett | Layout | Bedömning |
|---|---|---|---|---|---|
| 1 | Match – Statistik | stående | 0,47 | 0,26 | Samma ordning: tävlingsflikar, matchhuvud med sköldar, Hemma/X/Borta-kort, fördelningsstapel, rättvisa odds, flikrad, kortrutnät 3 × 2, startelvor och matcher i vald liga |
| 2 | Match – Djupanalys | stående | 0,29 | 0,21 | Samma matchhuvud, flikrad och kortstruktur: senaste form, skador och avstängningar, analys och slutsats, startelvor. Mockupen har även xG/xGA, faktorpoäng (AI), spelarbetyg, vilodagar och taktisk match-up. MatchIQ visar i stället snitt för/emot och inbördes möten, eftersom poäng och betyg utan källa inte hittas på |
| 3 | Match – Oddsjämförelse | stående | 0,73 | 0,15 | Samma upplägg. Fliken är tom tills en oddskälla aktiveras – inga odds hittas på |
| 4 | Match – Datakvalitet | stående | 0,48 | 0,24 | Täckning, källor och flaggor i samma kortstruktur |
| 5 | Matchlista | stående | 0,58 | 0,21 | Ligahuvud, matchlista med tid till vänster, 1X2 och status, sidopanel med matchanalys |
| 6 | Match – Statistik | liggande | 0,55 | 0,15 | Som 1, med tvåkolumnslayout |
| 7 | Match – Djupanalys | liggande | 0,31 | 0,15 | Som 2 |
| 8 | Match – Oddsjämförelse | liggande | 0,54 | 0,14 | Som 3 |
| 9 | Match – Datakvalitet | liggande | 0,50 | 0,07 | Som 4. Ljusare tabeller i MatchIQ ger låg korrelation |
| 10 | Matchlista | liggande | 0,43 | 0,24 | Ligahuvud, flikar Matcher/Tabell/Datatäckning, lista och högerpanel |

## Medvetna avvikelser från mockuperna

* **Klubbmärken och ligalogotyper** är varumärkesskyddade och används inte. MatchIQ ritar sköldar i klubbens
  färger med initialer och flaggor för ligorna. Egna märken kan laddas upp per lag.
* **Mått utan tillåten källa visas inte som siffror.** Mockuperna har rutor för gula kort, frisparkar,
  målvaktsräddningar, publiksnitt, TV-kanal, faktorpoäng och spelarbetyg. Kravspecifikationens mått är mål, hörnor, skott och skott på mål,
  och för de övriga saknas tillåten källa i grunddatan. MatchIQ visar i stället förväntade mål, BTTS och
  modellens 1X2 med intervall. Saknade mått markeras *saknas* och hittas aldrig på.
* **V2/V3-växeln och modellmärkningen** (V2 bärnsten, V3 ljusgrön och *experimentell*) finns inte i
  mockuperna men krävs av specifikationen. Därför finns också en extra flik: *V2 mot V3*.
* **Flikarna *Eftermatch* och *Rapporter*** är tillagda för utfallsflödet och PDF-arkivet.
* **Startelvor** visar status (*bekräftad / förväntad / ej publicerad*) och källa. Utan publicerad elva visas en
  tom ruta med förklaring i stället för en gissad elva.
* **Tema:** mockuperna är mörka och kravtexten beskriver en ljus arbetsyta. Båda finns (*Inställningar →
  Utseende*) och skärmbilder levereras i båda teman.
