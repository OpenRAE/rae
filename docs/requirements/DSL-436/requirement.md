---
id: DSL-436
title: "Initial service state and native materialization semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-07-24T04:23:11.395722Z
updated_at: 2026-07-31T15:54:25.963535Z
---

# DSL-436 — Initial service state and native materialization semantics

## Statement

RAES SDL shall provide governed, provider-neutral extensions to scenario content and realization contracts for deterministic initial service state where ordinary node content placement is insufficient, including versioned content identity, exact service-target materialization requirements, reset ownership, deterministic generation inputs, and participant-equivalent readback, without treating age or narrative history as a distinct semantic object class.

## Rationale

Scenarios need coherent pre-existing files and application data across real products. Mature simulation architectures model these as initial conditions or initial world state, while keeping recorded trajectories, provenance, and live execution separate. RAES should extend its existing content and realization authorities only where operational materializers prove a reusable gap.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `859` (DSL-436 — Authored historical state and native materialization semantics)
- CONSTRAINS → SPEC `specs/sdl/stateful-resources.md` (Stateful realization resources)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/service_materialization.py` (Portable search-index schema capability and native realization contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/resources.py` (Typed portable search-index schema resource model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_requirements.py` (Search-index schema realization requirement lowering)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/core.py` (Exact backend capability and realization preflight)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_submission.py` (Direct-submission search-index schema validation)
- IMPLEMENTS → SPEC `specs/sdl/initial-service-state.md` (Initial service state normative SDL specification)
- TESTS → TEST `implementations/python/tests/test_initial_service_state.py` (Initial service state and search-index schema verification)
- IMPLEMENTS → GITHUB_ISSUE `1011` (Issue #1011: portable search-index schema profile)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/profile_selections.py`
- TESTS → TEST `implementations/python/tests/test_issue_1208_profile_selections.py`
