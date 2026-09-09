# Observability and Evidence Plane Formal Design

This cross-domain formal design artifact supports ADR-066 and issue #127 for:

- `SEM-224` - Observability Plane Separation Semantics
- `SEM-225` - Realization Augmentation And Environment-Visibility Semantics
- `DSL-123` - Scenario-Native Observability And Telemetry Systems
- `DSL-124` - Authored Data And Evidence Requirements
- `RUN-316` / `API-419` / `ASR-525` / `EXP-731` / `EXP-732` -
  Operational apparatus observability and run-level augmentation/evidence
  conformance

It is design coverage. It defines the invariant set and source-to-contract-to-
test matrix that the spawned implementation issues must realize in SDL models,
semantic helpers, contract fields, fixtures, validators, and tests.

## FM Classification

Classification: FM2, Semantic Graph / Constraint.

Rationale:

- The design defines cross-artifact relationships between SDL authoring,
  participant-runtime visibility, experiment-core capture/evidence contracts,
  processor/backend apparatus telemetry, and derived analysis outputs.
- The key obligations are type separation, reference ownership, visibility
  projection, provenance links, loss/redaction disclosure, and comparability
  claims across artifacts.
- This artifact does not define a live state machine or runtime protocol.

## Plane Definitions

### Scenario-Native Observability

In-world observability systems authored as part of the scenario. They are
targetable only when represented by an SDL section, runtime family, or typed
relationship endpoint. Examples include network sensors, detection engines,
security monitoring managers, forwarding agents, telemetry collectors, tracing
services, dashboards, or metrics stores when the scenario makes them part of
the environment.

### Authored Evidence Requirement

An authoring obligation that names the data, evidence, output, source, scope,
window, channel, or boundary that must be captured. It may compile to or bind
with `experiment-capture-spec-v1`, but it is not captured evidence and is not a
participant objective.

### Processor/Backend Operational Observability

Apparatus data used to operate, audit, or diagnose processors and backends:
logs, traces, diagnostics, audit records, health checks, setup evidence,
measurement-channel facts, and capability declarations. These facts are not
scenario meaning unless explicitly projected into an SDL or runtime contract.

### Captured Evidence

Concrete evidence artifacts or `experiment-evidence-record-v1` records. They
cite the capture specification or authored requirement they satisfy and carry
source, capture time/window, raw content reference or bounded summary,
sensitivity, redaction state, provenance, and integrity metadata.

### Derived Analysis

Interpreted outputs over evidence: derived measures, result summaries, outcome
interpretations, studies, reports, exports, and claims. They must cite source
evidence and must not stand in for raw evidence.

## Augmentation Classification

An augmentation is processor/backend-added apparatus behavior or
instrumentation used to satisfy evidence, evaluation, operational, or
comparability needs. The classification set is additive:

| Classification | Meaning | Required carrier |
| --- | --- | --- |
| `apparatus_only` | Visible only to processor/backend/operator/control apparatus. | Diagnostic, manifest, apparatus context, audit, setup evidence, or other apparatus carrier. |
| `environment_visible` | Changes or adds realized environment behavior. | Runtime/evidence/provenance carrier plus realized-form or equivalent disclosure. |
| `participant_visible` | Can affect participant-visible information. | Participant visibility projection, observation envelope, marking, and redaction carrier. |
| `comparability_relevant` | Can affect run/backend/participant/condition comparison. | Run provenance, validity note, realized-form disclosure, or derived-analysis support record. |

## Invariants

| ID | Invariant | Enforcement target |
| --- | --- | --- |
| OE-01 | Every claim-bearing observability/evidence artifact has exactly one primary plane, even when it references artifacts in other planes. | Plane classifier over SDL, runtime, experiment, and apparatus carriers. |
| OE-02 | Scenario-native observability is targetable only through SDL authoring surfaces, runtime-family refs, or typed relationship endpoints. | SDL semantic validation and reference-resolution catalog. |
| OE-03 | Authored evidence requirements name source, scope, window or trigger, channel or boundary, sensitivity, integrity, and loss/redaction expectations before they can claim capture intent. | SDL evidence-requirement model and validator. |
| OE-04 | A capture requirement is not proof of capture. Satisfaction requires a captured evidence record or artifact with an explicit satisfaction link. | Experiment-core reference validation and traceability checks. |
| OE-05 | Captured evidence must not contain metric values, scores, evaluation decisions, or derived conclusions as raw evidence meaning. | Contract model validators and invalid fixtures. |
| OE-06 | Derived analysis must cite source evidence and must not reveal hidden adjudication assets without governed marking, redaction, and authorization. | Derived-measure/run/study validators and redaction checks. |
| OE-07 | Backend diagnostics, logs, traces, and audit records are apparatus operational observability until a governed projection maps them into another plane. | Runtime diagnostics and control-plane API gates. |
| OE-08 | Participant-visible observation claims must pass the ADR-022/ADR-054 visibility projection, marking, redaction, and information-guarantee rules. | Participant observation envelope and behavior-history validators. |
| OE-09 | Augmentation that is environment-visible, participant-visible, or comparability-relevant must have a first-class disclosure carrier. | Augmentation disclosure validator and provenance links. |
| OE-10 | Loss, redaction, latency, observer effects, weaker capability guarantees, and unsupported capture concerns are explicit when a claim depends on them. | SDL, experiment-core, and participant-runtime validators. |
| OE-11 | The same string value, such as `log`, `telemetry`, `observation`, or `evidence`, does not decide plane ownership by itself. | Concept/vocabulary binding plus carrier-type classifier. |
| OE-12 | No observability/evidence plane may use `RuntimeSnapshot.metadata`, evaluator detail fields, audit blobs, raw backend DTOs, or free-form tags as its only portable carrier. | Policy, semantic validation, and review gates. |

## Source-To-Contract-To-Test Matrix

| Requirement | Clause | Current design artifact | Future contract/helper | Lifecycle enforcement point | Positive fixture | Negative fixture | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SEM-224 | Distinguish scenario-native observability systems. | ADR-066; this spec; SDL catalog. | Plane classifier plus SDL runtime-family target helper. | SDL semantic validation and compiler address emission. | In-world detection engine referenced by participant action and capture requirement source. | Backend-only log treated as a participant-visible observation. | #334 |
| SEM-224 | Distinguish authored evidence requirements. | ADR-066; this spec; SDL catalog. | Authored evidence-requirement model and capture-spec binding helper. | SDL validation, instantiation revalidation, experiment capture binding. | Requirement names source, scope, window, channel, sensitivity, integrity, and loss disclosure. | Raw capture record treated as authored requirement satisfaction with no requirement ref. | #334, #337 |
| SEM-224 | Distinguish processor/backend operational observability. | ADR-066; this spec. | Apparatus observability classifier over diagnostics, manifests, audit, setup evidence, and measurement channels. | Processor/backend manifest and control-plane diagnostic gates. | Backend health trace cited as setup evidence with sensitivity metadata. | Backend trace projected into scenario meaning by free-form metadata. | #334 |
| SEM-224 | Distinguish captured evidence. | ADR-066; this spec; ADR-064. | Evidence satisfaction validator over capture spec, evidence record, artifact refs, and provenance. | Experiment-core contract validation and run traceability. | Evidence record cites capture spec, requirement, source, window, raw content, redaction state, and checksum. | Evidence record carries a derived score as raw evidence meaning. | #334 |
| SEM-224 | Distinguish derived analysis outputs. | ADR-066; this spec; ADR-065. | Derived-analysis source-evidence validator. | Derived-measure, run, study, and report validation. | Derived measure cites source evidence and method. | Hidden adjudication asset leaks through analysis output without marking/redaction. | #334 |
| SEM-225 | Define augmentation used to satisfy evidence, evaluation, or operational requirements. | ADR-066; this spec. | Augmentation disclosure model with concern, carrier, classification, evidence refs, and markings. | Compiler/runtime provenance and experiment run validation. | Apparatus-only packet capture sidecar disclosed as measurement-channel augmentation. | Instrumentation modifies environment but appears only in backend logs. | #335 |
| SEM-225 | Include environment-visible augmentation. | ADR-066; this spec. | Environment-visible augmentation validator. | Runtime/provenance validation. | Added sensor service has realized-form disclosure and scenario/runtime refs. | Environment behavior changes without disclosure. | #335 |
| SEM-225 | Include participant-visible augmentation. | ADR-066; this spec; ADR-054. | Participant-visible augmentation validator. | Participant observation envelope and visibility projection. | Participant sees monitoring dashboard through explicit projection. | Hidden adjudication asset reaches visible observation history. | #335 |
| SEM-225 | Include comparability-relevant augmentation. | ADR-066; this spec; ADR-065. | Comparability disclosure support record. | Run/study validity and derived-analysis validation. | Augmentation names comparison impact and supporting evidence refs. | Observer effect omitted from a benchmark comparison claim. | #335 |
| DSL-123 | Support scenario-native observability, telemetry, logging, tracing, and monitoring as first-class scenario elements. | ADR-066; SDL catalog. | Runtime-family or section model for product-neutral in-world service identity. | SDL parser, schema, semantic validator, and reference resolver. | Telemetry collector has stable id and typed refs. | Generic top-level `observability` bag accepts unrelated vendor payloads. | #336 |
| DSL-123 | Allow those elements to be depended on, interacted with, or targeted. | ADR-066; SDL catalog. | Typed relationship/reference edges and target helper. | SDL references, typed relationship subtypes, and compiler addresses. | Objective/action targets an in-world observability service. | Bare ambiguous ref resolves by first match. | #336 |
| DSL-124 | Support authored requirements for data/evidence/output capture. | ADR-066; SDL catalog. | Evidence-requirement model and capture-spec binding. | SDL parser, schema, semantic validator, instantiation, compiler. | Requirement names source, scope, window, channel, role, sensitivity, and loss disclosure. | Capture requirement has no source or window. | #337 |
| DSL-124 | Requirements come from declared sources, scopes, windows, or comparable boundaries. | ADR-066; SDL catalog. | Qualified source/scope/window resolver. | SDL semantic validation and experiment binding. | Requirement references runtime sensor and run window. | Requirement references an unknown hidden backend object. | #337 |
| DSL-124 | Requirements are independent of participant objectives. | ADR-066; SDL catalog. | Cross-plane validation between objectives and evidence requirements. | SDL semantic validation and compiler. | Evidence requirement exists without an objective. | Objective success criterion is treated as capture requirement by implication. | #337 |
| DSL-124 | Requirements are distinct from scenario-native observability systems. | ADR-066; SDL catalog. | Plane classifier and source binding helper. | SDL semantic validation. | Requirement cites an observability system as source but remains a separate obligation. | Observability system declaration is treated as proof of capture. | #337 |
| RUN-316 / API-419 / ASR-525 / EXP-731 / EXP-732 | Backend observation capability declarations and run records must make operational augmentation support and realized evidence provenance portable. | ADR-066; this spec; experiment-core run contracts. | Backend manifest authority plus experiment-run conformance diagnostics. | Backend profile fixture conformance and run archive validation. | Run augmentation names portable carrier refs, affected refs, and traced evidence refs. | Run augmentation is traced but omits affected refs. | #128 |

## Negative Probe Set

The minimum adversarial fixture set for implementation is:

- backend logs treated as participant observations;
- raw capture treated as evidence-requirement satisfaction;
- hidden adjudication assets leaking through analysis;
- augmentation changing environment-visible behavior without disclosure;
- participant-visible augmentation without a visibility projection;
- comparability-relevant observer effects omitted from evidence claims;
- loss, redaction, or latency omitted from evidence claims;
- a generic observability bag accepting vendor payloads without typed refs;
- ambiguous evidence source refs accepted by first match; and
- derived measures accepted with no source evidence.

## Non-Goals

- This design does not add SDL syntax, schemas, fixtures, runtime services,
  APIs, storage, capture scheduling, telemetry collection, packet parsing,
  analysis engines, or backend adapters.
- This design does not replace ADR-022, ADR-054, ADR-064, ADR-065, SEM-218, or
  existing control-plane security and diagnostics.
- The design criteria above do not by themselves transition SEM-224, SEM-225,
  DSL-123, or DSL-124 to implementation coverage. The implementation coverage
  sections below record realized subsets as spawned issues land.

## Implementation Coverage (#334 / SEM-224)

SEM-224 is realized as a carrier-oriented plane classifier plus portable plane
traceability over the existing carriers. The classifier
`raes.observability_plane_semantics` is the single source of plane
ownership; it assigns exactly one primary plane by contract role or runtime
family identity and never by a free string (OE-01, OE-11). The three
claim-bearing experiment-core carriers publish their plane as an `x-raes-plane`
annotation sourced from that classifier. The plane *separation* each carrier
enforces was already realized by the EXP-707/708/709 contracts and SEM-216; this
issue adds the unifying classifier, the portable annotation, and the SEM-224
probe set.

| Invariant / matrix row | Realizing artifact | Test | New in #334? |
| --- | --- | --- | --- |
| OE-01 single primary plane | `observability_plane_semantics.classify_contract_plane`, `assert_single_primary_plane` | `test_each_claim_bearing_contract_maps_to_exactly_one_plane`, `test_assert_single_primary_plane_rejects_zero_or_multiple` | yes |
| OE-11 carrier, not string, decides plane | `classify_contract_plane` (fail-closed), `token_decides_plane`, `AMBIGUOUS_PLANE_TOKENS` | `test_classify_contract_plane_fails_closed_on_unknown_carrier`, `test_token_never_decides_plane` | yes |
| Distinguish scenario-native observability | `SCENARIO_NATIVE_OBSERVABILITY_FAMILIES` over `RUNTIME_SERVICE_FAMILIES`; SEM-216 B5 boundary | `test_scenario_native_observability_families_are_registered_and_distinct`, `test_backend_observability_is_not_a_participant_observation` | classifier new; B5 reused |
| OE-04 capture requirement is not proof of capture | required `capture_requirement_ref` on `ExperimentEvidenceRecordModel` | `test_capture_record_without_requirement_ref_is_rejected` (fixture `sem224-capture-record-without-requirement-ref.json`) | probe new |
| Distinguish processor/backend operational | `PLANE_BY_CONTRACT_ID` (manifests, apparatus context) | `test_operational_carriers_map_to_processor_backend_plane` | yes |
| OE-05 captured evidence is not derived analysis | `ExperimentEvidenceRecordModel` shape; SEM-216 B3 | `test_derived_analysis_is_not_captured_evidence` | classifier new; B3 reused |
| OE-06 derived analysis must cite source evidence | `ExperimentDerivedMeasureModel.source_evidence_refs` (`min_length=1`) | `test_derived_measure_without_source_evidence_is_rejected`, `test_reference_derived_measure_cites_source_evidence` | pre-existing rule, SEM-224 probe |
| Plane traceability published portably | `x-raes-plane` on the three experiment-core schemas | `test_claim_bearing_contracts_publish_their_plane_annotation` | yes |

## Implementation Coverage (#335 / SEM-225)

SEM-225 is realized as run-level augmentation disclosure on
`experiment-run-v1`. `ExperimentAugmentationDisclosureModel` records the
augmentation purpose, realization layer, additive classifications, processor or
backend authority, first-class carrier refs, disclosure policy, markings,
observer/comparability effects, and evidence-record refs. The run validator
keeps augmentation evidence refs tied to `traceability.evidence_record_refs` so
augmentation claims do not float free of captured evidence.

The model keeps the three SEM-225 axes separate:

- `environment_visible` requires an explicit environment effect and a portable
  carrier ref rather than a backend-log-only reference;
- `participant_visible` requires participant visibility text plus markings; and
- `comparability_relevant` requires both comparability impact and observer
  effect disclosure.

| Invariant / matrix row | Realizing artifact | Test | New in #335? |
| --- | --- | --- | --- |
| OE-09 first-class augmentation disclosure | `ExperimentAugmentationDisclosureModel`, `ExperimentRunModel.augmentation_disclosures` | `test_sem_225_accepts_run_augmentation_disclosure`, `test_experiment_run_schema_publishes_sem_225_augmentation_surface` | yes |
| Environment-visible augmentation is not backend-log-only | portable carrier validation in `ExperimentAugmentationDisclosureModel` | `test_sem_225_rejects_environment_visible_backend_log_only_disclosure` | yes |
| Participant-visible augmentation carries visibility/marking context | participant visibility and marking validation | `test_sem_225_rejects_participant_visible_augmentation_without_markings` | yes |
| Comparability-relevant augmentation names observer effect | comparability and observer-effect validation | `test_sem_225_rejects_comparability_relevant_augmentation_without_observer_effect` | yes |
| Processor/backend authority boundary | `augmented_by_ref` constrained to processor/backend refs | `test_sem_225_rejects_non_processor_backend_augmentation_authority` | yes |
| Evidence provenance remains traced | run-level augmentation evidence refs checked against traceability | `test_sem_225_augmentation_evidence_refs_must_be_run_traced` | yes |

## Implementation Coverage (#336 / DSL-123)

DSL-123 is realized as SDL scenario-native observability over existing runtime
families and targetable reference edges. It does not add a generic top-level
`observability`, `telemetry`, `logs`, or `traces` bag. The implementation keeps
the carrier-oriented plane classifier from SEM-224, exposes an explicit
scenario-native observability reference collector, and proves that qualified
runtime-family refs can be relationship endpoints, objective targets, and
participant action interaction targets.

| Invariant / matrix row | Realizing artifact | Test | New in #336? |
| --- | --- | --- | --- |
| Scenario-native observability systems are first-class SDL elements | `SCENARIO_NATIVE_OBSERVABILITY_FAMILIES` validated against `RUNTIME_SERVICE_FAMILIES`; `classify_runtime_family()` | `test_dsl_123_exposes_scenario_native_observability_refs_without_second_resolver` | helper/test coverage new; classifier reused |
| Observability target refs are explicit runtime-family refs | `collect_scenario_native_observability_refs()` as a filtered view over `collect_qualified_runtime_family_refs()` | `test_dsl_123_exposes_scenario_native_observability_refs_without_second_resolver` | yes |
| In-world observability systems can be depended on or targeted | `SemanticValidator._named_ref_index(targetable=True)` and relationship endpoint validation | `test_dsl_123_observability_refs_are_targetable_relationship_objective_and_action_refs` | test coverage new; resolver reused |
| Participant actions can interact with in-world observability systems | `ParticipantInteractionDeclaration.target` and `shared_state_refs` validation through the targetable index | `test_dsl_123_observability_refs_are_targetable_relationship_objective_and_action_refs` | test coverage new |
| Bare runtime ids do not resolve by first match | Fail-closed targetable reference resolution requires the qualified runtime-family path | `test_dsl_123_observability_refs_do_not_resolve_by_bare_runtime_id` | test coverage new |

## Implementation Coverage (#337 / DSL-124)

DSL-124 is realized as the SDL `evidence_requirements` section. It records
authored capture intent and remains separate from participant objectives,
scenario-native observability systems, raw evidence records, and derived
analysis. Concrete source, scope, channel, trigger, and boundary refs reuse the
existing fail-closed targetable reference resolver; class-level requirements use
closed source/channel/redaction/integrity/retention/loss-disclosure
vocabularies instead of free-form observability bags.

| Invariant / matrix row | Realizing artifact | Test | New in #337? |
| --- | --- | --- | --- |
| Authored evidence requirements are first-class SDL authoring surfaces | `Scenario.evidence_requirements`, `EvidenceRequirement` | `test_dsl_124_accepts_authored_evidence_requirement_independent_of_objectives` | yes |
| Requirement records source/scope/window or comparable boundary plus channel and handling expectations | `EvidenceRequirement._validate_capture_intent` and required sensitivity/redaction/integrity/retention/loss fields | `test_dsl_124_rejects_capture_requirement_without_window_trigger_or_boundary` | yes |
| Scenario-native observability can be a source without satisfying capture | `collect_scenario_native_observability_refs()` plus `EvidenceRequirement.source_refs` | `test_dsl_124_accepts_authored_evidence_requirement_independent_of_objectives` | yes |
| Source refs fail closed and bare runtime ids do not first-match | `SemanticValidator._verify_evidence_requirements` over `_validate_named_ref(targetable=True)` | `test_dsl_124_source_refs_fail_closed` | yes |
| Evidence requirements are independent of participant objectives | `evidence_requirements.` is excluded from targetable refs | `test_dsl_124_evidence_requirements_are_not_objective_targets` | yes |
| SDL section plane ownership is carrier-based | `PLANE_BY_SDL_SECTION`, `classify_sdl_section_plane()` | `test_dsl_124_accepts_authored_evidence_requirement_independent_of_objectives` | yes |

## Implementation Coverage (#128 / RUN-316, API-419, ASR-525, EXP-731, EXP-732)

Issue #128 connects the already-realized observability/evidence carriers to the
backend conformance runner. `experiment-run-v1` is now part of the governed
backend observation evidence surface, so backend profiles can require it and
manifest observation capability checks can detect a missing archival run
carrier.

The conformance runner registers `experiment-run-v1` and applies
`observability_evidence_conformance_diagnostics()` after schema validation. The
diagnostics keep the declaration/reporting split explicit: manifests declare
support for the run/evidence carriers, while concrete runs disclose actual
augmentation and realized-form behavior.

| Invariant / matrix row | Realizing artifact | Test | New in #128? |
| --- | --- | --- | --- |
| RUN-316 operational apparatus observability has a portable run carrier | `BACKEND_SUPPORTED_CONTRACT_IDS`, `OBSERVATION_CAPABILITY_REQUIRED_CONTRACTS`, reference/stub observation manifests | `test_backend_manifest_v2_declares_observation_capability_dimensions`, `test_fixture_suite_exercises_experiment_run_observability_semantics` | yes |
| API-419 augmentation reports name affected carriers | `_augmentation_conformance_diagnostics()` requires `affected_refs` and portable `carrier_refs` | `test_observability_evidence_conformance_requires_affected_refs`; fixture `augmentation-without-affected-refs.json` | yes |
| ASR-525 conformance validates experiment-run semantics | `_MODEL_VALIDATORS["experiment-run-v1"]`, `_semantic_diagnostics()` | `test_fixture_suite_exercises_experiment_run_observability_semantics` | yes |
| EXP-731 run-scoped capture refinements preserve authored requirements | `_run_refinement_conformance_diagnostics()` requires `authored_ref` for capture-window and measurement-channel disclosures | `test_observability_evidence_conformance_requires_authored_ref_for_run_refinement` | yes |
| EXP-732 augmentation and refinements remain evidence-traced | experiment run model traced evidence refs plus conformance evidence-ref checks | `test_observability_evidence_conformance_accepts_traced_augmentation`, `test_observability_evidence_conformance_requires_authored_ref_for_run_refinement` | yes |

## Implementation Coverage (#1112 / Required-Capture Admission)

Issue #1112 makes OE-03, OE-04, and OE-10 operational. Explicit SDL and
experiment capture requirements compile to one normalized demand form. A pure
conjunctive matcher admits a demand only against one coherent backend offer;
legacy discovery lists cannot be cross-producted into support. Ordinary
planning, admitted-trial compilation, trial realization, runtime apply, and all
control-plane plan domains fail before effects when required capture is not
admitted. Trial compilation performs this check after selecting each concrete
scenario, so variable-backed capture terms are matched by their realized value.

Post-run validation follows the exact chain from task evidence reference to
capture requirement, evidence record, emitted artifact, supplied bytes, and
required JSON fields. Reference-only satisfaction assertions remain descriptive
metadata and cannot prove capture.

| Invariant | Realizing artifact | Test |
| --- | --- | --- |
| Coherent, versioned capture offer with exact authored scope targets | `ObservationCaptureOfferModel`, `ObservationCaptureOffer` | `test_manifest_capture_offers_are_closed_and_round_trip`, `test_sdl_scope_refs_require_exact_offer_scope_targets` |
| Every explicit demand is checked conjunctively | `CaptureDemand`, `capture_admission_diagnostics()` | `test_planner_rejects_every_unmet_capture_dimension_before_execution` |
| Trial inputs pin exact capture-spec bytes | `AdmittedTrialPlanInputRefsModel.capture_spec_refs`, `TrialCompilationRequest.capture_specs` | `test_capture_specs_are_required_digest_bound_trial_inputs` |
| All runtime plan domains retain the authorization boundary | `RuntimeControlPlane.register_planner_produced_plan()` and HTTP submission gates | `test_control_plane_rejects_unregistered_effectful_plans` |
| Emitted content, not an adapter assertion, proves satisfaction | `validate_experiment_run_evidence()` | `test_post_run_validation_requires_emitted_bytes_and_promised_fields`, `test_static_artifact_id_cannot_stand_in_for_the_validated_capture_artifact` |
| Output-contract schema and owning semantic model, capture-window time, and exact redaction policy are bound to emitted evidence | `validate_experiment_run_evidence()` | `test_output_contract_shape_and_registry_are_enforced_before_selectors`, `test_output_contract_semantic_invariants_are_enforced`, `test_post_run_validation_rejects_evidence_outside_the_capture_window`, `test_redaction_policy_and_artifact_sensitivity_are_bound_to_the_capture` |
| Authoritative run/study/conformance validation requires content-backed evidence inputs | `validate_experiment_run_against_task()`, `validate_experiment_study_against_tasks_and_runs()` | `test_authoritative_task_run_validation_requires_and_consumes_content_inputs` |
| Evidence-based study conditions consume only content-proven bindings | `validate_study_run_task_membership()`, `_run_satisfies_condition_assignment()` | `test_study_evidence_conditions_consume_only_validated_bindings` |
| Trial capture demand is evaluated after concrete family selection | `trial_compiler._validate_selected_scenario()`, `compile_scenario_capture_demands()` | `test_capture_admission_uses_each_selected_scenario_value` |
