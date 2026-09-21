---
id: SEM-207
title: "Declarative Objective Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:55:58.710666Z
updated_at: 2026-05-10T19:42:47.837158Z
---

# SEM-207 — Declarative Objective Semantics

## Statement

The ecosystem shall define explicit semantics for objective actor binding, target resolution, success interpretation, windows, and dependency ordering.

## Rationale

Requirement inventory phase. Status audit deferred until the full canonical graph is complete.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/objectives.py` (Independent ownership and participant assignment)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/objective_semantics/__init__.py`
- IMPLEMENTS → SPEC `specs/sdl/participant-identity.md` (Ownership, assignment, and action constraints)
- TESTS → TEST `implementations/python/tests/test_issue_1338_participant_identity.py`
- TESTS → TEST `implementations/python/tests/test_issue_1338_identity_authority.py`
- TESTS → TEST `implementations/python/tests/test_issue_1338_identity_migration.py`
- TESTS → TEST `implementations/python/tests/test_issue_1338_identity_examples.py`

- IMPLEMENTS → DOCUMENTATION `specs/formal/objectives/declarative-objective-semantics.md` (SEM-207 formal semantic boundary (canonical inputs, required semantics, cross-cutting gates, anti-patterns, implementation mapping))
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/objective-semantics.md` (SEM-207 implementer-facing reference note (ADR-016 governed))
- TESTS → TEST `implementations/python/tests/test_semantics_objectives.py` (Objective semantics analyzer + dependency-partition unit tests (TestObjectiveSemantics, TestObjectiveDependencyPartition))
- TESTS → TEST `implementations/python/tests/test_fm2_semantics.py` (Cross-stage objective-semantics agreement (TestObjectiveSemanticAgreement))
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py` (SDL validator objective-binding tests (TestVerifyObjectives))
