# Issue #304 — Participant tool and affordance support preflight

Date: 2026-10-27. Requirement: API-414. Inspection baseline: `4aa67d06`.

This note supplies architecture guardrails, not an implementation plan or
evidence of delivered support. ADR-041/060/083/095, the API-407
[#1072 preflight](issue-1072-api-407-feature-support-preflight.md), and
[ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md) already settle
ownership. No new ADR, authored profile family, or native adapter is needed.

## Authority and feature mapping

The [#301 decision](issue-301-participant-tool-profiles.md) and its normative
ACT-619 TP-1–TP-9/K1–K5 rules define the authored profile:
`ParticipantBehaviorSpecification`, its `tool_affordances`, selectors,
`semantic_version`, and lifecycle. Its canonical specification/binding addresses
identify authored instances. The [#298 decision](issue-298-tool-authoring.md)
owns import/reference behavior. API-414 declares what the selected processor
can process and backend can realize; it does not redefine either authority.

Package paths below are relative to `implementations/python/packages/`.

| #301 feature or obligation | Processor declaration and boundary | Backend declaration and boundary |
| --- | --- | --- |
| Profile identity, version, lifecycle and reuse through ADR-053 imports | `ProcessorManifestV2Model.capabilities.supported_sdl_versions` identifies the authoring contract; `ProcessorFeature.COMPILATION` is only a broad processing claim. Declare support for the actual profile semantics without enumerating user-authored specification names or treating their version labels as wire-contract versions. | `BackendManifestV2Model.capabilities.participant_runtime.feature_support` is the existing realization-strength surface. A backend consumes resolved semantics; it need not parse imports or claim to own authored profile lifecycle. |
| Stable tool/binding identity, optional `tool_ref`, action/observation subsets, duplicate-relation rejection | Reuse `raes` reference/composition/semantic checks and `raes_processor/compiler/participant_behaviors.py`; preserve canonical relations and owning specification in IR. Declare preservation/processing support, not tool installation. | Reuse the same feature-support entry with the actual required backend-facing contracts. Action execution bindings apply where their existing protocol owns execution, not as a new universal tool registry. A shell/browser expectation or content-installation capability proves no affordance support. |
| Absolute participant/role selectors, narrowing to the parent, empty scoped selection, TP-9 equivalence and K1–K5 conflicts | Declare the selector semantics actually supported. Keep `select_participants`, subset validation, raw-selector scopedness and explicit specification selection. Never silently intersect an overbroad selector or merge overlapping profiles. | Declare ability to honor the selected participant/specification scope and disclose exclusions. A role-specific offered surface grants no action permission. Support cannot compensate for invalid authored relations. |
| Role-specific surfaces, visibility, argument contracts and scoped-binding version behavior | Preserve #301's v1 refusal for every syntactically scoped binding, including whole-parent selectors; use v2's participant filter before disposition checks. A generic runtime-control-plane flag does not establish this behavior. | State the exact surface/protocol versions the backend actually consumes or realizes. Keep participant implementation selection and delivery separate; do not require every backend to own participant-facing projection. Contract ownership must justify any new supported-contract id. |
| Constraints, limitations, supported/partial/unsupported behavior | Root `constraints` is descriptive text, not a machine-checkable strength/version declaration. Add only the smallest typed declaration within the existing processor capability surface where its current fields cannot express an independently testable claim. | Reuse API-407's `exact`, `bounded`, `disclosed_weak`, `unsupported`, plus distinct constraint, limitation, disclosure and evidence refs. Do not introduce a second full/partial/unsupported enum or hide enforceable limits in `constraints`. |
| Selected profile evidence, live admission and observed execution | Keep the instantiated SDL snapshot, canonical specification/binding addresses and digest-bound apparatus selection. Processing success establishes neither delivery nor invocation. | Keep selected manifest/configuration identity, declared support, effective admitted support, delivery and execution evidence distinct. Extend the existing conformance report; general reporting remains #222's responsibility. |

Current gaps are material: `ProcessorCapabilitiesV2Model` has only SDL versions
and broad processing flags. API-407's governed behavior/interaction vocabulary
has no tool-profile terms, and `ParticipantFeatureSupportModel` has no dedicated
version coordinate. Existing fields must be reused before adding any field;
where versions/bounds cannot be expressed, use a closed, owning capability
coordinate referencing existing contracts/context. Do not encode tuples in
feature names, overload `supported_contract_versions` with authored profile
names, or invent a second profile registry. Authored `semantic_version` is an
unchecked label today; exact scenario bytes/digests supply identity, not an
assumed semantic-version range or automatic compatibility promise.

## Declaration and admission guardrails

Use `raes_contracts/manifest_authority.py` for authorized contract ids,
term-to-required-contract mappings and evidence-required features. Govern any
new terms through `contracts/concept-authority/controlled-vocabularies-v1.json`
and its existing scopes/concept bindings. The participant implementation's
`tool_affordance_expectations` is a consumer expectation, not processor/backend
support. A contract's existence or a method signature is also insufficient.

Keep the wire models in `raes_contracts/contracts/manifests.py`,
`participant_manifests.py` and `feature_support.py`, the incumbent internal
declarations in `raes_processor/capabilities.py` and
`raes_backend_protocols/participant_capabilities.py`, processor emission in
`raes_processor/manifest.py`, and both backend adapters in
`raes_backend_protocols/manifest.py` consistent. Existing model/dataclass
validation overlaps; preserve parity without adding consumer-local rule tables
or broadening this work into a validation rewrite. JSON Schema handles wire
shape; contextual joins retain their owning validators.
The reference processor currently advertises every `ProcessorFeature` enum
member. Adding a member must not automatically assert unimplemented support;
emit only honest claims and retain them through public manifest projections.

Derive required features, versions and bounds from the composed, instantiated,
selected scenario and its actual bindings. Do not depend solely on authors
remembering `backend_feature_support_refs`, nor require unused optional
features. Compare against each selected processor/backend independently before
accepting an executable scenario; a union of claims across components is not
joint support. Retain the existing `planner/core.py` diagnostic path,
`capability_admission.py`/`participant_feature_admission.py`, and
`trial_compiler/apparatus.py`/`realization_admission.py` selected-apparatus joins.
Public direct Python, CLI, MCP and trial paths must reach the same owning
comparison; a CLI-only check or report-only warning leaves an admission bypass.
`raes_mcp/tools/operations.py::sdl_plan` calls `plan()` directly rather than
`ReferenceProcessor.realize()`, so a guard only in the latter is insufficient.
Keep MCP's stub-manifest dry-run claim boundary; it grants no live authority.

`resolve_participant_feature_support()` may return `None` for a listed legacy
feature outside `PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES`. That is not an
explicit strength result. New tool claims need explicit declarations, governed
required-contract mappings and evidence obligations; an unknown extension with
an empty mapping cannot pass vacuously. Preserve unrelated legacy behavior.
Do not add declaration-only tool terms to `PARTICIPANT_RUNTIME_POLICY_FEATURES`:
that set also drives runtime policy behavior. The backend wire validator's
`_validate_participant_policy_contracts()` currently indexes the behavior map;
placing evidence-required terms in another scope requires deliberate reuse of
a scope-aware lookup, not a second map or an accidental `KeyError`.

Positive presence lists and strength entries must agree. Reject missing,
unknown, contradictory, unsupported, insufficient-version and exceeded-bound
claims. Below-exact support needs disclosures/limitations; bounded support
needs applicable bounds, and positive claims need the owning evidence/contracts.
A limitation ref is not itself an evaluated bound. Static shape checks cannot
prove truth: trusted contextual resolution and conformance establish the
relevant relationships. The existing downgrade parameters check reference
presence, not authority. Any accepted weakening needs scoped authorization,
policy/provenance, satisfied bounds and an explicitly weaker effective claim;
unsupported is never a permitted downgrade. Otherwise reject admission.

## Cross-cutting layers the design must pass

| Layer and canonical incumbent | Required satisfaction |
| --- | --- |
| Bytes and SDL phases | Keep `raes/parser.py`, `_yaml_loader.py`, `_source_profile.py`, `SDLModel`, reference indexes, composition rewriters, `instantiate_scenario()` and `admit_instantiated_scenario()`. Revalidate after substitution; preserve private-ref, ambiguity and portable-address rules. Support cannot repair malformed SDL. For any changed/new JSON ingress, reuse `raes_contracts/json_ingress.py::parse_bounded_json_object` with bounded reads, byte/depth limits, duplicate-member rejection and finite numbers. The CLI's current stat/read/`json.loads` sequence is not a race-free read bound or duplicate-safe precedent. |
| Wire/config shapes | Retain `ContractModel(extra="forbid")`, controlled vocabularies, owning validators and `schema_bundle()`. Check duplicate/blank refs, contradictory claims, numeric bounds and JSON-Schema/model/dataclass parity. `NonEmptyString` alone permits whitespace, closed models can coerce values, and frozen models do not guarantee deeply immutable collections. Do not trust a digest while retaining caller-mutable claim data. |
| Apparatus and installed target | Reuse `ExperimentManifestReferenceModel`, `validate_selected_apparatus()`, `validate_admitted_apparatus()` and canonical digests in `trial_compiler/apparatus.py`. Join exact subject/schema/version/digest and configuration; prevent replacement after admission. Retain `BackendRegistry`, `RuntimeTarget`, `registry_target_validation` presence/signature checks and `ControlPlaneConfiguration`. Resolve full realization envelopes through `backend_manifest_from_v2_model_with_envelope()` when required; envelope identity alone is insufficient. |
| Authentication and authorization | Add no route. Any existing served consumer retains `create_control_plane_app()`, `ControlPlaneSecurityConfig.strict_defaults()`, API `_auth`, sealed route authority, actor/run/target scope, request-size guards and no-store responses. Scenario roles are not HTTP roles. Support grants no controller, participant, crossing, release or final-sink authority. |
| Secrets, configuration and environment | Reuse `ConfigurationTargetRegistryModel`, `ConfigurationTargetDeclarationModel.validate_value`, `realize_participant_configuration()` and `validate_participant_configuration_selection()`. Secret targets admit only `SecretReferenceBindingValueModel`/`SecretReferenceId`; normalization must preserve reference identity, kind and target set. No secret lookup, new environment/options bag or config override belongs in a capability. Existing environment consumers keep `RuntimeEnvironmentVariable` name/source/exclusivity checks and `enforce_observed_value_redaction`; credentials and prompts never enter manifests, limits or evidence refs. |
| Live action and disclosure | Keep `participant_binding_v2.py`, delivery validation and `participant_decision_surface_control_v2.py` anchor/digest/argument checks, including revalidation within `control_plane_mutation`. Keep action applicability, time, resource, information-flow and final-sink gates independent. An admitted scenario is not permanent invocation authority; backend support cannot expose hidden actions, evaluator truth, rejection reasons or another participant's capability scope. |
| Host/OS | Declarations are inert data. No executable lookup, imports, tool installation, URL fetch, listener, process or daemon probing follows from a feature/ref. Backend owners retain native launch, credentials, environment injection and cleanup. Never put tokens or payloads into argv, shell interpolation, filenames, environment dumps or subprocess output. Dry conformance and manifest inspection require no host access or credentials. |
| Errors and observability | Reuse `SDLParseError`, `SDLValidationError`, `SDLInstantiationError`, existing `CompilationFailure`, `Diagnostic`/`Severity`, planner gaps and operation receipts. Use `portable_diagnostic_payload()`/`DiagnosticModel`: JSON-Pointer addresses and 512-character messages. It converts addresses, not oversized or sensitive messages. Bound lists and sanitize rejected terms/keys before transport; do not echo Pydantic inputs or raw resolver/provider exceptions. Keep API `_responses._conflict_detail` and `_operation_routes` coarse redacted envelopes, existing rejection auditing, and conformance's `sanitized_failure_message()` within its package. ADR-066's telemetry, observations, evidence and analysis planes remain distinct. |
| Persistence and workflow | Keep `RuntimeSnapshot`, `ControlPlaneStore`/atomic expected-head commits, immutable operation receipts, `AuditEvent`, behavior history and trial provenance. Preserve CAS, idempotency, append-only evidence and actor/run/target binding. No new store, support cache as authority, logger, audit stream, retry loop or workflow engine. Reports contain safe refs/digests and scoped claims, not raw configuration, provider output or hidden state. |

## Extensibility, conformance and compatibility

The extension seam belongs in the existing capability comparison: required
feature, exact semantic surface/contract revision, required support level,
applicable constraints and selected apparatus/configuration context. Keep
authored instance identity separate from supported semantics. A future profile
revision, additional selection restriction or backend should supply governed
coordinates and context through that seam; it must not require editing authored
profiles to name a backend, copying constraints, choosing a provider by name,
fetching a latest profile or installing a new resolver/workflow stack. Reuse
existing downgrade policy/provenance parameters where applicable.

Conformance stays in `raes_conformance.conformance`: `run_fixture_suite()`,
`run_target_conformance()`, `ConformanceCaseResult`, `BackendConformanceReport`,
`BehavioralClaimBindingModel` and `validate_backend_conformance_report()`.
`target.py::_participant_feature_cases()` currently filters policy features;
new tool terms will not automatically appear in reports. Extend the owning
report/probe selection without classifying tools as policy enforcement.
Declared/effective support fields on a static case are not observed execution.
Keep execution basis, outcome, finite scope, limitations, nonclaims and exact
manifest/profile/configuration/probe digests. Reference-valued evidence needs
the existing trusted joins, not merely a nonempty string. Fixture or stub
success cannot claim native realization; external backends attach through the
injected `RuntimeTarget`/conformance harness, per ADR-115.

The existing `test_processor_manifest.py`, `test_backend_manifest.py`,
`test_backend_manifest_v2_adapter.py`, `test_runtime_conformance.py`,
`test_issue_1004_apparatus_backend_capabilities.py`, #301 profile/conflict tests
and `tool_profile_support.py` supply declaration, parity and real v2 admission
patterns. Meaningful coverage must distinguish a supported profile, an honest
limitation both inside and outside its bound, unsupported/missing support, a
contradictory declaration, and a structurally valid false claim contradicted by
a probe. Include imported/role-scoped bindings, version mismatch, overlapping
specifications, legacy omission and a rejection with no dispatch/state change;
validate the portable error envelope as well as the internal diagnostic.

Published schemas under `contracts/schemas/` are authority (ADR-009).
Follow ADR-061/075 and `contracts/schema-publication/README.md`: the root
publication manifest is now an index, with hashes/`last_change` in each owning
`entries/` record and tombstones for removals. Current processor/backend v2
entries are draft, not stable promises. Publish omission/default/version and
migration behavior: an old manifest must not gain new tool support by default,
and tool-free legacy scenarios should retain existing acceptance. Optional new
fields do not make new producers readable by old closed readers. Stable
breaking changes require a new contract version; draft same-suffix changes
still need recorded hashes, compatibility guidance and matching generator,
fixtures and installed corpus. Reuse `check_generated_schemas.py`,
`check_schema_publication.py`, `check_json_artifacts.py`, schema-invariant and
catalog checks, and existing package boundaries in `tools/policy/adr_policy.yaml`.
Retain installed corpus access through `raes_contracts.corpus`, with existing
`implementations/python/pyproject.toml`/`hatch_build.py` packaging; published
declarations and conformance must work without a source checkout or backend
auto-discovery.

Workflow remains `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/nox_support/` and existing hooks. Set `RAES_REQUIREMENT_UID=API-414`
where the branch does not carry the UID. Run relevant explicit local cases or
`verify-fast-feedback`; full test/integration/fuzz/completion and policy suites
belong to CI. This note changes no schema or claim, and creates no IMPLEMENTS
or TESTS evidence for API-414.

## Non-goals and anti-patterns

No new authored `tools`/`tool_profiles` section, permission profile, profile IR
family, tool runner, gateway, sandbox, credential broker, native backend,
participant UI/prompt format, generic report family or implementation plan.
Do not copy action constraints or visibility policies into manifests, make
support imply visibility/admission, equate expectation with provision, weaken
closed readers, or claim execution from declaration/validation alone. #298
retains authored bindings, #301 profile meaning and #222 general reporting.
API-414 owns portable processor/backend declarations and their compatibility
checks; it does not implement the tools they describe.
