---
name: brainstorming
description: Use before creative work - designing trading algorithms, building UI components, adding pipelines, or planning new features
---

# Brainstorming for Traderbot

## Overview

Explore requirements, clarify edge conditions, and evaluate architectural alternatives before writing code.

## Workflow

1. **Investigate Existing Code First:**
   - Use `read_file` or invoke a `research` subagent to check how existing algorithms, endpoints, or UI components are structured.
   - Check `GEMINI.md` for existing constraints (e.g., indicator reuse in `algorithms/bands.py`, existing endpoints in `lab/`, UI design system in `MASTER.md`).
2. **Present Architectural Options:**
   - For algorithmic features: compare computational complexity, causality implications, and execution friction (maker vs taker).
   - For Lab UI features: compare component reuse, state management with React Query, and token compliance.
3. **Socratic Clarification:**
   - Ask clarifying questions early if requirements are ambiguous.
   - Once aligned on the approach, transition into `writing-plans`.
