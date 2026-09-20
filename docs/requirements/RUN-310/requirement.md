---
id: RUN-310
title: "Intervention, Handoff, And Supervisory Lifecycle"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-04-03T06:15:47.797106Z
updated_at: 2026-07-26T14:14:31.531499Z
---

# RUN-310 — Intervention, Handoff, And Supervisory Lifecycle

## Statement

The runtime shall support ordered lifecycle transitions for supervision, approval or denial, external direction, intervention, controller handoff, override, and cancellation in mixed-control participant execution, including stale and conflicting decisions, append-only evidence, and explicit relationship to admission, execution, and observation.

## Rationale

Issue #794 clarifies that behavior mode is not controller state and that supervisory actions require explicit validity, ordering, idempotency, conflict, provenance, and evidence semantics.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1016` (Coordinate admitted mixed-runtime phase and controller handoff)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/mixed_runtime_phase.py` (Bounded evaluator-driven phase progression and handoff evidence)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/mixed_runtime_lifecycle.py` (Pre-effect participant-provider cut and lifecycle result evidence)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_episode_control.py` (Active admitted participant-provider lifecycle routing)
- TESTS → TEST `implementations/python/tests/test_issue_1016_mixed_runtime_coordination.py` (Stale, idempotent, bounded, and failed handoff witnesses)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1013` (Compose the existing RUN-310 authority in SEM-234 without changing its runtime contract)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/cross-backend-participant-control.md` (Revisioned mixed-composition compatibility boundary)
- TESTS → TEST `implementations/python/tests/test_sem_234_mixed_composition.py` (Bounded composition with incumbent RUN-310 authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_boundary.py` (RUN-310 control-ingress lifecycle enforced at the final sink)
- TESTS → TEST `implementations/python/tests/test_issue_1003_final_sink_flow_enforcement.py` (RUN-310 control-ingress final-sink enforcement tests)
- IMPLEMENTS → GITHUB_ISSUE `1003` (Issue #1003 enforce participant flow policy at final runtime sinks)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_mediation.py` (RUN-310 supervisory lifecycle mediation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_control_history.py` (RUN-310 append-only control-history invariants)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_targets.py` (RUN-310 control target resolution)
- TESTS → TEST `implementations/python/tests/test_run_310_supervisory_lifecycle.py` (RUN-310 supervisory lifecycle tests)
- IMPLEMENTS → GITHUB_ISSUE `255` (Intervention, Handoff, And Supervisory Lifecycle (RUN-310))
