# Validering av modellerna

Genererad från valideringskörningen 2026-10-15T08:16:21Z (`scripts/gen_docs.py --data-dir …`). Samma siffror visas live i appen under **Utvärdering**.

## Upplägg

- **Tävling:** UCL
- **Valideringssäsonger (modellval):** 2023/24, 2024/25
- **Orörd holdout (test):** 2025/26, 2026/27
- **Träningskällor:** manual, openfootball, uefa
- **Datagräns per prognos:** matchdagens början (Stockholm) – expanderande fönster, endast matcher som spelats och publicerats före datagränsen; matcher avgjorda i förlängning ingår inte som 90-minutersobservationer.
- **Modellval låst:** 2026-10-15T08:16:10Z, före utvärderingen av holdouten.
- **Mått:** Brier (summa över tre klasser), log loss, träffprocent för 1X2; MAE, RMSE, bias och faktisk täckning för 80 %-intervallet (P10–P90) för mål, skott, skott på mål och hörnor (per lag och match).

## Orörd holdout

| Modell | n 1X2 | Brier | Log loss | Träff | Mål MAE / bias / täckn. | Skott MAE / bias / täckn. | Skott på mål MAE / bias / täckn. | Hörnor MAE / bias / täckn. |
|---|---|---|---|---|---|---|---|---|
| V3 (experimentell) | 214 | 0,543 | 0,920 | 59 % | 1,10 / -0,20 / 90 % (n=428) | 3,94 / -0,50 / 80 % (n=428) | 1,99 / -0,32 / 85 % (n=428) | 2,07 / 0,03 / 85 % (n=428) |
| V2 (baslinje) | 214 | 0,552 | 0,935 | 58 % | 1,11 / -0,10 / 91 % (n=428) | 4,21 / -0,24 / 66 % (n=428) | 2,06 / -0,23 / 80 % (n=428) | 2,13 / -0,03 / 78 % (n=428) |
| Baslinje | 214 | 0,614 | 1,018 | 50 % | 1,18 / -0,24 / 87 % (n=428) | 4,71 / -0,74 / 62 % (n=428) | 2,28 / -0,02 / 75 % (n=428) | 2,27 / 0,18 / 74 % (n=428) |

## Valideringssäsonger (där V3:s parametrar valdes)

| Modell | n 1X2 | Brier | Log loss | Träff | Mål MAE / bias / täckn. | Skott MAE / bias / täckn. | Skott på mål MAE / bias / täckn. | Hörnor MAE / bias / täckn. |
|---|---|---|---|---|---|---|---|---|
| V3 (experimentell) | 312 | 0,529 | 0,906 | 60 % | 1,01 / -0,08 / 91 % (n=624) | 4,09 / -0,38 / 79 % (n=624) | 1,96 / -0,12 / 84 % (n=624) | 2,17 / -0,15 / 83 % (n=624) |
| V2 (baslinje) | 312 | 0,558 | 0,943 | 57 % | 1,03 / -0,06 / 92 % (n=624) | 4,18 / -0,20 / 68 % (n=624) | 2,04 / -0,08 / 79 % (n=624) | 2,22 / -0,15 / 76 % (n=624) |
| Baslinje | 312 | 0,616 | 1,021 | 50 % | 1,10 / -0,09 / 92 % (n=624) | 4,59 / -0,47 / 63 % (n=624) | 2,20 / 0,33 / 76 % (n=624) | 2,34 / -0,02 / 72 % (n=624) |

## Per säsong (1X2)

| Säsong | V3 (experimentell) Brier / log loss (n) | V2 (baslinje) Brier / log loss (n) | Baslinje Brier / log loss (n) |
|---|---|---|---|
| 2023/24 | 0,529 / 0,906 (125) | 0,557 / 0,942 (125) | 0,631 / 1,046 (125) |
| 2024/25 | 0,530 / 0,906 (187) | 0,559 / 0,944 (187) | 0,606 / 1,004 (187) |
| 2025/26 | 0,552 / 0,933 (187) | 0,559 / 0,945 (187) | 0,620 / 1,027 (187) |
| 2026/27 | 0,479 / 0,831 (27) | 0,505 / 0,871 (27) | 0,572 / 0,955 (27) |

## V3: valda parametrar

```json
{
  "half_life_days": 2920.0,
  "k": 4.0,
  "half_life_days_counts": 730.0,
  "k_counts": 8.0,
  "bridge": "domestic",
  "beta": 1.0,
  "rho": 0.0,
  "window_days": 3650.0,
  "calibrated": true,
  "selected_on": [
    "2023/24",
    "2024/25"
  ],
  "selected_at_utc": "2026-10-15T08:16:10Z"
}
```

Sökordning (val på valideringssäsongerna, lägsta log loss för 1X2 respektive negativ log-likelihood för räknemått; en förändring måste förbättra med minst 0,002 för att väljas):

| Steg | Parametrar | Log loss 1X2 | NLL räknemått |
|---|---|---|---|
| hl_k | half_life_days=180.0, k=2.0 | 0,9424 | 2,6155 |
| hl_k | half_life_days=180.0, k=4.0 | 0,9439 | 2,5986 |
| hl_k | half_life_days=180.0, k=8.0 | 0,9582 | 2,5992 |
| hl_k | half_life_days=180.0, k=16.0 | 0,9790 | 2,6128 |
| hl_k | half_life_days=365.0, k=2.0 | 0,9359 | 2,5972 |
| hl_k | half_life_days=365.0, k=4.0 | 0,9339 | 2,5840 |
| hl_k | half_life_days=365.0, k=8.0 | 0,9428 | 2,5847 |
| hl_k | half_life_days=365.0, k=16.0 | 0,9611 | 2,5976 |
| hl_k | half_life_days=730.0, k=2.0 | 0,9309 | 2,5944 |
| hl_k | half_life_days=730.0, k=4.0 | 0,9284 | 2,5829 |
| hl_k | half_life_days=730.0, k=8.0 | 0,9332 | 2,5805 |
| hl_k | half_life_days=730.0, k=16.0 | 0,9465 | 2,5883 |
| hl_k | half_life_days=1460.0, k=2.0 | 0,9255 | 2,6020 |
| hl_k | half_life_days=1460.0, k=4.0 | 0,9233 | 2,5905 |
| hl_k | half_life_days=1460.0, k=8.0 | 0,9264 | 2,5851 |
| hl_k | half_life_days=1460.0, k=16.0 | 0,9360 | 2,5870 |
| hl_k | half_life_days=2920.0, k=2.0 | 0,9233 | 2,6116 |
| hl_k | half_life_days=2920.0, k=4.0 | 0,9209 | 2,5999 |
| hl_k | half_life_days=2920.0, k=8.0 | 0,9232 | 2,5926 |
| hl_k | half_life_days=2920.0, k=16.0 | 0,9307 | 2,5907 |
| bridge | bridge=league, beta=0.0 | 0,9181 | 2,5751 |
| bridge | bridge=domestic, beta=0.5 | 0,9111 | 2,5751 |
| bridge | bridge=domestic, beta=1.0 | 0,9062 | 2,5751 |
| rho | rho=-0.05 | 0,9094 | 2,5751 |
| rho | rho=-0.1 | 0,9131 | 2,5751 |

## Grindar – V3 (experimentell) (status: kandidat)

- ✅ 1x2: 214 tidsordnade testobservationer (krav ≥ 200)
- ✅ goals: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ shots: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ sot: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ corners: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ 4 säsonger i validering+test (krav ≥ 2)
- ✅ Modellval låst före orörd slutsäsong
- ✅ Lägre Brier och log loss än V2 på holdout
- ✅ Lägre Brier och log loss än baslinje på holdout
- ✅ shots: 80 %-intervallets faktiska täckning 80% (krav 70–90 %)
- ✅ sot: 80 %-intervallets faktiska täckning 85% (krav 70–90 %)
- ✅ corners: 80 %-intervallets faktiska täckning 85% (krav 70–90 %)
- ✅ goals: 80 %-intervallets faktiska täckning 90% (krav 70–90 %)
- ⚠️ Frysta T−30-prognoser med facit: 0 per mått (krav ≥ 200)

Föreslagen status: **kandidat** · produktion möjlig: **nej**

## Grindar – V2 (baslinje) (status: baslinje)

- ✅ 1x2: 214 tidsordnade testobservationer (krav ≥ 200)
- ✅ goals: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ shots: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ sot: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ corners: 428 tidsordnade testobservationer (krav ≥ 200)
- ✅ 4 säsonger i validering+test (krav ≥ 2)
- ✅ Modellval låst före orörd slutsäsong
- ✅ Lägre Brier och log loss än baslinje på holdout
- ⚠️ shots: 80 %-intervallets faktiska täckning 66% (krav 70–90 %)
- ✅ sot: 80 %-intervallets faktiska täckning 80% (krav 70–90 %)
- ✅ corners: 80 %-intervallets faktiska täckning 78% (krav 70–90 %)
- ⚠️ goals: 80 %-intervallets faktiska täckning 91% (krav 70–90 %)
- ⚠️ Frysta T−30-prognoser med facit: 0 per mått (krav ≥ 200)

V2 är jämförelsebaslinje; grindarna visas som information om dess kvalitet.

## Frysta prognoser mot faktiskt utfall (prospektivt)

Endast ögonblicksbilder som frystes före avspark (förmatchsbehöriga). Prognoserna räknas aldrig om.

| Modell | Matcher | Brier | Log loss | Träff |
|---|---|---|---|---|
| LEGACY-ORIG | 7 | 0,564 | 0,956 | 57 % |

## Benchmark mot den tidigare arbetsboken

Arbetsbokens V2-resultat reproduceras exakt av MatchIQ:s V2 (automatiskt test `test_v2_benchmark_reproduced`, körs när `MATCHIQ_WORKBOOK` pekar på arbetsboken): **517 matcher, Brier 0,556 mot baslinjens 0,616 och log loss 0,940 mot 1,020.** Arbetsbokens V3 var en skuggprototyp utan godkännande och importeras som arkiverad (LEGACY-V3). MatchIQ:s V3 är en ny modell som valideras ovan.

## Ligorna

Modellvalet ovan gäller Champions League. Walk-forward per liga (Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Allsvenskan) med samma parametrar körs i GitHub Actions på öppen data och publiceras i [datarapporten](https://github.com/steandols-cmd/matchiq/blob/datarapport/rapport/oppen_data.md). Den 15 oktober 2026 hade V3 lägre Brier än V2 i 20 av 23 ligasäsonger. Hörnor och skott kunde bara kontrolleras på 2017/18 (Wyscout).

## Tolkning och förbehåll

- V3 klarar alla backtest-grindar men saknar ännu ≥ 200 frysta T−30-prognoser med facit. Status är därför *kandidat*, och modellen visas som **experimentell** i hela appen. Produktion kan bara sättas manuellt när alla grindar är gröna.
- V3:s modellstruktur utvecklades med tillgång till hela historiken, även om parametervalet var låst före holdouten. Kravet på prospektiva T−30-prognoser finns för att fånga sådan överanpassning.
- Om träningskällorna ändras (t.ex. om UEFA-data spärras eller godkänns) ändras underlaget. Kör då om valideringen.
- LEGACY-ORIG är arbetsbokens egna frysta prognoser (importerade med ursprunglig tidsstämpel).

