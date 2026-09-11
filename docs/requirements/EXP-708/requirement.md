---
id: EXP-708
title: "Captured Artifact And Observation Model"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-03T06:39:28.640175Z
updated_at: 2026-06-22T02:15:38.425669Z
---

# EXP-708 — Captured Artifact And Observation Model

## Statement

The ecosystem shall support first-class models for raw captured observations, traces, telemetry, artifacts, and other run evidence.

## Rationale

Requirement inventory expansion. Raw captured evidence must be modeled explicitly rather than buried inside backend-local logs or result blobs.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md` (ADR-064 Experiment Evidence and Measure Contract Boundary)
- DOCUMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment Core Formal Specification)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Experiment evidence record conformance and rejection tests)
- IMPLEMENTS → GITHUB_ISSUE `88` (Experiment evidence & measures (EXP-707, EXP-708, EXP-709, EXP-715))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_run.py` (Structural task/run validation separated from evidence satisfaction claims)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_conditions.py` (Condition matching excludes unsupported evidence-id claims)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/evidence_satisfaction.py` (Content-backed emitted evidence satisfaction validation)
- TESTS → TEST `implementations/python/tests/test_issue_1112_capture_admission.py` (Evidence record, artifact byte, digest, and field proof coverage)
