#!/usr/bin/env python3
"""Walk-forward matrix evaluation with Monte Carlo OOS windows (real exchange data)."""

from __future__ import annotations

import argparse
import sys

from traderbot.backtesting.matrix_eval import MatrixEvalConfig, run_full_matrix_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run strategy x market x timeframe matrix evaluation.")
    parser.add_argument("--samples", type=int, default=100, help="OOS windows per cell (default 100)")
    parser.add_argument("--months", type=int, default=6, help="History months to download")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=str, default="results/strategy_eval")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    config = MatrixEvalConfig(
        sample_count=args.samples,
        months=args.months,
        seed=args.seed,
        out_dir=__import__("pathlib").Path(args.out_dir),
        use_cache=not args.no_cache,
    )

    def progress(message: str) -> None:
        print(message, flush=True)

    summary = run_full_matrix_evaluation(config, progress=progress)
    print(f"Wrote {config.out_dir / 'matrix_summary.json'}", file=sys.stderr)
    print(f"Selector: {summary.get('selector_path')}", file=sys.stderr)


if __name__ == "__main__":
    main()
