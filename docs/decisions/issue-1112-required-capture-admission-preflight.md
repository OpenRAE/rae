# Issue 1112 Required Capture Admission Preflight

Date: 2026-09-06

Issue: #1112. Requirement: none. The GitHub issue is the authoritative delivery
contract.

This note records architecture guardrails only. It does not implement capture,
change a published contract, select a backend, or prescribe an implementation
sequence.

## Preflight Finding

The repository has the right phase owners but no end-to-end satisfaction proof:

- SDL `EvidenceRequirement` and `ExperimentCaptureRequirementModel` express
  intent, while task observation and metric evidence requirements identify
  evidence the task needs.
- backend `ObservationCapabilities` advertises only independent coarse sets and
  global booleans. It cannot truthfully state which fields occur together in
  which emitted artifact, or distinguish unsupported, unavailable, lossy,
  redacted, and withheld coverage.
- planner evaluator checks reduce proposition evidence requirements to channel
  names; no planner check joins the effective SDL/task capture demand to the
  selected backend observation declaration.
- run validation currently accepts artifact identity or backend-authored
  `satisfies_refs` as satisfaction. Neither proves that bytes were emitted or
  that promised fields and semantics are present.

The correction is one closed evidence chain using the existing authored-intent,
manifest, planning, evidence-record, artifact, and run carriers. It must not add
a parallel evidence model, treat manifest validity as execution proof, or make
all describable scenario state into capture demand.

## Binding Boundaries

- ADR-064 owns capture intent, raw evidence, derived measures, and run
  traceability. ADR-066 and
  `specs/formal/observability-evidence-plane.md` own plane separation; in
  particular, a capture requirement or capability claim is not captured
  evidence.
- #341 retains task/run/study refinement and requires composition with
  `validate_experiment_run_against_task()`. #340 retains augmentation
  conformance. #342 retains the run-level provenance join and is the owner of a
  typed requirement-to-evidence satisfaction relation if existing references
  are insufficient.
- #1212 owns effective scoped observation/reporting demand and the distinction
  among no experimental data, operational-only use, selected observation,
  retention, and export. #1112 consumes that effective demand; it must not
  pre-empt #1212 with inferred demand or a second policy syntax.
- Exact image, file, package, topology, or realization requirements do not by
  themselves require experimental observation. Required execution, control,
  termination, evaluation, or analysis inputs still remain obligations when
  their owning contracts explicitly require them.

## Architecture Decisions And Guardrails

### Normalize only effective required demand

Compile a deterministic, internal capture-demand projection from the existing
owners rather than adding another authoring root. Each demand atom retains its
canonical origin identity and source pointer, requirement kind, required output
carrier/profile and field selectors, artifact role/media type where applicable,
source/scope/channel/window semantics, and integrity, sensitivity, redaction,
loss, retention, and export constraints.

The projection has four input families:

1. selected SDL `Scenario.evidence_requirements`, including requirements used by
   proposition, participant outcome, control, and temporal/termination
   semantics;
2. task `evaluation_protocol.observation_requirements` and each metric's
   `evidence_requirements`;
3. the concrete, selected `ExperimentCaptureSpecModel.capture_requirements`; and
4. typed execution/control/termination/evaluation/derived-measure inputs that
   an owning runtime or experiment contract makes mandatory.

Every task evidence reference must resolve to a concrete authored or capture
requirement (or a governed typed output profile) before capability matching. An
opaque or ambiguous id is an admission error, not a wildcard. A capture-spec
reference without the exact typed payload is likewise not admissible.

Do not scan all precise scenario fields, all available schemas, backend setup
recipes, generic `evidence_refs`, or all runtime metadata and call them demand.
The future #1212 policy result belongs as an explicit input to the same demand
projection. An empty effective demand is valid and does not require an
observation capability block.

### Extend the existing manifest observation seam with coherent offers

Publish field/artifact coverage under the existing
`ObservationCapabilitiesModel` / `ObservationCapabilities` block. Keep the
current coarse sets as discovery summaries only; they are never proof that a
particular requirement is satisfiable.

The admission-bearing unit is a coherent, versioned capture offer. One offer
binds, without an accidental Cartesian product:

- the output contract/profile and supported field selectors;
- artifact role and media type, or the typed inline/runtime carrier;
- capture kind, source class, scope, exact authored scope targets, channel, and
  supported window/trigger modes;
- integrity/sealing/chain-of-custody guarantees; and
- availability/applicability plus loss, redaction, withholding, retention, and
  export behavior.

A required datum or artifact must match every relevant dimension of one offer,
or an explicitly identified atomic offer group when one requirement genuinely
needs several coordinated outputs. Independent global lists, booleans, prose
`constraints`, supported contract ids, and apparatus `capability_refs` cannot
be combined into a synthetic offer.

Coverage dispositions are governed values with distinct meanings:

- **unsupported** means the backend has no implementation for the coverage;
- **unavailable** means the implementation exists but is not available for the
  selected applicability context;
- **lossy** means some events/fields may be omitted or transformed;
- **redacted** means declared content is transformed under a redaction policy;
  and
- **withheld** means content is intentionally not disclosed to this consumer.

These states are not aliases. `loss_disclosure_required` requires honesty about
loss; it does not authorize loss. A withheld or redacted reference is not
satisfaction of data needed for evaluation unless the effective requirement
explicitly permits that exact weaker semantic. A conflict between an explicit
prohibition and mandatory execution/operator policy is diagnosed, never
silently resolved by collecting or dropping the data.

### Use one pure, conjunctive admission matcher

One shared matcher must compare normalized demands with selected manifest
offers. It returns all unmet requirements as existing `Diagnostic` values in a
stable order based on origin/pointer and failed dimension. Matching must not be
first-fit, order-dependent, backend-named, or spread between the planner, trial
compiler, conformance runner, and adapters.

Use that matcher at every authoritative execution ingress:

- ordinary SDL planning adds its diagnostics in `raes_processor.planner.plan()`;
- trial compilation selects each concrete scenario, then evaluates its realized
  scenario demand plus task and concrete capture specs before sealing
  `AdmittedTrialPlanModel`;
- `trial_realization.realize_admitted_trial_entry()` revalidates the digest-bound
  inputs and selected manifest before producing an `ExecutionPlan`; and
- direct control-plane phase submissions cannot mint a new execution path.
  Generalize the existing exact planner-authorization digest gate for non-empty
  provisioning plans to non-empty orchestration and evaluation plans as well.

Concrete capture specs used for admission must be supplied to the pure trial
compiler and digest-bound through the existing admitted-plan input/integrity
chain. Refs alone are insufficient. Do not put an unsealed success assertion in
`admission.limitations`, a phase plan's free-form payload, or snapshot metadata.

`RuntimeManager.apply()` remains the in-process no-side-effects boundary: an
invalid `ExecutionPlan` is rejected before backend `validate` or `apply` calls.
The operation submission path must preserve the same property. Empty/no-op
plans may retain their existing behavior because they cannot start work.

### Prove satisfaction against emitted content

Strengthen the existing task/run cross-artifact validation; do not add a second
satisfaction algorithm. The authoritative post-run join is:

`effective demand -> capture requirement -> evidence record -> emitted carrier/artifact -> validated content fields`.

`ExperimentEvidenceRecordModel.capture_spec_ref` and
`capture_requirement_ref` are the direct capture-intent link. Run
`traceability.evidence_record_refs` must resolve to supplied evidence-record
payloads. If task evidence concepts cannot be related unambiguously through
those fields, add the typed relation anticipated by #342 under the existing run
traceability/provenance boundary. Do not strengthen `satisfies_refs` into a new
authority.

For each claimed satisfaction, validate identity/version/run/task/source,
capture window and kind, sensitivity/redaction/loss state, required artifact
role/media type, integrity policy, and the promised fields in the actual
emitted carrier. An artifact id, URI, checksum, `payload_summary`,
`satisfies_refs`, operation detail, audit entry, or adapter log is insufficient
on its own.

For external artifacts, use the associated-artifact validator's explicitly
supplied bounded `BinaryIO` readers to prove presence, size, and digest. Parse
structured content through `json_ingress` and the declared closed Pydantic
contract/profile before resolving field selectors. Never dereference arbitrary
artifact URIs, trust a backend-authored validation receipt as the sole proof, or
search host paths. If bytes or a governed parser/profile are unavailable, field
coverage is unproved and the claim fails closed.

Backend phase output continues through `_call_backend_apply()` and its snapshot
contract/transition/realization gates before persistence. Final experiment-run
satisfaction belongs at the run finalization/archive validation boundary,
because evidence may not exist during provisioning. A failed post-run proof
marks the run claim invalid/unsatisfied; it must not retroactively manufacture
successful evidence.

### Migrate fail closed and preserve schema authority

Absence of admission-bearing capture offers means unsupported whenever
effective demand is non-empty. Legacy coarse observation lists and positive
booleans do not receive a compatibility fallback. Backends may remain rejected
until they publish truthful offers and emit what they promised.

Assess the manifest change under ADR-061. If an additive v2 field can retain
published structural compatibility, admission may consume it fail closed; if
the change redefines an existing v2 claim for other consumers, publish the next
contract version instead of silently changing v2 semantics. In either case,
update the Pydantic source, dataclass mirror, canonical renderer/parser,
allowlists/profile declarations, generated schema bundle, fixtures, and schema
publication ledger together. Never hand-edit generated schemas.

## Equivalent-Gap Audit

| Existing surface | Gap to close with the same authority |
|---|---|
| `raes.validator._evidence_requirements` | `capture_spec_ref` and `capture_requirement_ref` are not resolved; bind them or reject them before planning. |
| `raes_processor.compiler.evaluation` and planner evaluator checks | Only proposition channel kinds reach evaluator compatibility. They cannot stand in for backend capture coverage or omit standalone/task requirements. |
| `observation_capability_contract_gaps()` | It checks required contract ids only when an observation block exists and is conformance-only. Reuse contract coupling, but require semantic offers only when effective demand exists. |
| backend manifest model/dataclass/rendering | Observation contract coupling and any new offer validation must agree in both representations and survive exact round trips. |
| `trial_compiler.apparatus._manifest_capability_ids()` | A supported contract id or alias is treated as an apparatus capability. It may prove contract transport only, never capture semantics. |
| trial compiler/admitted plan/realization | Capture specs are currently refs rather than exact compiler inputs. Bind payload digests and repeat the same check at realization. |
| control-plane operation routes | Only non-empty provisioning is planner-authorized; orchestration/evaluation can otherwise bypass full scenario/task admission. |
| `experiment_run._artifact_satisfies_evidence_reference()` | Artifact id and `satisfies_refs` are static claims. Replace semantic use with the shared content-backed run validator. |
| `experiment_conditions._condition_reference_matches_evidence()` | It repeats the same `satisfies_refs` bypass. Condition matching must consume validated satisfaction, not recompute trust from ids. |
| raw evidence and run traceability | `payload_summary`, content URI/checksum, and evidence-record refs prove neither readable content nor promised fields without supplied payloads/bytes. |
| participant/control/outcome/temporal `evidence_refs` | These refs are provenance/contract links. They create capture demand only where their owning semantics require it and prove nothing until resolved to validated evidence. |

The broader manifest audit must also exercise existing time, cleanup,
participant, realization-envelope, source-artifact, service-materialization,
domain-topology, evaluator, and orchestrator admissions for the same anti-pattern:
a contract id, coarse boolean/list, unchecked ref, or self-authored claim must
not replace the owning semantic matcher. Reuse their current validators; do not
fold those concerns into capture admission.

## Canonical Incumbents To Reuse

- **SDL/config:** `_yaml_loader`, `SDLModel(extra="forbid")`, `parse_sdl()`,
  `instantiate_scenario()`, `SemanticValidator`,
  `_verify_evidence_requirements()`, canonical targetable-reference resolution,
  and post-instantiation revalidation.
- **Plane and intent:** `EvidenceRequirement`,
  `ObservabilityEvidencePlane`, carrier-role classifiers,
  `ExperimentCaptureSpecModel`, `ExperimentCaptureRequirementModel`,
  `ExperimentTaskModel`, and `ExperimentEvaluationProtocolModel`.
- **Manifest:** `ObservationCapabilitiesModel`, `ObservationCapabilities`,
  `BackendManifestV2Model`, `BackendManifest`,
  `backend_manifest_v2_model()`, `backend_manifest_from_v2_model()`,
  `BACKEND_SUPPORTED_CONTRACT_IDS`, backend profiles, controlled vocabularies,
  and `observation_capability_contract_gaps()`.
- **Planning/admission:** `RuntimeModel`, `PropositionRuntime`,
  `raes_processor.planner.plan()`, `ExecutionPlan`,
  `TrialCompilationRequest`, `AdmittedTrialPlanModel`, exact apparatus manifest
  validation, trial input digest/sealing helpers, and
  `realize_admitted_trial_entry()`.
- **Runtime/API:** `RuntimeManager.apply()`, `_submitted_plan_diagnostics()`,
  planner-produced plan digests, `_call_backend_apply()`, snapshot contract and
  transition diagnostics, `ApplyResult`, baseline-snapshot rollback,
  `ControlPlaneSecurityConfig`, role/target auth, request-size guards,
  idempotency fingerprints, `AuditEvent`, and redacted FastAPI errors.
- **Evidence proof:** `ExperimentEvidenceRecordModel`,
  `ExperimentRunTraceabilityModel`, `ExperimentRunModel`,
  `ExperimentDerivedMeasureModel`, `ExperimentEpisodeControlModel`,
  `ParticipantControlOccurrenceModel`, `ParticipantTemporalStateTransition`,
  `ParticipantOutcomeInterpretationRecord`,
  `validate_experiment_run_against_task()`, associated-artifact manifests and
  validators, `json_ingress`, `uri_safety`, checksum models, and #342's existing
  run-level provenance boundary.
- **Diagnostics/persistence:** immutable `Diagnostic` / closed
  `DiagnosticModel`, `RuntimeSnapshot`, `ControlPlaneStore` and its atomic
  codecs, and schema-versioned experiment artifacts. No new exception family,
  logger, evidence repository, or workflow engine is needed.
- **Schema/workflow:** `ContractModel(extra="forbid")`, `schema_bundle()`,
  `contracts/schemas/`, `contracts/fixtures/`,
  `contracts/schema-publication-manifest.json`,
  `tools/generate_contract_schemas.py`, `tools/check_generated_schemas.py`,
  `tools/check_schema_publication.py`, `tools/check_json_artifacts.py`,
  `tools/policy/adr_policy.yaml`, `.ground-control.yaml`, and
  `.gc/plan-rules.md`.

## Cross-Cutting Layers The Design Must Pass

| Layer | Required behavior |
|---|---|
| YAML/source validation | Continue through safe YAML loading, duplicate/alias/tag/scalar limits, closed SDL models, fail-closed refs, variable-key rules, and instantiated semantic revalidation. Capture refs must resolve; an unknown id cannot degrade to free text. |
| Contract/schema validation | Use closed `ContractModel` shapes, governed enums/profile ids, cross-field invariants, valid/invalid fixtures, generated-schema parity, and the publication ledger. Schema validity is not admission or evidence. |
| Manifest/config shape | Keep Pydantic and dataclass forms symmetric through the canonical renderer/parser; validate contract allowlists, concept terms, offer coherence, unique ids, field selectors, and applicability. No env flag or free-form `constraints` entry grants coverage. |
| Digest/phase boundary | Digest-bind scenario family, task, capture specs, manifests, and admitted plan. Keep authored demand, planned capability, emitted evidence, and derived analysis distinct. Never let a ref-only or stale payload survive readmission. |
| Planner/admission | Run the shared conjunctive matcher, report every unmet atom deterministically, and keep `ExecutionPlan.is_valid` false. `RuntimeManager.apply()` and phase submission reject before any backend call. |
| Runtime backend output | Preserve deep-copy isolation, closed `ApplyResult` checks, changed-address/transition/snapshot validation, realization disclosure, sanitization, and baseline rollback. Backend details/logs cannot satisfy evidence. |
| Post-run evidence | Resolve typed records and artifacts, validate bounded bytes plus declared content schema/profile and required field selectors, then validate task/run satisfaction and derived inputs. Missing/lossy/redacted/withheld content passes only when explicitly admissible. |
| Persistence | Round-trip any typed admission/satisfaction data through the existing admitted plan, runtime snapshot where live state is required, and experiment run/evidence artifacts. Never use metadata, operation details, audits, or a sidecar as the only authority. |
| HTTP/auth | No new endpoint or auth mode is needed. Preserve strict defaults, constant-time bearer checks, trusted-proxy opt-in, backend/operator/auditor roles, target scoping, request bounds, idempotency, and denied/failed audit events. Evidence-content read authorization remains separate from run-metadata access. |
| Secret handling | Portable demands, manifests, diagnostics, audit details, fixtures, and run metadata carry ids, profiles, digests, sensitivity/redaction state, and bounded summaries only. Do not carry credentials, tokens, signed URLs, private keys, environment dumps, hidden truth, raw sensitive content, or backend reprs. |
| Env/config binding | This issue needs no new environment variable, token lookup, secret-binding shape, or backend-specific toggle. Operator capture/retention destinations remain deployment policy and cannot loosen portable requirements. |
| OS/process exposure | Admission is pure and requires no process. Content validation uses caller-supplied bounded readers, not URI fetching or host-path discovery. If an existing backend producer invokes a process, preserve fixed argv, no shell, allowlisted executable/runtime, bounded timeout/output, and never place secrets or raw evidence in argv/logs. |
| Error envelope/observability | Use Pydantic errors at parse boundaries and existing `Diagnostic` values in planner/runtime flows. API errors remain redacted; audits and logs contain safe ids/codes/counts, not payloads, URLs, exception text, stderr, or tracebacks. |
| Module boundaries | Portable DTOs stay in `raes_contracts`; backend dataclass mirrors stay in `raes_backend_protocols`; SDL compilation/matching stays in `raes_processor`; runtime effect gates stay in `raes_runtime`. Preserve `tools/policy/adr_policy.yaml`; do not introduce reverse imports. |

## Extensibility Seam

The seam is a versioned output contract/profile plus field/artifact selectors on
one coherent manifest offer, consumed by a matcher parameterized by effective
demand origin and applicability context. A future capture kind, output format,
or #1212 scoped-demand policy adds a governed profile/term, its closed content
validator, and an offer/demand adapter; it does not edit backend-name branches,
fork the planner, or redefine generic `satisfies_refs`.

Keep content acquisition separate from matching. The matcher accepts resolved,
digest-bound inputs; the post-run validator accepts explicit artifact readers
and a governed profile resolver. This permits a future storage mechanism or
structured format without granting ambient network/filesystem access or
changing evidence authority.

## Gotchas And Anti-Patterns

Avoid:

- interpreting exact images/files/packages, scenario detail, available schemas,
  or backend recipes as implicit observation demand;
- treating operational use, collection, retention, and export as one boolean;
- treating `loss_disclosure_required` as permission for loss, redaction support
  as permission to redact, or withholding as successful capture;
- flat lists/booleans whose Cartesian product overclaims a coherent output;
- using a supported contract id, channel name, media type, capability alias, or
  `capability_refs` entry as semantic coverage;
- accepting ids, URIs, checksums, summaries, `satisfies_refs`, traceability refs,
  manifest claims, adapter receipts, metadata, details, or logs as content
  proof;
- resolving requirements by title text, backend name, fixture path, first
  match, or fallback order;
- checking only the first gap, or emitting nondeterministic/set-order
  diagnostics;
- validating artifact bytes by ambient URI fetch, host-path search, unbounded
  parsing, or shell/process output;
- trusting a plan supplied over HTTP without exact in-process planner
  authorization;
- adding backend-specific exceptions or compatibility defaults for legacy
  manifests; and
- creating a second capture-spec, reference resolver, satisfaction algorithm,
  diagnostic/exception hierarchy, schema registry, persistence store, audit
  stream, plan type, or workflow path.

## Non-Goals And Implementation Boundaries

- No mandate to capture every describable or realizable field, and no #1212
  policy syntax/defaults in this issue.
- No backend-specific collector, packet/log/action capture implementation,
  scheduler, evaluator, retention service, export service, evidence browser, or
  artifact store.
- No weakening of #341 refinement, #340 augmentation conformance, #342
  provenance, existing participant visibility, or realization requirements.
- No claim that admission proves execution success; admission proves only that
  the selected manifest makes a sufficiently precise compatible promise.
- No claim that post-run schema validity alone proves scientific correctness,
  semantic truth, completeness beyond the admitted selectors, or independent
  corroboration.
- No new endpoint, auth mode, secret/config surface, environment variable,
  subprocess, persistence service, or exception family.
- No implementation code, contract/schema change, fixture, manifest migration,
  backend update, or test change in this preflight note.
