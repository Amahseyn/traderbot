---
name: verification-before-completion
description: Use before claiming work is complete, fixed, or passing - requires running verification commands and confirming fresh output; evidence before assertions always
---

# Verification Before Completion for Traderbot

## Overview

**Core principle:** Evidence before claims, always.

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't executed the verification command in this message, you cannot claim it passes.

## The Verification Gate

BEFORE claiming any status or asserting completion:

1. **IDENTIFY:** What exact command proves this claim?
   - For backend/core changes: `.venv/bin/pytest tests/test_<target>.py -q`
   - For Lab API changes: `.venv/bin/pytest tests/test_lab_api.py -q`
   - For Lab UI components: Typecheck / verify imports and rendering under `apps/lab-ui/`
2. **RUN:** Execute the fresh command using `run_command`.
3. **READ:** Read the full stdout/stderr, verify returncode 0, verify zero failures.
4. **VERIFY:** Does the output unequivocally prove the claim?
   - If NO: State actual output and failure details honestly.
   - If YES: State claim supported by the output evidence.
5. **ONLY THEN:** Announce task completion to the user.

## Common Failures & Red Flags

| Red Flag Phrase | Reality |
|-----------------|---------|
| "It should pass now" | Execute the command to prove it. |
| "The logic is sound so tests will pass" | Run pytest and check the exit code. |
| "I fixed the type error" | Re-run typecheck or test to prove zero errors. |
| "Subagent reported success" | Independently verify file changes and test outputs. |

## Traderbot Rules Compliance Checklist

Before declaring work finished on Traderbot:
- [ ] Pytest executed and passing with 0 failures on touched modules.
- [ ] No future lookahead introduced (bars strictly causal through current close).
- [ ] Minimal diffs preserved (no drive-by refactoring or unnecessary file modifications).
- [ ] Lab UI changes use design tokens from `MASTER.md` (no raw hex codes, semantic PnL colors only).

