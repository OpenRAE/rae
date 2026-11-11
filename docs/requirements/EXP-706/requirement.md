---
id: EXP-706
title: "Trial And Replication Model"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-04-03T06:39:28.417112Z
updated_at: 2026-06-25T18:25:28.797981Z
---

# EXP-706 — Trial And Replication Model

## Statement

The ecosystem shall support repeated runs, replications, and controlled variation across runs of the same task or study.

## Rationale

Requirement inventory expansion. Experiment systems must represent repeat trials and controlled variation explicitly.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_replacement.py` (Author-selected replacement triggers and additional-trial limits)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_replacement_archive.py` (Evidence-preserving archival supersession)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_replacement_analysis.py` (Single-count original-slot lineage and explicit shortfalls)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/replacement.py` (Separately admitted fresh trials with shared lineage bounds)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/trial-replacement-migration.md` (Author migration, explicit allocation and coordinator durability prerequisites)
- TESTS → TEST `implementations/python/tests/test_issue_1396_trial_replacement.py` (Replacement allocation, retention, exhaustion and study evidence validation)

- DOCUMENTS → ADR `docs/decisions/adrs/adr-068-experiment-trials-replication-and-replay-claims.md` (ADR-068: Experiment Trials, Replication, and Replay Claims)
- DOCUMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment Core Formal Specification)
- DOCUMENTS → DOCUMENTATION `docs/research/experiment-core/traceability-matrix-exp-706-712.md` (EXP-706/EXP-712 Clause Matrix)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-068-experiment-trials-replication-and-replay-claims.md` (ADR-068: Experiment Trials, Replication, and Replay Claims)
- IMPLEMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment Core Formal Specification)
- IMPLEMENTS → DOCUMENTATION `docs/research/experiment-core/traceability-matrix-exp-706-712.md` (EXP-706/EXP-712 Clause Matrix)
- IMPLEMENTS → DOCUMENTATION `docs/research/experiment-core/issue-105-exp-706-712-reproducibility-replay-preflight-guardrails.md` (Issue #105 Experiment Reproducibility and Replay Preflight Guardrails)
- IMPLEMENTS → DOCUMENTATION `docs/research/experiment-core/issue-267-exp-706-trial-replication-preflight-guardrails.md` (Issue #267 EXP-706 Trial Replication Preflight Guardrails)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Runtime contract tests for experiment study allocation and run provenance)
- IMPLEMENTS → GITHUB_ISSUE `267` (Trial And Replication Model (EXP-706))
