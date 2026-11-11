# Issue 1439: autonomous participant initialization admission

Reviewed 2026-10-27 at `f7e5f49a`. Non-normative architecture guidance.
The supplied issue #1439 is the delivery contract; this run has no formal
requirement. This note does not change that contract or prescribe an
implementation sequence.

## Boundary decision

Use `raes_runtime.backend_calls._call_backend_apply` around the native
`participant_runtime.initialize` invocation in
`participant_scheduler_initialization._ensure_participant_episode`. Build the
existing `ParticipantEpisodeInitializeRequest` once and derive
`realization=participant_effect_authority(request, snapshot)` from that same
request and immediate predecessor. Supply the predecessor as both the native
snapshot argument and the gate's `snapshot` parameter. Use a stable canonical
diagnostic address for initialization; the request's participant address, not
that diagnostic label, defines the authority target.

This reuses [runtime result admission](../../specs/formal/runtime-contracts/backend-result-admission.md),
made normative by [ADR-105](adrs/adr-105-recursive-partial-description-semantics.md).
No new ADR is needed. The gate owns argument/result isolation, bounded shape
admission, effect authority, transition accounting and refusal diagnostics.
The scheduler owns autonomous state, service state and budget composition after
an admitted episode result. Gating the complete scheduler result would confuse
these boundaries. Retain the existing already-initialized short circuit.

The current control-plane precedent includes
`participant_control_episode_admission.execute_participant_policy_call` and
`control_plane_participant_apply.apply_authorized_participant_action` (also
exported through `control_plane_execution`). Reuse their underlying gate and
authority helper; do not import their durable authorization workflow into the
scheduler. `participant_execution_control_boundary` uses the same boundary.

## Cross-cutting layers and canonical owners

Paths below are relative to `implementations/python/packages/` unless stated.

| Layer | Existing owner and required behavior |
| --- | --- |
| Source and policy admission | `raes.parser.parse_sdl`, semantic validation, `raes_processor.compiler`, planner admission and `raes_backend_protocols.capability_admission` already resolve autonomous policies, canonical participant addresses, clock bindings and supported features. Consume their admitted identities; add no YAML input, feature flag or parallel policy validator. |
| Request and config shapes | Keep `raes_contracts.participant_episode.ParticipantEpisodeInitializeRequest`, `runtime_state.ApplyResult` and `RuntimeSnapshot`. These internal dataclasses do not replace boundary validation. Closed published `ContractModel` DTOs, manifest/profile checks and environment-binding shapes remain unchanged; no new schema, environment binding, backend setting or schema publication is required. |
| Input and result limits | `_call_backend_apply` uses `backend_input_contracts.backend_input_violation` before isolation. `backend_call_contracts` and `backend_snapshot_contracts` bound and validate returned snapshots, diagnostics, details and changed addresses before acceptance. Preserve their canonical-address checks and portable value/work limits; do not copy or serialize an unchecked candidate in a new wrapper. |
| State authority | `participant_effect_authority` derives participant ownership and target scope from the request. For initialization, resource targets are empty. `backend_effect_transitions` and the exhaustive `SNAPSHOT_CARRIER_OWNERS` / `SNAPSHOT_VALUE_OWNERS` tables reject resource deletion, unrelated participant changes, clock changes, runtime metadata and provenance changes. Participant ownership is not authority over every participant or over every carrier sharing an address. Do not attach the enclosing provisioning plan or widen the target set. |
| Native state meaning | `_finalize_backend_apply` retains participant episode, behavior, shared-state, control, crossing and information-state validators, append-only history checks, shared-time transitions, and workflow/evaluation/proposition checks. A well-shaped result with valid episode history can still violate effect authority; both layers are required. |
| Authentication and authorization | This is an in-process manager call under already-admitted execution policy. It creates no HTTP principal or endpoint. Existing HTTP paths retain `ControlPlaneSecurityConfig.strict_defaults`, route authority/authentication, `RequestSizeLimitMiddleware`, closed request models, mutation authority, durable operation admission and terminal commit. The result gate neither authenticates a caller nor replaces controller-policy admission. |
| Secrets and host exposure | Initialization adds no credential resolution, file access, process invocation, argv, environment, socket, port or native driver command. Preserve typed `secret_references` and account credential projections. Initialization has no provisioning plan, so plan-specific credential sanitization is not a reason to pass one in or a guarantee about arbitrary result details. Do not copy snapshot values, credentials or backend exception text into diagnostics/logs. |
| Errors and observability | Reuse `backend_result_diagnostics`, `Diagnostic` and existing apply aggregation. Invalid results and backend `TypeError`/`ValueError` become `runtime.backend-contract-invalid`; other backend exceptions become the existing generic `runtime.backend-call-failed`. Refusal discards candidate details and changes. Existing HTTP handlers in `control_plane_api/_operation_routes.py` keep generic 422/500 responses and stable audit reasons. Add no exception hierarchy, candidate dump, logger or separate audit stream. |
| Publication and persistence | `RuntimeParticipantExecutionMixin._apply_participant_execution_phase` already records failure through `RuntimeManager._record_phase_result` / `_fail_apply_state`. Persist only accepted state using existing snapshot codecs (`control_plane_store_snapshots`), autonomous-state validation and revision-checked store commits where a control plane owns persistence. Keep account payloads value-free. No scheduler sidecar, direct store write, store migration or new transaction is needed. |
| Repository and verification | Follow `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml` package boundaries and `tools/verification_plan.py`. Imports stay within `raes_runtime` and its allowed dependencies. Use the existing requirement-free workflow resolution in `tools/nox_support/runner.py`; do not invent a requirement UID. Local feedback uses explicit test modules/cases or `verify-fast-feedback`; full suites remain CI-only. |

## Gotchas and extension seams

- Preserve the **immediate call predecessor**, including provisioning/time
  work and any earlier accepted initialization. An invalid proposal returns
  failure with `runtime.backend-contract-invalid`, no candidate details and no
  candidate changed addresses. Manager-level changes from earlier phases can
  remain. Do not restore the pre-apply snapshot or erase accepted resources.
- With multiple participants/policies, the predecessor can already contain
  earlier episode/scheduler state. The existing scheduler returns a failing
  child result without merging its accumulated change list. A per-call empty
  change list therefore does not establish batch atomicity or complete batch
  accounting. Do not silently expand this fix into that separate concern.
- Default `_BackendCallContext` is sufficient: no resolver or service
  collaborator is needed. `BaseParticipantRuntime.initialize` writes episode
  results/history only. The gate supplies trusted predecessor information-state
  history, so existing records survive without a resolver; new records still
  require contextual validation and fail closed without one. A future justified
  producer must receive the existing
  `_BackendCallContext.information_state_context_resolver` through its owning
  boundary, rather than weakening the validator or adding a global resolver.
- The authority extension seam is `participant_effect_authority` plus the
  existing `_RealizationApplyContext` owner/target fields. Another lifecycle
  call must derive authority from its admitted request and trusted scope there,
  rather than duplicating carrier lists or branching on backend names. The
  helper defines participant effects, not a new initialize-only allowlist.
- Argument detachment prevents writes reaching accepted state. It does not
  prohibit a backend from mutating its private copy; a mutation included in its
  returned proposal is then subject to admission. Result detachment also prevents
  later backend-held references from mutating accepted state. Copying only the
  input, checking only `success`, or filtering entries after acceptance is
  insufficient.
- Rejection does not undo backend object caches or native effects. Preserve
  existing failure/recovery semantics; do not automatically retry initialization
  or claim infrastructure rollback. Keep the driver stopped on phase failure.
- Leave native action admission/binding on their existing isolated arguments
  and `autonomous_action_result_violation` path. Keep coordinated reset inside
  the time-control gate with its injected `service_dependencies`; manager clock
  synchronization already uses `reset_participants=False`.

## Acceptance evidence and scope

The issue-specific regression belongs at the manager/scheduler path using
`test_dsl_437_benign_participant_execution` fixtures, alongside an honest-runtime
control. Both supplied mutations must fail after the fix and reproduce on the
unfixed code. Assert preservation of accepted entry identities/content and
metadata, not just a hard-coded entry count or returned `success`. Check both
the apply result and `manager.snapshot`, with no rejected candidate details.

Reuse `test_issue_1204_targeted_effects`, `test_issue_1204_result_owners`,
`test_issue_1204_result_shapes`, `test_issue_1204_input_bounds` and participant
history tests for generic gate behavior rather than duplicating those validators
or their entire test matrices. The issue's explicit autonomous/temporal,
execution-control, budget and concurrency modules remain compatibility
obligations; integration selection must name those modules and explicitly use
`-m integration` because pytest defaults exclude it.

Non-goals: changing SDL, protocols, DTOs, published schemas, participant episode
identity/lifecycle, scheduler policy/state formats, budgets, clock behavior,
control-plane authorization/persistence, backend selection, batch atomicity,
backend containment or infrastructure rollback. This is one missing invocation
boundary, not a scheduler redesign or a second admission framework.
