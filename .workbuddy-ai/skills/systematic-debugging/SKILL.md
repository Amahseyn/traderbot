---
name: systematic-debugging
description: Use when encountering any bug, test failure, unexpected backtest result, or Lab error before proposing fixes
---

# Systematic Debugging for Traderbot

## Overview

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose or apply fixes.

## When to Use

Use for ANY technical issue:
- Test failures (`pytest`)
- Backtest anomalies or unexpected trade executions
- Data causality violations (future leakage)
- Roundtrip cost / edge gate miscalculations
- Lab API errors (FastAPI 422, 500, SQLite issues)
- Lab UI client errors or proxy failures

## The Four Phases

### Phase 1: Root Cause Investigation
**BEFORE attempting ANY fix:**
1. **Read Error Messages & Traces Carefully:**
   - Read stack traces completely, noting file paths, line numbers, and parameter payloads.
   - For backtest discrepancies, log the exact bar timestamp and price series.
2. **Reproduce Consistently:**
   - Formulate a deterministic test command or script reproducing the exact failure:
     ```bash
     .venv/bin/pytest tests/test_<module>.py -k "<test_case>" -vv
     ```
3. **Trace Invariants:**
   - In trading logic: Check `known_at_unix_seconds` vs bar timestamps (`timestamp <= known_at_unix_seconds`).
   - In exchange calculations: Check fee schedule (`roundtrip_cost_pct`).
   - In database queries: Check SQLite schema migrations (`traderbot.db`).

### Phase 2: Pattern & Regression Analysis
- Formulate a test case in `tests/test_*.py` that reproduces the bug in isolation.
- Confirm that the test fails *specifically* due to the root cause identified in Phase 1.

### Phase 3: Targeted Minimal Fix
- Follow `GEMINI.md` conventions:
  - Make surgical, minimal diffs. No drive-by refactoring or unrelated cleanup.
  - Fix the root cause at the defining module (e.g. `utils/bars.py`, `traderbot/algorithms/price_context.py`), not by adding ad-hoc bandages at caller sites.

### Phase 4: Verification
- Run the reproduction test and confirm clean pass.
- Run the sibling module tests to ensure zero regressions:
  ```bash
  .venv/bin/pytest tests/test_<related>.py -q
  ```
- Verify evidence before reporting resolution.

## Common Traderbot Traps

| Symptom | False Fix | Root Cause Check |
|---------|-----------|------------------|
| Backtest shows unrealistic high winrate | Assuming strategy is amazing | Future lookahead in `on_bar` or indicators using unclosed bar data |
| High-frequency trades losing money | Blaming market randomness | `min_edge_over_cost` missing or fee friction exceeding move size |
| `sqlite3.OperationalError: no such table` | Patching inline DB queries | Run `.venv/bin/python -m lab init` or update migration schema |
| Lab UI 404/500 on `/lab-api` | Hardcoding direct FastAPI URLs | Next.js rewrite proxy configuration in `next.config.ts` |
