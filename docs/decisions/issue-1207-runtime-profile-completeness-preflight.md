# Issue 1207: runtime description and execution-profile boundaries

Architecture preflight for DSL-136, with the issue's DSL-132, DSL-137 and
DSL-134 adjacent-family scope. This is design guidance, not an implementation
plan or a claim that validation has changed. The supplied corrective issue
intent governs the upcoming change; the historical DSL-136 required-profile
wording must not reinstate the specimen requirements it corrects.

## Decision boundaries

Keep `RuntimeForwardingAgent` and its existing typed source, transform, target,
buffer, reload and setting children. Node-hosted and scenario-level agents
continue to share that model and their existing identity/reference rules.
Agent kind describes function; it does not implicitly select a Wazuh or
MISP-to-Suricata execution recipe. Base descriptions accept partial knowledge
and legitimate empty configured state. Complete abstract models need neither
a concrete agent installation nor an observation to be complete.

Selected execution contracts may impose necessary completeness, authority and
verification obligations. Check those against the backend's admitted completion
before mutation. A prerequisite selectable inside an inherited open scope is
the backend's responsibility, not automatically a required author field.
Explicit descendants and collection closure remain binding: a backend cannot
replace an explicitly empty destination set with a destination needed by its
chosen recipe. An unsatisfied or unsupported selected contract fails admission;
it does not retroactively make the description structurally invalid.

Reuse the existing separation among recursive authored constraints, typed
descriptive facts, prepared execution state and admitted runtime results.
`agent_kind`, validation-strength profiles, domain-profile identity, backend
capability and experimental capture policy are different concepts. Do not add
a global strict/partial switch, per-family validity mode, or second profile
registry. Ordinary concrete choices within an open scope need no public profile
binding merely because the backend uses a recipe internally.

## Guard disposition and adjacent-family review

The local [F4 review](../research/language-extensibility/design-review.md#f4-some-type-guards-require-complete-specimen-shaped-configuration)
and [scope inventory](../research/language-extensibility/scope-inventory.md)
record the #959 audit context. Apply its distinction between identity,
capability, configured state, content, policy, authority and evidence to both
positive requirements and prohibitions:

| Current owner / finding | Architectural disposition |
| --- | --- |
| `raes/runtime_forwarding_agent.py::require_profile_for_agent_kind` | Buffer plus ingestion endpoint for every log forwarder, and API pull plus IOC conversion plus reload for every synchronizer, are specimen completeness rules. Also review the bans on IOC transforms, synchronization buffers and enrollment: absence of a feature in the motivating specimen is not a universal incompatibility. Preserve independently justified type, numeric, identity and redaction invariants. |
| `raes/runtime_datastore.py::require_profile_for_data_model` | Persistence, index existence/geometry/mappings and keyspace replication are not universal description prerequisites. Explicit geometry, quantities, manifest references and incompatible asserted structures still need their owned checks. A known nonpersistent key-value service is a valid counterexample, not an unknown persistent one. |
| `raes/runtime_orchestration.py` and `validator/_runtime_orchestration.py` | Missing interface knowledge does not invalidate a host-root-equivalent observation. The semantic gate also hardcodes a read-write Unix path ending in `docker.sock`; fixing only the model leaves the product assumption intact. Preserve concrete same-node reference integrity and actual authority admission. A socket name is not proof of privilege, and unknown privilege is not permission. |
| `raes/runtime_app_authorization.py::_require_grants_for_resource_vocabulary` | A resource vocabulary currently forces a matching grant. A configured empty authorization store is legitimate; do not invent a grant to satisfy it. Retain grant effects, principal/role/resource references, uniqueness and redaction. Recorded application authorization remains distinct from control-plane authorization. |
| `raes/runtime_platform_application.py`, ADR-049 | #956 already separates composable capability from optional configuration/content. Preserve this correction and legacy input compatibility; do not restore a MISP sharing-group requirement or copy capabilities onto every family without matching semantics. |
| `runtime_security_monitoring/_models.py`, `runtime_network_detection.py` | Their aggregate validators already retain local uniqueness without compulsory rosters/rule corpora. Manager rosters and consumer rule sources remain separate from agent producers. Empty collections do not establish exhaustive observation. |
| `runtime_database.py`, `runtime_mounts.py`, `runtime_forwarding_buffer.py` | Reuse grant/reference, mount/control-interface redaction, typed path and nonnegative-count checks. The database engine/protocol pairing is an adjacent product-coupling review point: unknown protocol knowledge and an explicit contradictory protocol need different treatment. Empty top-level inventories do not imply that malformed supplied grants or interfaces should be accepted. |

This is a scoped architectural review of incumbents, not closure of the broader
#959 audit or permission to weaken every runtime validator.

## Cross-cutting owners and gates

Paths in this table are beneath `implementations/python/packages/` unless
otherwise stated. These are obligations for the intended implementation, not
claims that a future execution path has already passed security validation.

| Layer and canonical incumbent | Required treatment |
| --- | --- |
| Parsing and base shape: `raes/_yaml_loader.py`, `_source_validation.py`, `_source_profile.py::SDLParserLimits`, `_base.py::SDLModel`, `runtime_vocabulary.py`, `runtime_values.py` | Keep safe YAML, source diagnostics, import/composition/input budgets, closed model keys, portable IDs, variable parsing, quantities and governed vocabularies. Preserve equivalent bounded JSON/direct-model ingress. Do not use `unknown`, `other`, `${var}` or a private identity to evade admission. Security classification and privilege vocabularies do not become unrestricted strings. |
| References and ownership: `raes/_runtime_service_family_registry.py`, `validator/_runtime_platform.py`, `_relationships.py`, `_runtime_orchestration.py`, `_evidence_requirements.py` | Reuse the registry/declaration index and `SemanticValidator`. Keep cross-registry forwarding ID uniqueness, local child IDs, node/service ownership and inbound apparatus evidence bindings. Scenario-level agents have no implicit owning node. A declared invalid reference remains invalid; a partial report uses descriptive fact/coverage semantics instead of fabricated declarations. |
| Source meaning and compilation: `raes/explicitness.py`, `raes_contracts/realization_structure`, `bounded_domains`, processor `compiler/realization_structure.py`, `realization_requirements.py` | Preserve authored presence, recursive closure, exact siblings, stable collection identities and bounded relation outcomes through instantiation and serialization. Reuse source/`model_fields_set` provenance; normalized empty lists, empty strings and `None` must not fabricate authored or observed facts. Do not apply blanket `exclude_defaults` or nullability changes. |
| Descriptive reports: `raes_contracts/contracts/realization_descriptions.py`, `description_projection.py`, `description_coverage.py`, `description_reporting.py` | Reuse known/not-observed/known-absent/withheld/contradictory/not-applicable facts, coverage universe and provenance. Known empty, omitted and unknown remain distinct. Do not create a nullable mirror of every runtime family or use observation coverage as authored closure. Observed/independently-verified basis keeps its evidence obligations; backend-selected state is not independent evidence. |
| Selected profile/configuration: `raes_contracts/domain_profiles`, `realization_profiles.py`, `contracts/realization_plans.py`; repo-root `specs/sdl/plan-realization-profiles.md` | Reuse exact identity/version/digest, owner/context admission, local bounded no-retrieval schema validation, separate installed semantic support and core/profile conjunction. Bind the backend resolution-context/manifest digest to authenticated preparation authority. Schemas or support rows alone do not execute semantics. No remote `$ref`, executable validators in profile data, ambient lookup or profile-defined resource/privilege grants. |
| Preparation and alternate ingress: processor `planner/realization_preparation.py`, `prepared_node_admission.py`, `prepared_node_semantics.py`, `prepared_node_support.py`, `stateful_admission.py`; runtime `control_plane_submission.py`, `control_plane_plan_authorization.py` | Place necessary selected-completion checks on the shared pre-mutation admission route used by planned and directly submitted operations. Revalidate variables, native semantics, capabilities, generated-artifact entitlement and selected authority. Relaxing a base model also relaxes prepared-node parsing; preserve required execution checks explicitly here. No parser-context bypass or duplicated backend validation engine. |
| Secret and environment shapes: `raes/runtime_values.py::enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_generated_value.py`, `raes_contracts/secret_references.py`, `contracts/experiment_bindings.py` | Explicit redacted/operator-secret settings omit raw values; enrollment remains posture-only with its closed classification. Keep environment-name/exclusivity rules, typed secret-reference bindings, producer-output/consumer entitlement and producer-private exclusions. Generated secret outputs are not operator secrets. Forwarding settings gain no env resolver, credential store or secret interpolation. |
| Return integrity and projections: processor `semantics/realization_concerns.py`, `realization_concern_projections.py::project_forwarding_agents`, `realization_specialized_projection.py::recursive_forwarding`, `realization_concern_observations.py::validate_forwarding_agents_observation`; runtime `backend_snapshot_contracts.py` | Keep one concern descriptor, keyed child comparison, safe setting commitments and sanitization. Readback currently reuses `RuntimeForwardingAgent.model_validate`; accepting partial descriptions must neither reject truthful reports nor accept insufficient delivery as conformance. Preserve #1204's exact admitted-selection result checks before publication/persistence, including unchanged-state and predecessor recovery behavior. Scenario-level inventory is not automatically supported by the node concern descriptor. |
| Verification and capture: processor `semantics/realization_operational_verification.py`, `realization_observation_admission.py`, `capture_admission.py`; runtime `observation_admission.py`, `observation_results.py` | Keep selected operational verification scope/strength and #1112 required-capture gates. Current forwarding presence/configuration inference and daemon-observed floor are explicit compatibility review points, not permission to drop verification or collect everything. Reporting choices, experimental observation, retention and export remain independent under #1212/#1209. Inventory/readback proves neither shipment nor reload behavior. |
| API auth and policy: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_api_guards.py`, `control_plane_plan_authorization.py` | Reuse authenticated identities/roles, target authorization, request limits, idempotency and planner authority. Describing a privileged interface or a classified enrollment identity grants no access to it. No new controller, bypass endpoint or permission inferred from openness. |
| Errors and observability: `raes` SDLError hierarchy, `_model_diagnostics.py`, `raes_contracts/diagnostics.py::Diagnostic`, runtime `control_plane_api/_operation_routes.py`, operation receipts/status and existing audit route | Reuse bounded structured diagnostics and redacted 422/500 envelopes. Distinguish invalid description, conflicting constraints, unsupported semantics and insufficient evidence. New errors must not interpolate settings, selectors, source URLs, credentials, native output or Pydantic input dumps; bounding text alone does not redact it. No parallel exception hierarchy or logger. |
| Persistence and publication: `raes_runtime/control_plane_store.py`, `control_plane_store_local.py`, snapshot/payload/observation codecs; `raes_contracts/contracts/bundle.py::schema_bundle()` | Reuse atomic state storage and existing lifecycle DTOs; no agent database. Keep authority, backend selection and observations separate through durable reload and export. Published schemas, fixtures and manifest/entry metadata remain governed authority; generator parity is necessary, not permission for a schema change. Preserve defaults/presence semantics across old stored payloads. |
| Host/OS and acquisition: `raes_backend_protocols`, reference `drivers/oci.py`, `drivers/oci_image_trust.py`, libvirt drivers, existing artifact/configuration delivery | Inventory locations, selectors, reload refs and profile URIs stay inert during parsing/admission. No shell execution, source fetch, socket opening or agent launch is introduced. Any later backend realization uses admitted image/artifact trust, fixed argv, bounded timeout/output and existing secret-safe delivery; no credentials in argv, environment dumps, public temp files or exception output. A syntactically valid URL is not SSRF authorization. |

## Specific integration traps

- `_relationships.py` skips agreement when there are no ship targets, but with
  partial targets it can reject an unknown protocol or absent ingestion/enrollment
  port as disagreement. Separate insufficient knowledge from explicit conflict
  at that owner, preserving private protocol identity and selected execution
  obligations. `has_ingestion_endpoint()` currently means only non-`None` port
  (including zero or a variable); it is not proof of a resolved usable endpoint.
  Reload `target_ref` is not validated by the ship-target resolver; do not claim
  control-channel authority merely because a string parsed.
- ADR-050's old secret-name enforcement claim conflicts with current ADR-056/057
  and `test_secret_named_setting_may_carry_scenario_value`. Names are advisory;
  explicit classification enforces withholding. Do not silently strip legitimate
  scenario values or relax posture-only enrollment fields. Classified refs are
  references, not a place to smuggle raw credentials. Source/selector strings
  are not secret-safe merely because setting-value projection is sanitized.
- The existing `plan-realization-profiles-v1` host is programmatic provisioning
  input, not SDL inventory syntax. The reference implementation in
  `raes_reference_backend/profile_preparation.py` supports public resource labels
  only. Do not encode forwarding behavior in labels or assume that accepting a
  domain-profile schema supplies installed forwarding semantics.

## Extensibility seam and review evidence

Use the existing operation-specific admission seam: exact selected semantic
contract/profile identity, owning resource/scope, independently configured backend
support, bounded local resolution context and limits. A future queue-fed or
non-IOC synchronizer should reuse the same typed family and admitted semantic
contract path, without another core recipe catalog, family subclass or central
switch over products. A new host or installed semantic contract, if actually
needed, requires its own explicit supported boundary; this note does not invent
public syntax or promise support that current backends lack.

Review evidence must pair valid sparse descriptions with invalid or unsupported
execution where necessary, and with a successfully admitted backend completion
where delegation permits one. Cover a nonpersistent key-value store, partial
search/wide-column state, non-IOC synchronization, incomplete privileged-interface
knowledge, empty grants/configuration, and unchanged #956 MISP behavior. Include
explicit-empty versus omitted round trips, exact-child conflicts, concrete bad
refs, variable revalidation, redacted values, partial readback, direct submission,
unsupported profiles, selected-result tampering and required-capture refusal.

Build on `test_runtime_forwarding_agent.py`, `test_runtime_datastore.py`,
`test_runtime_orchestration.py`, `test_runtime_app_authorization.py`,
`test_runtime_platform_application.py`, `test_issue_1043_forwarding_agent_posture.py`,
the #1201/#1204/#1209 description/preparation/result suites and
`test_issue_1112_capture_admission.py`, plus existing schema fixtures. Historical
tests expecting specimen completeness cannot simply be deleted: retain their
security invariants and give genuinely selected execution requirements admission
coverage. This preflight adds no tests or runtime changes.

## Compatibility, workflow and non-goals

The [ADR follow-up](../research/language-extensibility/adr-follow-ups.md#adr-050)
already records the correction. Implementation must reconcile ADR-048/050/051
and ADR-046 (DSL-134), runtime docstrings and
`specs/sdl/runtime-inventory.md` §3.4 with the changed validation contract.
Accepted ADR changes follow ADR-059's amendment and pin rules; this note leaves
them unchanged. Preserve governed schema publication, semantic invariant metadata,
fixtures and migration review through `tools/check_generated_schemas.py`,
`tools/check_schema_publication.py` and the existing publication manifest.
Do not treat unchanged JSON field shapes as proof of semantic compatibility.

Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`
and its package import DAG, `noxfile.py`, `tools/nox_support/`,
`.pre-commit-config.yaml` and existing CI. Use `RAES_REQUIREMENT_UID=DSL-136`
where the branch lacks a UID; retain the issue's other requirement traceability
where affected. Policy/governance/verification owners remain
`check_repo_policy.py`, `check_requirement_governance.py` and `verify_all.py`.
Unavailable governance is unevaluated, not passed. Native implementation blockers
remain to be cleared; this preliminary design review does not establish their
status. No new workflow or release-please version/changelog edit is needed.

Non-goals are implementing shippers, content generation, enrollment, reload,
buffer persistence, liveness/probes, capture storage or a secret resolver;
replacing manager rosters, detection rule sources, filesystem/process evidence,
scheduled jobs or service units; a general runtime-agent superclass; arbitrary
configuration bags; global validator relaxation; or universal evidence collection.
The intended change separates description validity from necessary execution
admission within existing owners. It does not authorize deployments or broaden
host, participant or control-plane privileges.
