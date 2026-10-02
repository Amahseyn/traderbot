# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- GitHub Actions CI (pytest, ruff) on Python 3.10–3.12; weekly Chronos integration job.
- Ruff lint/format configuration and `ExecutionPolicy` for paper vs live signal handling.
- Indicator parity tests (batch ML features vs incremental strategy math).
- Streaming Bollinger updates in `traderbot/algorithms/bands.py`.
- Unified top-level `traderbot` CLI help and command dispatch.
- `CHANGELOG.md`.

### Changed

- `traderbot ml catalog` and `traderbot strategy catalog` accept `--implemented-only` (alias of `--implemented`).
- README clarifies `solutions/` (pipelines) vs ad-hoc `results/` output paths.
