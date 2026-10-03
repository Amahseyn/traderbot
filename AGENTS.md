# Agent notes

Rules: `.cursor/rules/` (`traderbot-core.mdc` always; ML/strategy rules on matching globs).

Index skips `data/`, `results/`, `solutions/`, CSVs, and images — pass explicit paths when reading outputs.

Layout: `cli/` (argparse), `backtesting/`, `nobitex/` (client + signing), `markets/market_data.py`, `data/export.py`, `data/intrahour.py`. No `*_cli.py` or `backtest.py` at package root.
