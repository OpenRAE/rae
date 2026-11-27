# Participant Opacity Implementation Program

Date: 2026-07-29

Parent issue: [#810](https://github.com/OpenRAE/rae/issues/810)

Milestone: `Participant Information-Flow & Behavioral Equivalence`

The machine-readable authority for this program is
[`implementation-program.json`](implementation-program.json). It records every
deliverable, requirement disposition, baseline dimension, relation boundary,
worked example, assurance lane, issue number, negative case, evidence
obligation, nonclaim, and dependency.

## Definition Delivered By #810

Issue #810 delivers:

- the research record and current-state assessment;
- ADR-099 and the SEM-231 formal opacity kernel;
- `participant-predicate-opacity` in behavioral-relations revision `rev5`;
- a mandatory revisioned relation-parameter profile for opacity claims;
- independent assurance axes in the shared claim surface;
- four finite falsification examples; and
- the requirement-backed downstream program.

It does not implement an opacity checker, model checker, proof, runtime
enforcement, or backend behavior.

## Dependency Graph

```text
#810 definition
  |
  v
#961 profiles + bounded falsification
  | \             \
  |  \             v
  |   v          #964 runtime enforcement
  v  #962 finite model check     |
#963 proof <-----/                |
  ^                               v
  +---------------------------- #965 backend realization/conformance
```

The authoritative dependency edges are also registered as GitHub issue
dependencies. Textual links are explanatory, not substitutes for those edges.

## Work Packages

### #961: Closed profiles and bounded falsification

Publish the executable opacity profile and finite-domain checker boundary.
Resolve every observer, secret, cut, memory, strategy, supervisor, release,
environment, order, time, and probability coordinate. Reject incomplete
profiles and falsify secret-only information cells with sanitized witnesses.

Required evidence includes valid and invalid fixtures, full domain/strategy
bounds, tool and profile digests, negative cases, and a `bounded-test` claim
binding. It establishes no model check, proof, runtime, or backend result.

Delivered by #961: the governed
`participant-opacity-baseline-v1@sem-231/rev2` profile, exact finite
analysis-input and digest-bound evidence contracts, canonical claim/profile
resolution, deterministic processor analysis and replay, and safe
counterexample fixtures. The delivered result vocabulary remains strictly
finite and bounded.

### #962: Finite-state model checking

Explore a pinned closed finite model across the declared state, strategy,
scheduler, and order bounds. Record tool/version, input digest, coverage, and
either a result or safe counterexample.

It establishes only the exact finite model. It is not an unbounded theorem and
says nothing about runtime or backend realization.

Delivered by #962: explicit input and evidence schemas, strict catalog/profile
and assumption joins, canonical breadth-first reachable-fixed-point
exploration, the shared SEM-231 information-cell kernel, complete aggregate
and per-strategy coverage, safe canonical counterexample paths, replay, and
valid/invalid exact-model fixtures. The baseline positive evidence binds only
the committed complete finite model under
`participant-opacity-baseline-v1@sem-231/rev2`.

### #963: Mathematical proof

State and independently check the opacity kernel, its knowledge
characterization, and the matching-profile implication from SEM-230
policy-noninterference. Explicitly reject the reverse implication and every
lift from one profile to a stronger timed, probabilistic, concurrent, or
coalition profile.

The proof does not establish runtime enforcement or backend behavior.

### #964: Reference-runtime enforcement

Implement a fail-closed subset of explicitly supported profiles through the
existing SEM-230/RUN-319 mediation and evidence authorities. Inventory every
supported observation channel and test decision, omission, timing, retry,
memory, and active-probe bypasses.

Runtime mediation is not a universal opacity result, supervisor synthesis, or
backend-native realization.

Delivered by #964: `participant-opacity-runtime-reference-v1@sem-231/runtime-rev1`,
one closed concrete observation inventory, exact catalog/profile/claim
admission, compact `runtime-enforcement/enforced/finite` bindings on API-423
decisions, idempotency and restart joins, and an exact uniform-denial mediator.
The mediator releases no participant payload or state and atomically records
the withheld egress opportunity. Unsupported or stale coordinates deny, while
an authorized weakening omits the positive opacity claim. The delivery excludes
useful allowed-action and delivered-view modes as well as
wall-clock/timed, probabilistic, coalition, partial-order, native-backend, and
unbounded opacity.

### #965: Backend declaration, realization, and conformance

Extend the existing API-407 participant-feature support vector for named
profiles. Keep declaration, native realization, and observed bounded
conformance separate. Exercise adversarial target cases with exact backend,
profile, environment, contract, and evidence identities.

Method presence or a boolean is not capability evidence. Bounded conformance
is not proof, cross-backend equivalence, or support outside the named profile.

Delivered by #965: the governed `participant_predicate_opacity` API-407
feature and required-contract map, bounded reference-backend declaration,
generic target-owned complete-transcript probes, three independent shared
claim bindings, exact six-way digest provenance, and fail-closed report
validation. The adversarial suite rejects backend observation drift,
runtime-only mediation, unexecuted declarations, forged manifest identity,
authorized weakening that retains stronger claims, missing contracts or
evidence, and secret-bearing diagnostics.

Corrected by #1374: the #965 probe accepted a fixed transcript from the
harness. The runner now derives each transcript from runtime execution and
backend readback. RUN-319 shields backend mechanisms under the runtime
profile, so the runner derives runtime-mediated evidence only. Catalog `rev13`
withdraws the backend declaration, realization, and conformance statuses.

## Program Invariants

- All claims use the exact applicable behavioral-taxonomy revision (current
  authoring authority `raes-behavioral-relations@rev13`) and one explicit
  assurance axis. The shipped runtime-reference profile retains its exact
  historical `rev11` binding; `rev5` introduced opacity and is not a permanent
  implementation pin.
- Universal opacity requires model-check or proof evidence whose scope matches
  the claim.
- Actual and alternative active points use the same participant strategy.
- Supervisor decisions and their observable behavior remain in the observer
  alphabet.
- Probability, timing, progress, concurrency, partial order, coalitions, and
  memory are never silently strengthened.
- No portable evidence contains raw secret values, possible worlds, private
  memory, policy bodies, supervisor internals, credentials, or unsafe
  counterexamples.
- Existing SEM-230/RUN-319/API-407 authorities are extended; no parallel policy
  engine, store, or backend registry is introduced.
