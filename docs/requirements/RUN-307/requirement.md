---
id: RUN-307
title: "Shared Operational State Model"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:15:47.404051Z
updated_at: 2026-06-20T05:57:33.819954Z
---

# RUN-307 — Shared Operational State Model

## Statement

The runtime shall provide a portable shared operational state model for evolving participant and environment state.

## Rationale

Requirement inventory expansion. Participant behavior depends on shared evolving state that cannot be left implicit.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `74` (Participant runtime: state/history, lifecycle, shared state, concurrency (RUN-305-308))
- DOCUMENTS → PULL_REQUEST `414` (PR #414: docs: add participant runtime design)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-054-participant-runtime-observable-lifecycle.md` (ADR-054: Participant Runtime Observable Lifecycle)
- DOCUMENTS → SPEC `specs/formal/participant-runtime/README.md` (Participant Runtime Formal Design)
- IMPLEMENTS → PULL_REQUEST `562` (PR #562: feat(runtime): add shared operational state snapshots)
- IMPLEMENTS → GITHUB_ISSUE `194` (Issue #194: Shared Operational State Model (RUN-307))
- IMPLEMENTS → SPEC `contracts/schemas/snapshots/runtime-snapshot-v1.json` (Runtime snapshot schema with first-class shared-state fields)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-shared-state-record-v1.json` (Participant shared-state record schema with revision/digest discipline)
- IMPLEMENTS → CONFIG `contracts/schema-publication-manifest.json` (Schema publication manifest entries for RUN-307 shared-state schemas)
- TESTS → TEST `implementations/python/tests/test_run_307_shared_operational_state.py` (RUN-307 shared operational state regression tests)
- TESTS → TEST `implementations/python/tests/test_issue_1373_history_consumers.py` (Stored shared-state and concurrency references retain validation)
