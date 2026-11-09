# Issue 1805: open concern disclosure preflight

The supplied issue #1805 is the contract; no formal requirement is attached.
This is architecture guidance, not an implementation plan. Existing ADRs
cover the owners and contracts; no new ADR or abstraction is needed.

## Decision and evidence boundary

Keep the correction in the shared runtime realization evaluation, reached
through the public `raes_processor.planner.realization_disclosure()` and
`realization_authority_disclosure()` interfaces. The latter reconstructs
requirements from admitted plan authority. A fix exercised only through the
private evaluator would leave the production acceptance boundary unverified.

For an applicable open concern with an operational or selected verification
floor, a successful result must not use missing backend data as evidence of
an empty concern. The issue's missing-value/empty-snapshot case must fail
with `runtime.backend-contract-invalid` and no new success provenance.
Require a valid report through the existing concern contract and sufficient
corroboration; do not manufacture an empty value from omission. Preserve the
outer evaluator's applicability rules for absent operations and DELETE.
Do not impose a new observation floor on kinds that have none.

Read-only reproduction in this checkout confirms that the minimal input's
`runtime-mail-services` requirement has configuration-scope verification,
no structure and no constraint document. Passing `MISSING_CONCERN_VALUE`
and an empty snapshot returns `(None, None)`. Its existing closed projection
accepts `[]` but rejects `None`, `{}` and `False`; even `[]` currently fails
without corroboration. Missing, explicitly empty, invalid and uncorroborated
are therefore distinct states. Python truthiness cannot classify them.

Preserve #1763's planning relaxation: an authored-empty open concern need
not advertise observation capability before deployment. That admission is
not proof of execution. This correction tightens runtime acceptance; do not
silently restore the planner capability demand as a workaround.

There is a compatibility consequence: the no-report success expectation in
`test_issue_1758_open_empty_concern.py` encodes the bypass. It cannot remain
the runtime oracle for #1805. The report-only wording in SEM-218 I2 at
`specs/formal/realization/explicitness-and-realization.md` and its companion
`docs/explain/reference/explicitness-realization-semantics.md` must describe
the same omission rule as the corrected gate. Do not reinterpret all absent
open concerns as exact authored emptiness or weaken explicit-empty validation
to preserve the old result. Backends unable to establish the required report
must refuse the success claim, rather than invent readback.

This gate evaluates evidence supplied through the backend contract. It cannot
detect an actual host addition concealed by a lying backend that also falsifies
an empty report and its observation. Refusing missing evidence closes the
reported bypass; it does not certify backend honesty or roll back physical
infrastructure. Independent observer isolation is outside this issue.

## Existing owners and cross-cutting gates

Package paths below are relative to `implementations/python/packages/`.

| Layer | Canonical incumbent and required guardrail |
| --- | --- |
| Authored shapes and intent | `raes.parse_sdl`, `SDLModel`, `SemanticValidator`, `explicitness`, `realization_designation`, instantiation revalidation and `raes_processor.compiler.realization_requirements` own syntax, closure and intent. Consume their compiled metadata. Do not parse YAML or infer intent from serialized defaults at runtime. Open membership does not erase exact children or authorize a new containing node. |
| Concern shapes and comparison | `raes_processor.semantics.realization_concerns.RealizationConcernDescriptor`, `RUNTIME_CONCERN_PROFILES`, `realization_concern_observations` and `realization_typed_runtime_projection` own paths, closed validation and safe projection. Validate before comparison or provenance. Missing parent, missing member, explicit empty collection and malformed parent must not become interchangeable. No mail-service-only kind list, duplicate DTO or parallel validator. |
| Verification and manifest configuration | `realization_operational_verification.operational_verification_requirement`, compiled requirement/plan authority verification fields, `RealizationSupportDeclaration`, `RealizationSupportDeclarationModel` and `BackendManifestV2Model` own demand and support. Reuse `matching_observation`, `manifest_corroborates`, `observation_posture_supported` and `observation_requirement_satisfied`. Match address, field path, domain and kind; the same supporting declaration must cover posture and claimed scope/source. Absent manifest, wrong identity, under-scoped evidence and unsupported source must fail. Source categories are alternatives, not a strength ranking; `driver-reported` and `none` cannot replace authoritative readback. |
| Input/result bounds and authority | `raes_runtime.backend_input_contracts`, `backend_call_contracts`, `backend_snapshot_contracts`, `backend_entry_transitions`, `backend_effect_transitions` and `raes_contracts.runtime_value_limits` retain shape, canonical-address, work bounds, identity, change-accounting and runtime-owned-field checks. An open node concern grants no unplanned resource membership. Preparation and descendant inventory keep their existing admission owners. |
| Secrets and environment binding | `raes.runtime_environment.RuntimeEnvironmentVariable` retains name validation, literal `value`/`value_from` exclusivity and generated-source classification rules; `runtime_values.enforce_observed_value_redaction` retains protected-value omission. Reuse descriptor sanitizers and `raes_runtime.backend_account_credentials` egress checks for additions too. Preserve allowed observed differences without masking unauthorized siblings or restoring planned values over observations. Do not copy raw environment, enrollment or credential data into evidence or errors. Existing presence/commitment formats and `raes_contracts.canonical` remain the authority; a hash is not independent readback or a substitute SDL value. |
| Acceptance and cleanup | `backend_calls._call_backend_apply` / `_validated_backend_result` and `backend_apply_results._finalize_backend_apply` own isolated predecessor state, shared disclosure, credential sanitization and post-sanitization revalidation. An invalid success returns the predecessor, empty changed addresses, no candidate details and no newly derived success provenance. Preserve existing predecessor provenance. The existing `result.success` distinction in `_realization_disclosure_result` separates success evidence from failed-apply cleanup inventory: do not lose recoverable resources by demanding successful readback from a failed apply. Cleanup still passes authority, identity, shape and secret gates. |
| Persistence and public schemas | `RuntimeSnapshot`, `RealizationObservationDisclosure`, `RealizationProvenanceEntry`, their models in `raes_contracts.contracts.realization_plans`, `ControlPlaneStore`, `control_plane_store_snapshots._snapshot_payload` / `_snapshot_from_payload` and `control_plane_api_models._snapshot_model` own carriers and round trips. No new carrier is needed. Ordinary disclosures are value-free; execution-binding/value fields are reserved for compute-substrate and operating-system contracts. `backend_apply_results` reuses transient observations for revalidation, then removes them from accepted state. Retain that separation; do not persist new readback just to fix omission. |
| Authentication and HTTP exposure | `ControlPlaneSecurityConfig`, `control_plane_api._auth`, administrative read/mutation identities, sealed route composition, target/run authorization, `RequestSizeLimitMiddleware` and `NoStoreResponseMiddleware` remain unchanged. Both manager and authenticated control-plane execution must reach the same result gate. No endpoint, bearer/config field, privilege or new data transfer is required. Transport authentication is not evidence of realization. |
| Errors, audit and OS exposure | Reuse `Diagnostic`, `Severity.ERROR`, `BACKEND_CONTRACT_INVALID`, existing refusal helpers, `portable_diagnostic_payload`, `raes_contracts.errors`, `operational_logging.foreign_failure_record`, `control_plane_audit` and redacted API envelopes. Name the concern identity and coarse reason, never raw values, Pydantic inputs, backend exception text or stdout/stderr. Diagnostic serialization validates shape; it does not sanitize arbitrary message text. Keep tokens and values out of argv, environment dumps, logs, audit details and fixtures. This correction needs no subprocess, host probe, listener, collector or secret resolution. |
| Repository policy and workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, `tools/policy/adr_policy.yaml`, `tools/policy/import_contracts.toml` and ADR-117 preserve module ownership, public interfaces and import direction. Do not add private cross-module imports or relax baselines. No schema change is expected; if one becomes necessary, ADR-009/061, published schemas, `schema_bundle()`, the publication ledger and parity checks govern together. Keep this requirement-free; do not invent a UID. Use targeted local checks; CI owns full suites and existing review/publication gates. |

## Extension and verification boundaries

The extension seam already exists: concern descriptors plus the requirement's
`verification_scope` and `required_observation_strength`, preserved in resolved
plan authority. A future registered concern must inherit the same omission
and corroboration rules without a backend-name switch or another kind table.
Keep applicability and the existing success/cleanup distinction at their
current owners; do not create a per-caller bypass flag or a new absence enum.
Compute-substrate, operating-system and process-limit special rules remain
with their current evaluators and typed apparatus contracts.

Preserve the runtime envelope's unique concern identities; do not resolve
duplicate/conflicting disclosures by whichever row happens to match first.
UNCHANGED resources must retain trusted state under their existing transition
rules. Retained provenance is not fresh corroboration for an addition, and
fresh verification must not require an unadmitted environment mutation.

Use existing test patterns in `test_issue_1758_open_empty_concern.py`,
`test_sem_218_runtime_realization.py`,
`test_issue_1067_resolved_realization_authority.py`,
`test_issue_1200_mixed_runtime_constraints.py` and
`test_issue_1638_credential_realization_observations.py`. The behavior needs
evidence through both disclosure routes and the adapter, including missing
entry/path, explicit empty versus malformed values, inadequate, duplicate and
adequate corroboration, safe backend-origin provenance, predecessor retention and
credential sanitization followed by revalidation. Preserve DELETE/no-operation
applicability, unchanged-resource retention and failed-apply cleanup. A private
helper assertion alone cannot establish durable or public acceptance behavior.

## Non-goals and anti-patterns

This preflight changes no implementation, tests, schema or normative spec.
The implementation boundary is runtime evidence acceptance and the matching
contract explanation. It does not reopen #1763's planner fix, redesign
realization authority, add a new snapshot store, exception/logger hierarchy,
manifest, schema registry, workflow or backend-specific workaround, or expand
observation into experimental capture. Provenance records origin; it is not
corroboration. Capability advertises support; it is not an observation.
Prepared selection is not observed state. A rejection restores trusted
portable state; it does not claim physical rollback.
