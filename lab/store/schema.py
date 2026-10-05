SCHEMA_VERSION = 4

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS configurations (
    id TEXT PRIMARY KEY,
    config_kind TEXT NOT NULL,
    strategy_id TEXT,
    model_id TEXT,
    symbol TEXT,
    resolution TEXT,
    horizon_label TEXT,
    parameters_json TEXT NOT NULL,
    data_context_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_configurations_kind ON configurations(config_kind);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id TEXT PRIMARY KEY,
    run_kind TEXT NOT NULL,
    config_id TEXT NOT NULL REFERENCES configurations(id),
    out_dir TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    compare_session_id TEXT,
    experiment_id TEXT,
    UNIQUE(out_dir, run_kind)
);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_kind ON evaluation_runs(run_kind);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created ON evaluation_runs(created_at_utc DESC);

CREATE TABLE IF NOT EXISTS compare_sessions (
    id TEXT PRIMARY KEY,
    csv_path TEXT NOT NULL,
    bar_count INTEGER,
    best_strategy_id TEXT,
    summary_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    pipeline_id TEXT,
    title TEXT,
    status TEXT,
    config_path TEXT,
    solution_root TEXT,
    payload_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    log_text TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL,
    finished_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    symbol TEXT,
    resolution TEXT,
    horizon_label TEXT,
    range_start_utc TEXT,
    range_end_utc TEXT,
    repo_path TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    registered_at_utc TEXT NOT NULL,
    last_seen_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_datasets_symbol ON datasets(symbol);

CREATE TABLE IF NOT EXISTS market_catalog (
    symbol TEXT NOT NULL,
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    label TEXT NOT NULL,
    catalog_scope TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (symbol, catalog_scope)
);

CREATE INDEX IF NOT EXISTS idx_market_catalog_scope ON market_catalog(catalog_scope);
CREATE INDEX IF NOT EXISTS idx_market_catalog_symbol ON market_catalog(symbol);
"""
