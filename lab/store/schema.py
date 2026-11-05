SCHEMA_VERSION = 11

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

CREATE TABLE IF NOT EXISTS sweep_sessions (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT,
    resolution TEXT,
    horizon_label TEXT,
    csv_path TEXT NOT NULL,
    bar_count INTEGER,
    rank_by TEXT NOT NULL,
    holdout_tail_bars INTEGER,
    min_trades INTEGER,
    cash REAL,
    fee REAL,
    param_grid_json TEXT NOT NULL,
    best_params_json TEXT NOT NULL,
    best_metrics_json TEXT NOT NULL,
    config_id TEXT REFERENCES configurations(id),
    manifest_path TEXT,
    optimize_start_utc TEXT,
    optimize_end_utc TEXT,
    compare_start_utc TEXT,
    compare_end_utc TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sweep_lookup ON sweep_sessions(strategy_id, symbol, resolution);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    exchange TEXT NOT NULL,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    artifact_path TEXT,
    report_json TEXT,
    created_at_utc TEXT NOT NULL,
    finished_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_discovery_runs_finished ON discovery_runs(finished_at_utc DESC);

CREATE TABLE IF NOT EXISTS marketcap_cache (
    cache_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pair_discovery_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    exchange TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    finished_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_pair_discovery_runs_created ON pair_discovery_runs(created_at_utc DESC);

CREATE TABLE IF NOT EXISTS pair_candidates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pair_discovery_runs(id),
    pair_id TEXT NOT NULL,
    symbol_a TEXT NOT NULL,
    symbol_b TEXT NOT NULL,
    correlation REAL NOT NULL,
    candidate_category TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pair_candidates_run ON pair_candidates(run_id);

CREATE TABLE IF NOT EXISTS pair_qualification_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pair_discovery_runs(id),
    pair_id TEXT NOT NULL,
    qualification_status TEXT NOT NULL,
    cointegration_status TEXT NOT NULL,
    hedge_ratio REAL NOT NULL,
    half_life_bars REAL,
    cointegration_pvalue REAL NOT NULL,
    adf_statistic REAL NOT NULL,
    rejection_reasons_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pair_qualification_run ON pair_qualification_results(run_id);

CREATE TABLE IF NOT EXISTS pair_ranking_snapshots (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pair_discovery_runs(id),
    snapshot_timestamp INTEGER NOT NULL,
    pair_id TEXT NOT NULL,
    ranking_position INTEGER NOT NULL,
    pair_quality_score REAL NOT NULL,
    liquidity_score REAL NOT NULL,
    stability_score REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pair_ranking_snapshots_run ON pair_ranking_snapshots(run_id);

CREATE TABLE IF NOT EXISTS pair_ranking_changes (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pair_discovery_runs(id),
    pair_id TEXT NOT NULL,
    previous_rank INTEGER,
    new_rank INTEGER,
    change_type TEXT NOT NULL,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_pair_ranking_changes_run ON pair_ranking_changes(run_id);

CREATE TABLE IF NOT EXISTS pair_strategy_signals (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    pair_id TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    action TEXT NOT NULL,
    spread REAL NOT NULL,
    z_score REAL NOT NULL,
    dominant_price REAL NOT NULL,
    hedge_price REAL NOT NULL,
    hedge_ratio REAL NOT NULL,
    dominant_qty REAL NOT NULL,
    hedge_qty REAL NOT NULL,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_pair_strategy_signals_pair ON pair_strategy_signals(pair_id, timestamp_utc DESC);

CREATE TABLE IF NOT EXISTS pair_paper_positions (
    id TEXT PRIMARY KEY,
    pair_id TEXT NOT NULL,
    status TEXT NOT NULL,
    opened_at_utc TEXT NOT NULL,
    closed_at_utc TEXT,
    entry_spread REAL NOT NULL,
    exit_spread REAL,
    entry_z_score REAL,
    exit_z_score REAL,
    leg_a_qty REAL NOT NULL,
    leg_b_qty REAL NOT NULL,
    entry_price_a REAL NOT NULL,
    entry_price_b REAL NOT NULL,
    exit_price_a REAL,
    exit_price_b REAL,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    total_fees REAL NOT NULL DEFAULT 0.0,
    total_funding REAL NOT NULL DEFAULT 0.0,
    snapshot_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pair_paper_positions_status ON pair_paper_positions(status);
CREATE INDEX IF NOT EXISTS idx_pair_paper_positions_pair ON pair_paper_positions(pair_id);

CREATE TABLE IF NOT EXISTS pair_execution_events (
    id TEXT PRIMARY KEY,
    position_id TEXT,
    pair_id TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    leg TEXT NOT NULL,
    action TEXT NOT NULL,
    requested_qty REAL NOT NULL,
    filled_qty REAL NOT NULL,
    fill_price REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0.0,
    slippage REAL NOT NULL DEFAULT 0.0,
    execution_status TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_pair_execution_events_pair ON pair_execution_events(pair_id, timestamp_utc DESC);

CREATE TABLE IF NOT EXISTS pair_risk_decisions (
    id TEXT PRIMARY KEY,
    pair_id TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    check_type TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reason TEXT NOT NULL,
    metrics_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pair_risk_decisions_pair ON pair_risk_decisions(pair_id, timestamp_utc DESC);
"""
