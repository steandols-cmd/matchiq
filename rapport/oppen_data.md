# Hämtad data – oppen_data (2026-10-15T12:51:19Z)

Siffrorna är räknade ur databasen som byggdes av appens egna källadaptrar i GitHub Actions.

## Körning per källa

| Källa | Status | Tid (s) | Resultat |
|---|---|---|---|
| openfootball | ok | 202 | {"files_in_scope": 96, "inserted": 30225, "updated": 0, "unchanged": 0, "skipped": 0, "files_imported": 96} |
| wyscout_public | ok | 46 | {"matches_in_source": 1826, "teams_linked_ENG1": 20, "teams_unlinked": 0, "link_conflicts": 0, "teams_linked_FRA1": 20, "teams_linked_GER1": 18, "teams_linked_ITA1": 20, "teams_linked_ESP1": 20, "match_unchanged": 1803, "match_updated": 23, "teamstats_inserted": 3652, "lineups": 3652} |

Händelsetyper i wyscout_public (topp 40):

- Pass / Simple pass: 1207448
- Duel / Ground attacking duel: 265456
- Duel / Ground defending duel: 264552
- Others on the ball / Touch: 165296
- Duel / Air duel: 158186
- Duel / Ground loose ball duel: 143861
- Interruption / Ball out of the field: 129179
- Pass / High pass: 123214
- Pass / Head pass: 91194
- Free Kick / Throw in: 80305
- Pass / Cross: 58634
- Others on the ball / Clearance: 53165
- Foul / Foul: 44293
- Free Kick / Free Kick: 43544
- Pass / Launch: 43303
- Shot / Shot: 40461
- Free Kick / Goal kick: 29725
- Pass / Smart pass: 28428
- Others on the ball / Acceleration: 24376
- Free Kick / Corner: 18181
- Pass / Hand pass: 13135
- Save attempt / Reflexes: 10192
- Free Kick / Free kick cross: 8134
- Offside / : 7821
- Save attempt / Save attempt: 6375
- Goalkeeper leaving line / Goalkeeper leaving line: 5779
- Free Kick / Free kick shot: 2038
- Foul / Hand foul: 1941
- Interruption / Whistle: 917
- Foul / Protest: 561
- Free Kick / Penalty: 541
- Foul / Out of game foul: 473
- Foul / Late card foul: 300
- Foul / Time lost foul: 205
- Foul / Simulation: 108
- Foul / Violent Foul: 74

## Driftstatus per tävling och mått

Fönster: 450 dagar. Operativ = minst 100 matcher med värde från en källa som får användas för träning.

| Tävling | Mått | Status | Matcher i fönstret | Totalt (tillåtet) | Senaste | Källor |
|---|---|---|---|---|---|---|
| UCL | Mål / 1X2 | operativ | 188 | 1985 | 2026-05-06 | OpenFootball (football.json, champions-league, europe m.fl.): 1985 |
| UCL | Hörnor | saknas | 0 | 0 | – | – |
| UCL | Skott | saknas | 0 | 0 | – | – |
| UCL | Skott på mål | saknas | 0 | 0 | – | – |
| SWE1 | Mål / 1X2 | inaktuell | 0 | 533 | 2025-05-04 | OpenFootball (football.json, champions-league, europe m.fl.): 533 |
| SWE1 | Hörnor | saknas | 0 | 0 | – | – |
| SWE1 | Skott | saknas | 0 | 0 | – | – |
| SWE1 | Skott på mål | saknas | 0 | 0 | – | – |
| ENG1 | Mål / 1X2 | operativ | 398 | 6098 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 6098, Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ENG1 | Hörnor | inaktuell | 0 | 380 | 2018-05-13 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ENG1 | Skott | inaktuell | 0 | 380 | 2018-05-13 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ENG1 | Skott på mål | inaktuell | 0 | 380 | 2018-05-13 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ESP1 | Mål / 1X2 | operativ | 429 | 5359 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 5359, Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ESP1 | Hörnor | inaktuell | 0 | 380 | 2018-05-20 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ESP1 | Skott | inaktuell | 0 | 380 | 2018-05-20 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ESP1 | Skott på mål | inaktuell | 0 | 380 | 2018-05-20 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| GER1 | Mål / 1X2 | operativ | 327 | 4917 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 4917, Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 306 |
| GER1 | Hörnor | inaktuell | 0 | 306 | 2018-05-12 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 306 |
| GER1 | Skott | inaktuell | 0 | 306 | 2018-05-12 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 306 |
| GER1 | Skott på mål | inaktuell | 0 | 306 | 2018-05-12 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 306 |
| ITA1 | Mål / 1X2 | operativ | 394 | 4944 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 4944, Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ITA1 | Hörnor | inaktuell | 0 | 380 | 2018-05-20 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ITA1 | Skott | inaktuell | 0 | 380 | 2018-05-20 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| ITA1 | Skott på mål | inaktuell | 0 | 380 | 2018-05-20 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| FRA1 | Mål / 1X2 | operativ | 323 | 4254 | 2026-09-20 | OpenFootball (football.json, champions-league, europe m.fl.): 4254, Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| FRA1 | Hörnor | inaktuell | 0 | 380 | 2018-05-19 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| FRA1 | Skott | inaktuell | 0 | 380 | 2018-05-19 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |
| FRA1 | Skott på mål | inaktuell | 0 | 380 | 2018-05-19 | Wyscout öppna händelsedata (Pappalardo m.fl. 2019, figshare): 380 |

## Täckning per tävling och säsong

| Tävling | Säsong | Matcher | Spelade | Resultat (källa: n) | Hörnor | Skott | Skott på mål | Spelarrader |
|---|---|---|---|---|---|---|---|---|
| ENG1 | 2010/11 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2011/12 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2012/13 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2013/14 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2014/15 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2015/16 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2016/17 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2017/18 | 380 | 380 | openfootball: 380, wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 515 spelare/380 matcher |
| ENG1 | 2018/19 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2019/20 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2020/21 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2021/22 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2022/23 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2023/24 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2024/25 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ENG1 | 2025/26 | 380 | 353 | openfootball: 353 | – | – | – | – |
| ENG1 | 2026/27 | 380 | 45 | openfootball: 45 | – | – | – | – |
| ESP1 | 2012/13 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2013/14 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2014/15 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2015/16 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2016/17 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2017/18 | 380 | 380 | openfootball: 380, wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 557 spelare/380 matcher |
| ESP1 | 2018/19 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2019/20 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2020/21 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2021/22 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2022/23 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2023/24 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ESP1 | 2024/25 | 380 | 370 | openfootball: 370 | – | – | – | – |
| ESP1 | 2025/26 | 380 | 365 | openfootball: 365 | – | – | – | – |
| ESP1 | 2026/27 | 380 | 64 | openfootball: 64 | – | – | – | – |
| FRA1 | 2014/15 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2015/16 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2016/17 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2017/18 | 380 | 380 | openfootball: 380, wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 542 spelare/380 matcher |
| FRA1 | 2018/19 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2019/20 | 380 | 279 | openfootball: 279 | – | – | – | – |
| FRA1 | 2020/21 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2021/22 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2022/23 | 380 | 380 | openfootball: 380 | – | – | – | – |
| FRA1 | 2023/24 | 306 | 306 | openfootball: 306 | – | – | – | – |
| FRA1 | 2024/25 | 306 | 306 | openfootball: 306 | – | – | – | – |
| FRA1 | 2025/26 | 306 | 282 | openfootball: 282 | – | – | – | – |
| FRA1 | 2026/27 | 306 | 41 | openfootball: 41 | – | – | – | – |
| GER1 | 2010/11 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2011/12 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2012/13 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2013/14 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2014/15 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2015/16 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2016/17 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2017/18 | 306 | 306 | openfootball: 306, wyscout_public: 306 | wyscout_public: 306 | wyscout_public: 306 | wyscout_public: 306 | wyscout_public: 472 spelare/306 matcher |
| GER1 | 2018/19 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2019/20 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2020/21 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2021/22 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2022/23 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2023/24 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2024/25 | 306 | 306 | openfootball: 306 | – | – | – | – |
| GER1 | 2025/26 | 306 | 294 | openfootball: 294 | – | – | – | – |
| GER1 | 2026/27 | 306 | 33 | openfootball: 33 | – | – | – | – |
| ITA1 | 2013/14 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2014/15 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2015/16 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2016/17 | 380 | 380 | openfootball: 380 | – | – | – | – |
| ITA1 | 2017/18 | 380 | 380 | openfootball: 380, wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 380 | wyscout_public: 534 spelare/380 matcher |
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
| UCL | 2011/12 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2012/13 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2013/14 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2014/15 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2015/16 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2016/17 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2017/18 | 125 | 125 | openfootball: 125 | – | – | – | – |
| UCL | 2018/19 | 125 | 125 | openfootball: 125 | – | – | – | – |
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

- Lag skapade per källa: {'openfootball': 223, 'seed': 157}
- Källans lag-ID kopplade till befintliga lag: {'uefa': 114, 'wyscout_public': 98}
- Lag flaggade för granskning: 64
- Resultatkonflikter mellan källor (samma match, olika 90-minutersresultat): 0

Matcher som bara finns hos en händelsekälla fast OpenFootball täcker säsongen (bör vara 0 om kopplingen fungerar):

- inga

Lag som skapades av händelsekällor (ej kopplade):

- inga

## Walk-forward per tävling (V3-parametrar valda på Champions League)

| Tävling | Säsong | Modell | n 1X2 | Brier | Log loss | Hörnor MAE / täckn. 80 % (n) | Skott MAE / täckn. (n) | Skott på mål MAE / täckn. (n) |
|---|---|---|---|---|---|---|---|---|
| ENG1 | 2017/18 | V2 | 380 | 0,587 | 0,984 | 2,19 / 78 % (720) | 3,36 / 78 % (720) | 1,74 / 85 % (720) |
| ENG1 | 2017/18 | V3 | 380 | 0,569 | 0,960 | 2,19 / 80 % (720) | 3,26 / 82 % (720) | 1,70 / 85 % (720) |
| ENG1 | 2017/18 | BASE | 380 | 0,644 | 1,067 | 2,32 / 74 % (720) | 4,22 / 64 % (720) | 1,97 / 80 % (720) |
| ENG1 | 2023/24 | V2 | 380 | 0,567 | 0,961 | – | – | – |
| ENG1 | 2023/24 | V3 | 380 | 0,546 | 0,928 | – | – | – |
| ENG1 | 2023/24 | BASE | 380 | 0,638 | 1,055 | – | – | – |
| ENG1 | 2024/25 | V2 | 380 | 0,598 | 0,999 | – | – | – |
| ENG1 | 2024/25 | V3 | 380 | 0,592 | 0,991 | – | – | – |
| ENG1 | 2024/25 | BASE | 380 | 0,656 | 1,082 | – | – | – |
| ENG1 | 2025/26 | V2 | 353 | 0,607 | 1,015 | – | – | – |
| ENG1 | 2025/26 | V3 | 353 | 0,596 | 0,998 | – | – | – |
| ENG1 | 2025/26 | BASE | 353 | 0,638 | 1,056 | – | – | – |
| ESP1 | 2017/18 | V2 | 380 | 0,585 | 0,981 | 1,97 / 82 % (720) | 2,94 / 80 % (720) | 1,72 / 85 % (720) |
| ESP1 | 2017/18 | V3 | 380 | 0,578 | 0,971 | 1,97 / 84 % (720) | 2,91 / 80 % (720) | 1,71 / 85 % (720) |
| ESP1 | 2017/18 | BASE | 380 | 0,636 | 1,053 | 2,04 / 81 % (720) | 3,28 / 75 % (720) | 1,89 / 82 % (720) |
| ESP1 | 2023/24 | V2 | 380 | 0,593 | 0,993 | – | – | – |
| ESP1 | 2023/24 | V3 | 380 | 0,574 | 0,966 | – | – | – |
| ESP1 | 2023/24 | BASE | 380 | 0,651 | 1,077 | – | – | – |
| ESP1 | 2024/25 | V2 | 370 | 0,588 | 0,988 | – | – | – |
| ESP1 | 2024/25 | V3 | 370 | 0,579 | 0,976 | – | – | – |
| ESP1 | 2024/25 | BASE | 370 | 0,647 | 1,070 | – | – | – |
| ESP1 | 2025/26 | V2 | 365 | 0,584 | 0,985 | – | – | – |
| ESP1 | 2025/26 | V3 | 365 | 0,571 | 0,966 | – | – | – |
| ESP1 | 2025/26 | BASE | 365 | 0,622 | 1,035 | – | – | – |
| GER1 | 2017/18 | V2 | 306 | 0,622 | 1,036 | 1,98 / 80 % (562) | 3,21 / 78 % (562) | 1,82 / 86 % (562) |
| GER1 | 2017/18 | V3 | 306 | 0,607 | 1,016 | 1,98 / 82 % (562) | 3,19 / 81 % (562) | 1,79 / 86 % (562) |
| GER1 | 2017/18 | BASE | 306 | 0,647 | 1,071 | 2,03 / 80 % (562) | 3,49 / 73 % (562) | 1,86 / 85 % (562) |
| GER1 | 2023/24 | V2 | 306 | 0,584 | 0,981 | – | – | – |
| GER1 | 2023/24 | V3 | 306 | 0,587 | 0,985 | – | – | – |
| GER1 | 2023/24 | BASE | 306 | 0,651 | 1,076 | – | – | – |
| GER1 | 2024/25 | V2 | 306 | 0,636 | 1,055 | – | – | – |
| GER1 | 2024/25 | V3 | 306 | 0,612 | 1,022 | – | – | – |
| GER1 | 2024/25 | BASE | 306 | 0,664 | 1,093 | – | – | – |
| GER1 | 2025/26 | V2 | 294 | 0,573 | 0,971 | – | – | – |
| GER1 | 2025/26 | V3 | 294 | 0,564 | 0,956 | – | – | – |
| GER1 | 2025/26 | BASE | 294 | 0,639 | 1,057 | – | – | – |
| ITA1 | 2017/18 | V2 | 380 | 0,561 | 0,949 | 2,16 / 80 % (720) | 3,43 / 76 % (720) | 1,88 / 83 % (720) |
| ITA1 | 2017/18 | V3 | 380 | 0,539 | 0,917 | 2,13 / 81 % (720) | 3,39 / 78 % (720) | 1,84 / 85 % (720) |
| ITA1 | 2017/18 | BASE | 380 | 0,648 | 1,070 | 2,31 / 77 % (720) | 4,24 / 65 % (720) | 2,13 / 77 % (720) |
| ITA1 | 2023/24 | V2 | 380 | 0,598 | 1,001 | – | – | – |
| ITA1 | 2023/24 | V3 | 380 | 0,590 | 0,989 | – | – | – |
| ITA1 | 2023/24 | BASE | 380 | 0,659 | 1,088 | – | – | – |
| ITA1 | 2024/25 | V2 | 370 | 0,598 | 0,998 | – | – | – |
| ITA1 | 2024/25 | V3 | 370 | 0,582 | 0,974 | – | – | – |
| ITA1 | 2024/25 | BASE | 370 | 0,662 | 1,091 | – | – | – |
| ITA1 | 2025/26 | V2 | 344 | 0,584 | 0,982 | – | – | – |
| ITA1 | 2025/26 | V3 | 344 | 0,567 | 0,958 | – | – | – |
| ITA1 | 2025/26 | BASE | 344 | 0,642 | 1,060 | – | – | – |
| FRA1 | 2017/18 | V2 | 380 | 0,587 | 0,987 | 2,17 / 78 % (720) | 3,40 / 76 % (720) | 1,80 / 85 % (720) |
| FRA1 | 2017/18 | V3 | 380 | 0,575 | 0,968 | 2,18 / 82 % (720) | 3,37 / 79 % (720) | 1,77 / 84 % (720) |
| FRA1 | 2017/18 | BASE | 380 | 0,644 | 1,066 | 2,17 / 76 % (720) | 3,59 / 72 % (720) | 1,88 / 84 % (720) |
| FRA1 | 2023/24 | V2 | 306 | 0,646 | 1,069 | – | – | – |
| FRA1 | 2023/24 | V3 | 306 | 0,623 | 1,035 | – | – | – |
| FRA1 | 2023/24 | BASE | 306 | 0,662 | 1,092 | – | – | – |
| FRA1 | 2024/25 | V2 | 306 | 0,578 | 0,974 | – | – | – |
| FRA1 | 2024/25 | V3 | 306 | 0,575 | 0,969 | – | – | – |
| FRA1 | 2024/25 | BASE | 306 | 0,636 | 1,053 | – | – | – |
| FRA1 | 2025/26 | V2 | 282 | 0,578 | 0,972 | – | – | – |
| FRA1 | 2025/26 | V3 | 282 | 0,570 | 0,960 | – | – | – |
| FRA1 | 2025/26 | BASE | 282 | 0,624 | 1,036 | – | – | – |
| SWE1 | 2023 | V2 | 218 | 0,601 | 1,006 | – | – | – |
| SWE1 | 2023 | V3 | 218 | 0,602 | 1,009 | – | – | – |
| SWE1 | 2023 | BASE | 218 | 0,639 | 1,056 | – | – | – |
| SWE1 | 2024 | V2 | 240 | 0,636 | 1,053 | – | – | – |
| SWE1 | 2024 | V3 | 240 | 0,626 | 1,039 | – | – | – |
| SWE1 | 2024 | BASE | 240 | 0,640 | 1,059 | – | – | – |
| SWE1 | 2025 | V2 | 53 | 0,577 | 0,968 | – | – | – |
| SWE1 | 2025 | V3 | 53 | 0,591 | 0,988 | – | – | – |
| SWE1 | 2025 | BASE | 53 | 0,642 | 1,059 | – | – | – |
