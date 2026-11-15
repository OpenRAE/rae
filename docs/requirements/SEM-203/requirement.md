---
id: SEM-203
title: "Workflow Control Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:39:40.192269Z
updated_at: 2026-04-05T02:40:10.318695Z
---

# `SEM-203` workflow control semantics

## Statement

The ecosystem shall define explicit, portable control semantics for workflow branching, joining, calling, retry, completion, and execution history.

## Rationale

Current state: implemented. Explicit state-machine rules keep workflow meaning the same in each execution environment.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/workflow_transitions.py` (Runtime graph control.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/workflow_execution.py` (Dispatch and response acceptance.)
- TESTS → TEST `implementations/python/tests/test_issue_2041_runtime_step_dispatch.py` (Graph order, shared steps, calls, barriers, and retries.)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/workflow/semantics.py` (Workflow step state and join rules)
- TESTS → TEST `implementations/python/tests/test_workflow_join_analysis.py` (Join checks against all paths in small graphs)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (SDL Sections Reference)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md` (SDL Semantic Validation)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/testing.md` (SDL Testing Guide)
- CONSTRAINS → ADR `ADR-006` (Workflow Control Language Redesign)
- CONSTRAINS → ADR `ADR-007` (Lightweight Formal Methods Policy for Semantic Systems)
- CONSTRAINS → SPEC `specs/formal/workflows/state-machine.md` (Workflow State Machine)
- CONSTRAINS → SPEC `specs/formal/workflows/README.md` (Workflow Semantics Overview)
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py` (Workflow Validator Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_models.py` (Workflow Runtime Model Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_manager.py` (Workflow Runtime Manager Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_planner.py` (Workflow Planner Semantics Tests)
