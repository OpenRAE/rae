# Proposition, assertion, and truth-result semantics

## Authority and claim level

This FM2 specification realizes [ADR-079](../../../docs/decisions/adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md).
The published JSON Schemas govern serialized shapes. The equations below govern
the reference truth algebra. Runtime tests and fixtures provide bounded
assurance; RAES does not claim a mechanized proof.

## Domains

For an instantiated scenario `S`:

```text
Subject(S)      = finite set of canonically addressable SDL resources
Truth           = {T, F, U}
Support         = {supported, unsupported}
PortableOutcome = {true, false, unknown, unsupported}
```

`unsupported` belongs to `PortableOutcome` but not `Truth`. It reports a failed
realization obligation, not a fact about the scenario world.

A proposition `p` is:

```text
p = (subjects, basis, predicate, quantifier, threshold, evidence_requirements)
```

where `subjects` is non-empty and finite; `basis` is `declared_state` or
`observed_state`; `predicate` is one member of the closed typed union; and
`threshold` exists exactly when `quantifier = at_least`.

The predicate is evaluated once per resolved subject. The proposition outcome
is the finite aggregation of those per-subject outcomes: `all` uses `all_of`,
`any` uses `any_of`, and `at_least(k)` uses the same `at_least(k)` table defined
below. Subject order has no semantic effect.

An assertion `a` is:

```text
a = (proposition_ref, role, polarity)
role     in {precondition, invariant, postcondition}
polarity in {positive, negative}
```

The owning objective/event/workflow/participant reference supplies scope. A
role does not create a clock.

## Predicate typing

```text
presence : property -> exists
boolean  : property x {equals, not_equals} x Bool
string   : property x {equals, not_equals} x String
         | property x {in, not_in} x NonEmptyUniqueList(String)
number   : property x OrderedComparison x FiniteNumber x Unit
```

Every property has a stable HTTPS/URN semantic reference. Numeric units have a
separate semantic reference. No implicit string-to-number or Boolean-to-number
coercion is permitted.

## Negation and composition

Let portable negation `not4` be:

| x | `not4(x)` |
|---|---|
| true | false |
| false | true |
| unknown | unknown |
| unsupported | unsupported |

Positive assertions preserve a proposition outcome; negative assertions apply
`not4`.

For non-empty sequence `xs`:

```text
all_of(xs) = false        if false in xs
           = true         if every x is true
           = unsupported  if unsupported in xs
           = unknown      otherwise

any_of(xs) = true         if true in xs
           = false        if every x is false
           = unsupported  if unsupported in xs
           = unknown      otherwise
```

For `at_least(k, xs)`, let `t` be the count of true values and `d` the count of
unknown plus unsupported values:

```text
at_least(k, xs) = true         if t >= k
                = false        if t + d < k
                = unsupported  if unsupported in xs
                = unknown      otherwise
```

`1 <= k <= |xs|`. Empty composition is undefined and rejected.

## Evidence admission

For an observed-state result `r`:

```text
Decided(r) => ProbeBinding(r)
              and NonEmpty(EvidenceRefs(r))
              and GovernedTemporalContext(r)
```

For a declared-state result:

```text
Decided(r) => InstantiatedArtifactDigest(r)
```

For every decided result:

```text
all(loss.within_admissible_bound for loss in r.loss_disclosures)
```

Missing, stale, partial, conflicting, redacted, lossy, or probe-failure evidence
produces `unknown` with a typed reason unless an admitted rule proves the loss
is within its bound. Missing capability produces `unsupported` with at least
one capability reference.

## Role admission

- Objective success references only invariant or postcondition assertions.
- Event triggers, workflow state predicates, and participant starting state
  reference only precondition assertions.
- False, unknown, or unsupported preconditions do not establish applicability.
- A postcondition is not established by command completion or evaluator
  lifecycle success.
- A sampled point does not prove an interval invariant without a governed
  coverage contract.

## Assertion satisfaction over a trace

Use the [shared trace interpretation](../time-model/README.md#trace-interpretation)
to resolve the run, owning occurrence, clock, segment, and scope boundaries.
An objective membership window alone does not supply these temporal bounds.
The interpretation must identify state cuts as well as event coordinates.
At one coordinate, the entry cut precedes the owning operation's effects;
the exit cut includes its admitted effects.
Neither cut follows from transport order or a host timestamp.

Let `P(tau, p, q)` be the existing proposition evaluation at state cut `q`.
It retains the declared or observed basis, finite subject quantification, and
evidence-admission rules above.
Define the assertion value at a cut before applying its temporal role:

```text
A(tau, a, q) = P(tau, a.proposition_ref, q)        if polarity is positive
              not4(P(tau, a.proposition_ref, q))  if polarity is negative
```

The following relations define each role for one owning occurrence.
`tau |=_G a` holds exactly when the role outcome is `true`.
`false` establishes violation. `unknown` and `unsupported` establish neither
satisfaction nor violation.

| Role | State scope and outcome |
| --- | --- |
| `precondition` | Evaluate `A` at the governed entry cut `q_in`, before the owner's effects. Only `true` establishes applicability. A later true value cannot repair the entry condition. |
| `invariant` | Evaluate `A` at every state cut in the nonempty governed interval `[q_in, q_out)`. Every value must be true for satisfaction. An admitted false value is a counterexample. |
| `postcondition` | Evaluate `A` at the governed completion cut `q_out`, including the owner's admitted effects. A true value at some earlier or later cut does not establish this postcondition. |

The owner semantics select which terminal transitions establish `q_out`.
A failed or cancelled scope cannot silently substitute its terminal cut for
a successful-completion boundary.
If no required completion cut exists yet, the postcondition remains unknown.
If the owner admits failure or cancellation as that boundary, evaluate its
actual state; lifecycle status alone supplies no proposition value.

Invariant scope includes intermediate state changes and microsteps, not only
its endpoint observations. Its lower bound is included; its upper bound is
excluded. A point obligation uses a precondition or postcondition instead.
An empty interval does not establish an invariant.

For finite, exhaustive state coverage, invariant aggregation uses `all_of`.
Thus an admitted false value is decisive even when other values are undecided.
Otherwise, complete true coverage yields true; required unsupported evaluation
yields unsupported; remaining incomplete or indeterminate coverage yields unknown.

A finite coverage representation must establish every state in the interval,
including persistence between recorded state changes.
The records need not enumerate unchanged states individually.
One sample, endpoint samples, or an observation gap cannot establish continuous
coverage without an admitted coverage contract.
An open prefix with no counterexample remains unknown until coverage and the
required interval closure are established.

Polarity applies before interval aggregation.
A negative invariant requires the proposition to be false throughout its scope.
One false proposition sample cannot satisfy a negative invariant over the
whole interval. Negating an aggregate positive invariant would express a
different claim and is not this assertion's meaning.

For declared state, an artifact digest establishes its identified state only.
It does not establish persistence over an execution interval.
For observed state, decided values retain probe binding, evidence references,
governed temporal context, and admissible loss disclosures.
Missing clock or coverage capability produces `unsupported` for the required
evaluation. Missing or inadequate captured evidence produces `unknown`.
The existing composition tables retain decisive true or false operands.

### Assertion boundary examples

These examples assume positive polarity unless stated otherwise.

| Role and trace | Outcome |
| --- | --- |
| Precondition false at entry, true after the first effect | False; applicability is not established. |
| Invariant true at both endpoints, false at an intermediate microstep | False from the admitted counterexample. |
| Invariant true at one sampled point, without interval coverage | Unknown. |
| Negative invariant with complete proposition values `false, false` | True. Replacing either value with true makes the invariant false. |
| Postcondition true at the governed completion cut | True, regardless of evaluator lifecycle success alone. |
| Postcondition with no completion cut in an unfinished prefix | Unknown. |
| Required clock or coverage capability absent | Unsupported, rather than a false world-state claim. |

## Equivalence boundary

`semantic_claim(r)` projects:

```text
(proposition, assertion, polarity, proposition_outcome, assertion_outcome,
 basis, indeterminacy_reason, temporal_context, loss_disclosures,
 unsupported_capabilities)
```

Equality of this projection permits comparing the same claim realized by
different bindings while retaining distinct binding/evidence provenance. It is
not a bisimulation claim. Park-style bisimulation would additionally require a
labelled transition system, an observation boundary, hidden-action treatment,
and a relation preserved by every transition.

## Realization mapping

The compiler emits separate proposition and assertion resources. A condition
binding may point to a proposition resource but cannot change its predicate.
The backend manifest declares supported predicate families, quantifiers,
portable outcomes, evidence channels, time domains, and binding-provenance
preservation. Admission reports unsupported instead of substituting a weaker
predicate or clock.

Planner admission compares every compiled proposition's predicate family and
quantifier with the evaluator declaration. For each cited evidence requirement,
it compares the explicit `channel` kind with `supported_evidence_channels`.
An evidence requirement that supplies only opaque `channel_refs` or a boundary
kind does not establish a channel kind and fails evaluator admission.
The planner MUST NOT infer modality from a reference name.

The current v1 runtime projection requires `scenario_time` for observed-state
proposition evaluation and no evaluator time domain for declared-state
propositions. The planner compares that requirement with
`supported_time_domains`. This projection does not establish a wall clock or
clock authority. A future authored per-proposition time domain requires a new
governed language/profile revision rather than a backend-local inference.

`PropositionTemporalContextModel` currently carries boundary, time-domain, and
clock-authority strings. It carries no coordinate, segment, or interval-coverage
proof. A valid v1 envelope therefore does not establish the trace interpretation
or invariant coverage defined above.
The current runtime admits truth-result identity and evidence shape; it does
not implement a general interval monitor for all assertion roles.

Runtime truth-result admission requires all of these conditions:

- Its proposition and assertion addresses resolve to semantic entries in the same snapshot.
- The proposition entry has the same evaluation basis.
- The assertion entry has the same proposition link and polarity.

A structurally valid envelope cannot change or detach the compiled claim.
