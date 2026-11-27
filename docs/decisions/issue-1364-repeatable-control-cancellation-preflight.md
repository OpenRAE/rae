# Issue #1364 — Repeatable control and evidenced cancellation

Architecture preflight for **RUN-310**, 2026-10-16, inspected at `e5cb3497`.
[Issue #1364](https://github.com/OpenRAE/rae/issues/1364) supplies the delivery
scope; the supplied RUN-310 amendment governs lifecycle semantics. Prerequisites
#1363 and #1362 are present, but neither establishes live rev1 control support.
This note is guidance only, not an implementation plan or a support claim.

[ADR-110](adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md),
[MC-01–MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md),
the [migration contract](../migration/reusable-mixed-control.md),
[supervision S1–S6](../../specs/formal/runtime-control-plane/supervision.md),
[backend operation supervision](../../specs/formal/runtime-contracts/backend-operation-supervision.md)
and [ADR-113](adrs/adr-113-reusable-execution-machinery.md) already decide the
architecture. Retain them and the [#1363](issue-1363-reusable-mixed-control-preflight.md)
and [#1362](issue-1362-supervised-execution-preflight.md) boundaries; no new ADR
or amendment to an accepted ADR is needed. Current source supersedes those
preflights' dated implementation-gap inventories.

Python paths below are relative to `implementations/python/packages/`.

## Concrete adoption risks

- `participant_control_mediation.py`, `participant_control_rejections.py` and
  `participant_control_occurrences.py` still replay fixed-coordinate compiled
  transitions. The compiler already supplies typed reusable policy children and
  `occurrence_policy_projection()`. Do not unroll edges, synthesize legacy
  transitions or copy the v2 fold into the runtime.
- `participant_control_targets.py` establishes historical existence, not current
  external action/attempt eligibility. `ParticipantControlOccurrenceTarget.available_at`
  establishes precedence only. Live episode, grant/revocation, target lifecycle,
  order, time and evidence must come from their owners at one fenced cut.
- `ParticipantCancellationOccurrenceV2Model` intentionally contains no outcome.
  The legacy builder's `_cancellation_effect(target_kind)` is not evidence and
  cannot implement this issue. The supervised invocation ledger already retains
  controls, acknowledgements, outcomes, one-use delivery and release commitments;
  connect those facts rather than creating another cancellation lifecycle.
- Direct control currently prepares/validates history before `_claim_record()`
  finds a retry. An exact historical retry must be resolved after current access
  authorization and before evaluation against today's state, grants or episode.
- Participant control uses ordinary mutation admission and HTTP `calls.mutate()`.
  Store claim paths also reject new claims after stop or during a supervised
  effect reservation. Merely calling `cancel_operation()` from that path can
  leave cancellation blocked behind the work it must supervise. Preserve a
  bounded supervisory route through **both** state authority and durable claim
  policy, without exempting new effects from exclusion.
- V1 assumptions extend to `raes_contracts/participant_control_history.py`,
  `contracts/realization_plans.py::RuntimeSnapshotEnvelopeModel`, target projection,
  API-423/424 control-record joins and manifest support. API-424 evaluation v2
  and API-409 occurrence v2 are independent lineages. Neither implies the
  other's adoption. Planner, runtime, constructor and mediation refusals are
  deliberate safety gates; narrow them only for a complete supported path.

## Control-state and work-outcome boundaries

Use `validate_participant_control_occurrence_context()` as the contextual
entry point and `fold_participant_control_episode_v2()` as the shared episode
state relation. The entry point additionally checks complete participant-wide
prefixes, identities, per-episode pins and cross-episode evidence reuse. Calling
the fold alone or `participant_control_history_verifiability()` alone cannot
certify an archive. The latter reports context availability, not validity.

Pin the trusted compiled policy to an admitted episode. Initialize revision zero
through the incumbent episode lifecycle with valid initial authority; only a
running episode admits fresh applications. At the commit cut instantiate actual
prior/resulting state, expected state revision, participant-wide append head,
fresh occurrence identity, exact target/proposal binding and admitted order.
Every accepted kind, including denial and same-state transitions, advances state
revision once. Rejections retain attempted coordinates and the observed cut,
advance no accepted order/state/script cursor, and never become authorizing
targets. Unsafe ingress failures stay bounded audit/operation refusals.
Finite scripts narrow the same relation, advance their cursor on acceptance
only and refuse exhaustion; they never silently become reusable policies.

Retain source-controller authority, canonical `self` resolution and handoff-only
controller changes with fresh completion evidence and independently valid
destination authority. Approval/denial resolve one live proposal revision;
direction does not approve it. New cycles use new proposal/decision identities,
not policy-edge IDs. Preserve their immutable own-revision-1 bindings;
transformed proposals retain source lineage and markings under a fresh identity.
Revalidate grant, scope, target eligibility and episode
at action admission/dispatch as well as control acceptance, so cancellation,
supersession, revocation or termination cannot leave a stale approval usable.

Retain `total-effective-order` with an admitted ordering authority. Arrival time,
lock acquisition and map order cannot arbitrate equal/ambiguous proposals. Ordered
competitors use the newly committed cut; stale requests are rejected, never
rebased. Intersect edge, finite-step, source and destination order windows with
`participant_control_validity_bounds()`. Temporal constraints additionally use
the existing shared-time clock/domain/segment/tick/microstep and admitted
mappings; order is not a tick. Missing mappings or invalid/reset segments fail
closed. Preserve shared strict count limits (1,000,000) and control-reference
limits (256 characters); exhaustion is refusal, never wrapping/truncation.
Bound rejected attempts, target/evidence resolution and accumulated history under
the admitted resource limits too. Rebuildable indexes may accelerate the owning
relation; they must not become independent authority or justify history pruning.

A successful operation recording control proves that control operation's result.
It does not prove cancellation of the target work. Keep independently retrievable
links among the accepted/rejected control occurrence, its operation/actor, the
exact target lifecycle, target operation/invocation/attempt/generations, backend
control ID/digest/disposition and validated outcome/evidence. Commit the control
fact, state/history, retry record and actor-bound audit atomically, including the
retained linkage needed to continue cancellation after a crash. External delivery
and later outcome evidence remain subsequent owner operations; never rewrite an
immutable accepted occurrence to fill in a later result.

The issue's PARTIAL terminology corresponds to the incumbent
`ParticipantCancellationEffect.PARTIAL_LIMITATION` / `partial-limitation` where
that projection applies. None of these outcomes is a new `OperationState`:

| Claim | Evidence required from the exact target's owner |
| --- | --- |
| PREVENTED | Durable cancellation/invalidation that wins before admission or one-use dispatch, with no already admitted/executing work escaping its scope; or verified absent effects plus cessation and a fence against further prohibited effects. A proposal/decision label alone proves neither. |
| PARTIAL | Verified residual effects with complete scope and native residual state, plus evidence of the achieved limitation/cessation. `CANCELLED` additionally requires the cancellation contract. An admitted-action label or accepted backend request proves no limitation. |
| TOO_LATE | Authoritative target lifecycle/settlement evidence that completion or the irreversible boundary won for the requested scope. An attempt, refusal, unsupported callback, timeout or missing acknowledgement alone cannot establish lateness. |
| Not established | Retain the request and actual disposition without fabricating any of the three claims. An executing operation may remain `RUNNING` while observation continues within budget. At terminal classification, unknown effects or unproved cessation require `INDETERMINATE` and retained exclusion. |

Serialize cancellation against the existing one-use dispatch claim. Before a
claim, prevention need not invent a target operation; an unconsumed `ACCEPTED`
invocation can become `CANCELLED`. A consumed/write-ahead `RUNNING` grant requires
evidence even if no call is believed to have occurred. Backend acceptance only
undertakes cancellation. A validated completion may still win; one terminal
commit wins and late evidence uses separately authorized linked resolution.
Fencing state publication does not prove remote cessation. Disconnect, cancelled
future, killed thread/process, scheduler counter release or restored predecessor
cannot release conflicting-effect reservations or prove rollback.

## Required cross-cutting layers

| Layer and canonical incumbents | Required satisfaction |
| --- | --- |
| Source and compiled policy: `raes/parser.py`, `_yaml_loader.py`, `_source_profile.py`, `_mapping_scopes.py`, `participant_mixed_control_policy.py`, `validator/_mixed_control_policy.py`, composition rewrites, `raes_processor/compiler/_mixed_control_policy.py` | Reuse safe bounded YAML, duplicate/normalized-key checks, instantiated-model revalidation, reference-purpose/scope validation and deterministic typed children. Preserve local edge/step IDs and canonical external identities. Resolve trusted policy from admitted compiler context, never raw `spec` dictionaries or client projections. This runtime issue needs no new authoring language. |
| Wire and in-process ingress: `ContractModel`, `ParticipantRuntimeBaseEnvelopeModel`, `participant_control_coordinates.py`, `participant_control_occurrence_v2.py::parse_participant_control_occurrence`, `raes_contracts/json_ingress.py` | Keep explicit closed lineage/form/kind dispatch and shared strict coordinates, including rejection of booleans/string integers. Reuse bounded JSON decoding with duplicate-member, depth and non-finite rejection before mapping conversion. HTTP body-size middleware and the legacy lax intent DTO alone do not satisfy rev1 ingress. Detach/revalidate nested owner/model inputs; base-model closure is not immutability. |
| Authentication and authorization: `ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, `ParticipantControlSubjectBinding`, `operation_admission_context`, `authorize_supervisor()` and worker authority | Keep sealed route roles, exact target/run and participant/controller binding, then independently check live semantic authority. Principal actor/scope must fit `OperationAdmissionContext`; binding participant addresses forbid `:` even though `ControlRef` permits it. Preserve independent authorization for the exact supervised parent, worker and every receipt/status disclosure. P0/P1 trust the embedder; constructing an identity authenticates no external caller. Do not launder a controller request through `identity=None`, a drain actor or an engine token. Invalid bearer tokens cannot fall back to proxy identity. |
| Configuration, secrets and host: `ControlPlaneOptions` / `ControlPlaneConfiguration`, `OperationSupervisionConfiguration`, `RuntimeEnvironmentVariable`, `SecretReferenceId`, `enforce_observed_value_redaction` | Use typed installed owner/provider/resolver bindings with shape checks and strict positive finite budgets/capacities. No new secret loader, environment bag, CLI, socket or subprocess is required. Any affected environment binding retains valid name, provenance/classification, literal/value-from exclusivity and redaction. Logical references never select executable code, arbitrary paths/URLs or credentials. Keep credentials/payloads out of argv, shell interpolation, snapshots, engine messages, logs and errors. TLS/proxy header stripping, process isolation and resource ownership remain host/backend responsibilities. |
| Mutation and responsiveness: `RuntimeMutationAuthority.supervision()` / `external_call()`, `SubordinateMutationGate`, HTTP `_ControlPlaneCallExecutor.control()`, `LocalExecutionAdapter` | Use the same writer and bounded separate control/store/effect capacity. No provider, evidence resolver or other extension runs under a logical state permit, subordinate lock or database transaction. Reacquire and compare the full cut after callbacks; preserve detached callback re-entry refusal. Admission, audit, provider locks/connections and store waits must also remain bounded while effects stall. Scenario pause cannot pause apparatus supervision. |
| Persistence: `RuntimeSnapshot.participant_control_history`, `participant_control_history.py`, `control_plane_store_snapshots.py`, `RuntimeDurabilityMixin`, `ControlPlaneStore.commit_control_transition` / `commit_participant_transition`, `commit_invocation_transition`, `operation_ledger_transactions.py` | Extend the incumbent lineage readers and invariant gates coherently. Preserve append-only bytes, exact history heads, snapshot CAS, immutable request commitments, actor-bound atomic commits and lost-ack readback/readiness poisoning. Cover memory, admitted local SQLite and any selected PostgreSQL store; retain private path/sidecar permissions, ownership/link checks, leases and profile/worker admission. No controller side database, metadata authority or process-lock-only ordering. |
| Backend control/evidence: `BackendOperation*Model`, `require_operation_provider()`, operation/policy admission helpers, response/history validators, `InvocationLedger`, `operation_provider_control.py`, `operation_provider_execution.py`, `OperationEvidenceResolver` | Require admitted capability and contextual willingness, exact request/control digests, binding/generation, allowed message kind, monotonic sequence and retained duplicate commitments. Authenticate, bound, scope-check and validate evidence through its installed owner; reference presence or provider shape proves no truth. Preserve native result/final-release validation and residual snapshots. No unsupported backend gains interruption guarantees. |
| Action and downstream gates: `participant_submission_options.py`, `participant_crossing_boundary.py`, `participant_flow_sink.py`, `participant_control_orchestration.py`, `participant_control_effects.py`, native `participant_scheduler_concurrent_*` owners | Preserve action binding, proposal/admission/attempt identity, execution-generation checks, native merge/history validation, exact crossing/IFC/final-sink authorization and causal budgets. Join an action/attempt to its actual execution owner before supervising it; target existence or the generic operation provider does not automatically cover native participant batches. Do not cancel unrelated peers or release their reservations. Governed ingress and API-424 effects use the same control relation. |
| Delivery and advertised support: DSL-142/API-423/424 contextual readers, `raes_contracts/manifest_authority.py`, planner/runtime `mixed_control_admission.py`, configuration and mediation gates | Admit only selected paths that can consume the exact accepted application and original policy. Delivery pins disclosure policy independently, never selects the latest event for an edge, and consumes each application/binding once. Keep unsupported joins refused. A schema registry entry or backend manifest assertion cannot bypass runtime capability admission. |
| Errors and observability: `raes/_errors.py`, `raes_contracts/diagnostics.py`, `AuditEvent`, `control_plane_api/_responses.py`, `_operation_routes.py`, `_participant_routes.py`, `_supervision_routes.py`, `control_plane_api_guards.py` | Reuse typed reasons, existing exceptions, bounded audit and stable redacted HTTP envelopes: 401/403, disclosure-safe 404, conflict 409, validation 422 and unavailable/internal 503/500. Preserve `no-store`, including retries/errors. Do not expose raw Pydantic input, exception text, model representations, tokens or evidence payloads. Diagnostic shape is not sanitization. ADR-066 keeps operational logs, participant disclosure and experiment evidence distinct; add no parallel log/error hierarchy. |
| Publication and workflow: `schema_bundle()`, `tools/generate_contract_schemas.py`, generated-schema/publication/coverage checks, `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/`, `tools/nox_support/` | Published schemas remain normative under ADR-009/061. Snapshot or consumer widening must include affected embedded definitions, `contracts/schema-publication/entries/` change summaries/content hashes and parity; keep legacy fixtures/readers and unknown-lineage refusal. Use existing policy/hygiene and targeted local feedback, with full/integration/fuzz suites in CI. Set `RAES_REQUIREMENT_UID=RUN-310` where the branch lacks a UID and retain issue/requirement traceability. Do not edit release-owned versions/changelog or add workflow machinery. |

## Replay, retries and extension seams

Preserve store-scoped `(principal, operation kind, client key)` retry identity;
participant/episode/policy/target/content belong in the commitment. Changed
content or episode under the same key conflicts. Exact authorized retries return
the retained receipt without another occurrence, interrupt, dispatch or budget.
A new cycle needs fresh operation identity, but does not automatically create a
new API-424 logical effect: retain trigger-root/rule/slot/firing-epoch claims.

Process recovery reconstructs the same episode, pinned policy, append positions,
proposal resolution, consumed dispatch/control grants and effect reservations
without backend redispatch. Episode reset/restart uses existing predecessor
linkage and fresh initial authority; pending proposals/script cursor do not
carry over and root budgets do not reset. Replay uses original policy and
retained cut/authority evidence, not today's grants/time. Missing context is
explicitly unverifiable, never a reason to substitute the latest policy.
Retain portable apparatus budget origins/consumption, not process-local monotonic
deadlines; uncertain restart continuity cannot award a fresh full budget.

The extension seam is the existing policy projection parameterized by
`episode_id` and explicit semantic/policy/form pin, composed with owner-resolved
live cut/target facts and the installed `OperationEvidenceResolver`. Retain enough
admitted compiler context and content pins to rebuild that projection after
reopening. Repeated visits change occurrence coordinates, not the policy.
Backend/target variations belong in the existing typed owner join and capability
admission, not `if target_kind` outcome inference or a new interpreter. Additional
portable projections, if necessary, evolve their owning schema under publication
policy; private trusted indexes are not a new wire contract. Keep policy,
proposal, state, append, wire, schema, store and execution generations distinct.
The configured supervision budgets/capacities remain parameters of
`OperationSupervisionConfiguration`, and provider/resolver installation remains
with `ControlPlaneConfiguration`; no per-target duplicate timers or runtime
registry is needed. A future target kind or ordering strategy must evolve its
closed vocabulary, owning relation and consumer admission together.

Required evidence builds on `test_run_310_supervisory_lifecycle.py`, the
`test_issue_1363_occurrence_v2_*` and schema/admission fixtures,
`test_issue_1362_{runtime_supervision,provider_execution,http_capacity,invocation_ledger,lost_ack,reconciliation}.py`,
and existing crossing/control durability tests. It must demonstrate real repeated
cycles, proposal concurrency/staleness, invalid validity coordinates, finite-script
exhaustion, mixed-lineage replay, process recovery versus episode restart,
cancel-before-admission/dispatch, both completion/cancel race orders, refused or
missing acknowledgements/evidence, residual effects, scoped authorization,
blocked effects with responsive control, atomic failure and exact lost-response
retry. Include ambiguous raw JSON, strict coordinate inputs, changed content under
the same retry/control identity, and unauthorized historical receipt disclosure.
Abstract folds, model-only conformance registry entries and mocked cancel
acceptance cannot establish durable fencing, backend cessation or final-sink
permission. This preflight does not run or claim those implementation tests.

## Non-goals and prohibited shortcuts

No new workflow engine, controller store, policy language, clock, generic DTO
base, exception hierarchy, outcome-inference helper or parallel validator. No
live policy/semantic upgrade within an episode, automatic legacy conversion,
historical rewrite, wildcard revisions, silent stale rebasing or edge unrolling.
Do not bypass current refusals, IFC, causal budgets or backend guarantees to make
rev1 executable. Do not conflate control acceptance, action admission, execution,
effect realization, operation cancellation, workflow cancellation, episode
termination, backend stop, verified cleanup, delivery or observation. Exactly-once
external effects, universal rollback/liveness, new deployment services/profiles
and cancellation of unrelated work are outside this issue's claims.
