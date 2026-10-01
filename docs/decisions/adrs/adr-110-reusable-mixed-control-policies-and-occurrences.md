# ADR-110: Reusable Mixed-Control Policies and Occurrences

## Status

accepted

Acceptance takes effect when the delivery PR for
[#1351](https://github.com/OpenRAE/rae/issues/1351) merges. An unmerged copy is
proposed delivery state. This decision publishes semantics and canonical
requirement amendments; it does not declare executable adoption complete.

## Date

2026-09-22

## Classification

Classification: FM3

Required artifacts: [normative state relation and invariants](../../../specs/formal/participant-semantics/reusable-mixed-control.md),
[worked cases and verification limits](../../research/reusable-mixed-control/cases.md),
[bounded model and property cases](../../../implementations/python/tests/test_issue_1351_mixed_control_design.py),
[migration contract](../../migration/reusable-mixed-control.md), and canonical
ACT-617/API-409/RUN-310/DSL-142 amendments.

Waivers: production typed-IR/wire-contract and backend conformance evidence is
not claimed by this semantic-design delivery. Current published schemas and
implementations retain their existing fixed-coordinate semantics. The bounded
model is design falsification evidence, not runtime or transport conformance.

## Context

`MixedControlTransition` currently fixes expected/resulting revisions,
effective order and proposal references in an authored declaration. RUN-310
replays those declarations, and API-409 requires occurrence coordinates to equal
the declaration. Returning to the same named state cannot reuse the edge at a
new revision. Unrolling every possible visit is a finite script, not reusable
permission. The [preflight](../issue-1351-reusable-mixed-control-preflight.md)
also identifies source/destination-controller, direction-target, policy-revision
and order/time disagreements at the DSL-142 join.

The workflow model already separates a graph from its execution state. Shared
time already separates order, clocks, segments and progression. ADR-085/095,
ADR-104 and ADR-108 supply the authority, occurrence, exact-cut, atomic-commit
and effect boundaries; this decision uses those distinctions.

## Decision

Adopt `mixed-control-policy-occurrence/rev1`, defined by the normative contract.
ACT-617 owns reusable permitted transitions. API-409 owns immutable occurrences
with actual identity, revisions, targets, order, validity and evidence. RUN-310
applies one revision-fenced relation through its existing entry/commit paths.
DSL-142 joins direction/intervention delivery to the exact accepted occurrence.

Retain finite scripts as an explicit finite list of constraints over the same
relation. Reusable edges carry no preassigned traversal revision or future
proposal identity. Every accepted application, even a same-state one, increments
the state revision exactly once. Rejection and retry do not. Ambiguous order
has no implicit winner; ordered competitors are revalidated without rebasing.

Retain source-controller authority. In the new semantic form only handoff
changes controller identity, with occurrence-specific completion evidence and
independently valid destination authority. Authentication principals remain
distinct from controllers. Approval and denial target an exact live proposal;
direction permits declared proposal/action/control targets and intervention
permits action/control/attempt targets. Historical reference, authorizing
eligibility and state advancement are different relations.

Evaluate authority and typed validity at the trusted commit cut. Control order
is not time. Pin policy for an episode; retain store-scoped retry identity,
append-only history and original-policy replay. New episodes establish fresh
authority and proposal context without resetting causal budgets. Provider
handoff, clock replay, process recovery and new trials keep their own meanings.

Directed delivery pins disclosure policy independently of control policy and
consumes one exact application/binding permission. General injects remain
general orchestration. Admission, control acceptance, effect realization,
delivery and observation require separate evidence.

## Compatibility and migration

The linked migration contract governs both producers and readers. Legacy
fixed-coordinate declarations and v1 occurrences retain exact historical
meaning, including their compiled-policy replay dependencies. New semantic
forms require an explicit reader/discriminator boundary and coordinated
authoring/compiler/contract/runtime/consumer support. Unsupported readers fail
closed; there is no wildcard-revision or silently reusable interpretation.

An explicit conversion may retain a provably equivalent finite script. Making
it reusable, splitting a legacy approval/controller change into separate facts,
or repairing ambiguous time/controller joins requires author decisions. No
persisted occurrence is retagged, regenerated or rewritten. Live policy-format
upgrade within an episode is unsupported.

Canonical requirement statements and normative entry points are amended in
this delivery. Existing ACTIVE lifecycle status and legacy evidence are retained
with an explicit amendment boundary. No accepted prior ADR is silently edited.

## Alternatives Considered

- Unroll another declaration for every visit: retains the finite limitation.
- Drop expected revisions or use wildcard revisions: admits stale decisions.
- Infer policy form from omitted fields: silently changes old author intent.
- Treat a destination, operator principal or inject as a controller grant:
  bypasses the current authority owner.
- Build another workflow, clock, controller store or generic policy language:
  duplicates existing owners without resolving the occurrence join.

## Consequences

One permitted edge can govern repeated cycles while every application remains
precise and independently reviewable. Finite scenarios keep their bounded
intent, and old evidence stays interpretable under its original contracts.

Adoption requires coordinated versioned boundaries and evidence at real
consumers. The design and bounded tests prove no backend support, liveness,
universal security, physical cancellation, delivery, observation or exactly-once
external execution.
