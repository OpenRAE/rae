---
id: ACT-622
title: "Participant Action-Space Modes"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:07.350185Z
updated_at: 2026-07-26T01:19:38.464457Z
---

# ACT-622 — Participant Action-Space Modes

## Statement

The ecosystem shall support participant action-space modes including open-ended action generation, constrained action forms, and enumerated candidate-action sets where appropriate.

## Rationale

Primary-source refresh shows that participant interaction surfaces vary between free-form and enumerated decision modes, and the ecosystem needs to support both without backend-specific reinterpretation.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior/__init__.py` (ACT-622 authored participant action-argument domains)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_decision_surface.py` (ACT-622 participant decision-surface contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_action_arguments.py` (ACT-622 normalized action-argument carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_binding.py` (ACT-622 fail-closed participant binding admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_action_admission.py` (ACT-622 fail-closed participant binding admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_binding_validation.py` (ACT-622 participant binding validation support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_binding_events.py` (ACT-622 participant binding event support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/__init__.py` (ACT-622 resolver public export)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_contracts.py` (ACT-622 action-argument shape compiler)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/decision_surface.py` (ACT-622 decision-surface projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/participant_action_arguments.py` (ACT-622 action-argument normalization and validation)
- TESTS → TEST `implementations/python/tests/test_act_622_participant_action_arguments.py` (ACT-622 participant action-argument verification suite)
- TESTS → TEST `implementations/python/tests/test_sem_226_participant_exposure.py` (ACT-622 participant exposure regression coverage)
- TESTS → TEST `implementations/python/tests/test_sem_220_participant_decision_surface.py` (ACT-622 decision-surface regression coverage)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/README.md` (ACT-622 formal participant action-space semantics)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (ACT-622 instantiated scenario schema)
- IMPLEMENTS → SPEC `contracts/schemas/satisfiability/scenario-satisfiability-evidence-v1.json` (ACT-622 satisfiability evidence schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/resources.py` (ACT-622 compiled runtime action-shape resource)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json` (ACT-622 instantiated snapshot schema)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (ACT-622 SDL authoring schema)
- IMPLEMENTS → GITHUB_ISSUE `303` (Issue #303: Participant Action-Space Modes)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-303-act-622-participant-action-space-modes-preflight.md` (ACT-622 architecture preflight)
