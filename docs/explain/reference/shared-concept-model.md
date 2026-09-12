# Shared Concept Model

This note is the implementation-facing design guidance for `GOV-917` and the
closely related concept-model requirements around extension discipline,
cross-artifact concept binding, reference models, and controlled vocabularies.

It is intentionally not an implementation plan. Its purpose is to keep the
next implementation pass aligned with the right architectural model.

## Goal

Make shared meaning real across RAES artifacts without turning the ontology
into the SDL, the manifests, or the contract schema layout.

The core problem is semantic drift:

- SDL says one thing
- processor manifests say something similar
- backend manifests say something similar
- provenance and reports reuse the same words

but none of those surfaces are actually bound to the same authoritative
concept.

## Layer Model

The shared-concept model has three layers.

### 1. Concept authority layer

This layer defines what relevant cyber-domain concepts mean.

For the current direction, UCO is the leading candidate semantic spine for
concept families such as:

- assets
- identities
- relationships
- observables
- actions or events
- tools or artifacts

This layer is about semantic authority, not authoring syntax.

### 2. RAES concept layer

This layer defines the concepts RAES needs that are not naturally covered by
the cyber-domain authority, including:

- scenarios
- tasks, runs, and studies
- processor, backend, and participant declaration surfaces
- realization and disclosure
- provenance and evidence requirements
- time, clocks, and apparatus concerns

These are RAES-native concepts, even when they relate to cyber-domain
concepts.

### 3. Artifact binding layer

This layer is where SDL, manifests, contracts, provenance, and reports bind
their declared meaning to canonical concepts.

The binding layer is what prevents artifact-local strings from becoming de
facto semantics.

## Guardrails

The following constraints should shape any `GOV-917` implementation.

### UCO is not the SDL

Authors should not be required to write UCO directly.

RAES remains the authoring and ecosystem layer. Shared concept authority exists
behind the authoring surface, not in place of it.

### Ontology structure is not contract structure

Contracts, manifests, and reports do not need to mirror ontology layout
mechanically.

Concept authority answers "what does this declared thing mean?" It does not
require every artifact to serialize in the same shape as the ontology.

### RAES-native concepts must be explicit

If RAES needs concepts outside the chosen cyber-domain authority, those
concepts must be declared explicitly as RAES-native extensions.

Do not create silent local forks of imported concepts and do not introduce new
portable labels without saying whether they are:

- adopted from the shared authority
- adapted from the shared authority
- native to RAES

### Bind concepts, not just labels

The implementation target is shared concept binding, not merely consistent
wording.

If two artifacts use the same word but point at different meaning, the system
is still drifting.

### Start with a narrow representative slice

The first concept-model slice should cover the cyber-domain concept families
most likely to appear across more than one artifact family:

- assets
- identities
- relationships
- observables
- actions or events
- tools or artifacts

That is enough to validate whether the method works across SDL, manifests,
provenance, and reporting without forcing the whole ecosystem into one big
ontology exercise.

## What The First GOV-917 Slice Should Make Possible

The first slice should enable the repo to say something stronger than
"different artifacts happen to use similar words."

It should make it possible for RAES artifacts to state:

- this SDL construct refers to a canonical concept
- this manifest capability or declaration refers to the same concept
- this provenance or reporting surface refers to that same concept

The authoritative concept-family catalog is keyed by canonical family
identifier. That keeps the concept identifier authoritative at one boundary
instead of repeating it as an artifact-local field that can drift, while
still allowing each artifact family to keep its own fit-for-purpose shape.

## Cross-Artifact Concept Binding (GOV-918)

`GOV-918` implements the artifact binding layer for apparatus manifests.

Both `v2` backend manifests and `v2` processor manifests require a
`concept_bindings` section. Each entry maps a dot-delimited field path (scope)
to a concept family identifier from the authoritative catalog.

For example, a backend manifest binds its provisioner vocabulary:

```json
"concept_bindings": [
  {"scope": "capabilities.provisioner.supported_node_types", "family": "assets"},
  {"scope": "capabilities.provisioner.supported_os_families", "family": "assets"},
  {"scope": "capabilities.provisioner.supported_content_types", "family": "tools-and-artifacts"},
  {"scope": "capabilities.provisioner.supported_service_materialization_profiles", "family": "tools-and-artifacts"},
  {"scope": "capabilities.provisioner.supported_account_features", "family": "identities"},
  {"scope": "capabilities.provisioner.supported_domain_profiles", "family": "identities"},
  {"scope": "capabilities.orchestrator.supported_sections", "family": "actions-and-events"},
  {"scope": "capabilities.evaluator.supported_sections", "family": "observables"}
]
```

This makes it possible for downstream tooling to answer: "which concept family
does this manifest field belong to?" without relying on field-name conventions
or documentation.

The binding is required (not optional) to prevent specification gaps where
concept bindings could be silently omitted. Family identifiers are validated
against the authoritative catalog at model time, and scope paths must resolve
to governed manifest vocabulary surfaces that are actually declared in the
artifact.

## External Knowledge Binding Effects (SEM-217)

`SEM-217` fixes what an external knowledge binding is allowed to do to native
RAES meaning. The effect is explicit and surface-owned; it is never inferred
from a label, a URL, or the fact that an external source uses similar words.

The current effect vocabulary is closed:

- `annotates`: the external reference adds reviewable context or evidence and
  does not change native validation, planning, runtime, or conformance meaning
  by itself.
- `aligns`: the RAES concept family is adopted from the external authority with
  equivalent meaning. For the current UCO slice, adopted families align and
  carry an empty divergence list.
- `refines`: the RAES concept family is adapted from the external authority.
  It preserves a reviewed correspondence while narrowing or diverging in an
  explicitly recorded way.
- `constrains`: a governed profile, manifest, or vocabulary surface restricts
  which family or term a field may use. A constraint is enforceable validation
  behavior, not descriptive metadata.

Implementation guidance:

- resolve effects from existing contract data: concept-family provenance,
  `uco-alignment-v1`, semantic-profile `required_bindings`, manifest
  `concept_bindings`, and controlled vocabulary governed scopes;
- do not add live ontology fetches, authority-specific runtime calls, or
  token-bearing process arguments;
- do not treat UCO, ATT&CK, OCSF, CACAO, STIX, OpenC2, CVE, exploit modules,
  or benchmark milestones as SDL syntax or as automatic schema inheritance;
- do not overload `ConceptBinding` into a general external term-mapping model;
  it remains the manifest vocabulary-to-family binding surface.

### Portable External Concept Assertions

The standalone `external-concept-bindings/v1` contract covers the different
case where an author or reviewer relates one exact, digest-pinned RAES subject
to a concept in an arbitrary versioned external scheme. ATT&CK Enterprise and
NIST CSF fixtures demonstrate the same scheme-neutral shape and offline
resolver. ACT-611 extends that proof with W3C ActivityStreams Activity types
and FIPA communicative acts bound to exact
`behavior_specifications.<name>` declarations; it does not add an
`autonomous_behavior_refs` field or a native agent ontology.

This assertion surface keeps relationship, motivation, effect, perspective,
provenance, evidence references, confidence, approximation or loss,
limitations, participant eligibility, and review status independently typed.
Its locator is inert and its semantic admission consumes only explicit local
subjects and pinned snapshots; absence, staleness, ambiguity, supersession, and
unknown concepts never trigger a live lookup or latest-version fallback.

The binding remains descriptive and reviewable. It is not a native manifest
`ConceptBinding`, proposition or outcome, realization instruction, capability,
evidence record, participant disclosure, or delivery receipt. The normative
model and resolution table are specified in
[`specs/concept-authority/external-concept-bindings.md`](../../../specs/concept-authority/external-concept-bindings.md).
The autonomous behavior source decisions and examples are specified in
[`specs/concept-authority/autonomous-behavior-vocabularies.md`](../../../specs/concept-authority/autonomous-behavior-vocabularies.md).

## RAES Extension Discipline (GOV-919)

`GOV-919` implements the RAES concept layer by making native extension metadata
normative in the concept-family catalog.

Every `native` concept family declares:

- `extension_scope`, describing the RAES-specific concern covered by the family
- `relation_rules`, describing how the native family may relate to adopted,
  adapted, or other native families
- `non_ambiguity_constraints`, describing how the family avoids shadowing
  shared cyber-domain concepts

This is intentionally stricter than treating native families as loose labels.
If a field denotes a cyber-domain asset, identity, observable, relationship,
action, event, tool, or artifact directly, it should bind to the adopted or
adapted family. Native families are for RAES experiment, runtime, apparatus,
provenance, and governance concerns that the shared authority does not
naturally cover.

## Shared Semantic Profiles (GOV-920)

`GOV-920` implements the composition layer above concept families, bindings,
reference models, and vocabularies. It does not redefine any of those
authority surfaces.

A shared semantic profile is a named interoperability declaration that says
which existing assumptions must hold together across authoring, exchange,
processing, and execution.

For this repo, that means:

- semantic profiles are not backend capability profiles. The checked-in
  `contracts/profiles/backend/*.json` artifacts remain apparatus capability
  declarations about required runtime contract surfaces. A semantic profile may
  reference or compose them, but it must not duplicate or replace them.
- semantic profiles are not concept families, reference models, or controlled
  vocabularies. Those remain separate authority surfaces; a profile only
  selects, constrains, or composes them.
- semantic profiles must resolve to existing normative artifacts instead of
  restating concept definitions, enum members, schema fragments, or behavior
  rules inline.
- if machine-readable semantic profile artifacts are introduced, they belong
  under `contracts/profiles/` with the repo's other normative profile
  declarations, not as implementation-only constants or ad hoc docs.
- the existing `scenario-instantiation-request-v1.profile` field is only a
  selector today. Do not let it become a second implicit authority surface
  with undocumented local-only behavior.
- validation should reuse the existing repo pattern: closed-world contract
  models for external shape, followed by repo-owned semantic validation for
  cross-artifact rules. Do not introduce a separate profile-specific exception
  hierarchy, schema DSL, or validator stack.
- required binding scopes remain governed by the artifact family that owns
  them. For the initial slice, semantic profiles may declare required
  bindings only for processor `v2` processing surfaces and backend `v2`
  execution surfaces. `authoring` and `exchange` stay binding-free until the
  repo defines governed vocabulary surfaces for those phases.

The initial machine-readable profile is
`contracts/profiles/semantic/reference-stack-v1.json`. It declares:

- authoring assumptions for SDL authoring and instantiation
- exchange assumptions for shared apparatus manifests and typed runtime
  envelopes
- processing assumptions for the reference processor contract and binding
  surfaces
- execution assumptions for the reference backend contract and binding
  surfaces

## Shared Reference Models (GOV-921)

`GOV-921` implements the reusable structure-authority layer for recurrent
federation-relevant objects.

For this repo, that means:

- shared reference models are not concept families. Families still answer what
  a declared thing means; reference models answer which published structure
  definitions are the repo-owned reusable shapes for recurrent objects.
- shared reference models are not semantic profiles. Profiles may select or
  compose reference models, but they do not replace them.
- shared reference models must anchor to existing published contract schema
  definitions and governed instance collections instead of restating object
  fields inline.
- the initial catalog belongs with the concept-authority artifacts under
  `contracts/concept-authority/`, with generated schema and fixture support
  under the matching concept-authority schema and fixture trees.

The initial machine-readable catalog is
`contracts/concept-authority/reference-models-v1.json`. It publishes the
current recurrent SDL object slice for assets, identities, relationships,
observables, actions-and-events, and tools-and-artifacts.

## Controlled Vocabularies And Enumerations (GOV-922)

`GOV-922` implements the portable term-authority layer for fields where
cross-artifact comparison depends on stable shared values.

The corrective runtime migration is governed by the
[issue #1206 architecture preflight](issue-1206-runtime-vocabulary-preflight.md).
It preserves exact private identities and closed operational semantics without
requiring a product/profile declaration for an unmentioned backend choice under
an open scope. The note records integration guardrails, not delivered migration.

For this repo, that means:

- a controlled vocabulary is not a concept family. Concept families govern
  what a field means; a controlled vocabulary governs which portable values
  may appear in that field.
- a controlled vocabulary is not a reference model. A reference model governs
  reusable structure; a controlled vocabulary governs term membership inside a
  field surface.
- not every repeated string field should become a portable controlled
  vocabulary. Only surfaces that need stable cross-artifact comparison should
  become governed vocabularies.
- the authority surface should distinguish between truly closed portable
  enumerations and governed-extension vocabularies. Some terms are mature
  enough to close; others need disciplined extension space rather than
  unconstrained local strings.
- governed extensions must be explicit and machine-checkable. For the initial
  slice, extension values use a namespaced `x-...:...` pattern instead of
  implicit ad hoc strings.
- the repo should preserve already-authoritative portable identifiers unless
  there is a deliberate migration. GOV-922 is about governing portable terms,
  not renaming them cosmetically while they are already wired into published
  artifacts.

The initial machine-readable catalog is
`contracts/concept-authority/controlled-vocabularies-v1.json`. It defines:

- closed portable enumerations for processor features, workflow features,
  workflow state-predicate features, realization support modes, and concept
  provenance categories
- governed-extension vocabularies for apparatus-manifest capability surfaces
  that still need controlled local extension space:
  `capabilities.provisioner.supported_node_types`,
  `capabilities.provisioner.supported_os_families`,
  `capabilities.provisioner.supported_content_types`,
  `capabilities.provisioner.supported_service_materialization_profiles`,
  `capabilities.provisioner.supported_account_features`,
  `capabilities.orchestrator.supported_sections`, and
  `capabilities.evaluator.supported_sections`

Validation treats that catalog as normative for both contract-model
validation and runtime capability declarations.

## Relationship To Other Requirements

`GOV-917` is the concept-authority decision surface.

The related requirements split the rest of the problem:

- `GOV-918`
  Cross-artifact concept binding (implemented)
- `GOV-919`
  RAES extension discipline over the shared authority (implemented)
- `GOV-920`
  shared semantic profiles (implemented)
- `GOV-921`
  shared reference models (implemented)
- `GOV-922`
  controlled vocabularies and enumerations (implemented)

The point is to avoid solving all of those implicitly and inconsistently inside
one implementation pass.

## Non-Goals For The First Pass

The first pass should not attempt to:

- replace SDL with ontology syntax
- make every contract structurally identical to the ontology
- define one universal super-model for every asset, identity, observable,
  action, event, relationship, and artifact occurrence in the ecosystem
- model all RAES concepts at once
- turn every repeated field group into a portable reference model without
  evidence that it is reused across artifact families
- solve all participant, provenance, evidence, and time/apparatus semantics in
  one step
- standardize every local implementation detail as a portable vocabulary term

If a proposed change would do one of those things, it is probably trying to
solve too much at once.
