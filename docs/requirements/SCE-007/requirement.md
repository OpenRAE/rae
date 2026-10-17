---
id: SCE-007
title: "Portable Clean-State And Cleanup Contracts"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-07-22T01:49:14.836945Z
updated_at: 2026-07-24T16:19:35.368724Z
---

# SCE-007 — Portable Clean-State And Cleanup Contracts

## Statement

RAES shall publish backend-neutral contracts that carry clean-state requirements and scoped cleanup obligations from an admitted trial entry into distinct execution attempts, record cleanup outcomes independently from the primary trial outcome, require evidence-bounded clean or reusable-state claims, prevent unsafe retries after non-idempotent effects, declare backend cleanup and verification capability, and default scheduling to serial unless complete isolation evidence admits bounded parallelism. Required cleanup shall not be silently skipped or downgraded, and the contracts shall not create a second scenario lifecycle or imply universal environmental reversal.

## Rationale

SCE-006 schedulers need a portable, falsifiable contract for clean initial state, cleanup, retry safety, backend capability, residual disclosure, and isolation proof before scheduler policy can safely dispatch or reuse trial environments.

## Traceability

- DOCUMENTS → SPEC `specs/formal/scenario-variation-trial-realization/cleanup-contracts.md` (Portable Clean-State And Cleanup Contracts)
- IMPLEMENTS → SPEC `contracts/schemas/plans/trial-cleanup-plan-v1.json` (Trial cleanup plan v1 schema)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/trial-cleanup-receipt-v1.json` (Trial cleanup receipt v1 schema)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/scheduler-isolation-proof-v1.json` (Scheduler isolation proof v1 schema)
- IMPLEMENTS → SPEC `specs/formal/scenario-variation-trial-realization/cleanup-contracts.md` (Portable Clean-State And Cleanup Contracts)
- IMPLEMENTS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v2.json` (Backend manifest v2 cleanup capability schema)
- TESTS → TEST `implementations/python/tests/test_sce_006_cleanup_contracts.py` (SCE-007 cleanup contract conformance tests)
- IMPLEMENTS → GITHUB_ISSUE `658` (SCE-007 — Portable clean-state and cleanup contracts for trials)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_cleanup.py` (Cleanup plan, receipt, and isolation models and the plan/receipt validator)
- TESTS → TEST `implementations/python/tests/test_sce_006_batch_scheduler.py` (Batch receipt join accepts truthful cleanup failure and rejects false success)
- TESTS → TEST `implementations/python/tests/test_sce_002_trial_realization.py` (Archival run join keeps truthful cleanup failure separate from the primary outcome)
- IMPLEMENTS → GITHUB_ISSUE `1612` (fix(contracts): accept truthful required-cleanup failure receipts)
