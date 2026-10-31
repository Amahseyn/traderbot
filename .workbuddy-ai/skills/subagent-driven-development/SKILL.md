---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks using AntiGravity subagents
---

# Subagent-Driven Development for AntiGravity

## Overview

Execute multi-step implementation plans by dispatching specialized subagents per task, reviewing task deliverables, and maintaining a strict progress ledger.

**Core principle:** Fresh subagent per task + verification gate = clean, context-efficient, and reliable delivery.

## AntiGravity Tool Mapping

| Action | AntiGravity Tool | Notes |
|--------|------------------|-------|
| Dispatch Subagent | `invoke_subagent` | `TypeName: "self"` for code edits & commands; `TypeName: "research"` for read-only exploration |
| Workspace Mode | `Workspace` argument | `"inherit"` (default) shares workspace; `"branch"` or `"share"` isolates Git branch/worktree |
| Task Tracking | Task Artifact | Maintain a markdown checklist artifact via `write_file` (with `ArtifactMetadata`). **Never** use `manage_task` (which is for background daemons). |
| Command Execution | `run_command` | Execute tests via `.venv/bin/pytest` |

## Execution Workflow

1. **Initialize Task Artifact:**
   Create a task tracking markdown artifact in `<appDataDir>/brain/<conversation-id>/` listing all tasks from the plan as `- [ ] Task Name`.
2. **Dispatch Implementer Subagent:**
   For each task in sequence, invoke `invoke_subagent`:
   ```json
   {
     "TypeName": "self",
     "Role": "Traderbot Implementer",
     "Prompt": "Implement Task X from plan: <details>. Ensure tests pass via .venv/bin/pytest. Adhere to GEMINI.md rules."
   }
   ```
3. **Reactive Wakeup:**
   The parent agent waits reactively (no busy-polling). When the subagent completes, review the diff and run verification commands.
4. **Update Task Artifact:**
   Use `edit_file` on the task artifact to mark the step `- [x]` completed.
5. **Continuous Execution:**
   Do not stop between routine tasks to ask "should I continue?". Continue until all tasks in the plan are executed or an unresolvable blocker is hit.
