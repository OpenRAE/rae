# Issue 1638: credential closure and observed realization values

Architecture preflight, 2026-10-25. GitHub issue #1638 is the contract; no
formal requirement UID is attached. This is boundary guidance, not an
implementation plan. Existing contracts suffice; no new ADR or schema is needed.

## Decision

Credential confidentiality and realization conformance are conjunctive. An
observed concern is not necessarily a plan echo: OPEN selects a value, CONSTRAINED
admits a bounded choice, and even EXACT compares the concern's semantic
projection rather than its raw representation. Credential-bearing plans must
use the same realization semantics as other plans.

The current `backend_account_credentials._closed_plan_payload()` admits only
address-bound `artifact_satisfaction` beside an exact plan payload. It therefore
rejects otherwise valid observed concern values. Reconstructing these concerns
from `operation.payload` would erase readback and fail repeat admission.

Keep the closed credential egress contract, with a precise distinction:

- Outside applicable admitted realization paths and existing authorized evidence,
  returned payloads must still match admitted operation values through
  `backend_snapshot_contracts.snapshot_values_equal`, including JSON types.
- Within an applicable concern, accept only its existing observed contract and
  publish its existing safe observation projection. Retain its selected meaning;
  never substitute the plan's null, declaration, raw fixture, or comparison-only
  representation. Structural validity alone does not establish satisfaction.
- Reconstruct account material only through
  `raes_contracts.account_credentials.value_free_account_placement_payload` at
  account-placement `spec.credential_bindings`. Fixture values and operator
  reference IDs become presence-only posture. Neither observation authority nor
  preparation may substitute or broaden an account binding.

Permission is bound to the admitted address, concern kind, canonical payload
path, authority mode and constraints. A registered field name alone is not
permission. CLOSED omissions remain closed; an OPEN parent does not override
exact/closed children or recursive membership constraints. A malformed value or
unknown field must not disappear into an ignored subtree before validation.

The owning processor concern descriptor and native validator must establish
which fragment can be projected safely. Credential code must not learn a second
inventory of runtime fields or reimplement concern semantics. Preserve the
initial result checks, credential closure, native safe projection and repeat
validation in `backend_apply_results`; any internal factoring must preserve
those obligations and the same permitted meaning at both validations.

This clarifies the plan-value/evidence distinction in the
[1603 preflight](issue-1603-credential-artifact-evidence-preflight.md): observed
concern replacements also have an existing authority contract. Artifact evidence
remains separately bound and validated; it is not a generic observation field.

## Cross-cutting layers and canonical owners

Package paths below are relative to `implementations/python/packages/`.

| Layer the design passes | Incumbent and required invariant |
| --- | --- |
| SDL and direct-plan credential validation | `raes/accounts.py`, `raes_processor/planner/account_credentials.py`, and `specs/sdl/account-credential-bindings.md` own the closed material union, safe logical references, account identity, primary authentication and `credential_bindings` capability admission before effects. Keep this input authority distinct from output posture. No new binding, option or configuration shape. |
| Submitted authority and preparation | `raes_runtime/backend_input_contracts.py`, `backend_calls.py`, `backend_realization_authority.py` and `backend_preparation.py` own bounded input admission, isolated request/predecessor, selected manifest and admitted completion. `raes_processor/planner/realization_authority.py` owns registry completeness, canonical pointers, modes and source-bound recursive constraints. Use the admitted completion for operation-value closure where present, while preserving the original governing constraints. Never derive permission from returned pointers or a backend-authored digest. |
| Result shape and resource effects | `backend_call_contracts._apply_result_contract_violation`, `backend_snapshot_contracts.snapshot_shape_violation`, `raes_contracts.realization_structure` and `runtime_value_limits` bound shape, depth and total work before copying/projection. `backend_entry_transitions.py` and `backend_effect_transitions.py` retain identity, dependencies, profiles, membership, DELETE/UNCHANGED and changed-address accounting. An open value grants no new resource or snapshot-carrier authority. |
| Concern shape and safe publication | `raes_processor/semantics/realization_concerns.py` owns `RealizationConcernDescriptor`, paths, observed validators, recursive projectors and sanitizers. Reuse `realization_concern_observations.py`, `realization_typed_runtime_projection.py`, `realization_snapshot_sanitization.py` and the typed SDL family models. Closed shape checks precede omission of annotations or native evidence; valid projected output must itself survive repeat admission. |
| Realization semantics and provenance | `realization_authority_disclosure`, `realization_disclosure`, `realization_runtime_evaluation.py` and the existing constraint/observation evaluators retain exactness, bounds, recursive children, observation scope/strength and manifest corroboration. OS and compute observations keep their dedicated binding contracts. The runtime derives provenance after successful revalidation; backend-authored provenance cannot authorize a value. |
| Supplemental evidence | `_supplemental_realization_requirements`, `ArtifactSatisfactionDisclosureModel` and `artifact_realization.evaluate_artifact_realization` retain address/requirement, selected backend, immutable artifact, route and trusted availability checks from #1603. Registry authority and supplemental artifact demand must coexist; neither may replace the other. |
| Secret and environment shapes | `account_credentials.py` owns account presence-only projection. Environment uses `RuntimeEnvironmentVariable`, `GeneratedArtifactValueSource`, `validate_environment_observation` and `project_environment`/`project_recursive_environment`; forwarding, mounts and typed runtime settings use their own validators and safe projectors. Preserve value/`value_from` exclusivity, explicit withholding, presence markers and versioned commitments. A credential binding is not an environment binding or a setting. ADR-057 does not authorize publishing account material. |
| Errors and observability | `value_free_backend_diagnostics`, `backend_result_diagnostics._backend_contract_invalid`, `_failed_apply_result`, `_backend_call_failed` and `backend_calls._validated_backend_result` provide coarse structured refusals. Keep arbitrary result `details` forbidden and replace backend diagnostic prose. Never expose rejected values, Pydantic error details, exception text, native output or payload diffs in diagnostics/logs. Reuse existing codes and exception guards; no new exception hierarchy or raw tracing. |
| Authentication, authorization and HTTP errors | `control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_plan_authorization.py`, `control_plane_operation_context.py` and `control_plane_audit.py` retain principal/role/target/run admission and value-free context/audit. `_operation_routes.py` retains redacted validation/exception responses. Authenticated input does not make backend output trusted. No endpoint, role or auth configuration changes are needed. |
| Persistence, recovery and API/CLI publication | `control_plane_store_payloads.py`, `control_plane_store_snapshots.py`, `control_plane_store_compatibility.py`, `control_plane_api_models.py` and `raes_cli/processor.py` consume accepted state and repeat the canonical account projection idempotently. Preserve snapshot round trips, operation commitments and existing atomic terminal commits/recovery. Downstream projection cannot repair an unsafe runtime acceptance. No new store, sidecar or migration. |
| Host and OS exposure | ADR-115 places concrete backends outside RAES; the portable runtime, injected `RuntimeTarget`, backend protocols and test doubles are the in-repo seam. This fix requires no native invocation, credential resolution or daemon access. Do not add shell commands, credential argv/environment propagation, temporary secret files or native inspect dumps to obtain observations. Live lilrae interoperability belongs downstream. |
| Repository governance | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`, `tools/check_repo_policy.py`, `noxfile.py` and `tools/nox_support/` own policy and verification. Keep ADR-015/036 dependency direction and source size rules. Published schemas under `contracts/schemas/` remain authoritative under ADR-009/061; a new observation DTO/schema is unnecessary. Do not fabricate a requirement UID or edit versions/changelog. Local checks stay targeted; full suites belong to CI. |

An invalid successful claim still returns `success=false`, the isolated immediate
predecessor, empty changed addresses/details and no candidate success provenance,
under [backend result admission](../../specs/formal/runtime-contracts/backend-result-admission.md).
Preserve a sanitization refusal rather than replacing it with a secondary failure
against the rejected candidate. Failed native readback can retain authorized
cleanup inventory under its existing closed contract; it does not establish
successful observation. This is state refusal, not infrastructure rollback or
permission to retry apply.

## Extensibility seam and gotchas

The seam belongs to existing processor realization projection: admitted
address/concern/path, mode/recursive constraint, observed validator and safe
sanitizer. Credential closure needs this authority context, not just the
supplemental requirements currently passed after registry concerns are filtered
out. Share any necessary factoring with `sanitize_plan_realization_snapshot`
and `sanitize_realization_snapshot`; do not expose their private helpers as a
new public protocol or add a parallel registry.

New runtime families must continue to enter through the existing descriptor and
`RUNTIME_CONCERN_PROFILES` inventory. Credential code should then require no
family-name switch. A descriptor without a safe projector, a scalar concern or
a specialized evidence carrier is not permission to copy an arbitrary value:
use its existing owning admission contract, and otherwise retain closed closure.
Do not authorize an entire `spec`, `node` or `runtime` subtree for one leaf.

Comparison and publication forms differ. For example, software repository
identity aliases are comparison-only, mount publication has its own sanitizer,
and environment/forwarding settings use commitments. Use
`descriptor.sanitize_observation()` through the incumbent snapshot sanitizer
for persisted values, with recursive context preserved. Do not use
`realization_payloads_match()` as an egress policy: it serves reconciliation and
does not authorize backend choice. Do not remove exact comparison globally or
compare only known keys. Missing, null, empty and false are distinct inputs;
retain typed exact comparison outside permitted concern paths.

Reuse admitted transient observations for repeat checks without recollection or
retention. Keep observation metadata separate from the observed concern value;
do not move values into provenance, `details`, metadata or observation envelopes
to bypass payload closure. Never restore authored sensitive values from the
plan while composing safe fragments. Preserve non-credential behavior and
unchanged predecessor resources.

String matching is not a confidentiality model. Keep rejection of unauthorized
credential carriers and the existing closed observed shapes; do not scan or
mask every string equal to a fixture/reference. Independent typed identities
may legitimately have the same text. This boundary does not certify a hostile
backend or detect every possible covert encoding of a secret.

## Verification obligations and boundaries

The regression must cross `_call_backend_apply`/finalization with credentials
and differing observations, including the issue's null-to-OPEN Linux capability
case. Accepted safe values and runtime-derived provenance must survive storage
and API projection while account material/reference IDs and transient
observations do not. Also cover an admitted constrained choice, exact semantic
projection, a typed runtime family and coexistence with artifact evidence;
one capability-only exception cannot satisfy the issue.

Reuse fixtures and assertions from `test_issue_673_account_credential_bindings.py`,
`test_issue_1603_credential_artifact_evidence.py`,
`test_issue_1067_resolved_realization_authority.py`,
`test_issue_1200_mixed_runtime_constraints.py`,
`test_issue_1204_prepared_credentials.py` and
`test_issue_985_runtime_realization_concerns.py`. Existing result-shape,
transition and durability tests cover their respective owners. Negative cases
must retain rejection of unknown/nested fields, wrong or absent authority,
CLOSED materialization, exact/child/bound violations, insufficient corroboration,
copied fixture/reference material, raw protected values, arbitrary details and
carrier mutations. Confirm refusal preserves a nonempty trusted predecessor and
safe error envelopes. Exercise preparation and durable recovery when affected.
Use explicit relevant test modules/cases locally, not full suites or live native
execution. These are acceptance obligations, not a request to implement tests
during preflight.

Non-goals: backend/env-pack workarounds, TechVault-specific exceptions, new
credential resolution/injection/storage, changed participant visibility,
weaker realization semantics, changed portable schemas or public protocols,
new logging/persistence/workflow systems, automatic retries or rollback. Limit
implementation to reconciling portable credential egress with the existing
realization contracts and the corresponding regression evidence.
