---
id: RUN-308
title: "Concurrent Participant Execution"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:15:47.508932Z
updated_at: 2026-06-20T18:23:28.229464Z
---

# RUN-308 — Concurrent Participant Execution

## Statement

The runtime shall support concurrent participant execution and interaction over shared scenario state.

## Rationale

Requirement inventory expansion. Multi-participant experiments require runtime support for concurrent behavior over shared state.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `74` (Participant runtime: state/history, lifecycle, shared state, concurrency (RUN-305-308))
- DOCUMENTS → PULL_REQUEST `414` (PR #414: docs: add participant runtime design)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-054-participant-runtime-observable-lifecycle.md` (ADR-054: Participant Runtime Observable Lifecycle)
- DOCUMENTS → SPEC `specs/formal/participant-runtime/README.md` (Participant Runtime Formal Design)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-joint-action-record-v1.json` (Participant joint-action record schema v1)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-time-management-context-v1.json` (Participant time-management context schema v1)
- TESTS → TEST `implementations/python/tests/test_run_308_concurrent_participant_execution.py` (RUN-308 concurrent participant execution contract tests)
- TESTS → TEST `implementations/python/tests/test_participant_backend_contracts.py` (Participant backend runtime contract regression tests)
- DOCUMENTS → GITHUB_ISSUE `1101` (Transactional rollback for concurrent participant reservations)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1101-concurrent-participant-rollback-preflight.md` (Concurrent batch rollback architecture and nonclaims)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_concurrency.py` (Batch-scoped reservation and snapshot rollback)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_concurrent_state.py` (Revision-safe snapshot merge and delta service accounting)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_concurrent_settlement.py` (Pre-dispatch rollback and post-dispatch indeterminate settlement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_autonomous_execution.py` (Compiled action-interaction footprints and explicit concurrent composition authority)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Authored participant-interaction commutativity and merge-rule declarations)
- TESTS → TEST `implementations/python/tests/test_participant_concurrent_batch_reservations.py` (Concurrent reservation failure and rollback regressions)
- TESTS → TEST `implementations/python/tests/test_issue_1373_history_consumers.py` (Stored shared-state and concurrency references retain validation)
