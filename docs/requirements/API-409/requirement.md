---
id: API-409
title: "Participant External Input And Intervention Contracts"
status: ACTIVE
type: INTERFACE
priority: SHOULD
wave: 3
created_at: 2026-04-03T06:16:04.587331Z
updated_at: 2026-07-25T16:22:35.566014Z
---

# API-409 — Participant External Input And Intervention Contracts

## Statement

The ecosystem shall define portable plain-data contracts for external action proposals, approvals or denials, directions, interventions, handoffs, overrides, and cancellations where mixed-control participant modes are supported, preserving controller and authority identity, order, policy revision, provenance, evidence, and explicit disposition.

## Rationale

Issue #794 found that mixed-control input needs more than an undifferentiated external-input envelope: approval, direction, intervention, handoff, override, cancellation, admission, and execution are separate facts.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `1072` (Typed modular requests referencing incumbent control authorities)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control.py` (Owning external control occurrence alternatives)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_validation.py` (Owning control occurrence contextual validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_effects.py` (Closed control, review, delay and lifecycle request bindings)
- TESTS → TEST `implementations/python/tests/test_api_424_control_effects.py` (Typed effects and conflict preservation)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1072-api-409-control-effect-bindings-preflight.md` (Reuse of incumbent control/effect authority)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_flow_control_incumbent_validation.py` (API-409 flow-control incumbent carrier joins)
- TESTS → TEST `implementations/python/tests/test_sem_233_flow_control_contracts.py` (API-409 flow-control incumbent join tests)
- IMPLEMENTS → GITHUB_ISSUE `1002` (Issue #1002 portable flow-control contracts)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → CODE_FILE `tools/generate_contract_schemas.py` (API-409 published schema generation routing)
- IMPLEMENTS → CONFIG `contracts/schema-publication/entries/participant-control-occurrence-v1.json` (API-409 schema publication entry)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-control-occurrence-v1.json` (API-409 participant control occurrence v1 schema)
- TESTS → TEST `implementations/python/tests/test_api_409_participant_control_occurrences.py` (API-409 contract, schema, and fail-closed validation tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-252-api-409-participant-intervention-contracts-preflight.md` (API-409 architecture preflight)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/lineage.md` (API-409 participant-control lineage and nonclaims)
