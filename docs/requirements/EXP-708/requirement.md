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

- TESTS → TEST `implementations/python/tests/test_exp_732_evidence_provenance.py` (Integrated apparatus provenance is retained in the context-bound content proof)

- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Retained production replay verifies the evidence implementation's source state)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Current capture binds the evidence contracts and processor source surfaces)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Current replay and immutable historical evidence remain separate)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/bundles/retest-v19.json` (Fresh bounded production replay of the integrated issue-1237 source state)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1237-v18.json` (Fresh source-bound coverage replay retains existing claim limits)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/capture_dimensions.py` (Shared captured-evidence admission dimension semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/observation_capture.py` (Evidence-eligible collection offers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/observation_manifest.py` (Round-trip preservation of evidence collection offers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/observation_capture.py` (Closed declarations of evidence collection capabilities)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/capture_admission.py` (Required-evidence admission before effects)
- TESTS → TEST `implementations/python/tests/test_issue_1237_capture_dimensions.py` (Capture dimension coverage and diagnostics protect evidence admission)
- TESTS → TEST `implementations/python/tests/test_issue_1237_capture_ingress.py` (Required-evidence admission across effectful entrypoints)
- TESTS → TEST `implementations/python/tests/test_issue_1237_governance.py` (Evidence ownership preserves prerequisites and traceability)
- IMPLEMENTS → GITHUB_ISSUE `1237` (Centralize capture admission and evidence proof authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/evidence_proof.py` (Immutable content proof retained across task, run, metric, study, and condition consumers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/evidence_output_validation.py` (Atomic published-schema and semantic-validator evidence eligibility)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_evidence_content_validation.py` (Bounded emitted-byte validation through the registered output owner)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_study_run_validation.py` (Study membership preserves each run's validated evidence proof)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_analysis.py` (Study allocation consumes proof-bound condition evidence)
- TESTS → TEST `implementations/python/tests/test_issue_1237_evidence_proof.py` (Immutable proof and shared task, run, and study negative content vectors)
- TESTS → TEST `implementations/python/tests/test_issue_1237_output_registry.py` (Missing schema and missing semantic owner fail closed)
- DOCUMENTS → DOCUMENTATION `docs/migration/required-capture-admission.md` (Proof consumption and evidence output extension points)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1237-capture-proof-authority-preflight.md` (Capture and evidence authority guardrails)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md` (ADR-064 Experiment Evidence and Measure Contract Boundary)
- DOCUMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment Core Formal Specification)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Experiment evidence record conformance and rejection tests)
- IMPLEMENTS → GITHUB_ISSUE `88` (Experiment evidence & measures (EXP-707, EXP-708, EXP-709, EXP-715))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_run.py` (Structural task/run validation separated from evidence satisfaction claims)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_conditions.py` (Condition matching excludes unsupported evidence-id claims)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/evidence_satisfaction.py` (Content-backed emitted evidence satisfaction validation)
- TESTS → TEST `implementations/python/tests/test_issue_1112_capture_admission.py` (Evidence record, artifact byte, digest, and field proof coverage)
