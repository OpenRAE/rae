---
id: EXP-720
title: "Canonical Run Provenance Record"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-04T22:58:17.054011Z
updated_at: 2026-06-22T02:05:42.732625Z
---

# EXP-720 — Canonical Run Provenance Record

## Statement

The ecosystem shall define a canonical run provenance record, serving as the authoritative archival run record distinct from live execution state, capturing task reference, scenario and module digests, processor identity, backend identity, manifest references or digests, configuration, parameters, stochastic controls, timestamps, and result or evidence pointers.

## Rationale

Canonical provenance is required so the authoritative archival run record can support comparison, review, and reproduction without inferring critical execution context from mutable operational state.

## Traceability

- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-run-v1.json` (Experiment run v1 published schema)
- IMPLEMENTS → CONFIG `contracts/schema-publication-manifest.json` (Schema publication manifest entry for experiment-run-v1)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Experiment run provenance runtime contract tests)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-065-experiment-run-provenance-contract-boundary.md` (ADR-065 Experiment run provenance contract boundary)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_experiment_records.py` (Build records for all started runs from stored facts.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_execution_accounting.py` (Keep typed attempt states and partial run facts.)
- TESTS → TEST `implementations/python/tests/test_issue_1630_run_records.py` (Test missing evidence, failure, cleanup, resume, and complete records.)
- TESTS → TEST `implementations/python/tests/test_issue_1630_record_failures.py` (Keep records through evidence failures and verify immutable archive retries.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_record_versions.py` (Share immutable version ownership across runtime archive paths.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_record_lineage.py` (Join additional accounting to the exact scientific artifact without transferring proof.)
- TESTS → TEST `implementations/python/tests/test_issue_1630_record_recovery.py` (Recover uncertain legacy writes and validate actual replacement studies with exact scientific versions.)
- TESTS → TEST `implementations/python/tests/test_issue_1630_record_consistency.py` (Reject contradictory archival provenance and resolve scientific originals through both archive paths.)
- TESTS → TEST `implementations/python/tests/test_issue_1630_record_semantics.py` (Keep scientific evaluation distinct from execution and reject conflicting retained versions.)
