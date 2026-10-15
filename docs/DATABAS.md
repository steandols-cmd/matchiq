# Databasmodell

SQLite, en fil: `matchiq.sqlite` i datamappen. Genererat från migreringarna i `backend/matchiq/migrations/`.

**Konventioner:** tider i UTC (ISO 8601 med `Z`), saknade värden = `NULL` (aldrig 0), varje observation bär `source_id` och `fetch_id`/`import_id`. `forecast_snapshots` och `reports` är oföränderliga (databastriggers stoppar UPDATE/DELETE).

## Datamapp

| Plattform | Sökväg |
|---|---|
| macOS | `~/Library/Application Support/MatchIQ/data` |
| Windows | `%APPDATA%\MatchIQ\data` |
| Linux | `~/.local/share/matchiq/data` |

Innehåll: `matchiq.sqlite`, `backups/` (automatiskt före varje migrering), `exports/`, `reports/ÅÅÅÅ-MM-DD/TÄVLING/*.pdf`, `raw/` (råfiler per källa, namngivna efter SHA-256), `imports/` (kopior av importerade filer), `logs/`, `crests/`.

## Migrering och export

- Vid start appliceras väntande migreringar (`schema_migrations` håller version, tid, appversion och SHA-256 för varje migreringsfil). En säkerhetskopia tas först.
- **Exportera hela databasen** (Inställningar eller `python -m matchiq.cli export --out fil.zip`) ger en zip med komplett SQLite-fil, en CSV per tabell, `schema.sql` och `manifest.json` (schemaversion, radantal, SHA-256 per fil).
- **Läs in export** (`python -m matchiq.cli import-db --file fil.zip`) verifierar kontrollsummor, säkerhetskopierar aktuell databas, ersätter den och migrerar framåt till appens schemaversion.
- Nya schemaändringar läggs som nästa numrerade fil (`0002_….sql`); äldre filer ändras aldrig.

## Migrering 0001 – initial

### `sources`

| Kolumn / regel | Definition |
|---|---|
| `id` | TEXT PRIMARY KEY |
| `name` | TEXT NOT NULL |
| `owner` | TEXT NOT NULL |
| `url` | TEXT NOT NULL |
| `terms_url` | TEXT |
| `license` | TEXT NOT NULL |
| `attribution` | TEXT |
| `allowed_uses` | TEXT NOT NULL — JSON-lista: display/training/benchmark/evaluation |
| `training_policy` | TEXT NOT NULL CHECK (training_policy IN ('allowed','conditional','unclear','blocked')) |
| `training_approval` | TEXT CHECK (training_approval IN ('approved','revoked')) |
| `training_approval_note` | TEXT |
| `training_approval_at_utc` | TEXT |
| `automated_fetch` | TEXT NOT NULL CHECK (automated_fetch IN ('allowed','api_key','disabled','manual_only')) |
| `enabled` | INTEGER NOT NULL DEFAULT 0 |
| `requires_api_key` | INTEGER NOT NULL DEFAULT 0 |
| `update_frequency` | TEXT |
| `coverage` | TEXT |
| `min_interval_seconds` | REAL NOT NULL DEFAULT 1.0 |
| `daily_quota` | INTEGER |
| `data_kinds` | TEXT |
| `notes` | TEXT |
| `catalog_version` | INTEGER NOT NULL DEFAULT 1 |
| `updated_at_utc` | TEXT NOT NULL |

### `source_audit`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `action` | TEXT NOT NULL |
| `detail` | TEXT |
| `at_utc` | TEXT NOT NULL |

### `fetches`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `job` | TEXT |
| `url` | TEXT NOT NULL |
| `started_at_utc` | TEXT NOT NULL |
| `finished_at_utc` | TEXT |
| `http_status` | INTEGER |
| `sha256` | TEXT |
| `bytes` | INTEGER |
| `parser_status` | TEXT CHECK (parser_status IN ('ok','partial','error','skipped','not_modified','pending')) |
| `rows_imported` | INTEGER NOT NULL DEFAULT 0 |
| `rows_updated` | INTEGER NOT NULL DEFAULT 0 |
| `rows_unchanged` | INTEGER NOT NULL DEFAULT 0 |
| `rows_skipped` | INTEGER NOT NULL DEFAULT 0 |
| `attempt` | INTEGER NOT NULL DEFAULT 1 |
| `error` | TEXT |
| `raw_path` | TEXT |

### `imports`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `file_name` | TEXT NOT NULL |
| `file_sha256` | TEXT NOT NULL |
| `file_bytes` | INTEGER NOT NULL |
| `stored_copy_path` | TEXT |
| `profile` | TEXT NOT NULL |
| `mapping_json` | TEXT |
| `started_at_utc` | TEXT NOT NULL |
| `finished_at_utc` | TEXT |
| `status` | TEXT NOT NULL CHECK (status IN ('preview','running','done','error')) |
| `summary_json` | TEXT |
| `error` | TEXT |

### `competitions`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `code` | TEXT NOT NULL UNIQUE |
| `name` | TEXT NOT NULL |
| `country` | TEXT |
| `kind` | TEXT NOT NULL CHECK (kind IN ('league','international_cup','domestic_cup')) |
| `show_in_tabs` | INTEGER NOT NULL DEFAULT 0 |
| `tab_order` | INTEGER |

### `seasons`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `competition_id` | INTEGER NOT NULL REFERENCES competitions(id) |
| `label` | TEXT NOT NULL |
| `*(regel)*` | UNIQUE (competition_id, label) |

### `teams`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `name` | TEXT NOT NULL |
| `short_name` | TEXT |
| `country` | TEXT |
| `domestic_competition_code` | TEXT |
| `color_primary` | TEXT |
| `color_secondary` | TEXT |
| `crest_path` | TEXT |
| `needs_review` | INTEGER NOT NULL DEFAULT 0 |
| `created_by_source` | TEXT |
| `created_at_utc` | TEXT NOT NULL |

### `team_aliases`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `alias` | TEXT NOT NULL |
| `alias_norm` | TEXT NOT NULL |
| `context` | TEXT NOT NULL DEFAULT '' — '' = global, annars land/tävlingskod |
| `source_id` | TEXT NOT NULL DEFAULT '' — '' = alla källor |
| `origin` | TEXT NOT NULL DEFAULT 'auto' — seed/auto/user |
| `created_at_utc` | TEXT NOT NULL |
| `*(regel)*` | UNIQUE (alias_norm, context, source_id) |

### `team_source_ids`

| Kolumn / regel | Definition |
|---|---|
| `team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `source_id` | TEXT NOT NULL |
| `source_team_id` | TEXT NOT NULL |
| `name_original` | TEXT |
| `*(regel)*` | PRIMARY KEY (source_id, source_team_id) |

### `players`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `name` | TEXT NOT NULL |
| `birth_date` | TEXT |
| `nationality` | TEXT |
| `created_at_utc` | TEXT NOT NULL |

### `player_source_ids`

| Kolumn / regel | Definition |
|---|---|
| `player_id` | INTEGER NOT NULL REFERENCES players(id) |
| `source_id` | TEXT NOT NULL |
| `source_player_id` | TEXT NOT NULL |
| `name_original` | TEXT |
| `*(regel)*` | PRIMARY KEY (source_id, source_player_id) |

### `matches`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `competition_id` | INTEGER NOT NULL REFERENCES competitions(id) |
| `season_id` | INTEGER REFERENCES seasons(id) |
| `stage` | TEXT |
| `round` | TEXT |
| `matchday` | TEXT |
| `kickoff_utc` | TEXT NOT NULL |
| `kickoff_time_known` | INTEGER NOT NULL DEFAULT 1 |
| `local_date` | TEXT NOT NULL — datum i Europe/Stockholm (dedupliceringsnyckel) |
| `home_team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `away_team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `venue` | TEXT |
| `status` | TEXT NOT NULL CHECK (status IN ('scheduled','live','finished','postponed','cancelled','awarded','unknown')) |
| `official_match_id` | TEXT |
| `natural_key` | TEXT NOT NULL UNIQUE |
| `created_at_utc` | TEXT NOT NULL |
| `updated_at_utc` | TEXT NOT NULL |
| `*(regel)*` | CHECK (home_team_id <> away_team_id) |

### `match_source_ids`

| Kolumn / regel | Definition |
|---|---|
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `source_id` | TEXT NOT NULL |
| `source_match_id` | TEXT NOT NULL |
| `*(regel)*` | PRIMARY KEY (source_id, source_match_id) |

### `match_results`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `fetch_id` | INTEGER REFERENCES fetches(id) |
| `import_id` | INTEGER REFERENCES imports(id) |
| `home_goals_90` | INTEGER |
| `away_goals_90` | INTEGER |
| `home_goals_aet` | INTEGER — ställning efter förlängning (NULL om ingen förlängning) |
| `away_goals_aet` | INTEGER |
| `home_pens` | INTEGER |
| `away_pens` | INTEGER |
| `decided_by` | TEXT CHECK (decided_by IN ('regular','extra_time','penalties','unknown')) |
| `home_goals_ht` | INTEGER |
| `away_goals_ht` | INTEGER |
| `original_home_name` | TEXT |
| `original_away_name` | TEXT |
| `available_at_utc` | TEXT NOT NULL — när resultatet tidigast var känt |
| `observed_at_utc` | TEXT NOT NULL — när vi hämtade/importerade det |
| `*(regel)*` | UNIQUE (match_id, source_id) |

### `team_match_stats`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `is_home` | INTEGER NOT NULL |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `fetch_id` | INTEGER REFERENCES fetches(id) |
| `import_id` | INTEGER REFERENCES imports(id) |
| `shots` | INTEGER |
| `shots_on_target` | INTEGER |
| `corners` | INTEGER |
| `fouls` | INTEGER |
| `yellow_cards` | INTEGER |
| `red_cards` | INTEGER |
| `offsides` | INTEGER |
| `saves` | INTEGER |
| `possession` | REAL |
| `passes` | INTEGER |
| `xg` | REAL |
| `available_at_utc` | TEXT NOT NULL |
| `observed_at_utc` | TEXT NOT NULL |
| `*(regel)*` | UNIQUE (match_id, team_id, source_id) |

### `player_match_stats`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `player_id` | INTEGER NOT NULL REFERENCES players(id) |
| `team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `fetch_id` | INTEGER REFERENCES fetches(id) |
| `import_id` | INTEGER REFERENCES imports(id) |
| `started` | INTEGER |
| `minutes` | REAL |
| `minutes_estimated` | INTEGER NOT NULL DEFAULT 0 |
| `goals` | INTEGER |
| `assists` | INTEGER |
| `shots` | INTEGER |
| `shots_on_target` | INTEGER |
| `xg` | REAL |
| `passes` | INTEGER |
| `key_passes` | INTEGER |
| `tackles` | INTEGER |
| `interceptions` | INTEGER |
| `fouls` | INTEGER |
| `yellow_cards` | INTEGER |
| `red_cards` | INTEGER |
| `available_at_utc` | TEXT NOT NULL |
| `observed_at_utc` | TEXT NOT NULL |
| `*(regel)*` | UNIQUE (match_id, player_id, source_id) |

### `lineups`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `status` | TEXT NOT NULL CHECK (status IN ('confirmed','expected')) |
| `formation` | TEXT |
| `source_url` | TEXT |
| `published_at_utc` | TEXT — källans publiceringstid om känd |
| `fetched_at_utc` | TEXT NOT NULL — när vi faktiskt såg elvan |
| `fetch_id` | INTEGER REFERENCES fetches(id) |
| `import_id` | INTEGER REFERENCES imports(id) |
| `content_hash` | TEXT NOT NULL |
| `*(regel)*` | UNIQUE (match_id, team_id, source_id, status, content_hash) |

### `lineup_players`

| Kolumn / regel | Definition |
|---|---|
| `lineup_id` | INTEGER NOT NULL REFERENCES lineups(id) |
| `slot` | INTEGER NOT NULL |
| `player_id` | INTEGER REFERENCES players(id) |
| `name_original` | TEXT NOT NULL |
| `shirt_number` | INTEGER |
| `position` | TEXT |
| `is_starter` | INTEGER NOT NULL DEFAULT 1 |
| `*(regel)*` | PRIMARY KEY (lineup_id, slot) |

### `availability`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER REFERENCES matches(id) |
| `team_id` | INTEGER NOT NULL REFERENCES teams(id) |
| `player_id` | INTEGER REFERENCES players(id) |
| `player_name` | TEXT NOT NULL |
| `kind` | TEXT NOT NULL CHECK (kind IN ('injury','suspension','doubtful','other')) |
| `reason` | TEXT |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `published_at_utc` | TEXT |
| `fetched_at_utc` | TEXT NOT NULL |
| `*(regel)*` | UNIQUE (match_id, team_id, player_name, kind, source_id) |

### `market_odds`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `source_id` | TEXT NOT NULL REFERENCES sources(id) |
| `bookmaker` | TEXT NOT NULL |
| `market` | TEXT NOT NULL DEFAULT '1x2' |
| `kind` | TEXT NOT NULL CHECK (kind IN ('opening','closing','snapshot')) |
| `odds_home` | REAL, odds_draw REAL, odds_away REAL |
| `published_at_utc` | TEXT |
| `fetched_at_utc` | TEXT NOT NULL |
| `*(regel)*` | UNIQUE (match_id, source_id, bookmaker, market, kind, fetched_at_utc) |

### `model_versions`

| Kolumn / regel | Definition |
|---|---|
| `id` | TEXT PRIMARY KEY |
| `family` | TEXT NOT NULL CHECK (family IN ('V2','V3','BASE','LEGACY')) |
| `version` | TEXT NOT NULL |
| `description` | TEXT NOT NULL |
| `params_json` | TEXT NOT NULL |
| `code_fingerprint` | TEXT |
| `status` | TEXT NOT NULL CHECK (status IN ('baslinje','experimentell','kandidat','produktion','arkiverad')) |
| `status_reason` | TEXT |
| `gate_report_json` | TEXT |
| `created_at_utc` | TEXT NOT NULL |
| `status_changed_at_utc` | TEXT NOT NULL |

### `model_status_history`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `model_version_id` | TEXT NOT NULL REFERENCES model_versions(id) |
| `old_status` | TEXT, new_status TEXT NOT NULL, reason TEXT, at_utc TEXT NOT NULL |

### `forecast_snapshots`

| Kolumn / regel | Definition |
|---|---|
| `id` | TEXT PRIMARY KEY |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `model_version_id` | TEXT NOT NULL REFERENCES model_versions(id) |
| `model_family` | TEXT NOT NULL |
| `kind` | TEXT NOT NULL CHECK (kind IN ('T-30','late','manual','legacy','test')) |
| `scheduled_for_utc` | TEXT |
| `created_at_utc` | TEXT NOT NULL |
| `data_cutoff_utc` | TEXT NOT NULL |
| `kickoff_utc_at_creation` | TEXT NOT NULL |
| `minutes_before_kickoff` | REAL NOT NULL |
| `is_late` | INTEGER NOT NULL DEFAULT 0 |
| `prematch_eligible` | INTEGER NOT NULL |
| `clock` | TEXT NOT NULL DEFAULT 'system' |
| `created_by` | TEXT NOT NULL |
| `report_job_id` | INTEGER |
| `p_home` | REAL, p_draw REAL, p_away REAL |
| `goals_home` | REAL, goals_away REAL |
| `corners_home` | REAL, corners_away REAL |
| `shots_home` | REAL, shots_away REAL |
| `sot_home` | REAL, sot_away REAL |
| `payload_json` | TEXT NOT NULL |
| `inputs_hash` | TEXT NOT NULL |
| `*(regel)*` | CHECK ((p_home IS NULL AND p_draw IS NULL AND p_away IS NULL) |
| `OR` | (abs(p_home + p_draw + p_away - 1.0) < 1e-9)) |

### `report_jobs`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `kind` | TEXT NOT NULL DEFAULT 'T-30' |
| `due_at_utc` | TEXT NOT NULL |
| `kickoff_utc` | TEXT NOT NULL |
| `status` | TEXT NOT NULL CHECK (status IN ('pending','running','done','missed','late_done','failed','cancelled','superseded')) |
| `created_at_utc` | TEXT NOT NULL |
| `started_at_utc` | TEXT |
| `completed_at_utc` | TEXT |
| `attempts` | INTEGER NOT NULL DEFAULT 0 |
| `last_error` | TEXT |
| `report_id` | INTEGER |
| `late_by_seconds` | INTEGER |
| `*(regel)*` | UNIQUE (match_id, kind, due_at_utc) |

### `reports`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `job_id` | INTEGER REFERENCES report_jobs(id) |
| `kind` | TEXT NOT NULL CHECK (kind IN ('T-30','late','manual','test')) |
| `is_late` | INTEGER NOT NULL DEFAULT 0 |
| `created_at_utc` | TEXT NOT NULL |
| `data_cutoff_utc` | TEXT NOT NULL |
| `path` | TEXT NOT NULL |
| `sha256` | TEXT NOT NULL |
| `bytes` | INTEGER NOT NULL |
| `snapshot_ids_json` | TEXT NOT NULL |

### `match_outcomes`

| Kolumn / regel | Definition |
|---|---|
| `match_id` | INTEGER PRIMARY KEY REFERENCES matches(id) |
| `home_goals` | INTEGER, away_goals INTEGER — 90 minuter |
| `home_corners` | INTEGER, away_corners INTEGER |
| `home_shots` | INTEGER, away_shots INTEGER |
| `home_sot` | INTEGER, away_sot INTEGER |
| `source_id` | TEXT REFERENCES sources(id) |
| `entered_by` | TEXT NOT NULL CHECK (entered_by IN ('auto','manual','import')) |
| `recorded_at_utc` | TEXT NOT NULL |
| `note` | TEXT |

### `backtest_runs`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `model_version_id` | TEXT NOT NULL REFERENCES model_versions(id) |
| `created_at_utc` | TEXT NOT NULL |
| `config_json` | TEXT NOT NULL |
| `summary_json` | TEXT NOT NULL |

### `backtest_predictions`

| Kolumn / regel | Definition |
|---|---|
| `run_id` | INTEGER NOT NULL REFERENCES backtest_runs(id) |
| `match_id` | INTEGER NOT NULL REFERENCES matches(id) |
| `split` | TEXT NOT NULL CHECK (split IN ('train','validation','test')) |
| `season` | TEXT NOT NULL |
| `competition_code` | TEXT NOT NULL |
| `cutoff_utc` | TEXT NOT NULL |
| `p_home` | REAL, p_draw REAL, p_away REAL |
| `outcome` | TEXT |
| `preds_json` | TEXT NOT NULL |
| `actuals_json` | TEXT NOT NULL |
| `*(regel)*` | PRIMARY KEY (run_id, match_id) |

### `notifications`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `created_at_utc` | TEXT NOT NULL |
| `level` | TEXT NOT NULL CHECK (level IN ('info','success','warning','error')) |
| `title` | TEXT NOT NULL |
| `body` | TEXT |
| `match_id` | INTEGER |
| `report_id` | INTEGER |
| `read` | INTEGER NOT NULL DEFAULT 0 |
| `delivered_os` | INTEGER NOT NULL DEFAULT 0 |

### `change_log`

| Kolumn / regel | Definition |
|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT |
| `at_utc` | TEXT NOT NULL |
| `entity` | TEXT NOT NULL |
| `entity_id` | TEXT NOT NULL |
| `field` | TEXT |
| `old_value` | TEXT |
| `new_value` | TEXT |
| `source_id` | TEXT |
| `fetch_id` | INTEGER |
| `import_id` | INTEGER |
| `actor` | TEXT NOT NULL DEFAULT 'system' |

### `settings`

| Kolumn / regel | Definition |
|---|---|
| `key` | TEXT PRIMARY KEY |
| `value_json` | TEXT NOT NULL |
| `updated_at_utc` | TEXT NOT NULL |

### `sync_state`

| Kolumn / regel | Definition |
|---|---|
| `source_id` | TEXT NOT NULL |
| `job` | TEXT NOT NULL |
| `scope` | TEXT NOT NULL DEFAULT '' |
| `last_run_utc` | TEXT |
| `next_run_utc` | TEXT |
| `last_status` | TEXT |
| `last_error` | TEXT |
| `etag` | TEXT |
| `last_modified` | TEXT |
| `calls_today` | INTEGER NOT NULL DEFAULT 0 |
| `calls_day` | TEXT |
| `*(regel)*` | PRIMARY KEY (source_id, job, scope) |

**Triggers:** `forecast_snapshots_immutable_update`, `forecast_snapshots_immutable_delete`, `reports_immutable_update`, `reports_immutable_delete`

