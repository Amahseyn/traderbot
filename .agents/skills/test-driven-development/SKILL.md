---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code in traderbot
---

# Test-Driven Development (TDD) for Traderbot

## Overview

Write the test first. Watch it fail. Write the minimal code to pass.

**Core principle:** If you didn't watch the test fail, you don't know if it tests the right thing.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over. Implement fresh from tests. Period.

## When to Use

**Always:**
- New trading strategies, indicators, or filters (`traderbot/algorithms/`)
- API endpoints or background task handlers (`lab/`, `cli/`)
- Market data transformations or causality filters (`utils/bars.py`, `markets/`)
- Bug fixes and refactoring across the repository

**Exceptions (confirm with user):**
- Throwaway exploratory spikes
- Pure static UI styling adjustments with no business logic

## AntiGravity & Traderbot Specifics

### 1. Test Command Execution
Always use the virtualenv test runner via `run_command`:
```bash
.venv/bin/pytest tests/test_<target>.py -q
```
- **Focused Tests Only:** Never run full integration test suites or matrix runs unless explicitly requested. Run only tests covering the code touched (per `GEMINI.md`).

### 2. Causality Invariant Testing
When writing tests for bar processing, signals, or indicators:
- Strictly test that `on_bar` or signal functions only receive data $\le$ `known_at_unix_seconds`.
- Verify that no future bars or lookahead data can leak into calculation matrices.
- Test edge cases around 1m/5m boundaries.

### 3. Cost-Aware Edge Testing
When testing strategy signals:
- Assert that signals obey `min_edge_over_cost` and `roundtrip_cost_pct`.
- Signals with expected move < roundtrip friction must evaluate to no-trade (neutral).

## Red-Green-Refactor Cycle

```
[ RED ]     --> Write failing test in tests/test_*.py
   ↓
[ VERIFY ]  --> Run `.venv/bin/pytest <test_file> -k <test_name> -q`
                Confirm failure with expected assertion/error
   ↓
[ GREEN ]   --> Write minimal implementation code
   ↓
[ VERIFY ]  --> Run pytest again. Confirm all green.
   ↓
[ REFACTOR]--> Clean up code, remove duplication, maintain minimal diffs
```

## Red Flags & Rationalization

- "This is just a small helper, I don't need a test" -> Simple code breaks too. Write the test first.
- "I'll write the code first to see how it shapes up" -> That's a spike. Throw it away, write the test first.
- "I know it works, I ran it manually" -> Manual runs are not regression-proof automated evidence.

