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
kind does not establish a channel kind and fails evaluator admission; the
planner MUST NOT infer modality from a reference name.

The current v1 runtime projection requires `scenario_time` for observed-state
proposition evaluation and no evaluator time domain for declared-state
propositions. The planner compares that requirement with
`supported_time_domains`. This projection does not establish a wall clock or
clock authority. A future authored per-proposition time domain requires a new
governed language/profile revision rather than a backend-local inference.

Runtime truth-result admission requires all of these conditions:

- Its proposition and assertion addresses resolve to semantic entries in the same snapshot.
- The proposition entry has the same evaluation basis.
- The assertion entry has the same proposition link and polarity.

A structurally valid envelope cannot change or detach the compiled claim.
