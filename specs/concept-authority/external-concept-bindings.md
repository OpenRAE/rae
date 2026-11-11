# Portable external concept bindings

## Scope

This specification defines `external-concept-bindings/v1`, the portable
author-facing contract for asserting a relationship between an exact RAES
subject and a concept in an arbitrary versioned external scheme.

The contract is scheme-neutral. A scheme is identified by data, not by a
schema discriminator or an authority-specific field. Adding a scheme therefore
does not change this contract.

An external concept binding is an authored assertion about native RAES
meaning. It is not an executable SDL construct and does not acquire authority
merely because an external scheme is named.

## Published contract

The normative JSON Schema is:

`contracts/schemas/concept-authority/external-concept-bindings-v1.json`

A document has a stable `binding_set_id`, an authored
`binding_set_version`, and a non-empty map of assertions. Every map key must
equal the assertion's `binding_id`. Two assertions with different ids must not
duplicate the same semantic identity.

## Exact RAES subject coordinate

Every assertion identifies its RAES subject with all of:

- `subject_kind`;
- `owning_contract_id`;
- `lifecycle_phase`;
- `canonical_ref`; and
- `artifact_digest`.

The coordinate is resolved as one unit. A prose name, alias, suffix, compiled
address, or matching reference with a different digest is not a substitute.
SDL authoring and instantiated subjects use canonical declaration addresses
from the collision-preserving declaration index and the canonical digest for
their lifecycle phase.

The lifecycle phase is explicit because a normalized authoring declaration,
an expanded declaration, an instantiated declaration, a compiled object, and
a realized or observed object are not interchangeable subjects.

## External scheme coordinate

Every assertion identifies the external concept independently with:

- `scheme_id`;
- `authority`;
- `revision`;
- `concept_id`; and
- at least one of `source_locator` or `source_digest`.

When both source fields are present, both participate in exact resolution.
Locators are inert identifiers. They must be absolute and credential-free,
must not use `file:` or `data:`, and must not contain fragments or
secret-bearing query parameters. Parsing and admission never dereference a
locator.

## Assertion dimensions

The contract keeps the following dimensions separate:

- `assertion.relationship_kind` describes the direction from the RAES subject
  to the external concept;
- `assertion.motivation` and `motivation_basis_refs` explain why the assertion
  was authored;
- `assertion.semantic_effect` and `semantic_effect_basis_refs` state the
  claimed SEM-217 effect;
- `perspective` identifies the asserting party, its stated perspective, and
  its authority basis;
- `provenance` records when the assertion was made and the typed sources on
  which it depends;
- `supporting_evidence_refs` point to typed evidence or evidence-record
  identities without embedding evidence;
- `confidence` records a qualitative posture and basis, with a numeric score
  permitted only when a calibration profile is also referenced;
- `approximation` declares exactness, approximation, or loss, and requires
  explicit loss details whenever meaning is not exact;
- `limitations` bound every assertion; and
- `review` records its review lifecycle independently of confidence.

These fields must not be collapsed into a mapping string or an unconstrained
metadata object.

### Relationship kinds

The closed relationship vocabulary is:

- `equivalent-to`;
- `broader-than`;
- `narrower-than`;
- `related-to`; and
- `instance-of`.

The direction is always RAES subject to external concept.

### Semantic effects

The `semantic_effect` field reuses the closed SEM-217 vocabulary:
`annotates`, `constrains`, `refines`, and `aligns`.

An effect is a claim by the asserting perspective. `annotates` does not alter
native meaning. `constrains` has enforceable effect only when an independently
governed RAES validator or profile already owns that constraint. `refines` and
`aligns` require the stated basis, approximation posture, limitations, and
review; they do not make the external scheme authoritative over RAES by
themselves.

## Participant availability

Participant scope is optional and has one permitted posture:
`eligibility-only`.

It records that named participants are intended to be eligible for the
assertion, together with typed basis references. It does not assert that the
binding or external source was disclosed, delivered, observed, or understood.
Actual availability remains governed by the existing information-flow,
participant-view, admission, and delivery contracts. Values such as
`delivered`, `visible`, or `disclosed` are invalid on this surface.

## Offline semantic admission

Structural validation is independent of contextual resolution. A structurally
valid assertion remains parseable when its external scheme is unavailable, but
it is inactive until resolved against explicit local inputs.

The canonical conformance registry admits the document structurally through
`external-concept-bindings-v1` and reports
`conformance.semantic-context-required` when the generic fixture boundary has
not been supplied the exact subjects and pinned snapshots needed below. This
prevents the model and resolver from becoming a parallel validation path.
The normative schema expresses local conditions with Draft 2020-12 keywords
and publishes cross-entry identity conditions through the required
`x-raes-invariants` semantic profile.

Semantic admission accepts only:

1. a structurally admitted binding document;
2. an explicit local collection of exact RAES subject coordinates; and
3. explicit local, digest-pinned scheme snapshots.

It must not perform network access, environment lookup, filesystem search,
subprocess execution, latest-version fallback, or mutable global-registry
lookup.

Resolution is deterministic:

| Outcome | Condition | Admission effect |
|---|---|---|
| `resolved-current` | Exactly one subject and one exact scheme snapshot resolve to a current concept. | Assertion is active. |
| `unavailable` | No local snapshot has the asserted scheme identity and authority. | Assertion remains parseable but inactive. |
| `stale` | The subject digest or scheme revision, locator, or digest conflicts with supplied local context. | Fail admission. |
| `ambiguous` | An exact subject or scheme coordinate resolves more than once. | Fail admission without choosing a candidate. |
| `superseded` | The exact concept is marked superseded in the pinned snapshot. | Preserve the original id; fail admission without successor rewriting. |
| `unknown-concept` | The exact pinned snapshot does not contain the concept id. | Fail admission. |
| `subject-not-found` | The exact RAES coordinate is absent from the supplied subject index. | Fail admission. |

Diagnostics are bounded and must not echo attacker-controlled concept
identifiers.

## Relationship to other RAES surfaces

### Native `ConceptBinding`

Manifest `ConceptBinding` maps a governed manifest vocabulary scope to a native
RAES concept family. It remains required for its owned processor, backend, and
participant-manifest surfaces.

`external-concept-bindings/v1` is a separate assertion contract for an exact
artifact subject and an arbitrary external concept. It complements, but does
not widen or replace, native `ConceptBinding`.

### Propositions and outcomes

A binding is neither a proposition nor an outcome assertion. It does not make
a proposition true, satisfy a success criterion, establish a behavioral
relation, or record an observed result. Those claims continue to use their
owned proposition, outcome, observation, and truth-result contracts.

### Realization envelopes

A binding does not request, authorize, prove, or change realization. It cannot
grant processor, backend, or participant capabilities; change the transition
system; bypass admission; or modify a realization envelope. A realized or
observed object may be an exact subject only when its owning contract and
lifecycle-specific digest coordinate are independently available.

### Evidence records

Typed evidence references support review of an assertion, but the binding is
not an evidence record and does not prove that referenced evidence exists,
was captured, or satisfies an experiment requirement. Evidence identity,
capture, integrity, access, and interpretation remain governed by the existing
evidence contracts.

## Scheme adapters

Authority-specific source artifacts may be adapted into the neutral local
snapshot model. ATT&CK Enterprise tactics and NIST CSF defensive categories
are the initial unrelated examples. Both use the same authored syntax, schema,
subject resolution, and offline admission path.

ACT-611 adds W3C ActivityStreams Activity types and FIPA communicative acts as
two further unrelated schemes targeting exact
`behavior_specifications.<name>` declarations. They use the same authored
syntax and admission path; their source, semantic, and rights boundaries are
specified in
[Autonomous Behavior Vocabulary Bindings](./autonomous-behavior-vocabularies.md).

An adapter projects a pinned source artifact into scheme identity, authority,
revision, locator, digest, and a multiplicity-preserving concept candidate
list. Candidate ids are not converted into dictionary keys: zero matches are
unknown, one match resolves, and multiple matches are ambiguous. An adapter
does not add branches to the portable authored contract or fetch an authority
at admission time.

## Semantic projection reports

`semantic-projection-report/v1` derives evidence-bounded concept views from
this contract without widening binding authority. It reruns the exact offline
admission path, uses an explicit pinned-snapshot inclusion set as its sole
denominator, and preserves binding resolution, approximation, loss,
limitations, and review as independent facts.

The reporting contract is specified in
[Semantic Projection Reports](./semantic-projection-reports.md). A report
selects one governed native predicate and may classify a concept as a witness,
gap, unknown, ambiguous, or excluded only within its complete digest-bound
frame. A binding never supplies native predicate truth by itself.
