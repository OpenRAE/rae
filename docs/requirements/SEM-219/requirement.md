---
id: SEM-219
title: "Participant Tool And Affordance Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:26.855124Z
updated_at: 2026-07-19T20:59:21.601117Z
---

# SEM-219 — Participant Tool And Affordance Semantics

## Statement

The ecosystem shall define explicit semantics for participant tool and affordance availability, visibility, invocation, and constraint handling.

## Rationale

Primary-source refresh shows that tool-using participants need shared semantics for what affordances exist and how their constraints are interpreted across syntax, runtime, and contracts.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `1204` (Preserve participant constraint and effect authority at backend boundaries)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_action_validation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_effect_transitions.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_execution.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_effect_authority.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_execution_control_boundary.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_targeted_effects.py`
- TESTS → TEST `implementations/python/tests/test_issue_898_participant_execution_control.py`
- TESTS → TEST `implementations/python/tests/test_issue_899_participant_resource_budgets.py`

- DOCUMENTS → ADR `docs/decisions/adrs/adr-083-participant-tool-decision-surface-and-exposure-semantics.md` (ADR-083 participant tool, decision-surface, and exposure semantics)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-119-sem-219-220-226-participant-decision-surface-preflight.md` (Issue 119 participant decision-surface architecture preflight)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-semantic-integrity.md` (Shared semantic integrity mapping for SEM-219/SEM-220/SEM-226)
- IMPLEMENTS → CODE_FILE `tools/check_sdl_catalog_parity.py` (SDL tool-affordance catalog parity gate)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (SEM-219 participant tool-affordance semantic and compiler tests)
- TESTS → TEST `implementations/python/tests/test_sdl_catalog_parity.py` (SEM-219 SDL catalog parity tests)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → GITHUB_ISSUE `294` (Issue 294 — Participant Tool And Affordance Semantics)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/README.md` (Normative participant tool and affordance semantics)
- IMPLEMENTS → SPEC `specs/sdl/references.md` (SDL participant tool-affordance reference contract)
- IMPLEMENTS → CONFIG `contracts/schema-publication-manifest.json` (Published SDL schema change ledger)
- IMPLEMENTS → CONFIG `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL authoring input schema)
- IMPLEMENTS → CONFIG `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated scenario schema)
- IMPLEMENTS → CONFIG `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json` (Instantiated scenario snapshot schema)
