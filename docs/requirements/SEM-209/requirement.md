---
id: SEM-209
title: "Multi-Participant Interaction Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:15:26.376206Z
updated_at: 2026-05-19T00:41:35.121699Z
---

# SEM-209 — Multi-Participant Interaction Semantics

## Statement

The ecosystem shall define explicit semantics for coordination, contention, interference, and shared-state change among concurrent participants.

## Rationale

Requirement inventory expansion. Multi-participant behavior cannot remain portable if interaction meaning is left implicit.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Preserve interaction references under module namespaces)
- TESTS → TEST `implementations/python/tests/test_act_612_relationship_integration.py` (Independent composed coordination references and endpoint agreement)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/README.md` (Participant Semantics Formal Design)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-022-participant-behavior-and-interaction-semantics.md` (ADR-022: Participant Behavior and Interaction Semantics)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (SEM-209 participant interaction semantics tests)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-behavior-history-event-stream-v1.json` (Participant behavior history interaction provenance schema)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL action contract interaction declaration schema)
- TESTS → TEST `implementations/python/tests/test_runtime_conformance.py` (SEM-209 cross-participant joint-action ordering conformance tests)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/precedents.md` (SEM-209 lineage to participant-semantics primary literature)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-semantic-integrity.md` (SEM-209 shared semantic integrity reference index)
- TESTS → TEST `implementations/python/tests/test_participant_semantics_invariant_oracle.py` (Participant semantics invariant oracle for SEM-209 interaction semantics)
