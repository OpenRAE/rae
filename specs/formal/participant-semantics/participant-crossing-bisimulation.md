# Participant-Crossing Bisimulation

Requirement: SEM-232.

Decision:
[ADR-100](../../../docs/decisions/adrs/adr-100-participant-crossing-bisimulation.md).

Historical profile sketch: `participant-crossing-dpbb-finite-v1@rev1`.

Relation catalog: `raes-behavioral-relations@rev8`,
`divergence-preserving-branching-bisimulation`.

Status: historical rev1 state/transition sketch. The relation clauses and
projection remain applicable. ADR-100's #971 amendment selects executable
profile/model rev2 as the downstream target. No equivalence, proof,
runtime-realization, or backend-conformance result is claimed here.

The [executable rev2 refinement](participant-crossing-models.md) records #971's
approved single-operation interpretation and independently generated models.
The rev1 design below remains the historical theorem sketch.

## Theorem Target

Let:

```text
A = (S_A, Act union {tau}, ->_A, a0)
C = (S_C, Act union {tau}, ->_C, c0)
```

be the complete reachable abstract SEM-230 crossing LTS and the independently
derived formal concrete API-423/RUN-319 crossing-kernel LTS for the closed
profile below. The downstream obligation is:

```text
a0 ~=_db c0
```

where `~=_db` denotes catalog relation
`divergence-preserving-branching-bisimulation` under
`participant-crossing-projection@rev1`.

This obligation is final for the selected finite profile only when `S_A` and
`S_C` are the complete reachable fixed points of the transition schemas. A
depth bound, sampled schedule, timeout-truncated exploration, fixture set, or
matching trace set is not the theorem.

## Closed Carrier

The following domains are complete:

```text
Participant P = {participant-0}
Audience    U = {audience-0}
Controller  Ctl = {controller-0}
Episode     E = {episode-0}
Request id  Rid = {request-0}
Policy cut  K = {p0, p1}, ordered p0 < p1
Input class X = {plain, transform, declassify, unsupported, forbidden}
Decision    D = {none, permit, deny, unsupported, transform, declassify}
Replay      Rpy = {fresh, same-cut, later-cut}
Delivery    Del = {none, pending, delivered, withheld}
```

The policy decision function is total:

| input | `p0` | `p1` |
| --- | --- | --- |
| `plain` | `permit` | `permit` |
| `transform` | `transform` | `transform` |
| `declassify` | `deny` | `declassify` |
| `unsupported` | `unsupported` | `unsupported` |
| `forbidden` | `deny` | `deny` |

Policy advancement `p0 -> p1` is possible once and is visible. There is no
reverse cut transition. Controller handoff is excluded by the singleton
controller domain. The environment supplies only the declared request and cut
advance actions.

## Abstract States

The abstract carrier is the reachable subset of:

```text
S_A =
  Phase_A x K x Pending x D x Del x Last

Phase_A = {idle, offered, decided, delivery-pending, terminal}
Pending = {none} union (Rid x X x K x Rpy)
Last = {none} union (Rid x K x D)
```

Reachability enforces:

- `idle` has no pending request and decision `none`;
- `offered` has one pending request and decision `none`;
- `decided` has one pending request and a non-`none` decision;
- `delivery-pending` is possible only for `permit`, `transform`, or
  `declassify`;
- `terminal` has a completed or refused decision recorded in `Last`;
- `deny` and `unsupported` terminate with delivery `withheld`; and
- a delivered observation records delivery `delivered`.

The initial state is:

```text
a0 = (idle, p0, none, none, none, none)
```

## Concrete States

The concrete formal carrier is the reachable subset of:

```text
S_C =
  Phase_C x K x Intent x Gate x Capability x D x Del x Head x Last

Phase_C = {
  idle, validating, resolving-cut, resolving-capability, gating,
  preparing-record, committing, delivery-pending, terminal
}
Intent = {none} union (Rid x X x K x Rpy)
Gate = {unresolved, permit, deny}
Capability = {unresolved, supported, unsupported}
Head = {h0, h1, h2, h3}
Last = {none} union (Rid x K x D)
```

`Head` is a bounded logical history coordinate, not a live UUID or digest.
Only transitions admitted by API-423 predecessor/context order and RUN-319
fail-closed gates are reachable. A refusal leaves the history head unchanged
until the typed refusal occurrence is atomically committed; a partial commit
state is unreachable.

The initial state is:

```text
c0 = (idle, p0, none, unresolved, unresolved, none, none, h0, none)
```

The abstract and concrete state definitions have different transition
authorities. A downstream exporter MUST NOT build both from one transition
table.

## Visible And Hidden Alphabets

The closed visible alphabet is:

```text
crossing.request
crossing.decision.permit
crossing.decision.deny
crossing.decision.unsupported
crossing.transform
crossing.declassify
crossing.delivery
crossing.observation
crossing.replay.reject
policy.cut.advance
```

The closed semantic hidden classes are:

```text
internal.validate
internal.resolve-policy-cut
internal.resolve-capability
internal.prepare-record
internal.atomic-commit
```

The checker exporter renames each hidden class to exactly `internal`; the
fixed checker argument is `--tau=internal`. No other label is `tau`.

`crossing.observation` is an occurrence label, not payload disclosure. It
remains visible even when the payload is redacted. Denial, unsupported status,
replay rejection, omission at a declared opportunity, sanitized errors,
deadlock, and termination are never hidden merely because content is absent.

## Abstract Transition Schemas

The abstract transition relation is the least relation closed under these
schemas:

1. **Fresh request.** From `idle` or `terminal`, a fresh request at the current
   cut emits `crossing.request` and enters `offered`.
2. **Decision.** From `offered`, emit exactly the visible decision label
   selected by the total policy table and enter `decided`.
3. **Change.** Decision `transform` emits `crossing.transform`; decision
   `declassify` emits `crossing.declassify`. Each then enables delivery.
4. **Delivery.** Decisions `permit`, `transform`, and `declassify` emit
   `crossing.delivery`, enter `delivery-pending`, then emit
   `crossing.observation` and terminate with delivery `delivered`.
5. **Refusal.** Decisions `deny` and `unsupported` terminate after their
   visible decision with delivery `withheld`.
6. **Same-cut replay.** Repeating the recorded request at the same current cut
   emits `crossing.request`, then the same visible decision/change/delivery
   sequence and does not create a second logical result.
7. **Cut advance.** A state with cut `p0` and no in-flight request may emit
   `policy.cut.advance` and change to `p1`.
8. **Later-cut replay.** Repeating a request recorded at `p0` after the cut is
   `p1` emits `crossing.request` followed by `crossing.replay.reject` and
   terminates without changing the recorded result.

No abstract transition is hidden.

## Concrete Transition Schemas

The concrete transition relation is independently closed under:

1. `crossing.request` stores one intent and enters `validating`.
2. `internal.validate` checks the closed intent and identity coordinates.
3. `internal.resolve-policy-cut` resolves the exact requested/current cut.
4. `internal.resolve-capability` resolves effective API-407 support.
5. The independent authority, visibility, marking, transformation, and
   capability gates select one visible permit, deny, or unsupported decision.
6. A permitted transformation or declassification emits its corresponding
   visible label.
7. `internal.prepare-record` constructs the typed API-423 occurrence without
   committing it.
8. `internal.atomic-commit` advances the expected history head once and makes
   the typed result durable; refusal paths preserve every unrelated state
   coordinate.
9. A deliverable result emits `crossing.delivery`, then
   `crossing.observation`; refusal terminates after its decision.
10. Same-cut replay reuses the committed logical result while matching the
    abstract visible replay sequence. A replay after `policy.cut.advance`
    emits `crossing.replay.reject` and commits no crossing result.
11. `policy.cut.advance` is enabled only with no in-flight intent and moves
    `p0` to `p1`.

Every internal schema may fire at most once per crossing phase. The progress
rank:

```text
validating > resolving-cut > resolving-capability > gating
  > preparing-record > committing
```

strictly decreases on an internal transition. Therefore the declared concrete
model has no internal divergence. A mutation that adds an infinite
`internal` loop must fail divergence-preserving comparison.

## Branching And Divergence Relation

Write `q => q'` for zero or more `tau` transitions. A symmetric relation
`B subseteq (S_A union S_C)^2` satisfies the branching transfer clauses when, for every
`p B q` and transition `p -x-> p'`:

```text
x = tau and p' B q

or

there exist q0, q' such that
  q => q0 -x-> q',
  p B q0,
  p' B q'.
```

The symmetric clause applies to steps from `q`. The explicit-divergence clause
requires that if:

```text
p = p0 -tau-> p1 -tau-> ... and every pi B q,
```

then `q` admits a nonempty `tau` continuation to a state related to some `pi`;
the symmetric condition also applies. The downstream check uses the semantics
of mCRL2 `dpbranching-bisim`, pinned by tool version.

The initial relation contains `(a0, c0)`. Its witness family is induced by the
abstraction map below; the downstream model child must enumerate and validate
the greatest fixed point rather than assuming every mapped pair belongs to it.

## Abstraction And Runtime Mapping

The candidate abstraction `alpha : S_C -> S_A` maps:

| concrete coordinate | abstract coordinate |
| --- | --- |
| `idle` | `idle` |
| `validating`, `resolving-cut`, `resolving-capability`, `gating` | `offered` |
| `preparing-record`, `committing` | `decided` |
| `delivery-pending` | `delivery-pending` |
| `terminal` | `terminal` |
| exact cut, intent, decision, delivery, last result | same semantic coordinate |
| gate/capability/head bookkeeping | removed only by the declared projection |

The design witness is:

```text
B0 = { (alpha(c), c) | c is reachable } plus its converse.
```

This is a witness proposal, not a checked result.

Live-runtime realization is separate. It must map
`ParticipantCrossingIntent`, policy-resolution and gate results, API-407
effective support, API-423 typed occurrences and predecessor order,
`RuntimeSnapshot` histories, expected heads, idempotency fingerprints, audit
facts, and unchanged-state refusal into `S_C`. UUIDs, wall-clock timestamps,
host paths, and audit-only details may be projected away only after the
mapping demonstrates that they cannot alter an enabled visible transition.

## Preserved Properties And Nonclaims

A positive result preserves, for this profile:

- visible branching structure and enabled visible choices;
- finite `tau` stuttering around the declared mediation steps;
- permit/refuse/unsupported/change/delivery/observation order;
- explicit success and refusal termination;
- structural deadlock; and
- explicit internal divergence.

It does not by itself preserve a secret or low-equivalence predicate.
Noninterference and opacity require separate theorems showing that their
carriers, strategies, releases, memories, and observer facts are preserved.
It does not establish live-runtime realization, backend conformance, whole
runtime equivalence, time, probability, fairness, concurrency, partial order,
policy behavior outside `{p0,p1}`, or controller handoff.

## Machine-Check Contract

The downstream fixed command is:

```text
ltscompare --equivalence=dpbranching-bisim --tau=internal \
  abstract.aut concrete.aut
```

Inputs are repository-relative, generated independently, canonical, and
digest-bound. Verification is noninteractive, offline, non-shell, and bounded
for CPU, memory, and output. Evidence records tool version and verified
archive checksum or immutable container digest, both input and source digests,
profile and projection revisions, complete domain and state/transition counts,
result, mutation outcomes, artifact digests, limitations, and nonclaims.

Public scientific-completeness claims wait for clean independent reproduction.
