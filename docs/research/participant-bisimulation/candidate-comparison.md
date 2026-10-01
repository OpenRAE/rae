# Participant Bisimulation Candidate Comparison

Historical #811 assessment. ADR-100’s #971 amendment selects the
[executable rev2 target](theorem-selection.md) for downstream work.

Date: 2026-07-29

Every candidate is evaluated against the same minimum surface: explicit state
spaces, initial relation, transition and enabledness assumptions, closed
labels/projection, exact relation, divergence/deadlock/termination semantics,
model dimensions, witness family, preserved properties, and runtime mapping.

## 1. Abstract SEM-230 Versus Complete Reference Runtime

- **Carriers:** full SEM-230 state versus every participant-relevant live
  runtime state and operational path.
- **Initial relation:** matching participant, audience, memory, policy cut,
  runtime snapshot, backend state, HTTP/error surface, and scheduler.
- **Transitions/enabledness:** every semantic and runtime operation, including
  persistence, retries, errors, audit, backend interaction, and scheduling.
- **Projection:** must disposition UUIDs, timestamps, errors, audit,
  persistence, and backend observations; none are automatically `tau`.
- **Exact relation:** divergence-preserving branching bisimulation would be
  appropriate only after the complete runtime carrier is formalized.
- **Dimensions:** concurrent, timed, scheduler- and backend-sensitive unless
  explicitly restricted.
- **Divergence:** must cover all live retry, wait, and worker loops.
- **Disposition:** future. The carrier is broader than current formal and
  mapping evidence.

## 2. Two Policy Configurations

- **Carriers:** two complete revisioned policy realizations over the same
  crossing semantics.
- **Initial relation:** matching participant/audience state and declared
  policy-low-equivalent cuts.
- **Transitions/enabledness:** every policy decision, release, transformation,
  change, retry, and memory effect in both configurations.
- **Projection:** one revisioned participant/audience observation function.
- **Exact relation:** depends on whether branching, divergence, secrecy, or
  only trace behavior is intended; equal projected histories are insufficient.
- **Dimensions:** policy change, supervisor visibility, strategies, memory,
  scheduler, time, and order remain profile coordinates.
- **Divergence:** hidden supervisor or policy loops must be matched.
- **Disposition:** future. No second closed policy carrier is selected by
  #811.

## 3. Abstract Crossing Versus Concrete Crossing Kernel

- **Carriers:** the complete finite abstract SEM-230 crossing operation and an
  independently formalized API-423/RUN-319 crossing kernel.
- **Initial relation:** the named idle `p0` states related by the profile
  abstraction map.
- **Transitions/enabledness:** closed finite request, decision,
  transform/declassify, delivery/observation, cut advance, and replay
  behavior; concrete validation, cut resolution, capability resolution,
  record preparation, and atomic commit are finite internal stages.
- **Projection:** one participant, audience, controller, episode, total order,
  exact cut, and closed visible/`tau` partition.
- **Exact relation:** divergence-preserving branching bisimulation.
- **Dimensions:** finite possibilistic branching, sequential, untimed,
  non-probabilistic, no fairness, no partial order, fixed controller, finite
  visible cut advance.
- **Divergence:** internal progress is ranked and finite; an added internal
  loop must fail.
- **Witness:** the concrete-to-abstract semantic abstraction graph, checked as
  a greatest fixed point rather than assumed.
- **Mapping:** API-423/RUN-319 differential realization is separate.
- **Disposition:** selected. It is bounded without being a trace-only toy.

## 4. Two Backend Realizations

- **Carriers:** complete operational state of two controlled backend
  implementations.
- **Initial relation:** matching declared profiles, provisioned state,
  capabilities, scheduler/environment, and participant history.
- **Transitions/enabledness:** backend-native actions and refusals, including
  unavailable inputs and failure behavior.
- **Projection:** backend internals require governed hiding and a divergence
  argument.
- **Exact relation:** may require I/O alternating, branching, probabilistic,
  timed, or failure-aware semantics depending on ownership and behavior.
- **Dimensions:** concurrency, time, probability, resource scheduling, and
  partial order cannot be assumed away.
- **Divergence:** backend wait/retry loops are uncontrolled.
- **Disposition:** rejected as the first theorem. API-407 declarations and
  finite conformance do not expose a complete carrier.

## 5. High-Action Hidden Versus Purge/Restriction

- **Carriers:** one high-action system after hiding versus a policy-purged or
  restricted system.
- **Initial relation:** matching policy-low-equivalent states, memory, cut,
  release schedule, low strategy, and environment.
- **Transitions/enabledness:** every high/low action, supervisor decision,
  declassification, purge, retry, and observation.
- **Projection:** SEM-230 low observation; a hidden action still needs explicit
  divergence treatment.
- **Exact relation:** a named branching relation may support a
  noninterference lemma, but policy noninterference remains a separate
  hyperproperty.
- **Dimensions:** adaptive strategies, schedulers, memory, release, order,
  time, and probability must match SEM-230.
- **Divergence:** high-only divergence can leak progress or termination.
- **Disposition:** future supporting lemma. It must not define
  noninterference into existence.

## Selection

Candidate 3 is selected as
`participant-crossing-dpbb-finite-v1@rev1`. The formal specification gives the
exact finite domains, states, transition schemas, labels, relation,
abstraction map, preserved properties, and nonclaims.
