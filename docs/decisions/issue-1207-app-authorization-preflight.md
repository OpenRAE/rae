# Issue 1207: Application authorization description and admission boundary

Date: 2026-09-13. Inspected revision: `d36608e8`. Requirement: DSL-134.

This preflight interprets the supplied #1207 corrective intent against the
existing implementation. It is guidance, not an implementation plan, a new
executable profile, or an amendment to accepted language contracts.

## Decision boundary

Reuse `RuntimeAppAuthorization`; DSL-134's inventory already exists. Keep one
node-scoped store referenced by datastore and platform `authorization_ref`, with
typed principals, roles, permission grants, mappings and tenants. Application
RBAC, OS-local identities, directory authorities, relational grants, participant
identity and control-plane operator authorization retain separate owners.

The correction is to separate description integrity from selected execution
obligations. A known resource vocabulary does not assert exhaustive knowledge
of grants or select a backend recipe. Omitted grants and legitimate configured
empty grants must be describable. Neither authorizes access. An explicit empty
closed constraint cannot be filled by the backend; an empty observation does
not close authored membership. Unknown, withheld, absent and omitted are also
distinct. Open scope delegates unspecified choices while exact descendants
remain binding; it is not a bypass for security policy or contradictory values.

DSL-134 and [ADR-046](adrs/adr-046-app-authorization-runtime-inventory.md)
currently require grant coverage unconditionally. The later corrective change
must explicitly reconcile that contract: retain matching-grant coverage where
an actually selected completeness/execution contract requires it, without
making it universal base-description validity. A backend may resolve a needed
choice within delegated authority; requiring concrete execution state does not
necessarily require the author to supply it. A complete abstract description
needs neither an RBAC deployment nor experimental evidence.

This changes observable validation semantics. Record the requirement/spec/test
alignment and the ADR amendment or supersession under
[ADR-059](adrs/adr-059-adr-amendment-policy-and-pin-gate.md); do not silently
delete the validator and leave the normative coverage requirement unchanged.
`specs/sdl/runtime-inventory.md` §3.4 explicitly assigns this correction to
#1207. This note does not claim the contract migration is already accepted.

## Current behavior and hazards

Package paths below are relative to `implementations/python/packages/`.

- `raes/runtime_app_authorization.py::validate_app_authorization()` combines
  duplicate-ID integrity with `_require_grants_for_resource_vocabulary()`.
  Separate their purposes; stable IDs remain concrete and authorization-local
  IDs remain unique across child kinds. Keep list duplicate checks.
- `resource_vocabulary` is currently **one scalar**, despite set-oriented prose
  in ADR-046 and the requirement. Coverage compares it with grant
  `resource_kind`. Do not introduce a list migration incidentally. Coverage is
  existential, not a rule that every grant must use the same kind; a matching
  deny grant satisfies today's check. It proves neither a usable allow grant
  nor effective authorization. Role inheritance, deny precedence, action syntax
  and resource-pattern interpretation are not evaluated by this inventory.
- A direct constructor probe rejected concrete, `other`, and private
  `x-acme:objects` vocabularies with empty grants; `unknown` passed. Concrete
  omitted grants also failed. A matching deny-only grant with no role or actions
  passed model validation. These are observations of the current model, not
  proposed execution policy or end-to-end validation results.
- Lists default to `[]`, `auth_enabled` to `None`, grant effect to `allow`, and
  principal credential classification to `none`. Preserve source presence and
  provenance through serialization and compilation. Defaulted values are not
  observations. `auth_enabled=false` does not mean an empty store, permission to
  execute unauthenticated, or proof that the deployment is safe.
- `raes/validator/_runtime_services.py` resolves supplied grant/mapping
  `role_ref` within the same authorization; blank and unresolved variable refs
  defer there today. `_runtime_platform.py` resolves datastore/platform
  authorization refs on the same node, and `_relationships.py` checks principal
  references for integrations. Preserve invalid-reference rejection. A partial
  observation missing a target needs explicit incomplete coverage in the
  description carrier, not a fabricated target or a globally disabled resolver.
  Mapping `users`, `hosts` and `backend_roles` are native strings, not implicitly
  portable principal refs; do not reinterpret them as OS identities or new joins.
- ADR-046's secret-name rejection prose is historical. Current
  `runtime_values.py`, ADR-056/057 and runtime-inventory §3.5 make name heuristics
  advisory; `test_secret_named_principal_may_use_none_classification` pins that
  behavior. Do not restore name-driven rejection. Conversely, posture-only
  principals must never acquire raw credential fields. Free-text fields remain
  possible leakage paths; classification does not sanitize arbitrary text.

## Canonical owners and gates

| Layer | Incumbents and required treatment |
| --- | --- |
| Source and model shape | `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py`, `_base.py::SDLModel`, `runtime_values.py`. Retain parser size/depth/alias limits, duplicate-key rejection, `extra="forbid"`, portable IDs, coercion and variable grammar. Accepting partial knowledge must not accept malformed fields or unknown syntax. Revalidate after substitution; a template exemption is not execution support. |
| Vocabulary and shared references | `raes/runtime_vocabulary.py::GovernedVocabulary`, `raes_contracts/controlled_vocabularies.py`, repo-root `contracts/concept-authority/controlled-vocabularies-v1.json`; `raes/_runtime_service_family_registry.py`, `_runtime_service_families.py`, `composition/` and `validator/`. Reuse core alias normalization and exact private identity; credential classification and grant effect remain closed. Preserve the registered qualified child-ref tree and import namespacing, rather than adding product-specific resolvers or duplicate registries. |
| Recursive author authority | `raes/explicitness.py`, `realization_designation.py`; `raes_contracts/realization_structure/`; processor `compiler/realization_recursive_constraints.py`, `realization_structure.py`, `realization_requirements.py`, `semantics/realization_concerns.py`, `realization_runtime_concern_profiles.py`, `realization_runtime_evaluation.py`. Reuse presence, scope, origin, relation and bounded evaluation. The app-authorization concern already has a recursive projector, but no explicit root `collection_identity_fields` or nested policy in `realization_specialized_projection.py`. Its recursive compiler therefore does not attach stable-ID collection profiles here; inspect sequence versus keyed semantics rather than assuming the reference registry supplies them. Merely removing a Pydantic guard does not establish nested constraint preservation. Bind keyed matching to existing authorization/child IDs; fail honestly for unsupported combinations rather than treating the whole inventory as unconstrained. |
| Description and comparison | `raes_contracts/contracts/realization_descriptions.py`, `description_projection.py`, `description_reporting.py`, `description_promotion.py`; processor `semantics/realization_concern_observations.py`. Reuse #1209's typed fact states, coverage universe/window and provenance, with explicit promotion into a new authored artifact. The older observation adapter still validates via SDL types and defaults; exercise that path as well as the newer carrier. Partial coverage cannot claim exhaustive conformance, and missing coverage cannot hide a known violation. |
| Profile definition and execution admission | `raes_contracts/domain_profiles.py`, `_domain_profile_admission.py`, `realization_profiles.py`; processor `planner/realization_profiles.py`; runtime `manager_plan_admission.py`, `control_plane_plan_authorization.py`, backend protocols and installed validators. Keep exact coordinate/digest, owner/context, independent host support, finite limits and offline schema resolution. Profile data cannot load handlers, resolve remote schemas or supply its own trust/support declaration. Reject unsupported execution before mutation and check selected result fidelity. The #1204 plan carrier is public provisioning data, not SDL inventory syntax or a general RBAC executor; the reference labels validator does not configure access policy. Do not claim an existing carrier already implements app-authorization completeness admission. |
| Validation basis | `raes_contracts/validation_profiles.py`, `contracts/validation_disclosure.py` and repo-root `contracts/profiles/validation/validation-profile-catalog-v1.json`. Reuse selected gates, limitation disclosure and strength caps. Validation-strength profiles, domain-profile definitions, runtime concern registration and backend capability are separate contracts; none alone proves operational admission or observation. No global strict/partial switch or parallel validity taxonomy. |
| API authentication and authorization | `raes_runtime/control_plane_security.py::ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, `control_plane_admission.py`. Preserve fail-closed trusted identity, target binding, role checks and denial audit. Inventory principal IDs, `auth_enabled`, an allow grant, profile admission or successful parsing never mint a control-plane identity or authorize an effect-capable plan. Direct submission and manager apply must retain the same admission boundary as planned execution. |
| Secrets, environment and configuration shapes | `raes/runtime_values.py::enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_configuration.py`, `raes_contracts/secret_references.py` and existing generated-artifact delivery validators. App authorization stays classification-only; no secret resolver is needed here. If adjacent execution uses environment delivery, keep literal/value-from exclusivity, generated-output resolution and producer-private restrictions. Generated secrets use the existing redacted delivery contract, not `operator_secret`; that posture denotes out-of-SDL operator custody. No new env binding, config bag, token source or ambient credential lookup follows from this change. |
| Host/OS exposure | `raes_backend_protocols`, existing `raes_backend_libvirt/drivers/` and `raes_reference_backend/drivers/`, local-control-interface and process-limit contracts. Inventory is inert: no new shell, credential command, socket access or provisioning hook. Selected host-root operations still require independently admitted authority and a supported concrete interface before execution. Future backend resolution uses existing bounded subprocess/artifact handling; never put credentials in argv, shell interpolation, environment dumps or public temporary files. |
| Errors and observability | `raes/_errors.py`, `_model_diagnostics.py`, `raes_contracts/diagnostics.py::Diagnostic` and `portable_diagnostic_payload`, `OperationReceipt`/`OperationStatus`; runtime `control_plane_api/_operation_routes.py::_install_request_guards` and `_responses.py`. Reuse source-anchored diagnostics, redacted HTTP envelopes and existing operation/audit ownership. Keep new messages value-free: message truncation does not redact interpolated input. Never publish Pydantic input dumps, native responses, credentials or tracebacks. Distinguish invalid shape/reference, incomplete knowledge, unsupported semantics and denied execution without a new exception hierarchy or logging pipeline. |
| Persistence and evidence | `raes_runtime/control_plane_store.py`, `control_plane_store_local.py`, existing payload/snapshot/observation codecs, `observation_admission.py`, `observation_execution.py`, `observation_results.py`; processor `capture_admission.py`. Retain atomic writes, recovery and audit ownership; no separate RBAC database. #1212 owns independent collection/retention/export policy and #1112 owns required capture and emitted-byte validation. Describing choices creates no automatic capture demand. Conversely, selected verification obligations cannot be satisfied by an echoed plan or bypassed by describing it as partial. |
| Contracts and repository workflow | Published `contracts/schemas/`, `raes_contracts/contracts/bundle.py::schema_bundle`, `schema_invariants.py`, publication entries/manifest and fixtures; `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`, `noxfile.py`, `tools/nox_support/`, `.pre-commit-config.yaml` and CI. Preserve the import DAG and schema authority/generator parity, including semantic invariant annotations. Follow ADR-061/075 for contract migration and ADR-059 for pins. Reuse policy, governance, generated-schema and publication checks; align DSL-134 traceability. No new workflow, release version edit or changelog fragment. |

## Adjacent-family rubric and extensibility

Apply the repository's product-shaped-semantics audit distinction: is the check
structural integrity, an explicit contradiction, a selected operational/security
prerequisite, or completeness inferred from a specimen? Preserve the first two;
scope the third to actual authority/operation; remove the fourth from universal
description validity through the reviewed migration.

| Family and incumbent | Boundary that must survive #1207 |
| --- | --- |
| `runtime_datastore.py::require_profile_for_data_model` | Search geometry/mappings, key-value persistence and wide-column replication are not universally known or required authored facts. Nonpersistent services and empty configured indexes/keyspaces are legitimate. The key-value helper also rejects incompatible partition kinds: do not erase that consistency check with its persistence requirement. |
| `runtime_forwarding_agent.py::require_profile_for_agent_kind` | Buffer/destination completeness and the API-pull/IOC-to-rule/reload sequence are selected operational obligations, not definitions of every forwarder or content synchronizer. Preserve typed transforms, endpoints, references and sensitive-value rules. |
| `runtime_orchestration.py::require_profile_for_privilege_class`, validator `_runtime_orchestration.py` | Incomplete privileged-interface knowledge is describable; executing privileged operations remains fail-closed. A Docker socket specimen cannot define all host-root authority. Preserve explicit interface identity, kind/access consistency and operator policy. |
| `runtime_platform_application.py`, `runtime_platform_application_content.py`, ADR-049 | Preserve #956's composable capability correction and optional configured state, including legitimate empty sharing groups. Product category cannot revive a compulsory MISP recipe or evidence obligation. |
| App authorization, `runtime_database.py`, `runtime_directory_identity.py`, `runtime_identity.py`, `runtime_file_service.py`, mail credential models | Keep application RBAC, relational grants, directory subjects, local users and posture-only credentials distinct. Shared observed-value handling does not authorize merging their schemas or globally relaxing their validators. |

The extensibility seam is the existing versioned domain-profile coordinate plus
owner/context, requested operation, host-supported semantic contract and bounded
validation policy. Resource identity uses the governed private-token seam; it
does not itself select execution. A future private resource vocabulary should
need no core product catalog edit. Richer semantics require explicit support,
not free-form executable validators. Locate any new completeness predicate at
the owning selected contract and reuse it across admission entry points; do not
duplicate it in each vendor model, controller or backend. If the existing host
cannot carry that contract, record the narrow missing host boundary rather than
overloading public provisioning labels or adding a parallel profile system.

Nested collection matching needs the existing stable-ID policy as a parameter
of shared relation/projection machinery. Do not use list position or native
display names as identity, and do not widen the scalar resource-vocabulary
field merely to anticipate hypothetical multi-vocabulary support.

## Review evidence, workflow and non-goals

Reuse `implementations/python/tests/test_runtime_app_authorization.py`, the
datastore/platform/forwarding/orchestration suites, `test_runtime_observed_values.py`,
`test_sdl_diagnostic_boundary.py`, and existing #1201/#1204/#1209/#1212/#1112
tests and schema fixtures. Later verification must pair acceptance of omitted,
empty, private-vocabulary and non-IOC examples with rejection of malformed IDs,
duplicate children, bad scoped refs, closed operator values, explicit secret
payloads and unsupported/unauthorized execution. Include grant-kind mismatch,
deny-only coverage, variable substitution, imported refs, keyed reordering and
exact-child violations under open scope. Check compile, admission, returned
results and durable round-trip; a constructor success is insufficient.

The repository policy check passed before and after this documentation change; local Markdown links and whitespace checks also passed. Runtime/schema implementation tests were not run for this documentation-only preflight. The
Ground Control context MCP call required approval unavailable in this session;
local `.ground-control.yaml` and `.gc/plan-rules.md` supplied workflow context.
This preflight does not attest current remote blocker or traceability status.
Use `RAES_REQUIREMENT_UID=DSL-134` for later applicable checks. The supplied
#1207 context requires native blockers cleared before dependent implementation;
preliminary architecture review is permitted now.

Non-goals: implement DSL-134/#1207, prescribe a coding sequence, execute RBAC
decisions, provision credentials, add backend recipes, make evidence universal,
change #956, or redesign identity/relational models. Avoid blanket optionality,
sentinel substitution to evade guards, `model_construct`/validation bypasses,
untyped security-config bags, synthesized grants or roles, per-product RBAC
schemas, a new service/repository, and duplicated validation/workflow engines.
