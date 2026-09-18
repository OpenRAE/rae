---
id: API-423
title: "Participant Crossing Policy And Evidence Contracts"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-07-15T05:45:06.923147Z
updated_at: 2026-07-26T14:27:17.956295Z
---

# API-423 — Participant Crossing Policy And Evidence Contracts

## Statement

The ecosystem shall define portable plain-data contracts for participant ingress and egress policy decisions, transformations, disclosures, interventions, participant-directed inject deliveries, and their bounded evidence and provenance without imposing a generic message transport or duplicating existing participant carriers.

## Rationale

API-406 and API-409 provide adjacent carriers, but no common contract records the policy revision, decision basis, transformation, marking, loss, weakening, and evidence for a governed participant-boundary crossing.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1014` (Bind composition edges to participant crossing policy and evidence authority)
- IMPLEMENTS → SPEC `contracts/schemas/plans/mixed-participant-composition-profile-v1.json` (Typed crossing subject, policy, loss, and evidence bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition.py` (Composition edge context resolution over incumbent crossing contracts)
- TESTS → TEST `implementations/python/tests/test_issue_1014_mixed_composition_contracts.py` (Crossing policy, evidence, mapping, and stale-reference rejection tests)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1013` (Compose the existing API-423 authority in SEM-234 without changing its runtime contract)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/cross-backend-participant-control.md` (Revisioned mixed-composition compatibility boundary)
- TESTS → TEST `implementations/python/tests/test_sem_234_mixed_composition.py` (Bounded composition with incumbent API-423 authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_flow_control_validation.py` (API-423 final-sink flow-control validation)
- TESTS → TEST `implementations/python/tests/test_sem_233_flow_control_contracts.py` (API-423 final-sink flow-control tests)
- IMPLEMENTS → GITHUB_ISSUE `1002` (Issue #1002 portable flow-control contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_flow_sink.py` (API-423 crossing decision bound to the SEM-233 final-sink permit)
- TESTS → TEST `implementations/python/tests/test_issue_1003_final_sink_flow_enforcement.py` (API-423 decision-binding and mismatch final-sink tests)
- IMPLEMENTS → GITHUB_ISSUE `1003` (Issue #1003 enforce participant flow policy at final runtime sinks)
- DOCUMENTS → GITHUB_ISSUE `803` (Document participant I/O control authoring, operations, and claim boundaries)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_crossing.py` (API-423 participant crossing contract models)
- IMPLEMENTS → GITHUB_ISSUE `798` (API-423 participant crossing policy and evidence contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_crossing_validation.py` (API-423 crossing context validation)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-crossing-occurrence-v1.json` (Published participant crossing occurrence schema)
- IMPLEMENTS → ADR `docs/decisions/issue-798-api-423-participant-crossing-contracts-preflight.md` (API-423 architecture preflight)
- TESTS → TEST `implementations/python/tests/test_api_423_participant_crossing_contracts.py` (API-423 participant crossing contract tests)
- IMPLEMENTS → GITHUB_ISSUE `802` (Migrate participant I/O control semantics and existing carriers)
- TESTS → TEST `implementations/python/tests/test_issue_802_participant_control_migration.py` (Issue #802 participant-control compatibility and migration tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-802-api-423-participant-control-migration-preflight.md` (Issue #802 participant-control migration architecture preflight)
- IMPLEMENTS → DOCUMENTATION `docs/migration/participant-information-flow-control.md` (Participant information-flow control migration guide)
- TESTS → TEST `implementations/python/tests/test_public_docs_policy.py` (Executable participant-control public guide claim example)
- DOCUMENTS → DOCUMENTATION `docs/public/participant-control.md` (Participant input and output control guide)
