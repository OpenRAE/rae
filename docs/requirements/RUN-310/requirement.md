---
id: RUN-310
title: "Intervention, Handoff, And Supervisory Lifecycle"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-04-03T06:15:47.797106Z
updated_at: 2026-09-22T01:33:58.710054Z
---

# RUN-310 — Intervention, Handoff, And Supervisory Lifecycle

## Statement

The runtime shall support ordered lifecycle transitions for supervision, approval or denial, external direction, intervention, controller handoff, override, and cancellation in mixed-control participant execution, including stale and conflicting decisions, append-only evidence, and explicit relationship to admission, execution, and observation.

The runtime shall instantiate reusable permissions at the exact admitted
episode/state/authority/target/time cut. Each accepted control occurrence,
including a same-state occurrence, shall advance state revision exactly once;
rejection and idempotent retry shall not. It shall reject ambiguous order,
revalidate ordered contenders without rebasing, preserve atomic state/history/
receipt/audit commit and existing store-scoped retry identity, and enforce
validity, finite-script and resource bounds. Episode initialization, termination,
new-episode admission, process recovery and historical replay shall preserve
their distinct meanings and pinned policy/evidence, without reusing old
proposal decisions or rewriting history. All incumbent control entry paths
shall share this lifecycle relation while retaining independent effect gates.

## Rationale

Issue #794 clarifies that behavior mode is not controller state and that supervisory actions require explicit validity, ordering, idempotency, conflict, provenance, and evidence semantics.

Issue #1351 requires repeated cycles to bind fresh occurrence coordinates
without weakening revision fencing, recovery, authority or historical meaning.

## Semantic amendment and evidence boundary

[ADR-110](../../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
and [MC-01–MC-09](../../../specs/formal/participant-semantics/reusable-mixed-control.md)
define the #1351 amendment. ACTIVE records the accepted contract, not proof
that every amended clause is implemented. Existing code/schema links evidence
the legacy fixed-coordinate form; the new bounded tests evidence a design
projection. Executable adoption and historical readers must meet the
[migration contract](../../migration/reusable-mixed-control.md).

## Traceability

- IMPLEMENTS → SPEC `specs/formal/participant-semantics/reusable-mixed-control.md` (Revision-fenced application/replay semantic amendment; not runtime conformance)
- IMPLEMENTS → GITHUB_ISSUE `1351` (Semantic decision and canonical requirement amendment)
- DOCUMENTS → DOCUMENTATION `docs/decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md` (Accepted-on-merge policy/occurrence decision)
- DOCUMENTS → DOCUMENTATION `docs/migration/reusable-mixed-control.md` (Producer/reader and historical-meaning rules)
- DOCUMENTS → DOCUMENTATION `docs/research/reusable-mixed-control/cases.md` (Worked cycles and bounded evidence claims)
- TESTS → TEST `implementations/python/tests/test_issue_1351_mixed_control_design.py` (Bounded abstract-model falsification; not production realization)

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
- IMPLEMENTS → GITHUB_ISSUE `1069` (Controller handoff dispatched as a separately admitted control effect)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_effects.py` (Admitted effects routed to their incumbent lifecycle owners)
- TESTS → TEST `implementations/python/tests/test_issue_1069_participant_control_effects.py` (Governed handoff effect with idempotent replay)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control.py` (Runtime entry point for separately admitted effect dispatch)
