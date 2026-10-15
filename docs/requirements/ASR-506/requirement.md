---
id: ASR-506
title: "Participant Semantic Artifacts"
status: DRAFT
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:16:16.574031Z
updated_at: 2026-04-03T06:16:16.574031Z
---

# ASR-506 — Participant Semantic Artifacts

## Statement

The ecosystem shall maintain normative semantic artifacts for participant behavior, interaction, visibility, causality, and outcome meaning.

## Rationale

Requirement inventory expansion. Participant behavior needs normative semantic artifacts just as workflows and objectives do.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `487` (Executable invariant oracle for participant-semantics abstract model (I1-I18) (review FM-2))
- DOCUMENTS → SPEC `specs/formal/participant-semantics/README.md` (Participant Semantics Formal Design executable invariant oracle mapping)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-semantic-integrity.md` (Shared semantic integrity participant-semantics oracle coverage rows)
- DOCUMENTS → TEST `implementations/python/tests/test_participant_semantics_invariant_oracle.py` (Participant semantics invariant oracle: spec-sync and discrimination checks over a test-local model, not production coverage)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/semantic-coverage.md` (Participant semantic coverage matrix: clause-to-contract-to-implementation-to-test mapping, evidence classes, coverage, and open owners)
- DOCUMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (Participant behavior model formal design and PBM cross-clause invariants)
- DOCUMENTS → SPEC `specs/formal/participant-runtime/README.md` (Participant runtime formal design and V1 traceability criteria)
- TESTS → TEST `implementations/python/tests/test_issue_219_participant_semantic_coverage.py` (Coverage matrix parity and integrity guard for participant semantic artifacts)
