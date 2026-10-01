# Issue 1211 progressive conformance architecture preflight

Recorded 2026-09-18. Inspected revision: `340ba7aa`.

Status: implementation guidance; non-normative.

This GOV-922 requirement-backed preflight covers GitHub issue #1211. It does not
implement the issue, change a runtime or schema, define an implementation
sequence, or claim that the acceptance cases pass. The issue and the governing
design-intent examples remain the delivery contract.

No new ADR is needed. ADR-064, ADR-066 and ADR-105 already decide the semantic
boundaries. This note prevents the integrated verification work from creating a
second constraint model, evidence system, conformance claim, catalog, or
workflow.

## Architecture decision

#1211 is a conformance aggregation and recurrence-prevention owner. It must
exercise the production path already owned by #1200--#1212, #1112 and the
experiment/runtime contracts; it must not become another production semantic
owner. A case is end to end only when the same authored input or explicit
negative mutation is traced through the applicable existing boundaries:

1. safe source decoding, closed structural models and semantic validation;
2. recursive normalization, composition/refinement and bounded evaluation;
3. compiler requirements, authority and independent observation demand;
4. planner admission, supported-completion selection and plan carriage;
5. authenticated runtime submission and backend result validation;
6. requested capture/report execution, retention and export policy;
7. atomic persistence/recovery and portable report projection; and
8. canonical formatting, composition, schema/model serialization and semantic
   round trip.

Not every negative case should reach the last boundary. It must fail at its
owning boundary, with the later side effects proven absent. A malformed parser
case is not evidence for planner refusal; an unsupported required selector is
not evidence for parser refusal.

The integrated suite should consume disk-backed ordinary YAML for the authoring
journey and existing closed JSON contracts for derived artifacts. Do not create
a progressive-specification test DSL or a duplicate scenario schema. Keep
test-only case parameters test-local. Reusable public scenarios follow the
existing `examples/scenarios` convention; raw source-profile conformance files
follow `contracts/fixtures/sdl/sdl-yaml-v1`; invalid rule-local mutations stay
beside the owning test or contract fixture.

The finite conformance claim must remain honest. Hermetic in-process lifecycle
coverage belongs in the canonical default/integration pytest graph. Released
pack/backend evidence from env-packs#312 and Hub#3 is separately identified
external journey evidence. It must not be represented as native execution by a
stub or recording driver, and RAE must not absorb the pack, backend recipe, or
private product catalog. If a durable backend conformance report is required,
extend the existing `raes_conformance` profile/report boundary and its bounded
claim validation; do not publish a second report hierarchy.

## Semantic separations the suite must preserve

| Concern | Distinctions that must remain independent | Canonical owner |
| --- | --- | --- |
| Author authority | omitted/delegated, exact, constrained, optional, forbidden, unknown and local closure | `raes_contracts.realization_structure`, ADR-105 |
| Collection identity | stable keyed identity, ordered occurrence and local closure universe | recursive realization normal form and profile-owned identity metadata |
| Backend admission | one selected supported completion versus universal envelope coverage | `backend-realization-preparation-v1`, planner preparation and ADR-070 envelope checks |
| Realized description | backend-selected value versus observed or independently verified fact | typed realization descriptions, realized-form disclosures and validation-basis disclosures |
| Data lifecycle | reporting, collection, retention, export and operational use | `observation-demand-v1`, ADR-064/066, #1112 capture admission |
| Extension identity | private/domain identity versus executable grammar operator or policy decision | controlled vocabularies, domain profiles and owning finite enums |
| Completeness | complete at the declared abstraction versus complete concrete machine inventory | recursive constraints and scientific scenario-completeness guidance |
| Assurance | fixture validity, hermetic realization, native realization and backend conformance | `raes_conformance` execution basis and bounded claim validation |

The acceptance anchors are a cross-product, not a catalog of independent
happy paths. In particular, realization detail must be crossed with observation
demand: exact image/filesystem with no experimental collection; abstract
behavior with bounded exhaustive action traces; and mixed packet,
operational-only and no-data scopes with independent retention/export policy.
The backend-known selection case carries backend basis without fabricated
evidence. Genuinely required capture and exact-value violations still fail.

## Canonical incumbents and required reuse

| Layer | Canonical incumbents | Required treatment |
| --- | --- | --- |
| Governing semantics | `docs/research/language-extensibility/design-intent.md`, ADR-064, ADR-066, ADR-105, `specs/sdl/recursive-realization-constraints.md`, `specs/sdl/observability-and-evidence.md` | Treat these as the semantic oracle. Tests must not redefine omission, openness, evidence basis or lifecycle defaults. |
| YAML and source limits | `raes._yaml_loader`, `_source_validation`, `_mapping_key_analyzer`, `_source_profile.SDLParserLimits`, `parse_sdl()` / `parse_sdl_file()` | Use YAML 1.2 safe decoding, duplicate/key diagnostics and byte/depth/node/alias/import/composition budgets. Do not call `yaml.safe_load` as an alternate authoring boundary. |
| Structural and semantic validation | `SDLModel(extra="forbid")`, `Scenario`/`ScenarioContent`, `SemanticValidator`, source-ranged `SDLParseError` and collect-all `SDLValidationError` | Test closed syntax separately from open realization semantics. Reuse target/reference resolution and model validators; do not duplicate them in the harness. |
| Published schemas | hand-governed `contracts/schemas`, reference `schema_bundle()`, schema publication entries and generated-parity checks | Validate normalized and derived artifacts through existing schemas. Schema validity is not semantic admission. #1211 needs no new schema unless a genuinely new public artifact is approved. |
| Recursive relations | `raes_contracts.realization_structure`, semantic addresses, collection profiles and `RealizationConstraintLimits` | Reuse normalization, evaluation, conjunction, refinement, stable identities and bounded outcomes. Do not add a test-only evaluator or leaf registry. |
| Composition and round trip | module expansion/provenance, `instantiate_scenario`, canonical SDL helpers, formatting, semantic revisions/comparison and phase contracts | Preserve omission, exact siblings, private identities, source origins and semantic addresses. Compare semantics, not incidental YAML ordering or DTO equality. |
| Compiler | `compile_scenario_runtime_model()` / `compile_runtime_model()`, `CompiledRealizationRequirement`, `CompiledRealizationAuthority` and compiler recursive adapters | Assert the existing authority and demand carriers. Do not infer evidence from realization detail or add a parallel compiled DTO. |
| Planner and capability admission | `raes_processor.planner.plan`, `ResolvedRealizationAuthority`, preparation authority, realization support/envelope diagnostics and `capture_admission_diagnostics()` | Keep selected-witness and universal-capability tests distinct. Planner-created and directly submitted plans must pass the same gates. |
| Runtime and result admission | `RuntimeManager`, `RuntimeControlPlane`, `backend_input_violation`, preparation/apply/result finalization, materialization and realization-honesty checks | Exercise the real admission/result path. Unsupported semantics and dishonest success fail before publication; backend exceptions do not become public payloads. |
| Observation and reporting | observation-demand normalization, runtime capability matching, `execute_observation_lifecycle`, typed descriptions, capture admission and evidence refinement | Use producer/store/export spies at the impurity boundaries. Report omission alone does not establish that collection or retention did not occur. |
| Persistence and recovery | `ControlPlaneStore`, `InMemoryControlPlaneStore`, `LocalControlPlaneStore`, snapshot codecs, terminal atomic commits and observation result payloads | Assert both value presence when explicitly retained and value absence everywhere when disabled/forbidden. Reuse revision, integrity, idempotency and recovery behavior; add no side store. |
| API and authorization | `ControlPlaneSecurityConfig`, `_ControlPlaneApiAuth`, request-size middleware, planner authorization, target binding and closed plan DTO projection | API cases use real role/target authorization and request admission. A reportable value or valid plan shape never grants access or planner provenance. |
| Diagnostics and audit | SDL error types, `Diagnostic`/`DiagnosticModel`, portable diagnostic projection, operation receipts/status and bounded audit paths | Assert stable codes, owning addresses and value-free messages. Do not add an exception family, log channel or raw backend-output assertion. |
| Backend/OS boundary | backend protocols, reference/libvirt targets, fixed-argv native helpers, bounded timeouts, private files and captured output | Hermetic cases do not launch native acquisition/probes. Released-native evidence retains no-shell/fixed-argv, timeout, environment and output controls. No secret or observed value enters argv or logs. |
| Conformance and CI | `raes_conformance.conformance`, existing backend profile artifacts, `BackendConformanceReport`, pytest markers, nox verification and canonical verification shards | Reuse bounded claims and execution-basis labels. Do not create a new CI workflow or opt the hermetic regression suite out of the required graph. |
| Prevention ledger | `product-semantics-audit.md`, `product-semantics-fields.md`, `scope-inventory.md`, the runtime semantic review checklist and `test_issue_959_audit_coverage.py` | The mechanical graph census proves coverage and drift detection only. Human dispositions decide ownership, closed-set rationale, private/partial behavior and extension/admission semantics. |

Existing focused tests are evidence inputs, not substitutes for an integrated
case. The five-node and recursive algebra anchors live in the #1201/#1203
suites; the Kali ladder in #1205; vocabulary/private/round-trip cases in #1206;
partial runtime descriptions in #1207; typed profile composition in #1208;
description lifecycle in #1209; migration/comparison in #1210; capture admission
in #1112; and scoped collection/persistence/API boundaries in #1212. The
observability corpus and #340 augmentation cases retain evidence-plane and
augmentation ownership.

## Cross-cutting security and operational gates

Every applicable integrated path must pass these existing layers:

| Layer | Required proof |
| --- | --- |
| Source admission | Input passes the canonical UTF-8/YAML source boundary and explicit parser limits. Limit mutations produce the bounded source or relation outcome rather than a crash, mismatch or success. |
| Model/config shape | SDL and contract DTOs remain closed; discriminators, enums, lists and scalar sizes retain their bounds. A private identity is admitted only by its owning vocabulary/profile grammar, never by `extra` fields or an arbitrary dictionary. |
| Reference/profile trust | Module, semantic-address, component and profile references resolve exactly once through existing offline/pinned resolvers. Tests do not fetch schemas, install handlers or execute profile-supplied code. |
| Secrets and environment | Use `BindingValue`, secret-reference/value-free account projection, `RuntimeEnvironmentVariable` and redaction validators. Fixtures contain synthetic references, not credentials. Diagnostics, snapshots, reports and case names contain no secret value or ambient environment capture. |
| API auth and plan provenance | Mutations pass verified identity/bearer comparison, role and exact target binding, request-size admission, planner-produced plan authorization, idempotency/fingerprint checks and bounded denial audit. Direct submission is not a bypass. |
| Backend impurity boundary | Admission completes before backend apply, capture or native execution. Backend arguments are isolated and results pass the existing input/result/materialization validators. Credential-bearing diagnostics and snapshots use the value-free projection. |
| OS/process exposure | The hermetic matrix performs no incidental subprocess or network work. Any separately labelled native journey uses allowlisted/fixed argv, no shell, bounded timeout and output, controlled working directory/environment and private files; tokens, selectors, credentials and observed values are absent from argv. |
| Data lifecycle | Required/prohibited conflicts, unsupported selectors and unavailable export/atomicity fail before collection. Non-retained data is absent from queues, result payloads, snapshots, local-store rows, temporary artifacts, audit details and recovery, not merely filtered from the response. |
| Persistence | Accepted terminal state, allowed observation payload and actor-bound audit commit atomically through the existing store with revision/integrity checks. Failed or forbidden cases leave the baseline snapshot and durable payload unchanged. |
| Error envelopes | Parser/semantic errors use the SDL hierarchy; portable failures use bounded diagnostics; HTTP validation and unexpected failures retain redacted 422/500 envelopes. Native stderr, Pydantic rejected input, host paths, exception text and private values do not cross the public boundary. |
| Logging/observability | Existing lifecycle and audit events record action, stable identity, scope and reason code only. Experimental data, description bodies, environment contents and backend stdout/stderr are not logged. |

## Extensibility seam

The test matrix varies four existing inputs independently: an ordinary scenario,
a backend target/manifest, an observation-demand policy and explicit work
limits. Expected outcomes name the owning terminal boundary and side-effect
posture. A new private profile, backend-supported completion, observation data
kind or non-cyber scenario plugs into those existing seams; it must not require
editing a central scenario/product enum or the recursive relation.

Backend variation belongs behind `RuntimeTarget`, manifest capability and
observation-runtime interfaces. Semantic extension variation belongs behind
pinned domain-profile/controlled-vocabulary admission. Observation variation
belongs in the versioned selector/policy algebra. If the suite needs reusable
case metadata, it remains a bounded test helper unless an independently reviewed
public conformance artifact is required.

This parameterization is also the guard for the next reasonable change: adding
another backend or domain example should add a target/case and its declared
capability, not fork parser, compiler, planner, validation, persistence or
reporting logic.

## Resolved dependency consumed by this delivery

The preflight revision had one documented catalog-shaped defect:
`RuntimeApplicationRoute.normalize_methods()` rejected extension methods and
collapsed method identity. #1298 has since shipped the owning correction, along
with exact private/WebDAV identity and migration coverage. #1297 and #1299's
service-manager/listener corrections are also present.

#1211 consumes those production boundaries without weakening HTTP method
validation locally or duplicating their implementations. The
candidate/disposition reconciliation must also retain #989's generic
classification-binding ownership and #1167's status-prose ownership instead of
reopening either implementation surface.

## Gotchas and anti-patterns

- One known product fixture, one backend, one valid schema document or one
  successful witness cannot establish this issue's class-wide claim.
- A Pydantic field being optional does not prove partiality; defaults and model
  validators may still make the surrounding product shape compulsory.
- Do not use schema acceptance as compiler/runtime conformance, or a census as
  semantic correctness.
- Do not copy one scenario independently into parser, compiler, planner and
  runtime fixtures. Drift would make the apparent end-to-end result a set of
  unrelated unit cases.
- Do not generate the ordinary authoring examples from Python dictionaries;
  that bypasses raw YAML presentation and makes the journey uninspectable.
- Preserve omitted, empty, null, absent, unknown, redacted and delegated as
  distinct states. Preserve exact siblings beneath inherited open scopes.
- Negative mutations must remove or alter one relevant fact and must assert the
  expected diagnostic plus absence of later side effects. Do not let an earlier
  malformed shape accidentally satisfy a later negative case.
- Keep backend-selected reporting distinct from experimental observation and
  independent verification. Never attach evidence refs to a value merely
  because the backend knew it.
- Test no-collection/no-retention with producer, store, temporary-artifact and
  export assertions. A concise or redacted final report is insufficient.
- Preserve the universal-capability negative tests when adding the allowed
  one-completion positive case. Do not redefine `subsumes` as overlap.
- A private identity or profile is not backend support, authorization,
  executable semantics or proof. Finite operators, security decisions and
  contract versions remain closed for stated reasons.
- Do not add a core/replacement catalog, generic attribute bag, per-property
  opt-outs, complete concrete-machine normal form, placeholder evidence, or
  fabricated infrastructure to make a fixture pass.
- Do not add a parallel schema bundle, validator, exception hierarchy,
  diagnostic renderer, log, store, API route, backend workflow or CI graph.

## Non-goals and implementation boundaries

#1211 does not own new SDL syntax, a runtime/schema correction, a backend or
pack implementation, profile distribution, task/run/study refinement, capture
capability implementation, augmentation semantics, source-provenance semantics,
evidence integrity, or export delivery. Defects found by the conformance matrix
remain with their focused semantic owner and block the broad completion claim.

It does not certify every backend, all private domains, all possible
realizations, native libvirt/OCI fidelity, universal support, or observational
completeness. The external LilRAE/env-packs journey is coordinated evidence,
not code moved into RAE. Audit #1198 and its documentation publication close
separately.

The issue owns integrated positive/negative regression evidence, lifecycle
side-effect assertions, the completed candidate/disposition reconciliation and
the practical review rule already housed in
`docs/explain/sdl/validation.md`. It must explicitly name the contrary tendency:
backend recipes/specimens becoming compulsory author detail, compulsory
extension catalogs, or unconditional evidence obligations.
