# Participant Bisimulation Current-State Assessment

Historical #811 assessment. ADR-100’s #971 amendment selects the
[executable rev2 target](theorem-selection.md) for downstream work.

Date: 2026-07-29

Parent issue: [#811](https://github.com/OpenRAE/rae/issues/811).

## Available Authority

ADR-081 and `raes-behavioral-relations@rev5` already distinguish strong and
weak bisimulation from traces, projections, probes, refinement, information
flow, and opacity. `BehavioralClaimBindingModel` separates carriers,
projection, quantifier scope, evidence scope, relation-parameter profile,
assurance axis, limitations, and nonclaims.

ADR-085, ADR-095, and SEM-230 revision 2 supply the participant/audience
projection coordinates, exact-cut policy, label classes, memory, order,
declassification, scheduler/environment boundary, and noninterference
nonclaims. SEM-231 adds the observer-relative opacity boundary without making
opacity a bisimulation.

API-423 supplies typed crossing request, decision, transformation, delivery,
observation, and audit occurrences. RUN-319 supplies the reference mediation
stages: authenticated binding, exact-cut resolution, independent fail-closed
gates, effective capability support, idempotency, replay protection,
append-only histories, and atomic persistence.

## Missing Authority

Before #811, the repository has:

- no normative pair of LTSs for an equivalence result;
- no exact divergence-preserving branching relation identity;
- no closed theorem profile naming a complete quantified carrier;
- no checked mapping from the concrete formal LTS to the live runtime;
- no pinned equivalence-check command or proof evidence contract; and
- no requirement that a machine-checkable bisimulation result be delivered.

The test-local SEM-230 falsification helper is not a normative LTS. ASR-535
finite cases and backend probes remain falsification or conformance evidence.
Source and artifact digests establish identity, not behavior.

## Boundary Findings

The complete reference runtime is broader than the modeled crossing kernel.
It includes HTTP/error behavior, schedulers, persistence paths, backend
interactions, UUIDs, timestamps, audit-only facts, and operational
bookkeeping. Those facts cannot all be hidden without a governed projection
and divergence argument.

Two backends are even less suitable for the first theorem because their
internal transition surfaces are uncontrolled. A policy-pair or purge lemma
needs a separate closed policy carrier and information-flow preservation
argument.

The bounded crossing-kernel surface is already split across independent
semantic, contract, and runtime authorities. It is the smallest target that is
both scientifically meaningful and achievable.

## Adopted Response

ADR-100:

- adds `divergence-preserving-branching-bisimulation` in taxonomy `rev6`;
- selects a complete finite SEM-230 abstract crossing LTS and an independently
  derived API-423/RUN-319 concrete formal LTS;
- fixes `participant-crossing-dpbb-finite-v1@rev1`;
- keeps live-runtime mapping and backend conformance separate;
- selects pinned mCRL2 finite equivalence checking; and
- allocates the mandatory result and independent reproduction to SEM-232
  child work.

No result is reported by this assessment.
