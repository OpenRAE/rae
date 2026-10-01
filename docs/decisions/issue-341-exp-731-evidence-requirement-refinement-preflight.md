# Issue 341 EXP-731 Evidence Requirement Refinement Preflight

Date: 2026-06-28

Updated: 2026-09-14

Issue: #341.

Requirement: EXP-731.

This note records architecture preflight guardrails for supporting task-, run-,
or study-level refinement and extension of authored data and evidence
requirements without silently rewriting authored scenario meaning. It is
implementation guidance only: it does not add schemas, validators, SDL syntax,
runtime behavior, APIs, storage, fixtures, tests, or coverage claims.

## Binding Sources

- ADR-066 is the semantic authority for observability/evidence plane
  separation.
- `docs/decisions/issue-337-dsl-124-authored-evidence-requirements-preflight.md`
  is the base authored evidence-requirement guardrail.
- `specs/sdl/observability-and-evidence.md`,
  `specs/sdl/references.md`, and `specs/sdl/sections.md` define the SDL
  authoring, reference-resolution, and section boundaries.
- ADR-055, ADR-064, and ADR-065 define experiment task, capture spec, evidence
  record, derived measure, run traceability, realized-form, augmentation, and
  study boundaries.
- ADR-074 and ADR-084 define the pre-run authoring and admitted-trial
  boundaries. ADR-076 defines portable declaration identity and canonical
  addresses. ADR-094 defines typed cross-plane authority bindings.
- `docs/decisions/issue-1112-required-capture-admission-preflight.md` and
  `docs/migration/required-capture-admission.md` define the canonical capture
  demand, coherent-offer admission, and content-backed satisfaction chain.
- `docs/decisions/issue-1212-scoped-observation-demand-preflight.md` and
  `specs/formal/observability-evidence-plane.md` define scoped observation
  policy and authority-aware composition.
- ADR-012, ADR-061, ADR-062, ADR-009, `contracts/schema-publication-manifest.json`,
  and `.gc/plan-rules.md` define concept authority, schema governance,
  authority boundaries, and workflow gates.
- ADR-056 and ADR-057 define explicit redaction and secret-handling boundaries.

## Architecture Decisions

- The issue #128 implementation is a partial regression guard, not the EXP-731
  architecture. Its run realized-form check only requires generic
  `authored_ref` and `evidence_refs` for `capture-window` and
  `measurement-channel` disclosures. It does not type or resolve the authored
  requirement, compare base and scoped obligations, cover task/study inputs, or
  prove that the base requirement was preserved.
- EXP-731 is a typed, scoped relationship over existing evidence concepts, not
  a new authored-meaning root and not a generic patch mechanism. The
  relationship must identify the immutable base declaration, the task/run/study
  authority that adds policy, and the materialized additional obligation.
- The authored SDL `evidence_requirements` map remains the base capture-intent
  declaration. Task-, run-, and study-level changes must not mutate that map or
  reuse the same requirement id with changed meaning.
- Base and scoped obligations compose conjunctively and retain separate
  authority and origin. Refinement adds a dimension-specific obligation that is
  demonstrably stricter or more specific; extension adds a separately
  identified obligation. An implementation must not serialize an "effective"
  requirement by overwriting the base.
- Weakening a base requirement is not refinement. If a later context cannot
  satisfy the base requirement, represent that as a new task/study version,
  explicit supersedure, run deviation, loss disclosure, invalidation, or
  exclusion criterion.
- Positive observation policy must reuse `observation-demand-v1` and its
  normalizer for purpose, semantic scope, selection, collection, retention,
  export, redaction, and integrity. Concrete capture products must reuse
  `EvidenceRequirement`, `ExperimentCaptureRequirementModel`, and
  `ExperimentCaptureSpecModel`; admission must reuse `CaptureDemand` and the
  coherent-offer matcher.
- Prospective run policy belongs in the experiment authoring/run-plan and
  selected capture-spec/admitted-plan boundary. `ExperimentRunModel` is the
  archival result. `realized_form_disclosures` describe processor/backend
  realization of underspecified concerns and must not become the prospective
  refinement carrier. Augmentation disclosure is a separate SEM-225 concept.
- Task- and study-scoped policy must have the same typed relationship and
  preserve the scenario/snapshot chain. It must not be hidden in evaluation
  prose, study inclusion criteria, validity notes, membership constraints, or
  analysis plans. A study remains an archival grouping/analysis contract, not a
  silent task protocol editor.
- Existing satisfaction validation remains authoritative. New refinement checks
  must compose with capture admission, `validate_experiment_run_against_task()`,
  and `validate_experiment_run_evidence()` instead of adding a parallel
  admission, matching, or evidence-satisfaction algorithm.
- A closed carrier can validate shape but cannot prove a cross-artifact
  refinement. The owning authoring/admission/run/study validation path must be
  given the resolved base scenario or snapshot, scoped owner, capture specs,
  and evidence inputs it needs. A context-free conformance runner must not claim
  full EXP-731 coverage.
- Requirement identity is document/snapshot scoped. Bind the exact authored
  scenario/snapshot identity (including digest where exactness is required) and
  ADR-076 canonical declaration address such as
  `evidence_requirements.<qualified-symbol>`. Materialized capture identity is
  the tuple of capture-spec id/version and requirement id. Bare requirement
  ids, titles, tags, fixture paths, and backend-native ids are not portable
  joins.
- `ExperimentEvidenceReferenceModel` and `ref_kind="evidence"` are already used
  across requirement, satisfaction, and run-artifact contexts. They do not, by
  themselves, prove which concept or authority is referenced. EXP-731 must not
  deepen that conflation: use the existing context-specific constrained
  references plus the canonical authored address, and change the shared
  reference taxonomy only through its concept/schema governance.

## Required Incumbents

- SDL base authoring: `EvidenceRequirement`, `Scenario.evidence_requirements`,
  `parse_sdl()`, `parse_sdl_file()`, `SDLModel`, `_HASHMAP_SECTIONS`,
  `SemanticValidator`, `_verify_evidence_requirements()`,
  `_named_ref_index()`, `_validate_named_ref()`, and post-instantiation
  semantic revalidation.
- Plane ownership: `ObservabilityEvidencePlane`, `PLANE_BY_SDL_SECTION`,
  `PLANE_BY_CONTRACT_ID`, `classify_sdl_section_plane()`,
  `classify_contract_plane()`, `assert_single_primary_plane()`, and
  `token_decides_plane()`.
- Experiment-core contracts: `ExperimentReferenceModel` and constrained
  reference subclasses, `ExperimentTaskModel`,
  `ExperimentSpecModel`, `ExperimentRunPlanModel`,
  `ExperimentEvaluationProtocolModel`, `ExperimentCaptureSpecModel`,
  `ExperimentCaptureRequirementModel`, `ExperimentEvidenceRecordModel`,
  `ExperimentDerivedMeasureModel`, `ExperimentRunTraceabilityModel`,
  `ExperimentRunModel`, `ExperimentStudyModel`, and
  `validate_experiment_run_against_task()`.
- Scoped policy: `ObservationDemandRule`, `ObservationDemandDocument`,
  observation-demand normalization/resolution, and the compiler mapping from
  `EvidenceRequirement.observation_demand` to a canonical
  `authority_ref`. Preserve each authority and origin; do not make a
  more-specific rule impersonate the authored rule.
- Admission and proof: `compile_scenario_capture_demands()`,
  `compile_capture_spec_demands()`, `capture_admission_diagnostics()`, exact
  capture-spec binding in admitted trial plans,
  `validate_experiment_run_evidence()`, and its content-backed artifact reader
  boundary.
- Parsing and diagnostics: the existing safe, size-bounded SDL and experiment
  spec loaders; `Diagnostic`, `Severity`, and `sanitized_failure_message()`.
  Semantic failures must use this diagnostic surface rather than a new
  exception hierarchy or raw Pydantic/backend messages.
- Schema authority: `ContractModel`, `schema_bundle()`,
  `tools/generate_contract_schemas.py`, `tools/check_generated_schemas.py`,
  `contracts/schemas/`, `contracts/fixtures/`, and
  `contracts/schema-publication-manifest.json`.
- Runtime/API exposure, if later needed: `ControlPlaneSecurityConfig`,
  `ControlPlaneIdentity`, `ControlPlaneRole`, request-size guards,
  idempotency/request fingerprints, audit records, `Diagnostic`, `Severity`,
  and the redacted FastAPI error envelope.
- Secret handling: `enforce_observed_value_redaction()`, sensitivity/redaction
  fields on experiment evidence contracts, and ADR-056/057 explicit-redaction
  discipline.

## Cross-Cutting Layers

- SDL/config layer: base authored requirements must pass safe YAML loading,
  normalized keys, closed `SDLModel` shapes, symbol-key rejection, fail-closed
  reference resolution, and instantiated revalidation.
- Experiment-input layer: task/run policy must pass the bounded safe YAML
  loader, closed `ContractModel`/Pydantic shapes, reference qualifier rules,
  observation-demand normalization, and deterministic admitted-plan digest
  binding. EXP-731 requires no new environment variable or untyped config
  dictionary.
- Plane-classifier layer: refinements remain in the authored evidence,
  captured evidence, derived analysis, processor/backend operational, or
  scenario-native planes by carrier role, never by words such as `log`,
  `trace`, `telemetry`, or `evidence`.
- Contract/schema layer: any new portable carrier must be a closed
  `ContractModel` with `schema_bundle()` parity, fixtures, semantic invariant
  annotations where needed, and a schema-publication manifest ledger entry.
- Experiment-core layer: refinement satisfaction must reuse capture-spec key
  equality, window resolution, evidence-record redaction/loss, derived-measure
  source-evidence, run traceability, and task/run cross-artifact validators.
- Admission layer: every base and scoped mandatory demand remains an independent
  conjunctive demand and must be satisfied by one coherent backend offer. Do
  not merge dimensions from different offers or let nearest-scope preference
  resolution erase an independently authored obligation.
- Study layer: study-level refinements require an explicit typed carrier and
  metric/run/evidence grounding. Existing inclusion criteria, run allocation,
  analysis plans, validity notes, and free text cannot carry a hidden protocol
  change.
- Auth/control-plane layer: future API exposure must reuse bearer/proxy
  authentication, backend/operator/auditor role gates, request-size limits,
  idempotency fingerprints, audit records, response DTOs, and redacted 500
  envelopes.
- Secret/env/OS exposure layer: refinement artifacts, diagnostics, fixtures,
  logs, command examples, and process argv must not carry operator secrets,
  bearer tokens, private keys, environment dumps, raw backend payloads, hidden
  answer keys, full tracebacks, or large raw evidence payloads. Use content
  refs, checksums, sensitivity, redaction state, and bounded summaries.
- Parser/content layer: do not fetch requirement or evidence URIs, discover host
  paths, invoke subprocesses, or pass sensitive material through argv. Exact
  comparison and normalization are pure in-process operations; evidence bytes
  remain behind caller-supplied, bounded readers used by the existing
  satisfaction validator.
- Error-envelope layer: report stable diagnostic code/address/severity and a
  bounded sanitized message. If this is ever exposed by the control-plane API,
  preserve its generic request-validation and internal-error responses and
  audit only bounded reason classes, not payloads or exception strings.
- Persistence layer: scoped refinements are portable contract data, not live
  runtime state. Do not store the only authoritative copy in
  `RuntimeSnapshot.metadata`, operation details, backend DTOs, audit blobs,
  raw logs, or free-form tags.
- Policy layer: implementation must satisfy Ground Control checks, module
  boundary policy, concept-authority governance, generated-schema parity,
  schema-publication governance, semantic coverage, and requirement
  traceability. At this preflight revision, `check_requirement_governance.py`
  rejects `EXP-731` because it is absent from
  `tools/policy/requirement_order.yaml`; implementation cannot claim a green
  governance gate until the requirement is mapped through the normal policy
  workflow.

## Extension Boundary

The extensibility seam is one typed scoped relationship with explicit
provenance, reused by the existing task/run/study input and archival owners:

- stable relationship id/version and relation kind `refine` or `extend`;
- exactly one task, run, or study authority/owner;
- exact base scenario/snapshot identity plus canonical authored declaration
  address;
- exact materialized capture-spec/requirement coordinate for the added
  obligation;
- typed, dimension-specific change and rationale/provenance; and
- fail-closed conflict/comparability results that retain both origins.

The comparison policy is the parameterized seam for the next variation: a
dimension-keyed comparator/normalizer may decide whether a value is stricter,
additional, equal, conflicting, or incomparable. Unknown dimensions and
incomparable combinations fail closed. Do not use arbitrary JSON Patch,
JSON Pointer mutation, blanket list inclusion, or a generic key/value overlay.
Future dimensions extend this governed comparison seam without changing base
identity or the admission/satisfaction chain.

This relationship is lineage, not a second evidence-requirement registry or
root persistence service. Supersedure, weakening, deviation, and exclusion are
separate explicit lifecycle concepts, not extra refinement operation values.

## Gotchas And Anti-Patterns

Avoid:

- rewriting authored SDL `evidence_requirements` during task, run, or study
  generation;
- extending `_RUN_REFINEMENT_CONCERN_KINDS` or generic realized-form
  `authored_ref` checks as though they establish prospective refinement;
- changing a requirement's meaning while preserving its id;
- treating a bare `requirement_id` as ecosystem-global, selecting the first
  matching requirement, or silently tolerating duplicate ids across capture
  specs;
- treating generic `ref_kind="evidence"` as a typed authored-requirement link,
  or conflating an evidence obligation, capture requirement, evidence record,
  satisfaction claim, and emitted artifact;
- feeding base and scoped rules to nearest-scope observation-demand resolution
  under the same authority so that the scoped value replaces the base;
- assuming that a narrower window/scope, replacement channel, longer
  retention, or stronger redaction is automatically a safe refinement. Such
  changes may leave the broader base unsatisfied, change output meaning, or
  conflict with privacy and retention policy;
- treating capture specs, backend capability claims, observability systems,
  audit records, diagnostics, or raw logs as proof of capture;
- loosening base requirements without explicit supersedure, deviation, loss,
  invalidation, or study exclusion semantics;
- resolving overlaps by first match, title text, tag strings, or backend-native
  object ids;
- putting refinement semantics only in `notes`, `metadata`, diagnostics,
  audit blobs, backend DTOs, or free-form tags;
- duplicating experiment-core capture, evidence-record, derived-measure, run,
  study, reference, capture-admission, satisfaction, observation-demand, or
  plane-classifier validators;
- leaking secrets, hidden truth, answer keys, prompts, private traces,
  environment dumps, process argv, full tracebacks, or raw evidence payloads
  through schemas, fixtures, diagnostics, logs, examples, or comments.

## Non-Goals

- Implementing EXP-731 behavior, schemas, validators, endpoints, persistence,
  capture scheduling, fixtures, tests, or requirement status changes in this
  preflight note.
- Adding a new top-level SDL section, generic evidence bag, universal
  observability model, archival provenance root, or study protocol override
  model.
- Adding HTTP endpoints, authentication roles, environment/config switches,
  subprocesses, URI fetching, host-path discovery, background workflow logic,
  or a new persistence store for the relationship.
- Defining universal ordering for dimensions that have domain-specific or
  policy-sensitive semantics. Only governed dimension comparators may classify
  a change as stricter.
- Replacing DSL-124 authored evidence requirements, experiment-core contracts,
  run provenance, study analysis semantics, control-plane security, schema
  authority, concept authority, diagnostics, audit, persistence, or workflow
  policy.
