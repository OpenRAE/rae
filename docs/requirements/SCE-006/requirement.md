---
id: SCE-006
title: "Isolated Batch Trial Scheduling"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-07-15T03:17:25.961655Z
updated_at: 2026-10-25T04:04:53.198209Z
---

# SCE-006 — Isolated Batch Trial Scheduling

## Statement

The RAE processor and runtime shall orchestrate and execute trials from an admitted experiment plan over the existing RAES single-scenario execution path. The external scheduler, including APTL, shall manage placement, isolation, timeouts, and cleanup only.

Scheduling shall default to serial execution. Explicitly configured bounded parallelism shall require proven isolation of independent range instances, host capacity, ports, storage, and control-plane locks. Every trial shall receive a clean or declared reusable initial state. Every trial shall receive deterministic ordering and identity, bounded timeouts, and verified cleanup. The scheduler shall not implement a second scenario lifecycle or a private comparison/scoring engine.

## Rationale

Batch execution is the apparatus mechanism that turns an RAES run allocation into executions. Isolation and clean-state guarantees are more important than throughput because cross-trial contamination invalidates experimental evidence.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `1624` (Correct trial orchestration ownership against ADR-084 and ADR-113)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/scenario-variation-and-trial-realization.md` (Processor/runtime orchestration and external scheduler authority)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1624-trial-orchestration-ownership-preflight.md` (Trial orchestration ownership and existing security boundaries)
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml` (Explicit isolated-batch-scheduling phase under existing requirement governance)
- TESTS → TEST `implementations/python/tests/test_sce_006_requirement_governance.py` (Admit SCE-006 documentation while retaining code traceability enforcement)
- DOCUMENTS → GITHUB_ISSUE `785` (SCE-006 — Isolated Batch Trial Scheduling)
- DOCUMENTS → GITHUB_ISSUE `788` (SCE-002: publish the admitted experiment trial-plan contract)
- DOCUMENTS → GITHUB_ISSUE `790` (SCE-002: integrate trial realization with SDL instantiation and run provenance)
- DOCUMENTS → SPEC `contracts/schemas/plans/admitted-trial-plan-v1.json` (Admitted trial-plan contract the isolated-batch scheduler consumes (serial-default + isolation-proof, cleanup, timeouts))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/batch_execution.py` (SCE-006 batch execution receipt contract + plan-to-schedule isolation-proof and receipt validators)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_scheduler.py` (SCE-006 deterministic batch scheduling policy (canonical order + sealed-plan admitted ceiling) over the one-entry realization seam)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_coordinate_order.py` (SCE-006 single-owner canonical trial-coordinate dispatch order helper (SVR-014/SVR-031))
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/batch-execution-receipt-v1.json` (SCE-006 published batch-execution-receipt-v1 contract (immutable per-attempt scheduling + cleanup evidence))
- TESTS → TEST `implementations/python/tests/test_sce_006_batch_scheduler.py` (SCE-006 batch scheduler tests: deterministic order, sealed-plan isolation authority, receipt validation, conformance corpus)
