# Issue 1603: credential egress and artifact evidence

Architecture preflight, 2026-10-15. GitHub issue #1603 is the contract; there is
no formal requirement UID. This note clarifies existing boundaries, not an
implementation plan. No new ADR or portable schema is needed.

## Decision and ownership

Credential confidentiality and artifact satisfaction are conjunctive contracts.
`backend_account_credentials._closed_plan_entry()` currently requires the
entire payload to equal the submitted operation; `evaluate_artifact_realization()`
requires backend-added `artifact_satisfaction`. Neither removing that evidence
nor admitting arbitrary extra payload fields is correct.

Keep the closed credential egress boundary. Separate plan-owned payload values
from explicitly authorized realization evidence. Evidence is admissible only
for an applicable admitted requirement at that entry's canonical address, with
its existing closed model and semantic checks. Compare the remaining payload
against the admitted operation using the incumbent typed exact comparison
(`backend_snapshot_contracts.snapshot_values_equal`), which distinguishes
booleans from integers. Preserve resource identity, domain, type, dependencies,
profile completion, status and transition accounting. Unknown additions and
mutations remain refusals, even if they contain no known credential token.

Reconstruct credential posture with
`raes_contracts.account_credentials.value_free_account_placement_payload` at
`account-placement.spec.credential_bindings`; do not copy backend credential
material into accepted state. An exact echo at that canonical material path is
input to projection, not permission to publish it. A credential copied to an
extra entry field, nested extra key or other unauthorized carrier is refused.
Operator references receive the same presence-only treatment. Resolved or
transformed secrets must never enter `ApplyResult`.

`artifact_satisfaction` remains evidence input in the existing payload location;
the runtime derives `RealizationProvenanceEntry.artifact_satisfaction` through
the existing evaluator. A backend-authored ledger is not a substitute for that
input. Preserve evidence through credential projection and native concern
sanitization so the existing second validation sees the same permitted meaning.
Do not move the field, skip revalidation, or collect observations again.

## Cross-cutting surfaces and canonical incumbents

Paths below are relative to `implementations/python/packages/` unless noted.

| Layer | Required boundary and reuse |
| --- | --- |
| Authoring and direct-plan validation | `raes.accounts.Account`, `account_credential_binding_issues`, `raes_processor/planner/account_credentials.py`, and submitted-plan capability admission continue to validate the closed material union, canonical account identity, and provisioner `credential_bindings` feature before side effects. No new binding/config shape. |
| Request isolation and preparation | `raes_runtime/backend_input_contracts.py`, `backend_calls._call_backend_apply`, `_bind_submitted_plan`, and `backend_preparation.py` retain bounded input admission and isolated predecessor/request authority. Compare with the admitted completion when present; preparation cannot rewrite credential material or purpose. Supplemental artifact requirements must still be available when registry authority is also present. |
| Result shape and work limits | `backend_call_contracts._apply_result_contract_violation`, `backend_snapshot_contracts.snapshot_shape_violation`, and `raes_contracts.realization_structure` run before recursive copying/projection. Preserve bounded depth, size, diagnostics and canonical addresses; schema parsing is not a substitute for these guards. |
| Resource and carrier authority | `backend_entry_transitions.py`, `backend_effect_transitions.py`, and snapshot carrier classification own membership, unchanged resources, DELETE, dependencies, profile completion and actual/reported changes. Evidence permission does not grant resource or carrier mutation authority. Retain the credential-specific closed carrier gate. |
| Evidence structure | `raes_contracts.artifact_requirements.ArtifactSatisfactionDisclosureModel` and `ContractModel(extra="forbid")` own disclosure shape, enums and unique refs. Reuse model validation and JSON serialization; never retain an unvalidated mapping or invent a parallel evidence DTO/schema. |
| Evidence semantics | `raes_processor/semantics/artifact_realization.evaluate_artifact_realization` owns requirement ID, immutable artifact, selected backend identity, mechanism/profile, acquisition/timing, candidates, locked inputs, constraints and trust checks against `ArtifactAvailabilityContext`. Well-shaped strings alone are not safe evidence: refs must join the trusted facts and admitted requirement. Never manufacture availability from returned claims. |
| Sanitization and repeat admission | `backend_apply_results._finalize_backend_apply`, `_sanitize_backend_realization`, `_supplemental_realization_requirements`, `_revalidated_diagnostics`, and processor `realization_snapshot_sanitization.py` retain initial validation, credential closure, native concern projection, repeat validation and runtime-owned provenance. No backend-only or manager-only bypass. |
| Secret, environment and config meaning | Reuse the canonical account projection; environment observations remain under `realization_concerns` and their existing projectors. ADR-057 explicit withholding is distinct from account-credential publication. Do not classify arbitrary mappings by field names, reinterpret environment values as credential bindings, scan all strings for fixture equality, or add env variables/options to enable evidence. Typed identities may legitimately equal fixture text. |
| Diagnostics and exception envelopes | `value_free_backend_diagnostics`, `backend_result_diagnostics._backend_contract_invalid`, `_failed_apply_result`, `_backend_call_failed`, and `backend_calls` exception guards provide existing coarse errors. Reject arbitrary nonempty `details`; replace backend diagnostic prose as today rather than echoing it. Never include Pydantic errors, rejected mappings, exception text or subprocess output in messages/logs. Preserve structured diagnostic identity under its native validator. No new exception hierarchy. |
| HTTP authorization and audit | `control_plane_security.ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, `control_plane_plan_authorization.py`, and `control_plane_audit.py` remain the owners of principal/role/target admission and audit. Authentication does not make backend output authoritative. Existing redacted HTTP errors and identifier/code audit records suffice; no endpoint, permission, token or logging payload is added. |
| Persistence and API exposure | `control_plane_store_snapshots.py`, `control_plane_store_payloads.py`, `control_plane_operation_context.py`, `control_plane_api_models.py`, and `raes_cli/processor.py` reuse the canonical idempotent credential projection. Keep accepted evidence and typed provenance round-trippable through existing snapshot serialization, local atomic writes and recovery. These downstream projections do not sanitize arbitrary rejected evidence for the runtime. No new store, sidecar or migration is expected. |
| Host/process boundary | This fix belongs to portable result admission and needs no process invocation or secret resolution. Existing `raes_reference_backend/drivers/oci.py`, `oci_observation.py` and `oci_image_trust.py` retain fixed argv, injected runner, bounded execution and trust/readback ownership. Do not put credentials in argv, shell commands, environment dumps, temporary files or logs to obtain satisfaction evidence. |
| Contract and workflow governance | Preserve ADR-009/061 schema authority and ADR-098 artifact semantics; no published schema change is expected. Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py` and canonical nox lanes. Requirement-free work must not fabricate a requirement UID. Local feedback stays targeted; CI owns full policy/test/integration/fuzz/completion suites. |

An invalid successful claim must still return `success=false`, the isolated
immediate predecessor, empty changed addresses/details and no candidate success
provenance, as specified in
[backend result admission](../../specs/formal/runtime-contracts/backend-result-admission.md).
The in-memory manager, durable control plane and recovery must agree. This is
state refusal, not an infrastructure rollback guarantee. Failed native readback
may return authorized cleanup inventory; preserve its existing closed projection
without presenting it as successful artifact realization. Do not overwrite a
sanitization refusal with a secondary comparison of the rejected candidate.

## Extensibility and verification guardrails

The seam is the existing admitted realization context: canonical address,
requirement kind, closed evidence projector and native semantic validator.
Scope evidence permission using that authority, including supplemental artifact
requirements; a global list of field names cannot authorize a disclosure.
For another evidence field, extend its owning existing concern/contract seam
with a closed projector and validator. Do not build a new general plugin
registry or hard-code backend names, image types, requirement IDs or exact-only
exceptions in credential logic. Exact/constrained/open artifact mechanisms
continue through their common satisfaction model and evaluator.

Reuse `test_issue_673_account_credential_bindings.py` for credential closure,
diagnostic replacement, details/metadata refusal and identity collisions;
`test_artifact_requirement_satisfaction.py` for artifact/trust rejection and
provenance round trips; and `test_issue_1204_prepared_credentials.py` for admitted
completion and credential non-substitution. The issue's regression must cross
the backend apply/finalization boundary with both credential bindings and exact
artifact demand, not merely exercise a sanitizer helper. It must demonstrate
accepted evidence survives and canonical credential values/references do not.

Negative coverage must distinguish unauthorized payload material from the
permitted canonical echo: copied fixture/reference values in extra or nested
fields, unknown keys inside evidence, wrong/absent requirement or address,
wrong digest/backend/route and unverified refs must not gain publication.
Retain details and diagnostic-prose non-disclosure, independent-identity
collision behavior, trusted-baseline refusal and non-credential behavior.
Exercise relevant transition/preparation and durable serialization cases when
those paths change. Do not add tests that only duplicate the projection code.

## Non-goals

No backend/env-pack workaround, credential resolver/store, native credential
installation change, participant disclosure rule, new schema/DTO, new API/auth
mode, artifact acquisition/build policy, transport protocol, persistence
service, logging framework or runtime lifecycle redesign. No relaxation of
exactness, trust or credential egress, and no automatic replay of apply. This
preflight changes guidance only; code, fixtures and tests belong to the later
implementation.
