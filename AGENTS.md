# Agent notes (traderbot)

Persistent guidance lives in **`.cursor/rules/`** (see `traderbot-core.mdc`, `strategies-recent-price.mdc`, `ml-features.mdc`).

**Ignore index noise**: `.cursorignore` excludes `results/`, `data/`, and image binaries — use explicit paths when reading CSVs or plots.

**Strategy compare with recent-price filters**:

```bash
traderbot strategy compare data/crypto/ohlc/BTCIRT_60.csv \
  --out results/strategies/compare_BTCIRT_60 \
  --context-bars 3 \
  --buy-min-recent-return -0.03 \
  --price-confirm \
  --visualize
```

`--context-bars 0` (default) keeps prior indicator-only behavior.
