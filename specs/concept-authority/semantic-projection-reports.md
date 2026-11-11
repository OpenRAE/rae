# Semantic projection reports

## Scope

This specification defines `semantic-projection-report/v1`, the portable
report contract for projecting governed native RAES predicate results onto the
scheme-neutral external concept bindings defined by
`external-concept-bindings/v1`.

A projection is a derived view over exact, explicitly supplied artifacts. It
does not make an external concept executable, give a scheme authority over
native RAES meaning, or alter a transition system. The selected native
predicate continues to be owned by its declaration, validation, proposition,
evidence, or verification contract.

The normative JSON Schema is:

`contracts/schemas/concept-authority/semantic-projection-report-v1.json`

## Complete projection frame

Every report embeds the complete projection frame and its canonical digest.
The digest uses the shared RFC 8785/JCS SHA-256 helper and binds all semantic
axes:

- exact scheme id, authority, revision, source digest, and a sorted non-empty
  concept inclusion set;
- native subject kind, owning contract, lifecycle phase, exact artifact
  digests, and whether the supplied finite scope is complete;
- one digest-pinned predicate profile, producing contract, and fixed trusted
  owner adapter;
- asserting, validating, observing, verifying, or participant perspective;
- explicit configuration and state coordinates or profile-backed
  `not-applicable` postures;
- existential, universal, or threshold quantification and its counted unit;
- evidence boundary, freshness policy, evaluation cut, time domain, and clock
  authority;
- exact external binding schema, set id, set version, and canonical digest;
  and
- every transformation id, version, and digest used to derive the view.

The closed predicate profile fixes which configuration, state, and transformation axes apply.
Each inapplicable configuration or state axis uses the predicate-specific `not-applicable` basis.
Forbidden transformation axes are empty.
The declared configuration coordinate is the canonical digest of the complete sorted native-subject scope.
The observed state coordinate is the canonical digest of the complete sorted proposition-truth-result set at the named evaluation cut.

Verified transformation coordinates reproduce these fields from the owner report:

- Status and artifact kind.
- Source and target profiles and digests.
- Canonicalization profile, policy digest, and derivation digest.
- Preservation profile and outcome.
- Canonical whole-report digest.

The contextual projector derives those coordinates again from the supplied authoritative artifacts.
It requires exact equality before classification.
An empty verified result set is therefore explicit and cannot carry a fictitious transformation.

Changing any frame axis creates a different view. It does not mutate a native
artifact or native transition semantics.

## Exact denominator and partition

The inclusion set is the only denominator. It must be explicit, sorted,
unique, non-empty, and resolvable in the exact pinned scheme snapshot. Every
concept in that snapshot appears in exactly one report row:

- `witness` means the selected native predicate and quantifier are decisively
  satisfied by replayable digest-stable witnesses and evidence;
- `gap` means a complete finite native scope is decisively negative under the
  exact predicate and quantifier;
- `unknown` preserves missing, partial, stale, conflicting, unsupported,
  withheld, or out-of-policy facts;
- `ambiguous` preserves a non-unique scheme, concept, binding, subject, or
  native-result join; and
- `excluded` means the concept belongs to the pinned snapshot but is outside
  the explicit inclusion set.

Absence is not a gap. Stale or unavailable binding context, missing evidence,
an incomplete subject scope, or an unsupported native producer remains
unknown. Duplicate candidates remain ambiguous and are never first-matched.

## Native predicates remain independent

The reference projector has fixed owner adapters for four independent views:

| View | Native authority |
| --- | --- |
| `declared` | exact digest-stable native declarations |
| `admitted` | `validation-basis-disclosure-v1` |
| `observed` | `proposition-truth-result-v1` with observed-state basis |
| `verified` | predicate-specific verifier profile carried by an artifact-transformation report |

These names are not ordered strengths. No adapter infers admission from a
declaration, observation from admission, verification from observation, or
any reverse implication. A report selects one exact profile and producer.
Adding a native predicate requires a governed profile and one trusted owner
adapter; it does not change the report partition or add a scheme branch.

Profiles resolve from a closed repository-governed registry. Callers cannot
replace the adapter digest or create a new approximation posture by resealing
a payload. Each fact retains its authoritative owner artifact, and the public
projector reruns the fixed adapter before classification. The admitted,
observed, and verified adapters require the subject to identify the exact
disclosure, truth result, or transformation report; a valid result for another
subject cannot be substituted.

Observed decided facts resolve every and only the evidence references declared
by their truth result through a trusted evidence resolver. Each result must
resolve typed `experiment-evidence-record/v1` artifacts whose canonical
digests, capture window, redaction posture, and probe provenance satisfy the
exact evidence boundary. Verified facts use the same resolver and require the
fixed `verify-semantic-predicate/v1` operation, the
`semantic-predicate-witness/v1` preservation profile, the exact predicate
profile digest as policy, and an exact native-subject join. A generic successful
transformation is not semantic verification. Every positive row carries the
exact native subject, native result id and digest, producer contract,
predicate-profile digest, and sorted evidence-artifact digests.

## Binding fidelity

Projection reuses `admit_external_concept_bindings()` with the exact supplied
binding document, subject scope, and one pinned local scheme snapshot. The
report preserves each contributing binding's resolution outcome, relationship,
semantic effect, confidence, approximation posture, loss details, limitations,
and review state.

Approximate or lossy bindings may contribute a witness only when the exact
predicate profile explicitly admits that posture. Their loss remains visible.
Stale, unavailable, superseded, unknown, rejected, or ambiguous bindings never
silently become positive evidence.

## Counts and qualified fractions

The summary contains integer counts for witnesses, gaps, unknowns, ambiguous
concepts, excluded concepts, and the included denominator. Counts must exactly
reconcile with report rows.

The only fraction is qualified by native predicate and frame digest, for
example:

`declared:7/12@sha256:<frame-digest>`

The contract has no `coverage`, `coverage_percent`, `score`, `quality`, or
`maturity` field. A report is not an environment capability or universal
completeness claim.

## Participant information flow

Internal projection is pure and introduces no authentication surface.
Participant-relative frames retain exact participant, episode, audience,
policy revision/digest, and applicable-cut coordinates, but the pure contract
projector refuses to emit them. Participant-visible reporting must invoke the
incumbent deny-first participant exposure-policy service, which resolves its
authorization from trusted apparatus, policy, and authorization-record
resolvers rather than accepting caller-constructible permit data. Actual
authorization, disclosure, transformation, delivery, observation, and audit
remain owned by those exposure and API-423 participant-crossing contracts.
Aggregation, counting, hashing, and identifier omission do not declassify
hidden source information.

## Determinism and runtime boundary

Projection is deterministic, bounded, in-process, and offline. It performs no
network request, URL dereference, filesystem search, environment lookup,
subprocess, dynamic import, mutable registry access, persistence, or host-clock
read. Inputs are already typed artifacts supplied explicitly by the caller.

The result is an ordinary versioned artifact. It is not stored in runtime
snapshot metadata, audit details, a new cache, a database, or a global report
registry.

Portable model and JSON Schema validation enforce the joins contained in the
report: frame and profile digests, subject scope, producer, witnesses, rows,
and counts. The exact scheme snapshot and native evidence artifacts are
contextual authorities, so `project_semantic_concepts()` validates the complete
snapshot partition and owner-evidence joins while those artifacts are present.
Generic conformance reports that this contextual validation is still required;
it does not claim that a standalone report can prove an omitted authority.

## Non-goals

This contract does not:

- define a universal quality, maturity, coverage, or capability score;
- make an external concept a native proposition, outcome, trace, realization,
  or executable subject;
- replace native validation, truth, evidence, transformation, or participant
  information-flow semantics;
- select or fetch a scheme or a latest profile;
- add an API, CLI, UI, dashboard, store, cache, or delivery carrier; or
- infer a gap from missing data.
