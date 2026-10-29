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

# Portable clean state and cleanup

## Statement

RAES shall publish backend-neutral contracts for clean state and cleanup.
The contracts shall carry clean-state requirements and scoped cleanup obligations from an admitted trial entry into distinct execution attempts.
They shall record cleanup outcomes separately from the primary trial outcome.
Clean or reusable-state claims shall require bounded evidence.
The contracts shall prevent unsafe retries after non-idempotent effects.
They shall declare backend cleanup and verification capability.
Scheduling shall default to serial execution.
Complete isolation evidence may admit bounded parallel execution.
Required cleanup shall not be silently skipped or made best effort.
The contracts shall not create a second scenario lifecycle.
They shall not imply that all environmental changes can be reversed.

## Rationale

SCE-006 schedulers need contracts that can be checked before they dispatch or reuse trial environments.
The checks cover clean initial state, cleanup, retry safety, backend support, residual state, and isolation.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_controls.py` (Derive trial supervision requirements from admitted controls and cleanup retry policy.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/trial_control_admission.py` (Require declared cleanup and supervision support before trial admission.)
- TESTS → TEST `implementations/python/tests/test_issue_1628_trial_control_admission.py` (Test required and best-effort cleanup, retry guarantees, and atomic refusal.)

- DOCUMENTS → SPEC `specs/formal/scenario-variation-trial-realization/cleanup-contracts.md` (Portable Clean-State And Cleanup Contracts)
- IMPLEMENTS → SPEC `contracts/schemas/plans/trial-cleanup-plan-v1.json` (Trial cleanup plan v1 schema)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/trial-cleanup-receipt-v1.json` (Trial cleanup receipt v1 schema)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/scheduler-isolation-proof-v1.json` (Scheduler isolation proof v1 schema)
- IMPLEMENTS → SPEC `specs/formal/scenario-variation-trial-realization/cleanup-contracts.md` (Portable Clean-State And Cleanup Contracts)
- IMPLEMENTS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v2.json` (Backend manifest v2 cleanup capability schema)
- TESTS → TEST `implementations/python/tests/test_sce_006_cleanup_contracts.py` (SCE-007 cleanup contract conformance tests)
- IMPLEMENTS → GITHUB_ISSUE `658` (SCE-007 — Portable clean-state and cleanup contracts for trials)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_cleanup.py` (Cleanup plan, receipt, and isolation models and the plan/receipt validator)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_trial_cleanup_validation.py` (Reset-retry and receipt result coverage and trigger-consistency checks)
- TESTS → TEST `implementations/python/tests/test_sce_006_batch_scheduler.py` (Batch receipt join accepts truthful cleanup failure and rejects false success)
- TESTS → TEST `implementations/python/tests/test_sce_002_trial_realization.py` (Archival run join keeps truthful cleanup failure separate from the primary outcome)
- IMPLEMENTS → GITHUB_ISSUE `1612` (fix(contracts): accept truthful required-cleanup failure receipts)
