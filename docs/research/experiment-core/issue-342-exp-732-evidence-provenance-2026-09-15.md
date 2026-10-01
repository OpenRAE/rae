# Issue #342 EXP-732 Evidence Source And Augmentation Provenance Preflight Guardrails

Date: 2026-06-28

Revalidated against the current repository: 2026-09-15.

Issue: #342.

Requirement: EXP-732.

This preflight narrows issue #128 to preserving authored evidence
requirements, the realized evidence sources that satisfied them, and
processor/backend augmentation added for capture, evaluation, or operation.
It is implementation guidance only: it does not add schemas, fields,
validators, storage, APIs, fixtures, tests, or coverage claims.

ADR-064, ADR-065, and ADR-066 remain the design authority. The supplied issue
context records a dependency on joint design #128/#127; the current tree already
contains their contracts and conformance machinery. Their presence is not proof
of end-to-end EXP-732 implementation or a change to the issue's dependency status.

## Architecture Decisions

- Treat `experiment-run-v1` as the canonical archival join point. Do not add an
  `experiment-evidence-provenance-v1`, `run-evidence-satisfaction-v1`, or
  parallel apparatus-provenance root.
- Preserve the distinction between authored requirement, executable capture
  specification, raw evidence record, run evidence artifact, derived measure,
  realized-form disclosure, and augmentation disclosure. None is a synonym for
  another.
- Preserve authored evidence requirements by reference to their retained,
  revision-pinned SDL carrier and explicit `experiment-capture-spec-v1` / capture
  requirement binding. Retain the authored source as well as the instantiated
  scenario; an address in today's mutable SDL is not historical provenance.
  A capture specification remains intent, and generation/resolution of that
  binding must not be assumed to exist merely because fields accept refs.
- Preserve realized evidence sources through `experiment-evidence-record-v1`
  `source_refs`, `capture_spec_ref`, `capture_requirement_ref`, raw-content
  metadata, redaction/loss state, and run `traceability.evidence_record_refs`.
  Do not treat backend logs, operation records, or audit events as realized
  evidence unless they are projected through evidence records or artifact refs.
- Preserve augmentation through existing run-level
  `augmentation_disclosures`. Environment-visible, participant-visible, or
  comparability-relevant augmentation must have evidence refs traced through
  the run; apparatus-only operational augmentation may omit supporting evidence
  only when neither its purpose nor its classifications require that evidence.
- Apparatus provenance remains `experiment-apparatus-context-v1` plus manifest
  identity, selected manifests, measurement channels, observed setup evidence,
  backend observation capability declarations, and run-level augmentation or
  realized-form disclosures. Apparatus context alone must not become a hidden
  satisfaction ledger. Operational-only augmentation must still be preserved;
  exemption from supporting capture evidence is not exemption from disclosure.

## Required Incumbents

- SDL authored requirement surface: `raes.evidence_requirements`,
  `Scenario.evidence_requirements`, `SemanticValidator._verify_evidence_requirements`,
  `parse_sdl()`, `instantiate_scenario()`, fail-closed targetable refs, and
  `raes.observability_plane_semantics`. Reuse `_language_metadata.py`,
  `composition/_behavior.py`, and `validator/_evidence_requirements.py` for
  reference rewriting, semantic scope, and forwarding-agent ownership checks.
- Experiment contracts:
  `ContractModel`, `ExperimentCaptureSpecModel`,
  `ExperimentCaptureRequirementModel`, `ExperimentEvidenceRecordModel`,
  `ExperimentRunTraceabilityModel`, `ExperimentRealizedFormDisclosureModel`,
  `ExperimentAugmentationDisclosureModel`, `ExperimentRunModel`,
  `ExperimentApparatusContextModel`, `ExperimentArtifactRefModel`,
  `ExperimentReferenceModel`, `schema_bundle()`, and
  `validate_experiment_run_against_task()`.
- Admission and content proof: `raes_processor.capture_admission`,
  `compiler/observation_demands.py`, `ObservationCaptureOfferModel`,
  `raes_backend_protocols.observation_capture.ObservationCaptureOffer`,
  `ExperimentRunEvidenceInputs`, `raes_contracts.evidence_satisfaction`,
  `_evidence_content_validation.py`, and `evidence_output_validation.py`.
  These own demand/offer matching and requirement-to-record-to-byte validation.
- Conformance: `raes_conformance.conformance.observability` and
  `contracts/profiles/backend/observability-evidence.json`. Invoke
  `observability_evidence_conformance_diagnostics()` in addition to model
  validation; do not replicate its rules in a producer.
- Apparatus and capability authority:
  processor/backend manifest models, `ObservationCapabilitiesModel`,
  `ObservationCapabilities`, `OBSERVATION_CAPABILITY_REQUIRED_CONTRACTS`,
  `observation_capability_contract_gaps()`, manifest-authority helpers,
  concept-authority catalogs, and governed observation vocabularies.
- Runtime/API incumbents for any future producer or publication path:
  `RuntimeControlPlane`, `ControlPlaneStore`, `ControlPlaneSecurityConfig`,
  `ControlPlaneIdentity`, `ControlPlaneRole`, request-size guards,
  idempotency keys, request fingerprints, audit events, closed FastAPI DTOs,
  `Diagnostic`, and the redacted HTTP 500 envelope.
- Backend/OS boundary incumbents:
  `DeploymentDriver`, fixed-argv OCI driver patterns, bounded timeouts,
  image trust policy, portable handles, and sanitized diagnostics.
- Governance:
  `contracts/schemas/`, `contracts/fixtures/`, `contracts/schema-publication-manifest.json`,
  `contracts/schema-publication/entries/`, `contracts/schema-publication/tombstones/`,
  `tools/generate_contract_schemas.py`, `tools/check_generated_schemas.py`,
  `tools/check_schema_publication.py`, `tools/check_json_artifacts.py`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`,
  `tools/verify_all.py`, `.ground-control.yaml`, and `.gc/plan-rules.md`.

## Existing Enforcement And Limits

- `ExperimentRunModel` checks disclosure identities and exact evidence-ref
  membership through `experiment_artifacts._experiment_reference_key` (kind,
  id, version, digest, path, and subject where applicable). Do not replace this
  with id-only comparison. Record ids, requirement ids, and artifact ids have
  different roles even when a fixture happens to give them the same string.
- Reference membership and allowed kinds do not prove that an affected source
  exists or that the named augmentation producer is the selected apparatus.
  Preserve the actual processor/backend manifest identity, apparatus/channel
  binding, and resolvable authored snapshot. Use the owning reference and
  manifest-authority helpers for these joins. Content proof checks the admitted
  channel; it does not independently attest every claimed source or side effect.
- SEM-225 model validation and ASR-525 conformance have separate responsibilities.
  The latter requires `affected_refs`, a portable carrier, and supporting evidence
  for `evidence`, `evaluation`, or `comparability` purposes, including apparatus-only
  classifications. All selected classifications apply cumulatively. A
  capture-window or measurement-channel refinement must retain `authored_ref`
  and evidence; use the existing EXP-731 realized-form disclosure boundary.
- `validate_experiment_run_structure_against_task()` establishes structural
  compatibility only. `validate_experiment_run_against_task(..., evidence=...)`
  is the content-backed authority used by study, repeatability, and necessity
  consumers. Its evidence validator checks supplied capture/record sets, execution
  identity, channel, window, sensitivity, artifact binding, size, checksum,
  output contract, semantic validation, and field selectors. Do not substitute
  structural checks, a conformance report, or a self-reported success flag.
- Today's proof accepts exactly one record per capture requirement and requires
  requirement ids to be unambiguous across supplied specs. Summary-only,
  withheld, unsupported-redaction-policy, or unprovable-window evidence cannot
  establish satisfaction. Disclosure of a failed/partial capture remains valuable
  provenance; never erase it or weaken the proof gate to make a run pass.
- Byte validation is currently bounded to 64 MiB per artifact and supported
  JSON/JSONL contracts. `schema_bundle()` membership alone is insufficient:
  `evidence_output_validation.py` also requires an owning semantic validator
  (currently evidence records and participant behavior history streams).
  Packet captures, arbitrary logs, checksum algorithms unavailable in the host's
  `hashlib`, and unsupported integrity modes must not be advertised as verified.
- `capture_admission_diagnostics()` checks each demand against one complete
  offer; it does not combine partial offers. SDL demands with unresolved
  `capture_spec_ref` / `capture_requirement_ref` fail closed today. No implicit
  authored-to-executable resolver or producer is supplied by these fields.
  Manifest capability, admitted demand, realized description, retained operation
  payload, and captured bytes remain separate claims.
- `typed_description` already exists on evidence and realized-form carriers.
  Reuse `TypedRealizationDescriptionModel`, `validate_description_host`, and
  `description_projection.readmit_description` when describing realized sources.
  Descriptive facts are non-authoritative and cannot establish capture satisfaction;
  withheld records cannot contain known descriptive values.

## Cross-Cutting Layers

- SDL/config layer: authored evidence requirements must pass safe parsing,
  closed `SDLModel` shapes, no variable placeholders in symbol keys,
  fail-closed reference resolution, and instantiated semantic revalidation.
  Use `raes.parser` / `_yaml_loader.py`; preserve inbound apparatus evidence
  bindings to measurement forwarding agents rather than attaching output refs
  or storage credentials to authored agent inventory.
- Plane-classifier layer: source and carrier meaning must come from
  `ObservabilityEvidencePlane` and carrier-role classifiers, not words such as
  `log`, `trace`, `telemetry`, `observation`, or `evidence`.
- Contract structural layer: external artifacts must pass generated draft
  2020-12 schemas and closed-world `ContractModel` validation. Unknown fields
  remain errors. Use `raes_contracts.json_ingress.parse_bounded_json` / the
  object variant for external JSON: enforce byte/root limits and reject duplicate
  members and non-finite constants before contract validation.
- Contract semantic layer: run traceability, evidence-record content/loss
  disclosure, augmentation disclosure semantics, realized-form evidence refs,
  apparatus manifest binding, task/run protocol binding, and task evidence
  satisfaction must use existing validators and `x-raes-invariants`.
- Auth surface: any future HTTP create/read path must use existing
  control-plane identity and role checks. Publishing provenance is a mutating
  operation; dereferencing evidence content is a separate authorized read.
  `control_plane_api/_auth.py` binds identities to the target and separates
  backend/operator mutations from auditor-capable reads. Neither a provenance
  ref, a sensitivity label, nor augmentation `markings` grants access or implements
  participant projection; reuse participant audience and flow-policy gates.
- Request/idempotency surface: future HTTP paths must keep request-size guards,
  idempotency keys, request fingerprints, audit recording, and closed DTOs.
  Do not add a provenance-specific request pipeline.
- Secret-handling surface: provenance may carry sensitivity-aware refs,
  checksums, bounded summaries, redaction state, loss disclosures, and
  non-secret provenance refs. It must not carry credentials, bearer tokens,
  private keys, hidden answer keys, prompts, raw trace payloads, environment
  dumps, backend-private object reprs, full tracebacks, process argv, or raw
  captured payloads.
- Config/env-binding surface: do not introduce a new environment, token, or
  secret-binding shape. If runtime values contribute evidence, use existing
  `RuntimeEnvironmentVariable` classification/provenance, `value`/`value_from`
  exclusivity, and `runtime_values.enforce_observed_value_redaction`. Generated
  values cannot claim `operator_secret`. Runtime fact inputs must pass
  `RuntimeFactDeclarationModel` / `RuntimeFactVersionModel`,
  `runtime_fact_binding_policy.validate_binding`, and value-free secret
  projections from `RuntimeFactBindingPlane`; never serialize its private values.
- OS-level exposure: producers, fixtures, and CLIs must not pass tokens,
  credentials, backend-private payloads, or large raw evidence content through
  process arguments. Use content files, URIs, checksums, bounded summaries, and
  synthetic fixtures.
  URI/path fields are locators, not permission to access host files or network
  endpoints. The caller supplies authorized immutable `BinaryIO` readers;
  `evidence_satisfaction` must remain free of URI fetching and host-path search.
  At any reader acquisition boundary enforce containment, link/race protection,
  access scope and bounded reads; exclude credential-bearing/signed URLs from
  portable refs. Fixed argv prevents shell injection but does not hide secrets.
- Error-envelope surface: validation failures should surface as Pydantic
  errors or existing `Diagnostic` values; HTTP failures use the existing
  redacted error envelope. `control_plane_api/_operation_routes.py` owns both
  generic 422 and 500 responses; raw Pydantic error rendering can expose inputs.
  CLI producers reuse `raes_cli.processor`'s sanitized summaries. Backend failure
  observations reuse `raes_backend_libvirt._observability.record_suppressed_failure`
  and portable diagnostics, never exception strings. Do not echo full run records,
  evidence payloads, stderr, tracebacks, argv, secrets, or backend internals.
- Persistence surface: do not store the only copy of authored requirements,
  realized source satisfaction, evidence records, or augmentation provenance in
  `RuntimeSnapshot.metadata`, operation records, participant histories, audit
  details, backend DTOs, raw logs, or free-form tags. Durable persistence, if
  added later, must preserve schema-versioned experiment artifacts and refs.
  Local operational archives already use `raes_operations.run_artifacts`
  (`run_artifact_path`, `portable_artifact_ref`, `serialize_run_artifact`,
  `atomic_write_json_artifact`). Its run-id check does not validate caller-supplied
  subdirectories/filenames, enforce symlink containment, seal content, or make a
  multi-file archive transactional; keep those path segments trusted and make
  the retained byte/identity relationship explicit before a satisfaction claim.
  Hash the retained bytes, not a differently serialized reconstruction.
  Runtime retention uses `observation_results.prepare_observation_execution`
  and the existing control-plane terminal transaction/store; local-store path
  protections live in `control_plane_store_paths.py`. Reuse these where applicable,
  preserving retry/recovery identity and avoiding publication of dangling refs.
  The libvirt evidence-run artifact is an operational proof with explicit
  structural/not-live limitations, not a substitute experiment-run contract.

## Extension Boundary

Use the existing run/capture/record/artifact relationships first; the private
validated binding in `evidence_satisfaction.py` already joins requirements to
records and artifacts. This preflight does not authorize a new persisted
satisfaction relation. Demonstrate a concrete unrepresentable relationship
before proposing a governed extension to the existing contracts.

The useful seams are explicit capture-spec/record inputs, caller-owned immutable
artifact readers, and typed backend capture offers. Select backend capability,
source identity, artifact location, and governed redaction policy through those
inputs rather than backend-name branches. A new output format belongs at the
existing content/semantic-validator boundary. A future multi-source or chunked
capture must address the current one-record/global-requirement-id assumptions
there, retaining full identity and window/source/loss semantics; it must not
silently merge records in a producer or add another satisfaction engine.

## Gotchas And Anti-Patterns

- Do not treat authored evidence requirements, capture specs, backend
  capability claims, traceability refs, or scenario-native observability
  declarations as proof of capture.
- Do not treat an evidence artifact id as equivalent to an evidence record,
  capture requirement, source ref, derived measure, or augmentation disclosure.
- Do not let backend logs, operation statuses, audit records, diagnostics,
  participant histories, runtime snapshot metadata, or backend-native DTOs be
  the only portable satisfaction carrier.
- Do not use `augmentation_disclosures` or `realized_form_disclosures` as
  unstructured log lists.
- Do not duplicate schema registries, validators, reference resolvers,
  exception hierarchies, persistence stacks, manifest renderers, logging/audit
  pipelines, or workflow logic.
- Published schemas remain normative authority under ADR-009/ADR-061. A Python
  generator change alone does not authorize a contract change. Any future
  governed schema change must keep published schemas and `schema_bundle()`
  identical, update fixtures/invariant metadata, and record hashes and
  `last_change` in the affected `contracts/schema-publication/entries/<id>.json`.
  The root manifest is now a stable index; removals use `tombstones/`.

## Verification And Workflow Boundaries

Reuse `test_observability_evidence_conformance.py` and its published valid,
schema-invalid, and semantic-invalid augmentation fixtures; these exercise
different gates. `test_dsl_124_authored_evidence_requirements.py`,
`test_issue_1112_capture_admission.py`, and
`test_issue_1209_description_evidence.py` cover authored bindings, content proof,
and descriptive limits. Producer changes must also respect
`test_libvirt_evidence_run.py`, `test_libvirt_failure_observability.py`, and the
existing control-plane security/durability tests when those paths are touched.
Include absent/mismatched/version-conflicting sources, unsupported proof modes,
secret-bearing failures, and retry/partial archive cases in the owning suites;
do not count a descriptive fixture or adapter-authored reference as live evidence.

The implementation uses `.ground-control.yaml` and `.gc/plan-rules.md` for repo
policy, requirement governance, generated-schema/publication/JSON checks and the
canonical verification workflow. Set `RAES_REQUIREMENT_UID=EXP-732` when needed.
Keep requirement traceability aligned with actual code/tests; this guidance
does not grant implementation coverage, change issue status, or authorize a merge.
The 2026-09-15 preflight check reports `requirement-policy-missing`: EXP-732 is
absent from `tools/policy/requirement_order.yaml`. Resolve this through existing
requirement governance before implementation completion; do not substitute an
unrelated UID or bypass the check.

## Non-Goals

- Implementing EXP-732 behavior, schema fields, validators, producers,
  storage, APIs, fixtures, tests, or status changes in this preflight.
- Implementing runtime evidence capture, packet/log/trace collection,
  retention, sealing, redaction execution, retrieval, schedulers, workers, or
  background capture orchestration.
- Implementing derived-measure computation, evaluator behavior, statistical
  analysis, study comparison, replay, or artifact dereference authorization.
- Replacing DSL-124, SEM-224, SEM-225, experiment-core contracts, apparatus
  context, participant visibility contracts, control-plane security,
  diagnostics, schema authority, concept authority, or Ground Control policy.
