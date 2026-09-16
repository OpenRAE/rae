# Schemas

`contracts/schemas/` publishes versioned JSON Schema documents for
language-neutral RAES external contracts.

This directory is now the contract bucket in the repo layout. It is intended to
be the home of the authoritative machine-readable artifacts, independent of any
single implementation language or package layout.

Current published schemas cover:
- SDL normalized authoring objects (not raw YAML presentation)
- instantiated scenarios and canonical instantiated snapshots
- backend manifests (shared-apparatus `v2`)
- processor manifests (shared-apparatus `v2`)
- concept-authority catalogs
- reference model catalogs
- UCO alignment evidence
- controlled vocabulary catalogs
- semantic profiles
- live-execution snapshots
- workflow result envelopes
- workflow history streams
- evaluation result envelopes
- evaluation history streams
- operation receipts and statuses
- exact participant action-to-target execution bindings, generation-fenced
  execution lifecycle control, and typed execution-service readback
- control-plane participant status/history/context views, including SEM-214
  context-view meaning and comparability semantics
- experiment-core task, run, apparatus-context, study/collection, capture
  specification, raw evidence, and derived measure contracts

`sdl/sdl-authoring-input-v1.json` begins after `sdl-yaml/v1` source decoding,
canonical-field recognition, shorthand expansion, enum normalization, and typed
construction. Its title and `x-raes-document-phase` annotation state that
boundary. Raw YAML properties such as duplicate keys, tags, directives,
anchors, aliases, Core scalar resolution, and resource limits are specified in
`specs/sdl/document-model.md` and tested by
`contracts/fixtures/sdl/sdl-yaml-v1/`; JSON Schema cannot express them.

`sdl/instantiated-scenario-v1.json` is a distinct closed derived-artifact
contract. It requires `instantiation_provenance`, forbids `variables`,
`imports`, and `module` even when empty/null, and forbids a `${name}` token in
every string value. `sdl/instantiated-scenario-snapshot-v1.json` adds the
required `raes-sdl-instantiated-snapshot/v2` canonical profile envelope. The
`x-raes-realization-dimension: false` annotation on
`instantiation_provenance` declares that this required exchange metadata is
excluded only from realization-envelope child-dimension enumeration; it remains
part of validation and canonical identity. The
corresponding valid and invalid fixtures live under
`contracts/fixtures/sdl/instantiated-scenario-v1/` and
`instantiated-scenario-snapshot-v1/`.

These schemas enforce portable structure and scalar constraints. Cross-field
provenance relations, reference resolution, and graph semantics remain the
normative model/semantic-admission layer; schema validity alone does not assert
that provenance is truthful or that an artifact is compiler-admitted.

## Participant Execution Control

The participant-runtime family publishes three issue #898 contracts:

- `participant-execution-binding-v1` declares one exact native action,
  target-service set, participant implementation, evidence/constraints, and
  finite timeout, retry, attempt, and in-flight bounds.
- `participant-execution-control-v1` carries generation-fenced `start`,
  `pause`, `resume`, bounded `drain`, `reset`, and `teardown` requests.
- `participant-execution-service-state-v1` separates lifecycle, generation,
  health, readiness, work admission, capacity, quiescence/resource release,
  policy/binding/shared-time digests, pacing deviations, and evidence.

The service state is embedded under
`runtime-snapshot-v1.participant_execution_services`; control mutations use
the existing operation receipt/status contracts. Schema validity does not
prove native execution. Autonomous capability conformance additionally
requires executable bounded actions, typed outcomes, operation accounting,
and lifecycle evidence.

Current filenames still use `runtime` for some live-execution artifacts. That
naming is preserved for compatibility while the repository migrates toward the
processor/runtime boundary described in
[ADR-008](../../docs/decisions/adrs/adr-008-processor-layer-and-execution-artifact-boundaries.md).

For apparatus manifests, `v2` is now the authoritative shared envelope:

- `identity`
- `supported_contract_versions`
- `compatibility`
- `realization_support`
- `constraints`
- `capabilities`

These sections are intended to be concrete declarations, not placeholders. In
particular:

- `supported_contract_versions` must declare at least one contract
- `compatibility` must declare at least one compatible apparatus surface
- `realization_support` entries must declare non-empty disclosure kinds and at
  least one exact or constraint support kind
- processor capability blocks must declare non-empty SDL and feature support
- backend capability blocks must declare concrete provisioning and orchestration
  surfaces rather than empty shells

Only the shared-apparatus `v2` backend and processor manifests are published;
no `v1` backend or processor manifest schema is checked in. The reference
stack, contract tests, and conformance profiles use `v2`.

## Concept Authority Catalog

The `concept-families-v1` schema publishes the machine-readable shared concept
authority catalog. Catalog entries distinguish adopted, adapted, and
RAES-native concept families.

Adopted and adapted families must declare `authority` and
`authority_reference`. Native families must not declare those authority fields;
instead they must declare non-empty `extension_scope`, `relation_rules`, and
`non_ambiguity_constraints`. This keeps RAES experiment, runtime, apparatus,
provenance, and governance concepts explicit without letting them silently fork
shared cyber-domain concepts.

## Behavioral-Relation Authority

The `behavioral-relations-v1` schema publishes the closed, revisioned relation
catalog used by validation, SDL transformations, backend realization and
comparison, participant-visible behavior, multi-agent claims, and independent
adequacy studies. It separates relation identity from evidence and assurance,
requires formal dimension treatment, and carries revision-pinned bibliography
coordinates and executable counterexamples.

The canonical catalog lives at
`contracts/concept-authority/behavioral-relations-v1.json`; consumer claims use
the shared `BehavioralClaimBindingModel` rather than copying relation meaning.
Finite evidence cannot be bound to a universal quantifier.

## UCO Alignment Evidence

The `uco-alignment-v1` schema publishes the machine-readable UCO alignment
evidence catalog. It pins the reviewed UCO version and maps each adopted and
adapted cyber-domain concept family (from `concept-families-v1`) to the UCO
object types it aligns to, enumerating adapted-family divergences explicitly.

The catalog lives at `contracts/concept-authority/uco-alignment-v1.json`.
Coverage is catalog-derived: every adopted or adapted family whose authority is
UCO must have exactly one alignment entry. Validation uses local evidence only
and does not fetch the UCO ontology; semantic checks beyond JSON Schema enforce
coverage, provenance agreement with `concept-families-v1`, canonical UCO IRIs,
and the adapted-family divergence rule.

## Semantic Profiles

The `semantic-profile-v1` schema publishes shared semantic profile documents.
Each profile declares the compatible concept, contract, and behavior
assumptions required across authoring, exchange, processing, and execution
phases.

The initial profile lives at `contracts/profiles/semantic/reference-stack-v1.json`.

The `validation-profile-catalog-v1` schema publishes the ASR-511 authority for
ordered validation strengths, subject kinds, gate kinds, limitation
categories, and versioned validation profiles. Its single canonical artifact
lives at
`contracts/profiles/validation/validation-profile-catalog-v1.json`. Profile
selection uses the exact profile id/version plus a declared subject kind; the
catalog does not execute gates or carry per-subject results.

The `validation-basis-disclosure-v1` schema publishes the ASR-515 record of
the validation/admission basis used for one concrete subject, joined to the
`validation-profile-catalog-v1` authority by `(profile_id, profile_version,
subject_kind)`. It carries the achieved strength, gate-result rows,
limitations, and safe evidence/producer/diagnostic references; scenario and
scenario-snapshot subjects are referenced (never re-modeled), and experiment
task/run/study contracts embed it as an optional `validation_basis_disclosures`
list. It does not execute gates, does not replace the ASR-511 catalog, and
does not add an admission, endpoint, or persistence surface.

## Semantic Projection Reports

The `semantic-projection-report-v1` schema publishes scheme-neutral,
evidence-bounded reports over `external-concept-bindings/v1`. Each report
embeds a complete canonical-digest-bound frame: exact scheme revision and
source digest, explicit concept inclusion set, native subject scope, one
governed predicate profile and producer, perspective, configuration/state
coordinates, quantifier, evidence/freshness boundary, binding-set digest, and
transformation versions.

Rows form an exact partition of the pinned scheme snapshot into witnesses,
gaps, unknowns, ambiguous concepts, and excluded concepts. A gap requires a
complete finite native scope and a decisive negative. Positive rows retain
digest-stable native witnesses and evidence. Binding resolution, confidence,
approximation, loss, limitations, and review remain visible and independent.

Summaries expose exact integer counts and a predicate- and frame-qualified
fraction such as `declared:7/12@sha256:<frame-digest>`. They do not expose a
bare coverage percentage, quality score, maturity level, or environment
capability. Participant-relative generation additionally requires complete
deny-first authorization for every contributing source digest; the report
itself is not an ACL or delivery record.

The normative schema lives at
`contracts/schemas/concept-authority/semantic-projection-report-v1.json`; the
semantic boundary is specified in
`specs/concept-authority/semantic-projection-reports.md`.

The `scientific-completeness-taxonomy-v1` and
`scientific-completeness-assessment-v1` schemas keep stable intended-use
profiles separate from time-varying delivery evidence. Their normative
artifacts live under `contracts/profiles/scientific-completeness/`; neither is
an SDL validation-strength profile or a backend capability declaration.
Its processing and execution phases also declare required concept bindings for
the governed apparatus-manifest vocabulary surfaces introduced by GOV-918.

## Shared Reference Models

The `reference-models-v1` schema publishes shared reference model catalogs.
Each catalog entry binds a recurrent object model to an authoritative concept
family and to published contract schema definitions plus governed instance
paths.

The initial catalog lives at
`contracts/concept-authority/reference-models-v1.json`. It anchors the current
recurrent SDL object slice for nodes, accounts, relationships, conditions,
events, and content to the shared concept-authority layer.

## Controlled Vocabularies And Enumerations

The `controlled-vocabularies-v1` schema publishes controlled-vocabulary
catalogs for stable portable term sets.

The initial catalog lives at
`contracts/concept-authority/controlled-vocabularies-v1.json`. It defines:

- closed portable enumerations for processor features, workflow features,
  workflow state-predicate features, realization support modes, and concept
  provenance categories
- governed-extension vocabularies for apparatus-manifest capability surfaces
  that need stable shared base terms plus disciplined extension space

For governed apparatus-manifest capability fields, contract validation and
runtime validation both treat the catalog as normative. Values must either be
declared terms or valid governed extensions; closed enumerations reject
extensions.

## Cross-Artifact Concept Binding

Apparatus manifests (`v2`) require a `concept_bindings` section that binds
vocabulary fields to canonical concept families from the concept-authority
catalog. Each binding entry declares:

- `scope`: a dot-delimited field path identifying the bound vocabulary surface
  (e.g. `capabilities.provisioner.supported_node_types`)
- `family`: a concept family identifier from the authoritative catalog
  (e.g. `assets`, `identities`, `tools-and-artifacts`)

This is the "artifact binding layer" described in ADR-012. It prevents
artifact-local strings from becoming de facto semantics by explicitly declaring
which concept family each vocabulary surface belongs to.

The field is required with at least one binding entry. Duplicate scopes within a
single manifest are rejected. Family identifiers must resolve against the
authoritative `concept-families-v1` catalog, and scope paths must resolve to a
governed vocabulary field that is actually declared in the manifest.

Generation or sync helpers may exist under `tools/`, but those helpers are
supporting repo machinery, not the authority boundary.

## Experiment Core

The `experiment-core` schema family publishes:

- `experiment-task-v1`
- `experiment-apparatus-context-v1`
- `experiment-run-v1`
- `experiment-study-v1`
- `experiment-capture-spec-v1`
- `experiment-evidence-record-v1`
- `experiment-derived-measure-v1`

These schemas keep SDL scenario authoring, experiment task protocol, execution
apparatus context, archival run provenance, study/collection analysis,
declarative capture requirements, raw evidence records, and derived
measure/evaluation outputs separate. The normative invariant set lives in
`specs/formal/experiment-core/`. ADR-055 records the original task/run/study
boundary, and ADR-064 records the evidence/measure and backend observation
capability extension. ADR-065 records `experiment-run-v1` as the canonical run
provenance record with required traceability links and realized-form
disclosures.

Schema-expressible invariants are encoded in the published schemas. In
particular, task/run reference-kind constraints and invalidated-run
requirements are part of `experiment-task-v1` and `experiment-run-v1`, while
identifier uniqueness for metrics, apparatus components, result summaries,
study members, and study factors is represented with keyed object maps.
Run traceability and realized-form disclosure invariants keep claims grounded
in evidence/derived-measure refs and keep realized choices distinct from
authored scenario meaning and result values.
Task, run-plan, run, and study schemas also embed the same closed
`ExperimentEvidenceRequirementRelationModel`. Its semantic invariant requires
exact authored-scenario/declaration lineage, exact capture-specification
coordinates, carrier-owned task/run/study authority, and fail-closed governed
refinement comparisons. Generic JSON Schema validates the relation shape;
consumers apply `validate_evidence_requirement_relations()` with resolved SDL
and capture-specification inputs before treating the relationship as valid.
The trial compiler and realization path apply this validation through
`compile_scoped_evidence_requirement_demands()` before capability admission and
processor planning. Governed semantic comparison selects relation-aware
version-2 projections for current task, run, and study carriers.
Cross-artifact or graph invariants that standard JSON Schema cannot express are
published under the RAES semantic-invariant profile with `x-raes-invariants`
entries that name the validator and input contract paths. The generated schemas
declare draft 2020-12 identity, and the annotation profile shape is published as
`raes-semantic-invariants-v1` and checked during generation. Generic JSON Schema
validation remains structural; consumers of experiment-core records must apply
the named semantic validators before accepting records as RAES-conformant.

The optional backend-manifest `capabilities.observation` block declares EXP-715
observation/evidence collection support. Backends that declare it must also
declare the published capture-spec, evidence-record, and derived-measure
contracts that make the claim inspectable.

## Shared Time

The `time` schema family publishes:

- `time-model-v1`, the canonical backend-neutral compiled declaration;
- `time-runtime-state-v1`, typed clock readback with append-only transitions;
  and
- `realized-time-model-v1`, run-scoped apparatus and realization provenance.

`backend-manifest-v2` declares support through a closed
`capabilities.time` block. Admission compares every required semantic term and
limit against that declaration. `runtime-snapshot-v1` carries the typed state,
and `experiment-run-v1` carries the realized model. ADR-090 defines the shared
time semantics; ADR-091 defines this portable contract and conformance boundary.
