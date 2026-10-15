-- MatchIQ – grundschema (migrering 0001)
-- Konventioner:
--   * Alla tider lagras som ISO 8601 UTC-strängar ("2026-10-20T16:45:00Z").
--   * Saknade värden lagras som NULL – aldrig som 0.
--   * Varje observation bär källa (source_id) och, när den kommer från nätet, hämtning (fetch_id).
--   * Prognossnapshots och arkiverade rapporter är oföränderliga (triggers nedan).

-- ---------------------------------------------------------------- Källor
CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  url TEXT NOT NULL,
  terms_url TEXT,
  license TEXT NOT NULL,
  attribution TEXT,
  allowed_uses TEXT NOT NULL,                 -- JSON-lista: display/training/benchmark/evaluation
  training_policy TEXT NOT NULL CHECK (training_policy IN ('allowed','conditional','unclear','blocked')),
  training_approval TEXT CHECK (training_approval IN ('approved','revoked')),
  training_approval_note TEXT,
  training_approval_at_utc TEXT,
  automated_fetch TEXT NOT NULL CHECK (automated_fetch IN ('allowed','api_key','disabled','manual_only')),
  enabled INTEGER NOT NULL DEFAULT 0,
  requires_api_key INTEGER NOT NULL DEFAULT 0,
  update_frequency TEXT,
  coverage TEXT,
  min_interval_seconds REAL NOT NULL DEFAULT 1.0,
  daily_quota INTEGER,
  data_kinds TEXT,
  notes TEXT,
  catalog_version INTEGER NOT NULL DEFAULT 1,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE source_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL REFERENCES sources(id),
  action TEXT NOT NULL,
  detail TEXT,
  at_utc TEXT NOT NULL
);

CREATE TABLE fetches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL REFERENCES sources(id),
  job TEXT,
  url TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  http_status INTEGER,
  sha256 TEXT,
  bytes INTEGER,
  parser_status TEXT CHECK (parser_status IN ('ok','partial','error','skipped','not_modified','pending')),
  rows_imported INTEGER NOT NULL DEFAULT 0,
  rows_updated INTEGER NOT NULL DEFAULT 0,
  rows_unchanged INTEGER NOT NULL DEFAULT 0,
  rows_skipped INTEGER NOT NULL DEFAULT 0,
  attempt INTEGER NOT NULL DEFAULT 1,
  error TEXT,
  raw_path TEXT
);
CREATE INDEX idx_fetches_source ON fetches(source_id, started_at_utc);

CREATE TABLE imports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_name TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,
  file_bytes INTEGER NOT NULL,
  stored_copy_path TEXT,
  profile TEXT NOT NULL,
  mapping_json TEXT,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  status TEXT NOT NULL CHECK (status IN ('preview','running','done','error')),
  summary_json TEXT,
  error TEXT
);

-- ---------------------------------------------------------------- Tävlingar, lag, spelare
CREATE TABLE competitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  country TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('league','international_cup','domestic_cup')),
  show_in_tabs INTEGER NOT NULL DEFAULT 0,
  tab_order INTEGER
);

CREATE TABLE seasons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  competition_id INTEGER NOT NULL REFERENCES competitions(id),
  label TEXT NOT NULL,
  UNIQUE (competition_id, label)
);

CREATE TABLE teams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  short_name TEXT,
  country TEXT,
  domestic_competition_code TEXT,
  color_primary TEXT,
  color_secondary TEXT,
  crest_path TEXT,
  needs_review INTEGER NOT NULL DEFAULT 0,
  created_by_source TEXT,
  created_at_utc TEXT NOT NULL
);

CREATE TABLE team_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id INTEGER NOT NULL REFERENCES teams(id),
  alias TEXT NOT NULL,
  alias_norm TEXT NOT NULL,
  context TEXT NOT NULL DEFAULT '',            -- '' = global, annars land/tävlingskod
  source_id TEXT NOT NULL DEFAULT '',          -- '' = alla källor
  origin TEXT NOT NULL DEFAULT 'auto',         -- seed/auto/user
  created_at_utc TEXT NOT NULL,
  UNIQUE (alias_norm, context, source_id)
);
CREATE INDEX idx_alias_team ON team_aliases(team_id);

CREATE TABLE team_source_ids (
  team_id INTEGER NOT NULL REFERENCES teams(id),
  source_id TEXT NOT NULL,
  source_team_id TEXT NOT NULL,
  name_original TEXT,
  PRIMARY KEY (source_id, source_team_id)
);

CREATE TABLE players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  birth_date TEXT,
  nationality TEXT,
  created_at_utc TEXT NOT NULL
);

CREATE TABLE player_source_ids (
  player_id INTEGER NOT NULL REFERENCES players(id),
  source_id TEXT NOT NULL,
  source_player_id TEXT NOT NULL,
  name_original TEXT,
  PRIMARY KEY (source_id, source_player_id)
);

-- ---------------------------------------------------------------- Matcher och observationer
CREATE TABLE matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  competition_id INTEGER NOT NULL REFERENCES competitions(id),
  season_id INTEGER REFERENCES seasons(id),
  stage TEXT,
  round TEXT,
  matchday TEXT,
  kickoff_utc TEXT NOT NULL,
  kickoff_time_known INTEGER NOT NULL DEFAULT 1,
  local_date TEXT NOT NULL,                      -- datum i Europe/Stockholm (dedupliceringsnyckel)
  home_team_id INTEGER NOT NULL REFERENCES teams(id),
  away_team_id INTEGER NOT NULL REFERENCES teams(id),
  venue TEXT,
  status TEXT NOT NULL CHECK (status IN ('scheduled','live','finished','postponed','cancelled','awarded','unknown')),
  official_match_id TEXT,
  natural_key TEXT NOT NULL UNIQUE,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  CHECK (home_team_id <> away_team_id)
);
CREATE INDEX idx_matches_kickoff ON matches(kickoff_utc);
CREATE INDEX idx_matches_comp ON matches(competition_id, kickoff_utc);
CREATE INDEX idx_matches_home ON matches(home_team_id, kickoff_utc);
CREATE INDEX idx_matches_away ON matches(away_team_id, kickoff_utc);
CREATE UNIQUE INDEX idx_matches_official ON matches(official_match_id) WHERE official_match_id IS NOT NULL;

CREATE TABLE match_source_ids (
  match_id INTEGER NOT NULL REFERENCES matches(id),
  source_id TEXT NOT NULL,
  source_match_id TEXT NOT NULL,
  PRIMARY KEY (source_id, source_match_id)
);
CREATE INDEX idx_msid_match ON match_source_ids(match_id);

CREATE TABLE match_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  fetch_id INTEGER REFERENCES fetches(id),
  import_id INTEGER REFERENCES imports(id),
  home_goals_90 INTEGER,
  away_goals_90 INTEGER,
  home_goals_aet INTEGER,                        -- ställning efter förlängning (NULL om ingen förlängning)
  away_goals_aet INTEGER,
  home_pens INTEGER,
  away_pens INTEGER,
  decided_by TEXT CHECK (decided_by IN ('regular','extra_time','penalties','unknown')),
  home_goals_ht INTEGER,
  away_goals_ht INTEGER,
  original_home_name TEXT,
  original_away_name TEXT,
  available_at_utc TEXT NOT NULL,                -- när resultatet tidigast var känt
  observed_at_utc TEXT NOT NULL,                 -- när vi hämtade/importerade det
  UNIQUE (match_id, source_id)
);

CREATE TABLE team_match_stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  team_id INTEGER NOT NULL REFERENCES teams(id),
  is_home INTEGER NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  fetch_id INTEGER REFERENCES fetches(id),
  import_id INTEGER REFERENCES imports(id),
  shots INTEGER,
  shots_on_target INTEGER,
  corners INTEGER,
  fouls INTEGER,
  yellow_cards INTEGER,
  red_cards INTEGER,
  offsides INTEGER,
  saves INTEGER,
  possession REAL,
  passes INTEGER,
  xg REAL,
  available_at_utc TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  UNIQUE (match_id, team_id, source_id)
);
CREATE INDEX idx_tms_team ON team_match_stats(team_id);

CREATE TABLE player_match_stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  player_id INTEGER NOT NULL REFERENCES players(id),
  team_id INTEGER NOT NULL REFERENCES teams(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  fetch_id INTEGER REFERENCES fetches(id),
  import_id INTEGER REFERENCES imports(id),
  started INTEGER,
  minutes REAL,
  minutes_estimated INTEGER NOT NULL DEFAULT 0,
  goals INTEGER,
  assists INTEGER,
  shots INTEGER,
  shots_on_target INTEGER,
  xg REAL,
  passes INTEGER,
  key_passes INTEGER,
  tackles INTEGER,
  interceptions INTEGER,
  fouls INTEGER,
  yellow_cards INTEGER,
  red_cards INTEGER,
  available_at_utc TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  UNIQUE (match_id, player_id, source_id)
);

CREATE TABLE lineups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  team_id INTEGER NOT NULL REFERENCES teams(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  status TEXT NOT NULL CHECK (status IN ('confirmed','expected')),
  formation TEXT,
  source_url TEXT,
  published_at_utc TEXT,                         -- källans publiceringstid om känd
  fetched_at_utc TEXT NOT NULL,                  -- när vi faktiskt såg elvan
  fetch_id INTEGER REFERENCES fetches(id),
  import_id INTEGER REFERENCES imports(id),
  content_hash TEXT NOT NULL,
  UNIQUE (match_id, team_id, source_id, status, content_hash)
);

CREATE TABLE lineup_players (
  lineup_id INTEGER NOT NULL REFERENCES lineups(id),
  slot INTEGER NOT NULL,
  player_id INTEGER REFERENCES players(id),
  name_original TEXT NOT NULL,
  shirt_number INTEGER,
  position TEXT,
  is_starter INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (lineup_id, slot)
);

CREATE TABLE availability (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER REFERENCES matches(id),
  team_id INTEGER NOT NULL REFERENCES teams(id),
  player_id INTEGER REFERENCES players(id),
  player_name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('injury','suspension','doubtful','other')),
  reason TEXT,
  source_id TEXT NOT NULL REFERENCES sources(id),
  published_at_utc TEXT,
  fetched_at_utc TEXT NOT NULL,
  UNIQUE (match_id, team_id, player_name, kind, source_id)
);

CREATE TABLE market_odds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  bookmaker TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT '1x2',
  kind TEXT NOT NULL CHECK (kind IN ('opening','closing','snapshot')),
  odds_home REAL, odds_draw REAL, odds_away REAL,
  published_at_utc TEXT,
  fetched_at_utc TEXT NOT NULL,
  UNIQUE (match_id, source_id, bookmaker, market, kind, fetched_at_utc)
);

-- ---------------------------------------------------------------- Modeller och prognoser
CREATE TABLE model_versions (
  id TEXT PRIMARY KEY,
  family TEXT NOT NULL CHECK (family IN ('V2','V3','BASE','LEGACY')),
  version TEXT NOT NULL,
  description TEXT NOT NULL,
  params_json TEXT NOT NULL,
  code_fingerprint TEXT,
  status TEXT NOT NULL CHECK (status IN ('baslinje','experimentell','kandidat','produktion','arkiverad')),
  status_reason TEXT,
  gate_report_json TEXT,
  created_at_utc TEXT NOT NULL,
  status_changed_at_utc TEXT NOT NULL
);

CREATE TABLE model_status_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_version_id TEXT NOT NULL REFERENCES model_versions(id),
  old_status TEXT, new_status TEXT NOT NULL, reason TEXT, at_utc TEXT NOT NULL
);

CREATE TABLE forecast_snapshots (
  id TEXT PRIMARY KEY,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  model_version_id TEXT NOT NULL REFERENCES model_versions(id),
  model_family TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('T-30','late','manual','legacy','test')),
  scheduled_for_utc TEXT,
  created_at_utc TEXT NOT NULL,
  data_cutoff_utc TEXT NOT NULL,
  kickoff_utc_at_creation TEXT NOT NULL,
  minutes_before_kickoff REAL NOT NULL,
  is_late INTEGER NOT NULL DEFAULT 0,
  prematch_eligible INTEGER NOT NULL,
  clock TEXT NOT NULL DEFAULT 'system',
  created_by TEXT NOT NULL,
  report_job_id INTEGER,
  p_home REAL, p_draw REAL, p_away REAL,
  goals_home REAL, goals_away REAL,
  corners_home REAL, corners_away REAL,
  shots_home REAL, shots_away REAL,
  sot_home REAL, sot_away REAL,
  payload_json TEXT NOT NULL,
  inputs_hash TEXT NOT NULL,
  CHECK ((p_home IS NULL AND p_draw IS NULL AND p_away IS NULL)
         OR (abs(p_home + p_draw + p_away - 1.0) < 1e-9))
);
CREATE INDEX idx_snap_match ON forecast_snapshots(match_id, created_at_utc);

CREATE TRIGGER forecast_snapshots_immutable_update BEFORE UPDATE ON forecast_snapshots
BEGIN SELECT RAISE(ABORT, 'forecast_snapshots är oföränderliga – skapa en ny snapshot i stället'); END;
CREATE TRIGGER forecast_snapshots_immutable_delete BEFORE DELETE ON forecast_snapshots
BEGIN SELECT RAISE(ABORT, 'forecast_snapshots får inte raderas'); END;

CREATE TABLE report_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  kind TEXT NOT NULL DEFAULT 'T-30',
  due_at_utc TEXT NOT NULL,
  kickoff_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','running','done','missed','late_done','failed','cancelled','superseded')),
  created_at_utc TEXT NOT NULL,
  started_at_utc TEXT,
  completed_at_utc TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  report_id INTEGER,
  late_by_seconds INTEGER,
  UNIQUE (match_id, kind, due_at_utc)
);
CREATE INDEX idx_jobs_due ON report_jobs(status, due_at_utc);

CREATE TABLE reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER NOT NULL REFERENCES matches(id),
  job_id INTEGER REFERENCES report_jobs(id),
  kind TEXT NOT NULL CHECK (kind IN ('T-30','late','manual','test')),
  is_late INTEGER NOT NULL DEFAULT 0,
  created_at_utc TEXT NOT NULL,
  data_cutoff_utc TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  bytes INTEGER NOT NULL,
  snapshot_ids_json TEXT NOT NULL
);
CREATE TRIGGER reports_immutable_update BEFORE UPDATE ON reports
BEGIN SELECT RAISE(ABORT, 'arkiverade rapporter är oföränderliga'); END;
CREATE TRIGGER reports_immutable_delete BEFORE DELETE ON reports
BEGIN SELECT RAISE(ABORT, 'arkiverade rapporter får inte raderas'); END;

-- Faktiska utfall (eftermatch) – lagras skilt från prognoser.
CREATE TABLE match_outcomes (
  match_id INTEGER PRIMARY KEY REFERENCES matches(id),
  home_goals INTEGER, away_goals INTEGER,          -- 90 minuter
  home_corners INTEGER, away_corners INTEGER,
  home_shots INTEGER, away_shots INTEGER,
  home_sot INTEGER, away_sot INTEGER,
  source_id TEXT REFERENCES sources(id),
  entered_by TEXT NOT NULL CHECK (entered_by IN ('auto','manual','import')),
  recorded_at_utc TEXT NOT NULL,
  note TEXT
);

-- Walk-forward/backtest
CREATE TABLE backtest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_version_id TEXT NOT NULL REFERENCES model_versions(id),
  created_at_utc TEXT NOT NULL,
  config_json TEXT NOT NULL,
  summary_json TEXT NOT NULL
);
CREATE TABLE backtest_predictions (
  run_id INTEGER NOT NULL REFERENCES backtest_runs(id),
  match_id INTEGER NOT NULL REFERENCES matches(id),
  split TEXT NOT NULL CHECK (split IN ('train','validation','test')),
  season TEXT NOT NULL,
  competition_code TEXT NOT NULL,
  cutoff_utc TEXT NOT NULL,
  p_home REAL, p_draw REAL, p_away REAL,
  outcome TEXT,
  preds_json TEXT NOT NULL,
  actuals_json TEXT NOT NULL,
  PRIMARY KEY (run_id, match_id)
);

-- ---------------------------------------------------------------- Drift
CREATE TABLE notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at_utc TEXT NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('info','success','warning','error')),
  title TEXT NOT NULL,
  body TEXT,
  match_id INTEGER,
  report_id INTEGER,
  read INTEGER NOT NULL DEFAULT 0,
  delivered_os INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE change_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at_utc TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  field TEXT,
  old_value TEXT,
  new_value TEXT,
  source_id TEXT,
  fetch_id INTEGER,
  import_id INTEGER,
  actor TEXT NOT NULL DEFAULT 'system'
);
CREATE INDEX idx_changelog_entity ON change_log(entity, entity_id);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE sync_state (
  source_id TEXT NOT NULL,
  job TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT '',
  last_run_utc TEXT,
  next_run_utc TEXT,
  last_status TEXT,
  last_error TEXT,
  etag TEXT,
  last_modified TEXT,
  calls_today INTEGER NOT NULL DEFAULT 0,
  calls_day TEXT,
  PRIMARY KEY (source_id, job, scope)
);
