# Issue #1069 — RUN-320 runtime orchestration preflight

Date: 2026-09-20. Inspection baseline: `e4136a6e`. Scope: architecture guidance
before implementation, not an implementation plan.

## Authority and present boundary

[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md),
[SEM-235](../../specs/formal/participant-semantics/modular-participant-control.md),
and [PC-01–PC-15](../research/modular-participant-control/composition.md) already
settle the architecture. API-424 is published in `raes_contracts` and
`raes_backend_protocols`: its closed selection, context, result, composition,
effect, realization, trusted-context validation, provider protocol and
API-407 support adapter are the portable boundary. No new ADR, policy algebra,
provider interface, effect vocabulary or contract family is needed for
RUN-320.

RUN-320 owns reference-runtime invocation, exact-cut composition, durable
admission and bounded triggered execution. It replaces the undeclared
`getattr(..., "resolve_flow_sink_decision")` path in
`raes_runtime/participant_flow_sink.py` and the matching method-presence probe
in `control_plane_composition.py::require_final_sink_flow_control_configuration`;
it does not relax the SEM-233 final sink or API-423 crossing gates. Any
temporary SEM-233 compatibility is an explicitly selected adapter into
API-424, never method-presence discovery at composition or invocation time.
`ParticipantControlProvider` is deliberately not runtime-checkable: a
callable `resolve` method proves neither installation, support nor authority.

The following similarly named incumbents must remain distinct:

- API-404 `ControlPlaneProfile` P0/P1/P2/P3 is the runtime transport and
  durability posture; API-424 participant-control profiles select mechanism
  semantics. Neither profile family selects, proves or upgrades the other.
- API-409/RUN-310 `participant_control_history` records supervisory actions;
  it is not modular provider state, contribution or effect history.
- SEM-234 `MixedRuntimeBinding` coordinates backend allocation/phases; it is a
  construction pattern, not a participant-control composition model.
- SDL `Orchestrator` and `RuntimeSnapshot.orchestration_history` own workflow
  execution; RUN-320 must not retag their records.
- API-424 eligibility is not API-423 permission, a committed intent is not a
  dispatch, dispatch is not observed application, and a realization claim is
  not external certainty.

Positive RUN-320/API-404 evidence must name an explicitly selected operating
profile. A legacy control plane with `profile=None` may retain compatibility
behavior but contributes no profile guarantee; provider installation or an
API-424 mechanism profile must never auto-select P0–P3.

## Runtime design guardrails

### Trusted binding and invocation

Add one immutable, operator/backend-constructed runtime binding through the
typed `ControlPlaneOptions`/`ControlPlaneConfiguration` seam, following the
validation and `MappingProxyType` treatment of `MixedRuntimeBinding`. It binds
the exact admitted selection/apparatus and trusted context/support resolvers to
a provider map whose keys exactly equal the selected mechanism instance IDs.
Provider objects never come from a scenario field, participant value, generic
options map, import path, module name, URL, command, environment expression or
filesystem search. `RuntimeTarget` remains a component/effect boundary, not a
plugin registry.

Invoke every provider only through
`raes_backend_protocols.protocols.ParticipantControlProvider.resolve`, under
the shared `RuntimeMutationAuthority` and `external_control_plane_call()`
re-entry fence. Supply a detached, revalidated `ParticipantControlRequestModel`
for one exact K. Revalidate returned models from their portable projection so
`model_construct`, mutable aliases or unchecked subclasses cannot bypass the
contracts. Convert exception, malformed return, missing slot and unsupported
support into the corresponding explicit unresolved result/support record;
never omit a contributor or permit on failure.

Construct and validate the complete `ParticipantControlEvaluationModel` with
API-424-owned composition logic and
`validate_participant_control_resolved_context()`. Its non-wire context must be
resolved independently from trusted runtime owners: admitted request, safe
references, exact installed bindings, effective support, result identity,
authorized effects, incumbent gate evidence, crossing/control/flow/inject
records and owner receipts. Provider output cannot certify any of those facts.
Do not copy slot, dependency, blocker, support, effect-conflict, digest or
trusted-context logic into runtime branches.

There is one current API-surface gap to close at the existing contract owner:
`participant_control_composition.py` and
`participant_control_effect_composition.py` validate a caller-constructed
composition, but expose no public pure operation that derives the canonical
`ControlCompositionModel` from results, effective support and incumbent-gate
facts. RUN-320 must expose and reuse that API-424-owned operation (or an
equivalent public constructor over the same logic) before runtime orchestration
consumes it. It must not independently reproduce private
`_mandatory_blockers`, effect-conflict accounting or disposition mapping in
`raes_runtime`. This closes a missing public seam; it does not authorize a new
schema, policy algebra or orchestration facade.

API-424 does not expose an open cross-provider rule interpreter. If an
admitted profile or dependency cannot be expressed by the published request,
slots and result contracts, record unsupported and perform no dispatch; amend
API-424 under its owner rather than pass provider-private dependencies through
metadata.

The provider is an operator-installed pure resolver, not an authenticated
caller, controller, declassifier or effect principal. Every triggered child
operation retains the originating `OperationAdmissionContext` actor and
authorization scopes, records `parent_operation_id`, and then passes the
ordinary owner authorization again. Never call `operation_admission_context()`
with an absent identity merely because execution is internal: that incumbent
fallback means trusted embedder and would launder a served caller into process
authority. Provider-declared authority refs remain claims checked by the
trusted context; they do not replace the operation actor.

`external_control_plane_call()` is a re-entry fence, not a sandbox or timeout.
A provider must perform no world effect, spawn no mutation path and return a
finite result. Attempt/expiry bounds do not prove wall-clock liveness; a stuck
in-process provider can stall the single mutation authority, so RUN-320 makes
no provider-availability or cancellation claim and must not hide this with an
unbounded worker/thread executor.

### One exact cut and one durable authority

Build K from the incumbent crossing/control owners: admitted apparatus and
profile, participant/episode, subject/crossing/direction, sink/audience/
destination, controller/authority, policy revision, input and provider-state
references, governed time/order, trigger root/depth/firings/attempt, and every
relevant history head. `prepare_participant_crossing()`,
`expected_participant_history_heads()` and the API-424 request validator own
those coordinates. A retry after any head, policy, selection, support or state
change resolves a fresh K; an old eligible result is never reused.

Use `RuntimeSnapshot`, `ControlPlaneOperationRecord`, `AuditEvent` and
`AtomicControlPlaneStore.commit_participant_transition()` as the only state
authority. The atomic write set contains the validated evaluation, all
contributions, proposed provider-state transition, logical effect claims,
root/depth/firing/attempt consumption, the effective decision and typed effect
intents before any backend call or participant disclosure. A stale expected
head, idempotency conflict, store error or uncertain commit means no dispatch.
P0 may make only its documented process-lifetime claim; restart/recovery
evidence uses the P1 local durable store, and P2 remains the authenticated HTTP
composition over that P1 core. RUN-320 does not make the unavailable P3
multi-owner/coordination profile real. Do not weaken
`adapt_control_plane_store()` capability admission or emulate atomicity in the
orchestrator.

Modular state and append-only history require first-class typed snapshot
carriers with fold/prefix and expected-head validation. They must be carried
through all exhaustive snapshot surfaces: `RuntimeSnapshot`,
`_snapshot_updates.py`, the runtime-snapshot contract/schema and publication
entry, `control_plane_store_snapshots.py`, `control_plane_store_history.py`,
`control_plane_store_paths.py` transition accounting,
`backend_snapshot_contracts.py`, `participant_result_contracts.py`,
`participant_crossing_state_cut.py`, backend transition validation,
`control_plane_api_models.py`, operational summaries, compatibility fixtures,
concurrency/restart checks, and both memory and local stores. Do not store authority in
`RuntimeSnapshot.metadata`, audit details, operation `result_payload`, a
private cache or a new trigger journal. Backend results must not be allowed to
rewrite runtime-owned modular carriers.

Treat persisted-shape evolution as an explicit compatibility boundary. Follow
`control_plane_store_record_migration.py` and the
`participant_crossing_history_presence()` precedent when distinguishing a
legacy snapshot that predates a carrier from a present empty carrier. Absence
may establish only that no modular-control history is available; it must not
synthesize an empty authoritative history, erase a retained head or permit a
resume. Once modular state or claims exist, missing or malformed carriers fail
closed. An unprofiled legacy control plane may retain its old behavior but
cannot acquire a RUN-320 conformance or restart-recovery claim implicitly.

Evaluations and later realization facts are immutable. Do not mutate an
evaluation's empty/pending realization list after dispatch; append separately
identified transitions that fold to current provider/effect state and retain
the original causal references. Operation lifecycle records remain the common
administrative index, but are not a substitute for required portable
contribution, state, budget and realization history.

### Admission, effect ownership and recovery

Preserve the incumbent order:

`resolve -> compose -> admit -> commit intent -> dispatch -> record outcome`

Immediately before dispatch, recheck the commit-bound generation and all
current authority, capability, policy, destination and history coordinates.
`RuntimeMutationAuthority` provides the in-process logical permit. The selected
control-plane profile supplies only its declared store fence: P0 has revision
CAS and no process-loss/owner-lease claim; P1/P2 add the local durable owner
lease, CAS and startup reconciliation. Expected heads bind the affected
participant histories in either case. Do not introduce a check-then-call gap or
imply P3/multi-owner support. If an asynchronous path cannot retain its
declared fence, it must re-enter final admission at a fresh cut.

Translate each closed API-424 effect through its existing owner, with no
backend-name or provider-name branch:

| Effect concern | Required incumbent owner |
| --- | --- |
| Permit, deny and withhold | API-423 crossing mediation, SEM-233 final-sink validation and RUN-319 commit-before-effect |
| Transform, mask and route | Fresh API-423/SEM-226 carrier identity, lineage, visibility and ordinary re-admission |
| Inject | DSL-111/142 authored identity/binding plus API-423 delivery/disclosure and API-409 when it changes control |
| Delay | API-421/RUN-308 governed clock, expiry and scheduler ownership |
| Review, handoff, interrupt and shutdown | RUN-310/API-409 participant, episode and workflow lifecycle owners |
| Audit | Existing `AuditEvent`/evidence and audience projection; never a second output channel |

The current `ParticipantInjectDelivery` surface is an authored/compiled
declaration and API-424 validation authority, not a runtime executor or an
"applied" receipt. The implementation must either route an inject through the
ordinary incumbent crossing/delivery owner or record unsupported with zero
dispatch. The same rule applies to every effect whose owner has no realizable
path: do not add a universal callback/executor bag to conceal the gap.

A required predecessor commits a withhold of the parent, runs as a separately
admitted operation, and causes fresh parent evaluation after satisfaction. A
subsequent effect is an independent operation whose failure cannot rewrite an
already applied parent. Use the owning operation kind where one exists; if a
new closed kind is genuinely required, update operation serialization,
recovery and all exhaustive lifecycle handling rather than treating an
arbitrary string as a kind.

Use the ADR-104 recovery distinction already implemented by
`control_plane_recovery.py`: intent/accepted, dispatch/running, observed
application, failed and externally indeterminate. A committed-but-undispatched
effect may resume only with durable proof dispatch never began. Once dispatch
may have begun, use the existing `RecoveryObserver` seam when supported;
otherwise retain indeterminate and require governed resolution. Never blind
retry a non-idempotent effect or claim distributed/external exactly-once.

The logical effect key is exactly `(run, trigger root occurrence, rule
id/revision, effect slot, admitted firing epoch)`. It is distinct from an
operation ID, transport `Idempotency-Key`, retry number, current-cut digest and
backend request ID. Allocate the fresh effect identity once per logical key,
retain it across retry/replay, return the prior receipt for identical canonical
content, and conflict on different content. A governed new trigger event—not
a retry—creates a firing epoch.

Depth, total effects per root, fan-out, per-rule firings, resolution attempts,
expiry and retry limits are durable state. An admitted effect consumes root and
per-rule budget even when dispatch later fails. Reset, handoff, transformed
identity, retry and restart do not erase the causal root or replenish budgets.
Diagnostics, audit and recovery observations cannot recursively trigger
effects unless a separately admitted rule explicitly names them and remains
within all bounds.

## Cross-cutting incumbents and security layers

| Layer | Required reuse and satisfaction |
| --- | --- |
| Portable shape/parser | Reuse API-424 `ContractModel` variants, strict/frozen field choices, `parse_bounded_json_object`, the published schemas and `parse_participant_control_evaluation()`. No parallel DTO/schema or unbounded JSON/file read. Direct Python values still require reconstruction and finite/bounded validation. |
| Admission and semantic validation | Reuse API-424 composition/effect validators and `ParticipantControlValidationContext`; compose API-409, API-423, SEM-233, support and inject owning validators. Shape validity never substitutes for freshness, authority or effect admission. |
| Package and host boundary | Keep portable models/validation in `raes_contracts`, the public provider protocol and support adapter in `raes_backend_protocols`, and invocation/durability in `raes_runtime`, per `tools/policy/adr_policy.yaml`. Runtime must not import `raes_conformance`; conformance may consume the runtime, never become runtime authority. Reuse `registry.py`/`registry_target_validation.py` and the exact backend manifest for target capability admission, but keep provider installation in the immutable runtime binding rather than turning `RuntimeTarget` into discovery. |
| Authentication/authorization | No new route is required. If an existing route is touched, retain `ControlPlaneSecurityConfig.strict_defaults()`, `_ControlPlaneApiAuth`, constant-time bearer-token comparison or explicitly enabled trusted-proxy identity verification, role/target binding, participant/controller/audience subject bindings and `RequestSizeLimitMiddleware`. Authentication is an adapter concern; authenticated operator status is not participant disclosure or declassification authority. |
| Configuration and secrets | Extend only typed `ControlPlaneOptions`/`ControlPlaneConfiguration`; reject unknown options and validate exact run/selection binding. Add no provider env/config bag, secret loader or portable credential. Carry only owner-approved safe refs: prompts, raw payloads, private provider state, policy bodies, tokens and credentials are excluded, and hashing a secret is not redaction. Existing `RuntimeEnvironmentVariable` and `enforce_observed_value_redaction()` remain mandatory if a future owner legitimately introduces environment binding. |
| OS/process exposure | RUN-320 needs no subprocess, dynamic import, shell, socket, host path, temporary executable or command-line option. Provider instances are injected in-process by the operator/backend. Never put provider input, credentials or governed values in argv, environment, filenames, stdout/stderr or shell interpolation. Provider/host integrity outside the declared experimental world remains a backend concern. |
| Concurrency and re-entry | Reuse `RuntimeMutationAuthority`, `control_plane_mutation()`, `external_control_plane_call()`, store ownership lease/CAS, scoped idempotency claims and expected history heads. No participant-local second lock, trigger mutex or provider callback re-entry into mutation. |
| Persistence and recovery | Reuse ADR-104, `ControlPlaneStore`/`AtomicControlPlaneStore`, `adapt_control_plane_store()`, `commit_participant_transition()`, the P0/P1/P2 capability declarations, operation lifecycle, memory/local codecs, startup reconciliation and `RecoveryObserver`. Snapshot, operation and audit changes share the existing atomic transaction; no second repository or recovery state machine. P0 evidence is process-local; only P1/P2 may claim durable restart recovery, and P3 remains unavailable. |
| Effect/backend result boundary | Route an admitted effect through its incumbent owner and the existing `backend_calls.py` input isolation, `backend_input_contracts.py` bounds, `backend_apply_results.py` finalization, `backend_snapshot_contracts.py` carrier ownership and `participant_result_contracts.py` append-only checks where backend work is involved. Extend those exhaustive carrier/transition tables for modular state. A backend result cannot author, erase or rewrite runtime-owned evaluations, claims, budgets, state proposals or realizations; invalid output becomes the existing value-independent failed `ApplyResult`. |
| Errors, audit and diagnostics | Catch provider/resolver/validation exceptions at the boundary and construct stable, bounded, value-independent `Diagnostic` messages. `portable_diagnostic_payload()` validates shape but does not redact. Preserve the coarse envelopes in `control_plane_api/_responses.py`, `_operation_routes.py` and `_participant_routes.py`. Reuse `AuditEvent` plus `require_audit_event_fields()`; any new action needs an explicit bounded detail-key/value allowlist, never an arbitrary details dump. Never expose exception text/class, Pydantic input, repr, unknown key, traceback or provider-chosen address. No new exception hierarchy, logger or audit channel. |
| Disclosure and observability | Apply SEM-220/226/230 projection and the existing `x-raes-plane` classification to decisions, reasons, evidence, review/withhold existence and timing—not only payload values. Administrative snapshot visibility is not participant delivery. Logs and audit records are not automatic experiment evidence or disclosure authority. |
| Workflow/publication | Follow `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/requirement_order.yaml`, existing nox/policy checks and `RAES_REQUIREMENT_UID=RUN-320`. The phase graph already defines `modular-control-runtime` after `modular-control-contracts`, but `ownership:` currently has no `modular-control-runtime` entry; implementation must add exact owned paths instead of borrowing broad `semantics-expansion`, `mixed-participant-runtime` or `participant-model` ownership. Any snapshot schema edit requires its per-contract publication entry/content hash, compatibility fixtures and exact `schema_bundle()` parity. Do not add an issue-local runner or edit the changelog/version. |

The canonical implementation precedents are `MixedRuntimeBinding` for exact
immutable construction, `participant_crossing_mediation.py` and
`participant_flow_sink.py` for exact-cut owner validation,
`participant_crossing_boundary.py::_authorize_action_effect` for atomic
authorization before backend work, `participant_crossing_egress.py` for
commit-before-serialization, `control_plane_store_*` for atomic durability,
`mixed_runtime_dispatch.py` for write-ahead dispatch evidence, and
`control_plane_recovery.py` for external uncertainty. Reuse
`raes_backend_protocols/participant_control_admission.py` for the API-407
manifest-support join and `control_plane_audit.py` for bounded audit content.
Reuse these boundaries, not their domain names or record types.

## Extensibility seam

The sole extension seam is the immutable runtime binding from an admitted,
revisioned `ParticipantControlSelectionModel` to exact operator-created
`ParticipantControlProvider` instances plus trusted owner resolvers. The
selection already parameterizes profile/mechanism identity, applicability,
roles, typed slots and dependencies, state/memory scope, protocol/support,
authority and finite bounds. Effect realization dispatches by the closed typed
target variant to an owning RAES service, not by backend/provider name.

This permits another conformant provider or another already-published effect
owner without editing the composition algorithm. A new semantic domain,
protocol revision or effect kind requires its own governed contract/semantic
revision and owner mapping; it must not arrive through `metadata`, an enum
fallback, a callback registry or a universal policy interpreter.

## Evidence gate for the implementation

Exercise the real `RuntimeControlPlane`, provider binding, crossing boundary,
store and effect owner—not only API-424 model validators. Reuse the test
patterns in `test_api_424_*`, `test_run_319_participant_flow_policy.py`,
`test_issue_1003_final_sink_flow_enforcement.py`,
`test_issue_1092_control_plane_crash_consistency.py`,
`test_issue_1181_unified_control_plane_mutations.py` and
`test_issue_1186_control_plane_recovery_operations.py`.

Evidence must include multiple providers and profiles with permuted provider
return order; deterministic, advisory, permissive, deny, transform, conflict,
IFC-driven inject and one non-inject effect; and instrumented zero-call/zero-
disclosure assertions for missing support, weakening, stale state, malformed or
failed resolution, conflict, exhausted bounds, denied owner admission and
failed commit. Both stores must preserve identical contribution, state,
logical-key, budget, dispatch and realization semantics during their supported
lifetimes and against concurrent stale writers. Only the P1/P2 local durable
store supports process-restart and retained-deduplication evidence; P0 must
instead prove its process-loss nonclaims. Cover crashes before dispatch, after
dispatch may have begun and after observed application; exact-key retry versus
changed-content conflict; predecessor versus subsequent failure; provider
re-entry; actor laundering; and diagnostic/audit/error-envelope leakage. A
bounded design witness or a mocked composition unit test is not runtime
evidence.

## Non-goals and anti-patterns

- Do not ship a production IFC engine, monitor, policy product, model wrapper,
  gateway, provider registry/plugin host, scheduler, backend adapter or
  scenario code loader.
- Do not claim backend/provider protection from out-of-world interference,
  universal noninterference, provider honesty, backend equivalence, liveness,
  distributed atomicity or exactly-once external effects.
- Do not disable or bypass API-409/API-423/SEM-233 admission, final-sink
  enforcement, fresh identity, visibility/projection, target capability or
  ordinary downstream validation because API-424 composition was eligible.
- Do not collapse profile, mechanism, provider, result slot, decision, effect
  intent, logical effect key, operation, dispatch, delivery, observation or
  realization into one identifier/status/DTO.
- Do not resolve conflict or missing mandatory support by registration order,
  provider order, lexical order, last writer wins, specificity, advice or a
  permissive default. Unknown, malformed, weakened without acceptance, stale,
  exhausted and failed all block prohibited dispatch.
- Do not mutate histories, replace contribution records, erase provider state
  or causal budgets, or use snapshot metadata/audit/logs as operational state.
- Do not duplicate API-424 schemas/composition, API-409 control, API-423
  crossing, operation/idempotency, store/recovery, exception, diagnostic,
  audit, authentication or configuration logic behind a new orchestrator
  facade.
- Do not leak governed values, rejected inputs, provider errors, credentials,
  private state or policy content through errors, logs, audit, digests,
  examples, environment, argv, filenames or timing without its owning
  projection and disclosure authority.
- Do not treat a provider as the caller, synthesize trusted-embedder identity
  for a served trigger, or drop parent-operation and authorization-scope
  lineage on a child effect.
- Do not claim P0 restart durability, infer P2 from HTTP availability, expose
  P3, or use an API-424 mechanism profile as an API-404 operating profile.
