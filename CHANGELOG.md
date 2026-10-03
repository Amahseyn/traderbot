# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Conda `environment.yml` (`traderbot` env, Python 3.12).
- GitHub Actions CI (pytest) on Python 3.12; weekly Chronos integration job.
- `ExecutionPolicy` for paper vs live signal handling.
- Indicator parity tests (batch ML features vs incremental strategy math).
- Streaming Bollinger updates in `traderbot/algorithms/bands.py`.
- Unified top-level `traderbot` CLI help and command dispatch.
- `traderbot interface`: complete `catalog` JSON (`command_tree`, strategies, models, pickables), plus `list`, `describe`, interactive `pick`, and `run <id>` (`traderbot/interface/`).
- `traderbot data markets` and `traderbot data live`: multi-market Nobitex UDF snapshots and dashboard PNG (`traderbot/markets/`).
- `traderbot auth`: login (session Token + TOTP), `apikeys list`/`create`, `check` for signed API key pair (`traderbot/auth/`).
- Interactive hub: bare `traderbot` / `traderbot cli` opens a prompt menu (`traderbot/interactive/`).
- Interactive **Charts & compare** menu (live charts, strategy/ML plots, ranked compare, filters).
- Modular `traderbot/terminal/` package: `catalog`, `run`, `once`, `replay` subcommands.
- `CHANGELOG.md`.

### Changed

- Ad-hoc CLI output defaults to a structured **`results/<domain>/…`** tree (`runs/`, `reports/`, `visualizations/`) aligned with `solutions/`.
- Project and CI target **Python 3.12** only (`requires-python >= 3.12`; single CI job).
- `traderbot ml catalog` and `traderbot strategy catalog` accept `--implemented-only` (alias of `--implemented`).
- README clarifies `solutions/` (pipelines) vs ad-hoc `results/` output paths.
