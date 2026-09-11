# Issue 989 Generic Classification Bindings Preflight

Date: 2026-09-07

Issue: #989.

Requirements: DSL-114 — External Knowledge Reference Surface; ASR-530 — Claim
Falsification And Evidence Gate. The requirement statements and the GitHub
issue title, body, acceptance criteria, and non-goals together define the
authoritative contract.

This note records architecture guardrails for removing domain-shaped SDL
classification syntax in favor of the portable external concept bindings from
issue #986. It is guidance only: it does not change SDL, schemas, validators,
fixtures, deprecation state, or runtime behavior, and it is not an
implementation plan.

## Governing Boundary

Issue #986 already decided the canonical representation:
`external-concept-bindings/v1` is a standalone, closed, scheme-neutral authored
artifact whose exact RAES subject is bound by lifecycle phase, canonical
reference, and artifact digest. It already separates relationship, effect,
perspective, provenance, evidence, confidence, approximation/loss,
limitations, review, and participant eligibility. Issue #989 must reuse that
contract and `admit_external_concept_bindings()`; it must not add a smaller SDL
binding object, a second mapping DTO, or a top-level SDL binding collection.
Issue #989 extends DSL-114's existing implementation and traceability; it is not
a requirement-free cleanup.

The standalone boundary remains necessary. Embedding a binding in the SDL
whose digest it names would be self-referential, would make classifications
part of every SDL phase, and would encourage compilers and backends to treat an
annotation as execution input. Canonical output is therefore an ordinary SDL
artifact containing native configuration and behavior plus one or more linked
`external-concept-bindings/v1` artifacts containing authored interpretation.

The existing semantic owners remain distinct:

- `Scenario`, `SemanticValidator`, instantiation, compilation, and planning own
  native configuration and transition semantics;
- `ExternalConceptBindingDocumentModel`, `external_concept_subjects()`, pinned
  scheme snapshots, and `admit_external_concept_bindings()` own external
  assertions;
- `ArtifactTransformationReportModel` and the all-or-none transformation result
  convention own migration provenance, preservation checks, and explicit loss;
- participant content, exposure, crossing, disclosure, and observation remain
  owned by ADR-085/095 and API-423; and
- native manifest `ConceptBinding` continues to bind governed apparatus
  vocabulary scopes to RAES concept families. It is not the #986 authored
  assertion contract and is not replaced by this issue.

The classification retirement changes ADR-001's original requirement to preserve
the OCR-derived native vulnerability section. Record that exception through the
issue-989 amendment to accepted ADR-001 and its ADR-059 manifest entry. This
amendment replaces the classification-section constraint without changing the
other semantic owners above; a guidance-only preflight is not its authority.

## ASR-530 Evidence And Retest Boundary

The migration tests and a coherent architecture do not by themselves prove the
issue's major claims. Before any maturity statement calls classification
externalization demonstrated, an issue-bound, preregistered record must state
the exact claim boundary, threats to validity, objective pass/fail criteria,
allowed and disallowed evidence, named artifacts, limitations, and one ADR-021
status: `untested`, `partial`, `demonstrated`, or `refuted`. In particular, keep
these claims independently falsifiable:

- native configuration and transition results are unchanged for the declared
  migratable corpus when classification assertions move to sidecars;
- no admitted binding changes capability, transition, proposition,
  realization, authorization, or participant knowledge; and
- a new external scheme is admitted through data and the existing generic
  contract without a new SDL field or scheme-specific runtime branch.

The SDL and compiled-result digest changes also affect the existing
`docs/research/formal-semantic-validation/` replay evidence. Those historical
releases are immutable. Reuse its bounded JSON loading, repository containment,
atomic release manifest, SHA-256 pins, production-entrypoint replay, derived
analysis, and exact baseline-drift dispositions. Preserve every indexed prior
release and publish a higher, coherent release containing the current snapshot
and analysis; never edit an old observation, replace its pinned digest, weaken
digest equality to outcome-only comparison, or label representation drift
automatically benign.

The current formal-evidence release dispatcher recognizes one fixed integrated
retest revision. A follow-on release therefore needs an explicit versioned
validator path that still validates every historical release and selects the
latest coherent release deterministically. Do not loosen the incumbent checker
to accept arbitrary future revisions, combine newest protocol/corpus/snapshot
parts independently, or hide a stale evidence bundle by changing only tests.
If qualifying evidence is not recorded when the implementation lands, the
affected claims and maturity summaries remain `untested` or `partial` as their
bounded records require.

## Classification Inventory And Required Disposition

The following is the repository-wide SDL inventory. “Compatibility syntax”
means the field may remain accepted only under an explicit deprecation record
and timeline; it is not part of the target canonical SDL meaning.

| Surface | Current propagation | Classification | Required boundary |
| --- | --- | --- | --- |
| top-level `vulnerabilities` and `Vulnerability.{name,description,technical,class}` | normalized, expanded, and instantiated SDL; declaration/alias indexes; module composition; canonical digests; compiler `vulnerability_templates`; MCP authoring/inspection/reporting | compatibility syntax plus external authored assertion; `class` is CWE-shaped and the declaration has no native transition predicate | remove from canonical SDL. Each supported legacy association becomes a binding from the exact native subject to a pinned external concept. Unreferenced declarations, unsupported uses, or missing scheme context refuse migration or require explicit authorized loss. |
| `nodes.*.vulnerabilities[]` | semantic reference validation, composition, node compiler `spec`, variation point `nodes.vulnerabilities` | external authored assertion expressed as an intrinsic node property | bind the exact node subject; it must not enter node desired state or backend payloads |
| `features.*.vulnerabilities[]` | semantic reference validation, composition, feature template/binding payloads | external authored assertion expressed as an intrinsic feature property | bind the exact feature subject; native feature source/configuration remains sufficient |
| `entities.*.vulnerabilities[]` | recursive entity validation/composition and compiled entity metadata | external authored assertion expressed as an intrinsic entity property | bind the exact entity subject; it must not imply participant role, authority, or capability |
| `nodes.*.runtime.applications[].routes[].vulnerability_refs[]` | runtime-application validation and node runtime `spec` | external authored assertion about a route | bind an exact stable route subject only if the owning subject adapter exposes one. Widening the subject to the application or node is loss and must not happen implicitly. |
| `behavior_specifications.*.offensive_behavior_refs[]` | controlled-vocabulary catalog, semantic validator, compiler/runtime tuple and raw `spec`, generated SDL schemas, docs/tests | ATT&CK-shaped external authored intent classification | map the governed term to the pinned ATT&CK source id and bind the exact behavior specification; never infer an action, goal, role, capability, or realized tactic |
| `behavior_specifications.*.ai_offensive_behavior_refs[]` | same path as above | ATLAS-shaped external authored intent classification | map the governed term to the pinned ATLAS tactic id through the neutral snapshot adapter and bind the exact behavior specification |
| `behavior_specifications.*.defensive_behavior_refs[]` | same path as above | NIST-CSF-shaped external authored intent/outcome-domain classification | map the governed term to the pinned NIST category id and bind the exact behavior specification; never infer detection, mitigation, recovery, or conformance |
| `action_contracts.*.external_mappings[].{system,identifier,loss_label,rationale}` | SDL action-contract model, generated schemas, examples/tests, and the raw compiled action-contract `spec` | weakly typed external authored assertion | replace with the complete #986 assertion against the exact action-contract subject. The four legacy strings are insufficient to infer scheme authority/revision, relationship, perspective, provenance, confidence, or review. |
| `entities.*.categories[]` | SDL/entity schema, canonical digests, compiled entity metadata | unqualified authored classification | no intrinsic SDL effect. Convert only with an explicit scheme coordinate and assertion context; otherwise refuse or record explicitly authorized omission. |
| `entities.*.mission` | SDL/entity schema, canonical digests, examples, compiled entity metadata | author narrative or participant-visible content, not a native fact and not necessarily a scheme concept | keep distinct from configuration. If a participant is meant to receive it, deliver it as ordinary governed content; do not treat mere SDL presence as participant knowledge. |

The vulnerability declaration is currently targetable through the generic SDL
reference index. A legacy vulnerability used by propositions, objectives,
relationships, temporal constraints, variation points, or another generic
targetable-reference surface cannot be mechanically retargeted to a native
configuration subject. Such a case must fail with an exact reference diagnostic
unless a reviewed migration rule preserves the intended native semantics.

The following adjacent classification-looking fields are **native operational
semantics**, not candidates for externalization merely because their names use
`role`, `class`, `kind`, `type`, `mode`, `purpose`, `profile`, or `mapping`:

- `entities.*.role` and
  `behavior_specifications.*.participant_role_refs[]` select and validate
  participant aggregates; the role still does not imply offensive/defensive
  capability;
- node `roles` bind exercise access, while account credential `purpose` and
  authentication method participate in credential binding and uniqueness;
- `nodes.*.endpoint_persona` participates in deployment-tenancy and carrier
  invariants;
- assertion role/polarity, proposition basis/predicate/quantifier, action
  precondition/effect/failure/interaction classes, behavioral granularity,
  behavior mode, workflow step type, relationship type, content/feature/node
  type, and time mapping kind select closed RAES semantics or validation;
- evidence source class, boundary kind, artifact role, sensitivity, and
  runtime value/credential classifications drive observation, redaction, or
  secret-handling policy;
- realization profile references, backend failure mappings, and time-domain
  mappings bind native realization or transition behavior; and
- manifest capabilities, supported participant roles/predicate families, and
  native apparatus `concept_bindings` are admission claims, not authored
  external classifications.

`action_contracts.*.procedure_basis` and `fidelity_claim` remain explicit
RAES-authored claim/basis text, but they must not be used as an alternate
channel for an external scheme coordinate. A formal ATT&CK, CWE, CVE, NIST,
tool, or other catalog relation belongs in the #986 artifact.

Derived `semantic-projection-report/v1` classifications (`witness`, `gap`,
`unknown`, `ambiguous`, and `excluded`) also remain. They are report outcomes
within an exact digest-bound frame, not intrinsic SDL labels. Security and
redaction classifications likewise remain native policy inputs.

## Repository Surfaces That Carry The Legacy Shape

The implementation must treat these as one contract change rather than a
model-only edit:

- SDL models and metadata: `raes.scenario`, `raes.vulnerabilities`,
  `raes.nodes`, `raes.features`, `raes.entities`,
  `raes.runtime_application`, participant action/behavior models,
  `_language_metadata`, `_mapping_scopes`, `_module_symbols`, declaration and
  targetability indexes, composition rewriters, and variation-point slots;
- parsing and validation: the bounded YAML source loader, source diagnostics,
  closed `SDLModel`, `SemanticValidator`, node/feature/entity/runtime-service
  reference validators, and participant controlled-vocabulary validation;
- lifecycle and identity: normalized/expanded/instantiated phase models,
  `instantiate_scenario()`, instantiated admission, canonical SDL/snapshot
  digests, module imports/exports, exact declaration addresses, and retargeting
  of already-linked binding documents;
- compiler/runtime: provisioning template construction, node/feature/entity
  `spec` payloads, participant behavior runtime fields, action-contract raw
  `spec`, alias indexes, temporal subject resolution, resource payloads, and
  any capability checks or report counters that see those fields;
- published contracts: `sdl-authoring-input-v1`, `instantiated-scenario-v1`,
  `instantiated-scenario-snapshot-v1`, and the nested snapshot in
  `scenario-satisfiability-evidence-v1`; `schema_bundle()` and every matching
  schema-publication entry/hash must move together;
- concept authority and manifests: the three legacy governed scopes in
  `controlled-vocabularies-v1`, their Python scope allowlist and parity tests,
  ATT&CK/ATLAS/NIST source-integrity checkers, and manifest/schema fixtures.
  Source snapshots and adapters may remain; the old SDL scopes may not remain
  privileged target semantics;
- projections and reports: scenario semantic/structural comparison
  projections, satisfiability witnesses, semantic projection reports,
  transformation reports, MCP operation summaries, and any docs claiming a
  vulnerability or behavior classification is runtime state; and
- authoring/examples/tests: shipped scenario examples, library/MCP templates,
  MCP reference and reference-inspection helpers, SDL catalog parity,
  valid/invalid migration fixtures, stress/fuzz/real-world corpora, and
  generated-schema parity.

Removing typed fields while leaving them inside a compiler `spec` dictionary,
runtime tuple, template counter, generated schema definition, controlled
vocabulary scope, or comparison projection is incomplete. Conversely, source
catalogs, adapters, fixtures, and profiles are not privileged SDL semantics and
need not be deleted merely because their former SDL fields are removed.

## Compatibility And Canonical Migration

Compatibility reading and canonical migration are separate operations.

During the notice window, a deprecated reader may accept the exact historical
shape and emit bounded source diagnostics under the existing SDL error and
migration-policy conventions. That does not make the legacy fields canonical
or manufacture a binding artifact. New canonical authoring and all generated
examples use the generic sidecar representation.

Canonical migration is an explicit, pure, all-or-none SDL transformation. It
must build on `SDLTransformationResult`, `ArtifactTransformationPolicy`,
`ArtifactTransformationReportModel`, canonical digests, semantic comparison,
and the existing linked-binding retargeting helper. Its result contains:

- an admitted SDL artifact with no legacy classification fields;
- complete `ExternalConceptBindingDocumentModel` sidecars, including any
  existing sidecars retargeted to the target SDL digest; and
- a transformation report covering exact inputs, policy, affected identities,
  preservation checks, diagnostics, and every authorized loss.

Do not mutate the source, hide generated bindings in private model attributes,
drop classifications during `parse_sdl()`, or return a successful SDL without
the sidecars and report. The source artifact and its old digest remain
readable; the migrated SDL receives a new canonical digest, and all output
binding subjects use that target digest.

Legacy syntax alone is not enough for most complete assertions. A migration
context must explicitly supply any missing asserting-party identity and kind,
authority basis, assertion time and source references, relationship/effect,
confidence basis, review posture, and exact scheme coordinate/snapshot. These
are data in a versioned migration profile or request, not environment defaults.
If required context is absent, the deterministic result is refusal with a
stable migration diagnostic, not a plausible invented assertion.

Known base behavior terms may resolve through the checked-in pinned ATT&CK,
ATLAS, and NIST source artifacts, translating the legacy catalog key to the
source concept id. Governed `x-<owner>:<term>` extensions have no implied
authority, revision, digest, or concept-id mapping and therefore require an
explicit supplied snapshot/coordinate. CWE-shaped `class` values currently
have no pinned CWE source artifact in this repository; they cannot be admitted
as current external concepts until an exact local source context is supplied.
Action `external_mappings` likewise omit the necessary source and assertion
dimensions and must not default to `related-to`, `annotates`, accepted review,
or any confidence posture without an explicit governed migration rule.

One legacy declaration referenced by several native subjects becomes one
assertion per exact subject. Preserve multiplicity until ambiguity and
duplicate-semantic-identity checks run. Unreferenced vulnerabilities,
route-level subjects without an exact subject rule, duplicate aliases,
ambiguous source-term mappings, stale digests, superseded concepts, generic
references to vulnerability declarations, and collisions all refuse or require
an explicitly authorized and reported loss.

The removal/compatibility schedule belongs in
`specs/evolution/deprecation-records.yaml` under the existing ADR-075 policy.
The record must name every exact legacy surface (or one unambiguous grouped
identifier), first notice, replacement, migration reference, removal
eligibility rule, and evidence that compatibility remains supported. The
checker’s canonical record floor must retain the record after removal.
Published schema changes also update their ADR-061 publication entries and, on
removal, required tombstones. Do not encode lifecycle state in a new runtime
registry or an ad hoc parser version check.

## Participant Knowledge Is Ordinary Information Flow

A binding's `perspective.participant_availability` remains
`eligibility-only`. It never means visible, delivered, disclosed, observed, or
understood.

When an author intends a participant to receive a classification, the
participant-facing representation is ordinary content linked to the exact
binding artifact identity/version/digest. Delivery uses the existing
participant-directed inject/content path: source and result item references,
observation boundary, exact participant/audience, revisioned policy,
information-flow admission, redaction/transformation, crossing record,
delivery evidence, and observation semantics. Environment content or an SDL
field is not participant knowledge. A rendered label may be disclosed while
the full binding or source catalog remains withheld, but that transformation
and its loss/provenance remain recorded by the incumbent flow contracts.

Do not add binding-specific ACLs, audience lists, delivery flags, disclosure
logs, participant knowledge fields, or a second policy engine.

## Cross-Cutting Concerns To Reuse

| Concern | Canonical incumbent and required use |
| --- | --- |
| portable assertion | `ExternalConceptBindingDocumentModel`, published `external-concept-bindings-v1`, `external_concept_subjects()`, neutral local snapshot adapters, and `admit_external_concept_bindings()` |
| concept authority | ADR-012/062, `specs/concept-authority/`, source snapshots, controlled vocabularies, and SEM-217 effects; source catalogs remain inputs, never SDL field authorities |
| SDL ingress | `SDLParserLimits`, safe YAML 1.2 loader, mapping-key diagnostics, `SDLMigrationPolicy`, `SDLModel(extra="forbid")`, and `_model_parse_error()` |
| semantic validation | `SemanticValidator`, exact declaration/reference indexes, collision preservation, module composition, participant behavior validators, and post-instantiation admission |
| identity and lifecycle | ADR-076/078, canonical declaration addresses, lifecycle-specific subjects, `canonical_sdl_digest()`, `canonical_instantiated_sdl_digest()`, and JCS/SHA-256 helpers |
| migration | `SDLTransformationResult`, `ArtifactTransformationPolicy`, `ArtifactTransformationReportModel`, linked-binding retargeting, all-or-none refusal, and canonical semantic comparison |
| schema authority | hand-governed `contracts/schemas/`, `schema_bundle()` parity, schema-publication entries/hashes/tombstones, and generated-schema checks |
| diagnostics/errors | `SDLParseDiagnostic`, SDL exception owners, `Diagnostic`/`DiagnosticModel`, conformance `sanitized_failure_message()`, CLI/MCP diagnostic renderers, and bounded messages |
| participant information flow | ADR-085/095, participant inject delivery, observation boundaries, exposure bindings, flow-control relation/context, crossing occurrences, and audit/history owners |
| evidence/provenance | typed experiment references, evidence records, associated artifacts, semantic projection reports, and transformation reports; do not copy payloads into bindings |
| manifests/admission | native apparatus `ConceptBinding`, controlled-vocabulary validators, manifest authority, feature support, and realization/capability admission; classifications cannot satisfy them |
| persistence | ordinary immutable/versioned SDL, binding, source, and transformation-report artifacts joined by exact digest; no database, cache, generic metadata bag, or runtime snapshot stuffing |
| workflow | SDL catalog/reference parity, deprecation checker, schema checker, public docs checker, repository policy, canonical nox graph, and `tools/verify_all.py` |

## Security, Configuration, Runtime, And Error Layers

The intended design passes these layers in order:

1. **YAML/source shape:** the existing byte, scalar, depth, node, alias, import,
   and composed-size limits; YAML tag/directive/duplicate/non-string-key guards;
   canonical-key handling; and source ranges run before legacy recognition.
   Compatibility syntax does not bypass source-profile validation.
2. **Closed SDL shape:** historical input is admitted only by the exact legacy
   compatibility model/profile. Target SDL is reconstructed through the closed
   current `Scenario` model and full `SemanticValidator`, never by deleting
   dictionary keys after validation or setting the private validated flag.
3. **Composition and lifecycle:** imports pass the existing confined
   file-backed resolver, trust/digest/export/collision/budget checks;
   instantiation and snapshot admission rerun their invariants. Legacy fields
   do not survive in expanded, instantiated, compiled, planned, or snapshot
   payloads on the canonical path.
4. **Binding contract shape:** `ContractModel`, strict shared scalar/time/digest
   types, conditional validators, key/id equality, uniqueness, approximation
   loss, confidence calibration, review evidence, and
   `validate_safe_absolute_uri()` apply once through the #986 model/schema.
5. **Binding semantic admission:** exact lifecycle subject coordinates and
   explicit pinned local scheme snapshots pass
   `admit_external_concept_bindings()`. Missing, stale, ambiguous, superseded,
   or unknown inputs remain inactive or fail according to that contract. No
   parser, compiler, or report creates a second resolver.
6. **Authentication and capability:** the pure parser/migrator has no auth
   surface; authored `authority`, role, or asserting-party strings are not
   verified identities. If exposed by an API, existing strict control-plane
   security configuration, authenticated identity, audience/target and role
   checks, request-size guards, idempotency/fingerprints, and audit records
   apply. A classification cannot grant action, backend, OS, or API capability.
7. **Secret handling:** inputs contain no credentials, tokens, secret values,
   secret-reference resolution, environment-variable names, private prompts,
   or hidden answer keys. URI safety rejects user information, `file:`/`data:`,
   fragments, and secret-bearing query fields. A digest does not declassify
   source or classification content.
8. **Configuration/environment:** migration behavior is selected only by
   explicit typed profile/request values and pinned artifacts. No environment
   variable, current directory, locale, wall clock, installed plugin, mutable
   registry, or “latest” source selects a scheme, assertion default, or loss
   policy. Existing parser/config validators remain authoritative.
9. **OS/process/network:** parse, migration, admission, replay, and report
   generation perform no network lookup, shell interpolation, subprocess
   dispatch, daemon call, or host mutation. Locators, concept ids, rejected
   values, and secrets never enter process argv. Optional remote source
   verification remains an explicit maintenance-tool mode, not runtime
   admission.
10. **Participant disclosure:** participant-facing content passes authenticated
    audience binding, exact-cut deny-first flow policy, markings,
    redaction/declassification, crossing, delivery, and observation stages.
    Binding eligibility or an entity mission is never enough.
11. **Errors/logging/envelopes:** expected migration failures use stable codes,
    safe JSON-pointer/canonical addresses, bounded messages, and typed refusal
    reports. CLI/MCP/conformance adapters reuse their existing renderers and
    `sanitized_failure_message()`; public errors and logs exclude whole source
    documents, rejected identifiers/locators, URI queries, Pydantic input
    echoes, environment dumps, raw exceptions, and tracebacks.
12. **Persistence/publication:** durable units remain exact SDL, binding,
    source-snapshot, transformation-report, and optional participant-flow
    artifacts. Schema publication and deprecation ledgers record contract
    lifecycle. No issue-specific store, repository, cache, audit sink, logger,
    metric namespace, or control-plane endpoint is justified.

## Extensibility Seam

The required seam is explicit migration context over the existing generic
binding and transformation boundaries:

- a pinned scheme-snapshot adapter maps source-native term ids into the neutral
  `ExternalConceptSchemeSnapshotModel`;
- an owning subject rule exposes an exact stable RAES subject and lifecycle
  digest (including a route only when the runtime-application owner defines a
  stable route coordinate); and
- a versioned migration profile maps one recognized legacy field meaning into
  the complete assertion dimensions and declares any required author input or
  loss.

A new external scheme requires a pinned source artifact/adapter or supplied
neutral snapshot and data, not a new SDL field, Pydantic union arm, compiler
tuple, manifest scope, or report branch. A new exact RAES subject kind adds one
owner rule. A changed migration interpretation adds a profile revision rather
than silently changing old normalization.

## Gotchas And Anti-Patterns

- Do not call apparatus manifest `concept_bindings` and authored
  `external-concept-bindings/v1` interchangeable.
- Do not add `classifications`, `mappings`, `taxonomy_refs`, `ontology`,
  `metadata`, or `extensions` bags to SDL as a smaller replacement.
- Do not embed #986 assertions in SDL, compiled resources, plans, runtime
  snapshots, history events, generic metadata, logs, or reports.
- Do not remove only `vulnerabilities.class` while preserving a privileged
  native vulnerability object and association graph with the same implied
  meaning.
- Do not leave legacy data in raw compiler `spec` payloads, runtime tuples,
  template counts, aliases, temporal subjects, or semantic-comparison
  projections after deleting model fields.
- Do not infer a route assertion about its node, a vulnerability declaration
  about every related resource, or a role/mission about participant capability.
- Do not map legacy display keys directly when the pinned source concept id is
  different; ATT&CK shortnames, ATLAS shortnames, NIST adapted term ids, and
  source ids are distinct identities.
- Do not invent authority, revision, digest, relationship, perspective,
  provenance time, evidence, confidence, review, or exactness merely to make a
  legacy artifact migrate.
- Do not use current wall time, file path, username, environment, a remote
  “latest” release, or first/last match in deterministic output.
- Do not auto-follow superseded concepts, collapse collisions with a set/map,
  or silently discard unreferenced or generically referenced vulnerabilities.
- Do not treat a schema pass, source citation, binding admission, participant
  eligibility, report witness, or transformation success as realization,
  truth, capability, authorization, disclosure, delivery, or observation.
- Do not duplicate schema generation, vocabulary validation, exception trees,
  semantic diff logic, migration reporting, participant policy, persistence,
  or CI workflows.

## Non-Goals And Implementation Boundary

Issue #989 does not:

- remove native predicates that select validation, configuration, transition,
  realization, security, redaction, evidence, workflow, or participant
  behavior semantics;
- prohibit ATT&CK, ATLAS, NIST, CWE, private catalogs, curated profiles,
  source-integrity fixtures, or adapters;
- define a universal ontology for weakness, behavior, purpose, role, family,
  participant, or evidence;
- infer that an environment realizes, exhibits, knows, or proves an external
  concept;
- redesign propositions, objectives, outcomes, action contracts, realization
  envelopes, evidence records, semantic projection, participant information
  flow, native manifest concept bindings, or backend capability admission;
- add live catalog retrieval, plugin discovery, a global registry, database,
  cache, API, controller, or new persistence/audit service; or
- make migration succeed when the historical syntax does not contain and the
  caller does not explicitly supply the information required by the canonical
  binding contract.
