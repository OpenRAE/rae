---
id: SEM-223
title: "Participant Budget, Quota, And Exhaustion Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:33.596128Z
updated_at: 2026-10-09T00:00:00Z
---

# SEM-223 — Participant Budget, Quota, And Exhaustion Semantics

## Statement

The ecosystem shall define explicit semantics for participant budgets, quotas, resource consumption, exhaustion, and limit-triggered effects or termination.

## Rationale

Primary-source refresh shows that budgeted interaction is not just metadata; it affects what participants may do and how benchmark outcomes are interpreted.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-episode-model/README.md` (Participant episode + budget model formal design (issue #122))
- IMPLEMENTS → GITHUB_ISSUE `306`
- DOCUMENTS → SPEC `specs/formal/participant-semantics/autonomous-execution.md` (SEM-223 consumption, exhaustion, limit-effect, and reset-scope semantics with traceability table)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_resource_exhaustion.py` (Derived exhaustion and fail-closed budget-event, governed-attempt, and disclosure checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_resource_reservation.py` (Typed logical-budget rejection distinct from shared-pool throttling)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_resource_accounting.py` (Generation-fenced, exactly-once settlement and crossed-boundary reconciliation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_resource_rejection.py` (Undispatched SEM-211 resource_exhausted attempt)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_pre_dispatch.py` (Shared rejected-attempt behavior history record)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_resources.py` (Scheduler routing of budget rejections into governed attempts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_operations.py` (Pre-dispatch admission of rejected attempts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_lifecycle.py` (Episode-boundary reconciliation at shared-clock reset)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_result_contracts.py` (Runtime result and history-transition enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/snapshot_semantics.py` (Published runtime-snapshot SEM-223 conformance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_resource_budgets.py` (Authored participant-owned parent rule)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_resource_budget_owners.py` (Participant-local owner scope)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_resource_validation.py` (Contract participant-owned parent rule)
- TESTS → TEST `implementations/python/tests/test_issue_306_participant_budget_exhaustion.py` (Exhaustion, effect, reset-scope, owner, disclosure, and conformance positives and negative fixtures)
- TESTS → TEST `implementations/python/tests/test_issue_306_participant_budget_oracle.py` (Differential accounting oracle and traceability-table sync)
