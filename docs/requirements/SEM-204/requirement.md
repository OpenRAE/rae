---
id: SEM-204
title: "Workflow Compensation Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:39:40.306252Z
updated_at: 2026-04-05T02:41:37.997067Z
---

# SEM-204 — Workflow Compensation Semantics

## Statement

The ecosystem shall define explicit compensation semantics for registration, triggering, ordering, and observation of compensating actions.

## Rationale

Current state: implemented. Compensation behavior must be declared and portable rather than invented as backend-local rollback logic.

## Traceability

- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (SDL Sections Reference)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/testing.md` (SDL Testing Guide)
- CONSTRAINS → ADR `ADR-006` (Workflow Control Language Redesign)
- CONSTRAINS → SPEC `specs/formal/workflows/compensation.md` (Workflow Compensation Semantics)
- CONSTRAINS → SPEC `specs/formal/workflows/README.md` (Workflow Semantics Overview)
- CONSTRAINS → SPEC `specs/formal/runtime-contracts/workflow-results.md` (Workflow Result Contracts)
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py` (Workflow Compensation Validator Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_models.py` (Workflow Compensation Runtime Model Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_manager.py` (Workflow Compensation Runtime Manager Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (Workflow Compensation Control Plane Tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_workflows.py` (Automatic compensation in reverse completion-instant order)
- TESTS → TEST `implementations/python/tests/test_issue_1462_compensation_order.py` (Cancellation and timeout compensation order across admitted timestamp forms)
- TESTS → TEST `implementations/python/tests/test_issue_1462_policy_ownership.py` (SEM-204 phase routing, bounded ownership and delivery governance)
- IMPLEMENTS → GITHUB_ISSUE `1462` (fix(runtime): order workflow compensation by completion instant, not timestamp text)
