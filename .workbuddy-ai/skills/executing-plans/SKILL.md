---
name: executing-plans
description: Use when executing an implementation plan inline in the current session as the implementer yourself
---

# Executing Plans Inline for Traderbot

## Overview

Execute implementation plans task-by-task directly within the current session without spawning separate implementer subagents for every task.

**Core principle:** The plan already did the architectural thinking. Execute with discipline, prove every step with failing-then-passing tests, maintain minimal diffs, and keep an accurate task artifact.

## When to Use

- When tasks are tightly coupled or small enough that subagent context switches add unnecessary overhead.
- When direct inline pair programming is preferred.

## Workflow

1. **Task Tracking via Artifact:**
   - Create a task tracking artifact listing all tasks with checkboxes `- [ ]`.
   - Update it with `edit_file` to `- [x]` as each task passes verification.
2. **Per-Task TDD Cycle:**
   - For every task, write or update the test first in `tests/test_*.py`.
   - Run `.venv/bin/pytest tests/test_<target>.py -q` and watch it fail for the right reason.
   - Implement the minimal required change in `traderbot/`, `lab/`, or `apps/lab-ui/`.
   - Re-run pytest and verify green.
3. **Continuous Execution:**
   - Proceed through the task list without stalling for routine confirmations.
   - If an ambiguity arises, make an authoritative engineering ruling adhering to `GEMINI.md` invariants, record it, and proceed.
4. **Final Whole-Branch Verification:**
   - Execute verification before claiming completion.
