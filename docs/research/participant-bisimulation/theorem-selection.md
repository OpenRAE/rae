# Participant-Crossing Theorem And Profile Selection

Date: 2026-07-29. Amended by #971 on 2026-09-27 under ADR-100.

## Selected Statement

The downstream proof obligation is to establish, for the complete reachable carrier of
`participant-crossing-dpbb-finite-v1@rev2`, the initial state of
`sem-230-participant-crossing-abstract@rev2` and the initial state of
`api-423-run-319-crossing-kernel@rev2` under
`participant-crossing-projection@rev1` satisfy relation id
`divergence-preserving-branching-bisimulation`. The evidence boundary is that
exact complete finite profile; this design does not report the result.

The executable domains, transition schemas, and completion semantics are in
[the rev2 model authority](../../../specs/formal/participant-semantics/participant-crossing-models.md).
The [original specification](../../../specs/formal/participant-semantics/participant-crossing-bisimulation.md)
retains the relation clauses and projection. Its candidate abstraction is
historical design input, not an established witness for the executable models.

## Why This Is A Final Finite Target

The profile's participant, audience, controller, episode, request, policy-cut,
input, decision, replay, delivery, time, order, and scheduler domains are
closed and finite. Both LTSs are the least reachable fixed points of their
transition schemas. Downstream enumeration continues until no new state or
transition exists; it does not stop at a trace depth, test count, elapsed time,
or selected schedule.

Consequently, exhaustive equivalence checking is final for this exact
quantified carrier. It remains silent about every excluded dimension.

## Construction Boundary

The abstract model is hand-authored from SEM-230 and reviewed as formal
authority. The concrete model is independently authored from API-423/RUN-319
stages. They share only the closed relation profile and label projection.

The live Python runtime is not used to generate the abstract model. Its
differential mapping to the concrete model is separate child work. A source
digest is a drift alarm, not a mapping proof.

## Relation And Projection

Ordinary weak bisimulation is too weak for this target: the branching point
before visible permit/refusal behavior matters, and an infinite internal loop
must not match finite mediation. Strong bisimulation is too strong because the
selected participant does not observe finite validation, resolution,
capability, record-preparation, or atomic-commit stages.

The exact relation is therefore
`divergence-preserving-branching-bisimulation`. A redacted occurrence, refusal,
unsupported outcome, replay rejection, delivery, observation, cut advance,
deadlock, and termination are not internal labels.

## Preservation Boundary

A positive result preserves visible branching, enabled visible choices,
visible order, finite internal stuttering, structural deadlock, explicit
termination/refusal, and explicit divergence for this profile.

It does not establish:

- live-runtime realization or backend behavior;
- policy noninterference or predicate opacity;
- time, probability, fairness, true concurrency, partial order, or controller
  handoff; or
- any carrier larger than the declared complete finite domain.

Noninterference or opacity may use the result only after a separate theorem
shows matching secret, low-equivalence, observer, memory, release, strategy,
and environment coordinates.
