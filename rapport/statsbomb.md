# Hämtad data – statsbomb (2026-10-15T13:22:27Z)

Siffrorna är räknade ur databasen som byggdes av appens egna källadaptrar i GitHub Actions.

## Körning per källa

| Källa | Status | Tid (s) | Resultat |
|---|---|---|---|
| openfootball | ok | 202 | {"files_in_scope": 96, "inserted": 30225, "updated": 0, "unchanged": 0, "skipped": 0, "files_imported": 96} |
| wyscout_public | error – ValueError("Taggen 'key_pass' finns inte i tags2name.csv – importen avbryts") | 17 | {} |
| statsbomb_open | blocked – Dygnskvoten för StatsBomb Open Data (Hudl) (2000 anrop) är förbrukad – hämtningen fortsätter automatiskt nästa dygn. | 2102 | {"teams_linked": 119, "matches_todo": 2187, "match_updated": 1672, "events_imported": 1954, "match_inserted": 283} |

## Driftstatus per tävling och mått

Fönster: 450 dagar. Operativ = minst 100 matcher med värde från en källa som får användas för träning.

| Tävling | Mått | Status | Matcher i fönstret | Totalt (tillåtet) | Senaste | Källor |
|---|---|---|---|---|---|---|
| UCL | Mål / 1X2 | operativ | 188 | 1985 | 2026-05-06 | OpenFootball (football.json, champions-league, europe m.fl.): 1985, StatsBomb Open Data (Hudl): 14 |
| UCL | Hörnor | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 18 |
| UCL | Skott | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 18 |
| UCL | Skott på mål | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 18 |
| SWE1 | Mål / 1X2 | inaktuell | 0 | 533 | 2025-05-04 | OpenFootball (football.json, champions-league, europe m.fl.): 533 |
| SWE1 | Hörnor | saknas | 0 | 0 | – | – |
| SWE1 | Skott | saknas | 0 | 0 | – | – |
| SWE1 | Skott på mål | saknas | 0 | 0 | – | – |
| ENG1 | Mål / 1X2 | operativ | 398 | 6098 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 6098, StatsBomb Open Data (Hudl): 418 |
| ENG1 | Hörnor | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 418 |
| ENG1 | Skott | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 418 |
| ENG1 | Skott på mål | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 418 |
| ESP1 | Mål / 1X2 | operativ | 429 | 5359 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 5359, StatsBomb Open Data (Hudl): 867 |
| ESP1 | Hörnor | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 867 |
| ESP1 | Skott | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 867 |
| ESP1 | Skott på mål | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 867 |
| GER1 | Mål / 1X2 | operativ | 327 | 4917 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 4917, StatsBomb Open Data (Hudl): 68 |
| GER1 | Hörnor | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 68 |
| GER1 | Skott | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 68 |
| GER1 | Skott på mål | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 68 |
| ITA1 | Mål / 1X2 | operativ | 394 | 4944 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 4944, StatsBomb Open Data (Hudl): 148 |
| ITA1 | Hörnor | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 148 |
| ITA1 | Skott | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 148 |
| ITA1 | Skott på mål | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 148 |
| FRA1 | Mål / 1X2 | operativ | 323 | 4254 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 4254, StatsBomb Open Data (Hudl): 435 |
| FRA1 | Hörnor | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 435 |
| FRA1 | Skott | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 435 |
| FRA1 | Skott på mål | saknas | 0 | 0 | – | StatsBomb Open Data (Hudl): 435 |

## Täckning per tävling och säsong

| Tävling | Säsong | Matcher | Spelade | Resultat (källa: n) | Hörnor | Skott | Skott på mål | Spelarrader |
|---|---|---|---|---|---|---|---|---|
| ENG1 | 2003/04 | 38 | 38 | statsbomb_open: 38 | statsbomb_open: 38 | statsbomb_open: 38 | statsbomb_open: 38 | statsbomb_open: 371 spelare/38 matcher |
| ENG1 | 2010/11 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2011/12 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2012/13 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2013/14 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2014/15 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2015/16 | 380 | 380 | openfootball: 380, statsbomb_open: 380 | statsbomb_open: 380 | statsbomb_open: 380 | statsbomb_open: 380 | statsbomb_open: 550 spelare/380 matcher |
| ENG1 | 2016/17 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2017/18 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2018/19 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2019/20 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2020/21 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2021/22 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2022/23 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2023/24 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2024/25 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2025/26 | 380 | 353 | openfootball: 353 | – | – | – | – |
| ENG1 | 2026/27 | 380 | 45 | openfootball: 45 | – | – | – | – |
| ESP1 | 1973/1974 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 24 spelare/1 matcher |
| ESP1 | 2004/05 | 7 | 7 | statsbomb_open: 7 | statsbomb_open: 7 | statsbomb_open: 7 | statsbomb_open: 7 | statsbomb_open: 113 spelare/7 matcher |
| ESP1 | 2005/06 | 17 | 17 | statsbomb_open: 17 | statsbomb_open: 17 | statsbomb_open: 17 | statsbomb_open: 17 | statsbomb_open: 240 spelare/17 matcher |
| ESP1 | 2006/07 | 26 | 26 | statsbomb_open: 26 | statsbomb_open: 26 | statsbomb_open: 26 | statsbomb_open: 26 | statsbomb_open: 314 spelare/26 matcher |
| ESP1 | 2007/08 | 27 | 27 | statsbomb_open: 27 | statsbomb_open: 27 | statsbomb_open: 27 | statsbomb_open: 27 | statsbomb_open: 337 spelare/27 matcher |
| ESP1 | 2008/09 | 31 | 31 | statsbomb_open: 31 | statsbomb_open: 31 | statsbomb_open: 31 | statsbomb_open: 31 | statsbomb_open: 338 spelare/31 matcher |
| ESP1 | 2009/10 | 35 | 35 | statsbomb_open: 35 | statsbomb_open: 35 | statsbomb_open: 35 | statsbomb_open: 35 | statsbomb_open: 362 spelare/35 matcher |
| ESP1 | 2010/11 | 33 | 33 | statsbomb_open: 33 | statsbomb_open: 33 | statsbomb_open: 33 | statsbomb_open: 33 | statsbomb_open: 355 spelare/33 matcher |
| ESP1 | 2011/12 | 37 | 37 | statsbomb_open: 37 | statsbomb_open: 37 | statsbomb_open: 37 | statsbomb_open: 37 | statsbomb_open: 383 spelare/37 matcher |
| ESP1 | 2012/13 | 381 | 381 | openfootball: 380, statsbomb_open: 32 | statsbomb_open: 32 | statsbomb_open: 32 | statsbomb_open: 32 | statsbomb_open: 354 spelare/32 matcher |
| ESP1 | 2013/14 | 381 | 381 | openfootball: 380, statsbomb_open: 31 | statsbomb_open: 31 | statsbomb_open: 31 | statsbomb_open: 31 | statsbomb_open: 351 spelare/31 matcher |
| ESP1 | 2014/15 | 380 | 380 | openfootball: 380, statsbomb_open: 38 | statsbomb_open: 38 | statsbomb_open: 38 | statsbomb_open: 38 | statsbomb_open: 373 spelare/38 matcher |
| ESP1 | 2015/16 | 380 | 380 | openfootball: 380, statsbomb_open: 380 | statsbomb_open: 380 | statsbomb_open: 380 | statsbomb_open: 380 | statsbomb_open: 540 spelare/380 matcher |
| ESP1 | 2016/17 | 382 | 382 | openfootball: 380, statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 360 spelare/34 matcher |
| ESP1 | 2017/18 | 382 | 382 | openfootball: 380, statsbomb_open: 36 | statsbomb_open: 36 | statsbomb_open: 36 | statsbomb_open: 36 | statsbomb_open: 365 spelare/36 matcher |
| ESP1 | 2018/19 | 384 | 384 | openfootball: 380, statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 362 spelare/34 matcher |
| ESP1 | 2019/20 | 384 | 384 | openfootball: 380, statsbomb_open: 33 | statsbomb_open: 33 | statsbomb_open: 33 | statsbomb_open: 33 | statsbomb_open: 370 spelare/33 matcher |
| ESP1 | 2020/21 | 380 | 380 | openfootball: 380, statsbomb_open: 35 | statsbomb_open: 35 | statsbomb_open: 35 | statsbomb_open: 35 | statsbomb_open: 383 spelare/35 matcher |
| ESP1 | 2021/22 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2022/23 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2023/24 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2024/25 | 380 | 370 | openfootball: 370 | – | – | – | – |
| ESP1 | 2025/26 | 380 | 365 | openfootball: 365 | – | – | – | – |
| ESP1 | 2026/27 | 380 | 64 | openfootball: 64 | – | – | – | – |
| FRA1 | 2014/15 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2015/16 | 380 | 380 | openfootball: 380, statsbomb_open: 377 | statsbomb_open: 377 | statsbomb_open: 377 | statsbomb_open: 377 | statsbomb_open: 574 spelare/377 matcher |
| FRA1 | 2016/17 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2017/18 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2018/19 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2019/20 | 380 | 279 | openfootball: 279 | – | – | – | – |
| FRA1 | 2020/21 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2021/22 | 382 | 382 | openfootball: 380, statsbomb_open: 26 | statsbomb_open: 26 | statsbomb_open: 26 | statsbomb_open: 26 | statsbomb_open: 328 spelare/26 matcher |
| FRA1 | 2022/23 | 381 | 381 | openfootball: 380, statsbomb_open: 32 | statsbomb_open: 32 | statsbomb_open: 32 | statsbomb_open: 32 | statsbomb_open: 387 spelare/32 matcher |
| FRA1 | 2023/24 | 306 | 306 | openfootball: 306 | – | – | – | – |
| FRA1 | 2024/25 | 306 | 306 | openfootball: 306 | – | – | – | – |
| FRA1 | 2025/26 | 306 | 282 | openfootball: 282 | – | – | – | – |
| FRA1 | 2026/27 | 306 | 41 | openfootball: 41 | – | – | – | – |
| GER1 | 2010/11 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2011/12 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2012/13 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2013/14 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2014/15 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2015/16 | 310 | 310 | openfootball: 306, statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 346 spelare/34 matcher |
| GER1 | 2016/17 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2017/18 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2018/19 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2019/20 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2020/21 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2021/22 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2022/23 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2023/24 | 306 | 306 | openfootball: 306, statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 34 | statsbomb_open: 373 spelare/34 matcher |
| GER1 | 2024/25 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2025/26 | 306 | 294 | openfootball: 294 | – | – | – | – |
| GER1 | 2026/27 | 306 | 33 | openfootball: 33 | – | – | – | – |
| ITA1 | 2013/14 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2014/15 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2015/16 | 380 | 380 | openfootball: 380, statsbomb_open: 148 | statsbomb_open: 148 | statsbomb_open: 148 | statsbomb_open: 148 | statsbomb_open: 521 spelare/148 matcher |
| ITA1 | 2016/17 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2017/18 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2018/19 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2019/20 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2020/21 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2021/22 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2022/23 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2023/24 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2024/25 | 380 | 370 | openfootball: 370 | – | – | – | – |
| ITA1 | 2025/26 | 380 | 344 | openfootball: 344 | – | – | – | – |
| ITA1 | 2026/27 | 380 | 50 | openfootball: 50 | – | – | – | – |
| SWE1 | 2023 | 240 | 240 | openfootball: 240 | – | – | – | – |
| SWE1 | 2024 | 240 | 240 | openfootball: 240 | – | – | – | – |
| SWE1 | 2025 | 240 | 53 | openfootball: 53 | – | – | – | – |
| UCL | 1970/1971 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 24 spelare/1 matcher |
| UCL | 1971/1972 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 24 spelare/1 matcher |
| UCL | 1972/1973 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 24 spelare/1 matcher |
| UCL | 1999/00 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 28 spelare/1 matcher |
| UCL | 2003/04 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 28 spelare/1 matcher |
| UCL | 2004/05 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 27 spelare/1 matcher |
| UCL | 2006/07 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 28 spelare/1 matcher |
| UCL | 2008/09 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 27 spelare/1 matcher |
| UCL | 2009/10 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 27 spelare/1 matcher |
| UCL | 2010/11 | 1 | 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 27 spelare/1 matcher |
| UCL | 2011/12 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 25 spelare/1 matcher |
| UCL | 2012/13 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 26 spelare/1 matcher |
| UCL | 2013/14 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 28 spelare/1 matcher |
| UCL | 2014/15 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 28 spelare/1 matcher |
| UCL | 2015/16 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 26 spelare/1 matcher |
| UCL | 2016/17 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 28 spelare/1 matcher |
| UCL | 2017/18 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 27 spelare/1 matcher |
| UCL | 2018/19 | 125 | 125 | openfootball: 125, statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 1 | statsbomb_open: 28 spelare/1 matcher |
| UCL | 2019/20 | 119 | 119 | openfootball: 119 | – | – | – | – |
| UCL | 2020/21 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2021/22 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2022/23 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2023/24 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2024/25 | 189 | 189 | openfootball: 189 | – | – | – | – |
| UCL | 2025/26 | 189 | 189 | openfootball: 189 | – | – | – | – |
| UCLQ | 2024/25 | 90 | 90 | openfootball: 90 | – | – | – | – |
| UCLQ | 2025/26 | 92 | 92 | openfootball: 92 | – | – | – | – |

## Kontroll av lagkoppling

- Lag skapade per källa: {'openfootball': 223, 'seed': 157, 'statsbomb_open': 14}
- Källans lag-ID kopplade till befintliga lag: {'statsbomb_open': 143, 'uefa': 114}
- Lag flaggade för granskning: 68
- Resultatkonflikter mellan källor (samma match, olika 90-minutersresultat): 3

Matcher som bara finns hos en händelsekälla fast OpenFootball täcker säsongen (bör vara 0 om kopplingen fungerar):

- ESP1 2012/13 statsbomb_open: 1
- ESP1 2013/14 statsbomb_open: 1
- ESP1 2016/17 statsbomb_open: 2
- ESP1 2017/18 statsbomb_open: 2
- ESP1 2018/19 statsbomb_open: 4
- ESP1 2019/20 statsbomb_open: 4
- FRA1 2021/22 statsbomb_open: 2
- FRA1 2022/23 statsbomb_open: 1
- GER1 2015/16 statsbomb_open: 4

Lag som skapades av händelsekällor (ej kopplade):

- Albacete (statsbomb_open)
- CD Numancia de Soria (statsbomb_open)
- Charlton Athletic (statsbomb_open)
- Gimnàstic Tarragona (statsbomb_open)
- Hércules (statsbomb_open)
- Metz (statsbomb_open)
- Middlesbrough (statsbomb_open)
- Portsmouth (statsbomb_open)
- Racing Santander (statsbomb_open)
- Real Murcia CF (statsbomb_open)
- Recreativo Huelva (statsbomb_open)
- Strasbourg (statsbomb_open)
- Tenerife (statsbomb_open)
- Xerez (statsbomb_open)

Resultatkonflikter (första 50):

- match 27451: openfootball 3–4 / statsbomb_open 1–1
- match 27701: openfootball 4–1 / statsbomb_open 1–1
- match 27951: openfootball 5–3 / statsbomb_open 1–1
