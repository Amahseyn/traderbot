---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step traderbot task, before touching code
---

# Writing Plans for Traderbot

## Overview

Produce actionable, bite-sized implementation plans for Traderbot features, algorithmic strategies, and Lab UI enhancements.

## Rules for Traderbot Plans

1. **Map Files & Boundaries:**
   - Adhere strictly to project layout:
     - Core trading: `traderbot/`
     - Strategy algorithms: `traderbot/algorithms/` (registered in `registry.py`)
     - Lab backend: `lab/` (FastAPI)
     - Lab frontend: `apps/lab-ui/` (Next.js App Router)
     - Market connectors: `hyperliquid/`, `nobitex/`, `markets/`
2. **Enforce Invariants:**
   - Every algorithmic plan must include causality verification (no lookahead, bar time $\le$ `known_at_unix_seconds`).
   - Every strategy plan must include roundtrip friction gate checks (`min_edge_over_cost`, `roundtrip_cost_pct`).
   - UI plans must follow `apps/lab-ui/design-system/traderbot-lab/MASTER.md` (tokens only, no raw hex colors).
3. **Step Granularity:**
   Each task must specify:
   - Target files
   - Failing test command
   - Minimal implementation code
   - Passing test verification command
4. **Output Format:**
   Plans can be saved to `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` or emitted as a planning artifact with `RequestFeedback: true`.
