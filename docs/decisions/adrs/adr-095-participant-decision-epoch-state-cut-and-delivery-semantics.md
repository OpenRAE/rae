# ADR-095: Participant Decision Epoch, State-Cut, And Delivery Semantics

## Status

accepted

## Date

2026-07-26

## Classification

Classification: FM3

Required artifacts: an explicit labelled-transition model, separately typed
order coordinates, a versioned participant-decision contract, participant and
assurance projections, cut-relative information-flow decisions, delivery and
admission bindings, positive and adversarial fixtures, bounded behavioral
models, migration guidance, revision-pinned lineage, and clause-to-test
evidence.

Waivers: issue #909 does not claim a universal simulation, refinement,
bisimulation, noninterference, epistemic, strategic, probabilistic, timed, or
partial-order proof. It does not add a theorem prover, model checker, scheduler,
agent implementation, backend transport, policy engine, world-state store, or
participant-history authority.

## Context

ADR-013 separates participant episodes from workflow, control-plane, and
backend lifecycles. ADR-022 separates world truth, participant-relative view,
participant local history, and archival evidence. ADR-054 defines participant
runtime occurrences, delivery bases, local-history order, partial order, and
participant-relative hiding. ADR-083 defines a participant decision surface
`D(p,e,o)`. ADR-085 defines revisioned participant information-flow crossings.
ADR-081 prevents bounded execution evidence from being reported as simulation,
refinement, bisimulation, or universal noninterference.

The first executable SEM-220 contract made the abstract coordinate `o` an
integer named `observation_order`. Its reference implementation used that
integer as:

- the index of one participant behavior-history occurrence;
- the order coordinate for selecting effective visibility;
- the order coordinate for projection-policy and authorization validity;
- the upper bound for realized delivery;
- the identity of a participant decision surface and its selection; and
- a label embedded in context, evidence, and provenance references.

Those meanings agree only in a single serialized fixture where every semantic
transition advances one shared counter. They do not agree in the RAES runtime.
One participant action produces several behavior occurrences, policy changes
need not coincide with participant decisions, and partial or causal order need
not have one privileged linearization.

The conflation also excluded the initial participant decision. Immediately
after RUN-311 reaches `episode_running`, compiled `V_p,0` exists but the new
episode has no participant behavior occurrence. Requiring a behavior-history
index either fabricates behavior or leaves the first action outside the
governed decision loop.

Changing `observation_order` in place to mean a per-episode decision ordinal
would repair that one symptom while silently changing SEM-226 policy timing,
delivery timing, historical v1 payload meaning, and the observation projection
used by future simulation and noninterference arguments. Issue #909 therefore
requires a new semantic contract rather than another interpretation of the v1
field.

## Decision

### 1. Type every order domain independently

For participant `p`, episode `e`, decision epoch `k`, runtime state `q`, and
participant-relative state cut `c`, the decision surface is:

```text
D(p, e, k) = Pi[p, audience, policy-decision, c](q)
```

The following coordinates are distinct:

| Coordinate | Meaning |
| --- | --- |
| episode identity and generation | The RUN-311 scope created by initialize, reset, or restart. |
| decision epoch `k` | Zero-based participant choice opportunity within one episode. |
| state cut `c` | The exact total-order prefix or partial/causal frontier from which the surface is derived. |
| derivation anchor | A trusted lifecycle or terminal-observation occurrence witnessing `c`. |
| policy decision | The projection/exposure-policy revision resolved as effective at exactly `c`. |
| surface occurrence | The identity of the derived participant view and its assurance projection. |
| disclosure decision | The SEM-226 authorization for releasing each participant-view item. |
| delivery occurrence | Evidence that the participant-facing view crossed the participant boundary. |
| participant observation | The declared delivery/acknowledgement fact admitted to local history. |

An integer from one row cannot satisfy another row merely because the current
reference backend serializes both. Every serialized order field names its
domain. A scalar is valid only for a declared total or backend-serialized order.
A partial or causal cut carries its frontier and relation identity.

### 2. Establish an explicit reactive decision lifecycle

The portable sequential lifecycle is:

```text
episode_initialized | episode_reset | episode_restarted
  -> episode_running
  -> derive D(p,e,0) from V_p,0 and the empty behavior cut
  -> authorize participant projection
  -> disclose
  -> deliver or explicitly declare emission-is-delivery
  -> participant observes the surface
  -> participant proposes/selects from that delivered surface
  -> validate and admit the proposal
  -> action_attempted
  -> state_transition_recorded
  -> terminal observation_emitted
  -> derive D(p,e,1) from that exact terminal-observation cut
```

Projection is not disclosure. Disclosure is not delivery. Delivery is not
participant acknowledgement or interpretation. Presentation is not selection.
Selection is not admission. Admission is not an attempt or outcome. A carrier
or runtime helper may combine occurrences only when it declares the applicable
ADR-054 delivery basis and preserves the individual semantic facts.

`episode_running` is the readiness anchor for `D(p,e,0)`. Its state cut is the
complete current participant-episode lifecycle prefix and an empty
current-episode participant-behavior history. A later surface is anchored by
the exact current terminal `observation_emitted` occurrence and the complete
current-episode behavior prefix. The derived decision epoch equals the number
of completed terminal observations in that episode. Callers do not author it.

### 3. Publish v2 and preserve historical v1 meaning

`participant-decision-surface-v1` retains its published historical meaning:
`observation_order` identifies the selected occurrence in the supplied
time-indexed behavior history. It remains available for historical validation
and migration but is not actionable through the new runtime-admission path.

`participant-decision-surface-v2` is the actionable contract. It does not carry
`observation_order`. It contains:

1. a participant-facing view with participant, episode, `decision_epoch`,
   information-state identity, visible context, action entries, affordances,
   selection form, markings, redaction, and disclosed limitations;
2. an assurance projection with the typed derivation anchor and state cut,
   policy-at-cut decision, apparatus and boundary refs, exact exposure
   bindings, participant-memory scope and reset authority when applicable,
   evidence, provenance, and the canonical participant-view digest;
3. an explicit lifecycle state, initially `projected`; and
4. a delivery occurrence when the lifecycle state is `delivered`.

The canonical digest uses the incumbent RFC 8785/JCS contract-digest helper. It
binds the exact participant-facing bytes and meaning to assurance, delivery,
selection, and admission without exposing assurance-only metadata.

V1-to-v2 migration is not a field rename. A v2 surface must be reprojected from
the current trusted runtime snapshot and exact policy authorities. A historical
v1 record may remain historical evidence; it cannot be made actionable by
copying its `observation_order`.

### 4. Separate participant information from verifier evidence

The participant-facing view is the low observation. Derivation event ids,
history prefix length, anchor-local order, policy-decision records, raw
authorization records, evidence refs, and provenance refs belong to the
assurance projection. They enter the participant-facing view only through an
independent SEM-226 exposure decision.

This separation is semantic, not cosmetic. Action presence, absence, ordering,
eligibility, constraint values, rejection detail, refresh behavior, surface
identity, and metadata can all convey information. The participant projection
therefore includes every field actually delivered to the participant, and the
assurance projection cannot be serialized as participant payload by default.

### 5. Resolve information-flow decisions at exact cuts

Projection-policy selection, exposure-policy selection, item authorization,
declassification, marking, and realized delivery are evaluated at an exact
state or delivery cut. Their authoritative resolver returns a decision bound to
that cut. A decision epoch is never used as a policy-effective order unless a
future policy contract explicitly declares `decision_epoch` as its order
domain.

A later policy revision cannot authorize an earlier projection or delivery. A
delivery-time decision is resolved again at the delivery cut; it cannot inherit
the derivation-time result merely because both occur within one decision epoch.
Unknown, stale, cross-policy, cross-cut, and incomparable coordinates fail
closed.

### 6. Make delivery a prerequisite for actionable selection

A projected surface is a valid derived artifact but is not yet an actionable
participant occurrence. A delivered surface carries a trusted delivery record
that agrees on:

- participant, episode, decision epoch, and surface identity;
- canonical participant-view digest;
- delivery basis and exact delivery cut;
- participant observation reference; and
- evidence, provenance, markings, and limitations.

A v2 selection binds surface identity, decision epoch, participant-view digest,
and delivery ref. Runtime admission re-resolves both the derivation anchor and
delivery record against current authority before action-shape, apparatus,
SEM-211, and backend admission checks. An undelivered, stale, replayed, reset,
restarted, terminated, superseded, forged, or cross-scope surface fails before
participant behavior is written.

### 7. Define the backend realization obligation directionally

Let `A` be the abstract RAES participant transition system and `B` a conformant
backend realization. The intended universal soundness relation remains:

```text
ParticipantProject(Traces(B)) subseteq Traces(A)
```

A concrete-to-abstract refinement mapping or forward simulation may establish
that inclusion by relating every concrete start state and step to an abstract
state and step sequence. `D(p,e,0)` supplies the required initial related
decision state. The decision epoch is stable under insertion of governed
backend-internal or evidence `tau` steps; the derivation cut witnesses the
concrete state used by the relation.

Trace inclusion alone permits an implementation that refuses required inputs.
For actionable participant interaction, a conformance or proof claim must also
state input/output ownership and action-availability obligations. Participant
proposals are inputs to the runtime; participant views and observations are
outputs; backend/environment/scheduler choices are separately controlled.
I/O simulation or alternating refinement is the intended stronger seam.

Current conformance remains bounded-probe evidence. It does not establish the
universal trace or simulation obligation.

### 8. Keep bisimulation optional and projection-relative

Two conformant backends may realize different behaviors allowed by RAES and
need not be bisimilar. Bisimulation is appropriate only for an explicitly
claimed substitutability or behavioral-equivalence result.

Strong bisimulation requires exact bidirectional label matching. Weak or
branching bisimulation requires a governed participant-relative `tau` set and
matching through hidden closure. A claim also declares divergence, termination,
progress, timing, probability, strategy, scheduler, and partial-order
treatment. Adding a hidden internal occurrence must not change decision epoch
or participant-view identity. Equal sampled traces, equal digests, or one
successful participant loop are not bisimulation.

### 9. Treat participant control as reactive information flow

SEM-230 noninterference is a hyperproperty over sets of runs. For autonomous or
human participants, future inputs depend on prior participant-visible history.
A complete reactive claim therefore quantifies over participant strategies
that map local histories to action choices or distributions, not only over
fixed open-loop input sequences.

The baseline strategy-relative obligation fixes participant, audience, policy
sequence, environment class, scheduler class, order model, declassification
schedule, and a class of low strategies. High-state or unauthorized-high-input
variation must preserve the permitted participant-visible history support sets
for every strategy in that class. Probabilistic strategies require a separately
governed probability kernel and relation.

Bounded tests may falsify this relation on their enumerated model. They do not
prove universal reactive noninterference.

### 10. Separate episode-local progress from participant memory

Reset and restart create a new episode identity and restart its decision epoch
at zero. They do not erase an observation already delivered to a persistent
human, agent process, shared memory, or external controller.

Every information-flow, epistemic, replay, and strategy claim declares a
participant-memory scope:

- `episode_local_reset`, when the participant implementation and every
  participant-visible memory channel are authoritatively reset; or
- `persistent_across_episodes`, when prior local history remains part of the
  participant information state.

Omitting the memory scope invalidates a positive noninterference, perfect
recall, or epistemic claim across reset.

## Invariants

- `decision_epoch` is derived independently of lifecycle-history and
  behavior-history indexes.
- Every v2 surface has one participant, episode, state cut, policy decision,
  and canonical participant-view digest.
- An initial surface has decision epoch zero, an `episode_running` readiness
  anchor, and an empty current-episode behavior cut.
- A later surface is anchored by the exact current terminal observation and
  complete current-episode behavior cut.
- V1 `observation_order` is never reinterpreted as v2 `decision_epoch`.
- Policy, authorization, and delivery decisions match an exact cut; no
  decision-epoch comparison substitutes for cut ordering.
- Assurance-only coordinates are absent from the participant-facing view
  unless independently exposed.
- A projected surface cannot be selected or admitted until a trusted delivery
  occurrence is bound.
- Selection and admission bind the canonical participant-view digest and
  delivery ref.
- Reset/restart invalidates the prior episode's actionable surface and does not
  silently erase persistent participant knowledge.
- A total-order implementation does not foreclose a future partial/causal
  frontier carrier.
- Bounded execution evidence never promotes a simulation, bisimulation,
  noninterference, epistemic, strategic, timed, or probabilistic assurance
  state.

## Consequences

### Positive

- The participant loop has a truthful initial state and an inductive transition
  boundary suitable for simulation/refinement arguments.
- Backend-internal stuttering no longer changes participant decision identity.
- Dynamic policy and delivery timing cannot be manufactured from a decision
  ordinal.
- Participant payloads stop inheriting verifier-only history and evidence
  metadata.
- Adaptive agents fit the same participant semantics as humans, scripts, and
  RL policies without pretending their choices are deterministic.
- Future partial-order, probabilistic, strategic, and proof-bearing work has
  typed extension seams instead of another overloaded integer.

### Negative

- V2 is a new contract and Python/runtime API. Existing actionable consumers
  must reproject rather than relabel v1 data.
- Projection, delivery, and admission require more explicit authority
  resolution and evidence.
- The reference implementation and every SEM-220/SEM-226 consumer must migrate
  together.
- Strong assurance remains visibly unproved until its complete model and proof
  artifacts exist.

## Rejected Alternatives

### Redefine v1 `observation_order`

Rejected. Structural draft status does not make two incompatible semantic
domains identical. It would preserve a filename while breaking historical
meaning, SEM-226 timing, and behavioral comparability.

### Use the behavior-history head as the decision id

Rejected. One decision creates several behavior occurrences, hidden stuttering
changes the index, and partial order may have no unique head.

### Use decision epoch for policy validity

Rejected. Policies, interventions, and deliveries may change between decisions
or concurrently with backend work.

### Put the anchor in the participant payload

Rejected. Event ids, prefix lengths, and evidence topology can disclose hidden
activity. Assurance and participant observation have different audiences.

### Treat projection as delivery

Rejected as a default. A specific boundary may declare
`emission_is_delivery`, but the declaration and delivery occurrence remain
explicit and evidence-backed.

### Require bisimulation for every conformant backend

Rejected. RAES intentionally permits realization choice and nondeterminism.
Directional soundness plus declared availability obligations is the baseline;
bisimulation is a stronger optional claim.

## References

- [ADR-013](adr-013-participant-episode-lifecycle-boundaries.md)
- [ADR-022](adr-022-participant-behavior-and-interaction-semantics.md)
- [ADR-054](adr-054-participant-runtime-observable-lifecycle.md)
- [ADR-061](adr-061-published-schema-evolution-policy.md)
- [ADR-075](adr-075-ecosystem-versioning-deprecation-and-migration-governance.md)
- [ADR-081](adr-081-behavioral-relation-taxonomy-and-claim-discipline.md)
- [ADR-083](adr-083-participant-tool-decision-surface-and-exposure-semantics.md)
- [ADR-085](adr-085-participant-information-flow-and-control.md)
- `specs/formal/participant-semantics/README.md`
- `specs/formal/participant-semantics/information-flow-control.md`
- `specs/formal/participant-runtime/README.md`
- `specs/formal/behavioral-relations/README.md`
- [V2 migration guidance](../../explain/reference/participant-decision-surface-v2-migration.md)

Primary intellectual lineage is revision-pinned in
`contracts/provenance/sdl-lineage-ledger-v2.json`.

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-09-14 | #1210 | Advanced current lineage authority to ledger v2 for the progressive semantic cutover; v1 remains a dated historical record. |
