# ADR-100: Proof-Bearing Participant-Crossing Bisimulation

## Status

accepted

## Date

2026-07-29

## Classification

Classification: FM3

Required artifacts: an exact relation identity, two independently derived
labelled-transition-system authorities, a closed participant/audience
projection, complete finite carrier bounds, a revisioned theorem profile,
machine-check and counterexample contracts, a runtime-mapping boundary,
independent reproduction, requirement ownership, and dependency-ordered
implementation work.

Waivers: issue #811 is design authority. It does not deliver either executable
LTS, an equivalence result, a proof certificate, a runtime mapping, backend
conformance, noninterference, or opacity. Those results remain blocked on
SEM-232 child work.

## Context

ADR-081 distinguishes strong and weak bisimulation from finite probes,
matching traces, and projected-history equality. ADR-085 and SEM-230 define
participant/audience-relative labels, projection, exact-cut policy,
declassification, memory, order, and policy noninterference. ADR-095 separates
decision, state cut, projection, delivery, and observation. API-423 defines the
portable participant-crossing occurrences; RUN-319 implements the reference
mediation boundary.

Those authorities do not state one exact pair of systems for a bisimulation
result. They also do not define which runtime bookkeeping is hidden, whether
hidden divergence matters, or what machine-check evidence would be final.
Schema equality, matching digests, projected traces, and bounded probes cannot
close that gap.

Issue #811 evaluates five possible theorem surfaces. The complete reference
runtime and uncontrolled backend implementations are too broad for a first
claim. A policy-pair or purge lemma would be useful only after its own closed
policy carrier and information-flow preservation theorem exist. The crossing
kernel is the smallest surface that already has semantic, contract, and
runtime mapping authorities.

## Decision

### 1. Select the crossing-kernel theorem

The first target is the complete finite abstract SEM-230 participant-crossing
LTS versus an independently derived formal concrete API-423/RUN-319
crossing-kernel LTS. The exact theorem profile is
`participant-crossing-dpbb-finite-v1@rev2`.

The theorem to be machine-checked by downstream work is:

> The declared initial states of
> `sem-230-participant-crossing-abstract@rev2` and
> `api-423-run-319-crossing-kernel@rev2` are
> divergence-preserving branching bisimilar under
> `participant-crossing-projection@rev1`, over the complete reachable carrier
> of `participant-crossing-dpbb-finite-v1@rev2`.

The #971 refinement closes request reuse, history advancement, event order,
and crossing completion in the [executable model authority](../../../specs/formal/participant-semantics/participant-crossing-models.md).
Rev1 remains the historical design sketch; downstream #972–#976 use rev2 of
both models and the profile, retaining projection rev1 and taxonomy rev8.
No rev1 executable bundle or equivalence result was published.

This is a theorem about two formal systems. A separate runtime-realization
claim must show that the live reference runtime maps to the concrete formal
system.

### 2. Add an exact relation identity

Behavioral-relation taxonomy revision `rev6` adds
`divergence-preserving-branching-bisimulation`. It is not an alias for ordinary
weak bisimulation. It preserves the branching point around visible behavior
and requires related states to agree on explicit infinite `tau` behavior.

For LTSs `L_A` and `L_C`, a symmetric relation `R` satisfies the branching
transfer clauses when every step from one related state is either:

- a `tau` step whose target remains related to the other state; or
- matched after a finite `tau` path on the other side whose intermediate
  branching state remains related, followed by the same visible label to a
  related target.

The explicit-divergence condition additionally requires an infinite `tau`
path that remains related to one opposite state to have matching divergent
behavior on the opposite side. The formal specification fixes the exact
transfer clauses and the checker semantics.

### 3. Close the first finite profile

The profile fixes one synthetic participant, audience, controller, episode,
request identity, and backend-independent crossing surface. It has two exact
policy cuts, five input classes, six decision values, one total
per-participant order, finite replay state, and finite delivery state.

`policy.cut.advance` is a visible environment action from `p0` to `p1`.
Controller handoff is excluded by fixing controller `c0`. Time, probability,
fairness, true concurrency, and partial order are excluded. The carrier is the
complete reachable fixed point of the declared finite transition schemas, not
a depth limit or sample.

One fresh operation uses the sole request identity once and retains its input.
Same-cut retries repeat the formal outcome protocol without another logical
commit; later-cut retries reject. One atomic result advances history h0 to h1;
h2/h3 are declared but unreachable. No identity recycling or head saturation
is admitted. Multiple fresh operations require the separate #1395 profile.
Transformation and declassification emit permit, change, delivery, then
observation. Refusal completes on its visible abstract decision. Terminal
means completion of one crossing, with retry/cut actions still enabled, rather
than global LTS termination. These are offline model semantics: no runtime
retry change, mandatory author proof work, or request-time checker is added.

The visible alphabet includes request, permit, deny, unsupported,
transformation, declassification, delivery, observation, later-cut replay
rejection, and policy-cut advance. A redacted occurrence remains visible.

Only these semantic classes are hidden:

- `internal.validate`;
- `internal.resolve-policy-cut`;
- `internal.resolve-capability`;
- `internal.prepare-record`; and
- `internal.atomic-commit`.

The exporter maps those five classes to the single checker action `internal`;
no other label is hidden. Every internal crossing path has a decreasing finite
progress rank, so a positive result must not erase an implementation-side
infinite internal loop.

### 4. Keep model construction independent

The abstract transitions are hand-reviewed formal authority derived from
SEM-230. The concrete transitions are independently derived from API-423 and
RUN-319 crossing stages. Both use the same closed label/projection profile, but
must not be generated from one table that already asserts correspondence.

The live-runtime mapping is a third artifact. It covers authenticated subject
binding, exact-cut resolution, independent gates, effective capability
support, transformed subjects, API-423 ordering, expected history heads,
atomic commit, refusal side effects, idempotency, and replay. Source digests
detect drift but do not prove the mapping.

### 5. Select an evidence-led toolchain

The finite equivalence decision uses mCRL2 `202607.0`:

```text
ltscompare --equivalence=dpbranching-bisim --tau=internal \
  abstract.aut concrete.aut
```

The child implementation must acquire the tool through checksum-verified
repository or immutable-container provenance, run without a shell or
verification-time network, and record exact input, source, profile, mapping,
tool, result, state-count, transition-count, mutation, and artifact digests.
The design does not invent an archive checksum before acquisition.

TLC remains suitable for auxiliary finite deadlock, replay, atomicity, and
progress properties, but property agreement is not bisimulation. Isabelle/HOL
is the proportionate future route for a parameterized or unbounded
coinductive theorem. The finite mCRL2 result is classified as `model-check`,
not `proof`.

A successful exit is not treated as a certificate the tool did not emit. The
exact pinned inputs plus a clean independent reproduction are mandatory.
Negative mutations require durable safe counterexamples; pure divergence
failures require an independent checked negative-result path if the selected
tool mode does not emit a diagnostic formula.

### 6. Separate every assurance claim

The formal result preserves visible branching behavior, enabled visible
choices, explicit termination/refusal, structural deadlock, and explicit
divergence for the named profile. It makes no claim about:

- the live runtime until differential mapping evidence exists;
- any backend until declaration, realization, and conformance evidence exists;
- SEM-230 policy noninterference or SEM-231 opacity without a separate
  profile-matching preservation theorem;
- time, probability, fairness, controller handoff, true concurrency, partial
  order, or inputs outside the complete named carrier; or
- the complete reference runtime beyond the crossing kernel.

Scientific-completeness and public proof claims remain blocked until the
positive result is independently reproduced.

### 7. Allocate requirement-backed work

SEM-232 (canonical Ground Control requirement id
`860b0b1e-55cc-42e6-9da8-b7eeeab7172c`) owns the machine-checkable result and
remains DRAFT. Downstream work is ordered:

- #971 — independent abstract and concrete formal models;
- #972 — reference-runtime mapping after #971;
- #973 — mutation and counterexample corpus after #971 and #972;
- #974 — finite equivalence decision after #971, #972, and #973;
- #975 — independent reproduction after #973 and #974; and
- #976 — scientific and public documentation after #974 and #975.

## Alternatives Considered

Use strong bisimulation. Rejected: finite validation, policy resolution,
capability lookup, record preparation, and commit bookkeeping are legitimately
internal to the selected participant projection.

Use ordinary weak bisimulation. Rejected: it can erase the branching point
before permit/refuse behavior and does not by itself preserve hidden
divergence.

Compare the abstract semantics with the complete live runtime. Rejected: the
first profile does not cover every HTTP error, scheduler, persistence,
backend, audit, timestamp, and operational path.

Compare two backend realizations. Rejected: backend internals are not governed
and cannot be declared `tau` by convenience.

Generate both LTSs from one correspondence table. Rejected: that would make the
equivalence result self-confirming.

Use matching temporal properties as the equivalence result. Rejected: two
systems can satisfy the same selected properties without being bisimilar.

## Consequences

RAES gains an exact, reproducible first bisimulation target and an honest path
to a positive machine-checkable result. The cost is a deliberately narrow
carrier and three independently reviewed boundaries: abstract model, concrete
model, and runtime mapping.

Revision `rev6` defines the relation and claim surface only. The catalog
assurance remains deliberately unproved and not model-checked until the child
program publishes its evidence.

## References

- [ADR-081](adr-081-behavioral-relation-taxonomy-and-claim-discipline.md)
- [ADR-085](adr-085-participant-information-flow-and-control.md)
- [ADR-095](adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md)
- [Participant-crossing formal authority](../../../specs/formal/participant-semantics/participant-crossing-bisimulation.md)
- [Candidate comparison](../../research/participant-bisimulation/candidate-comparison.md)
- [Proof-tool decision](../../research/participant-bisimulation/proof-tool-decision.md)
- R. van Glabbeek, B. Luttik, and N. Trčka, “Branching Bisimilarity
  with Explicit Divergence,” *Fundamenta Informaticae* 93(4), 2009,
  [doi:10.3233/FI-2009-109](https://doi.org/10.3233/FI-2009-109).

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-09-27 | #971 | Select executable profile/model rev2 and close the approved single-operation retry, history, ordering, and completion semantics; retain projection rev1 and separate runtime mapping. |
