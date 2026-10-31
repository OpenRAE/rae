---
id: EXP-710
title: "Provenance And Traceability"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-03T06:39:28.858157Z
updated_at: 2026-06-22T02:05:42.732590Z
---

# EXP-710 — Provenance And Traceability

## Statement

The ecosystem shall preserve traceability from task and run context through captured evidence to derived measures, evaluations, and experiment claims.

## Rationale

Requirement inventory expansion. Experiment claims require provenance and traceability rather than unsupported interpretation.

## Traceability

- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-run-v1.json` (Experiment run v1 published schema)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Experiment run provenance runtime contract tests)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-065-experiment-run-provenance-contract-boundary.md` (ADR-065 Experiment run provenance contract boundary)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_record_assembly.py` (Join task, snapshot, capture, and attempt facts.)
- TESTS → TEST `implementations/python/tests/test_issue_1630_run_records.py` (Check content-backed run and study evidence.)
