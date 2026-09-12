# Issue 1181 Unified Control-Plane Mutations Preflight

Date: 2026-09-12

Issue: #1181. Parent decision: ADR-104. Work package: CP-2. Issue #1151
and the issue body are the design and delivery authority; this note narrows the
implementation boundary and does not create a second architecture or an
implementation plan.

Checkout review: the mutation authority, atomic store adapter, strict audit
codec, recovery-writer removal, and CP-2 acceptance suite already exist. Build
on those incumbents; their presence does not establish completion of API-404
or the remaining ADR-104 profile work. The handoff requirements below are
review obligations, not claims that every failure boundary is already tested.

## Decision

`RuntimeControlPlane` has one operation-family-independent, in-process mutation
authority. Every accepted call that can change the authoritative snapshot,
operation records, participant control or crossing histories, or an accepted
operation's audit outcome enters that authority before reading the state cut
from which it will act. This includes generic provisioning, teardown and
observation execution; workflow cancellation and timeout reconciliation;
pre-computed/no-op terminal operations; participant action and episode control;
participant control transitions; and governed ingress and egress crossings,
including read-shaped calls that append crossing history.

The authority is a logical exclusive permit, not a Python lock held for the
duration of a backend call. A condition or mutex may protect only permit
bookkeeping and short cache publication/reload sections; its underlying lock is
released while the permit remains logically owned. Internal delegation may
re-enter the same permit, but a backend callback may not use that re-entrancy to
start another control-plane mutation. `_operation_lock` and
`_participant_control_lock` are subordinate bookkeeping or cache guards and
must not form independent consistency domains or wrap backend work. The HTTP
`_ControlPlaneCallExecutor` remains the bounded, event-loop-safe
admission/offload owner. Its existing asynchronous reservation must await the
core authority without parking a worker thread; do not restore an independent
HTTP serialization lock around backend work.

The P1 process-lifetime `RuntimeOwnerLease` remains held. It is store ownership
admission/fencing required by ADR-104, not a per-operation critical section;
releasing it around a backend invocation would admit a second process and break
the profile. “No lock across the backend” therefore prohibits store
transactions and application/store mutex critical sections across external
code, not the already-admitted owner's lifetime lease.

An accepted operation follows one invariant:

1. Pure request, identity, target, idempotency, and locally available semantic
   checks may run before the claim.
2. The immutable `OperationAdmissionContext` and `RUNNING` record are durably
   claimed before *any* backend method, including backend `validate()`, apply,
   observation, participant execution, or stop/cleanup work.
3. External work runs with no store transaction or application/store mutex
   held. The logical mutation permit remains owned so another mutation cannot
   derive from the same state cut.
4. One store transaction validates the expected snapshot revision and any
   participant history-head preconditions, then makes the complete terminal
   cut visible: resulting snapshot/revision when applicable, terminal operation
   record, and exactly one actor-bound terminal `AuditEvent`.
5. Derived caches and the receipt are published only after the authoritative
   commit. Store state wins after every post-commit publication failure.

Backend validation remains a gate: an error diagnostic skips apply and reaches
the same operation-only terminal failure transaction; moving `validate()` after
the claim must not turn it into advisory metadata. Trusted crossing policy,
final-sink, and transformation resolvers are specified as pure/non-mutating and
may prepare a decision before a claim, but they still run outside a physical
mutex while the logical mutation permit preserves their state cut, and their
existing closed result validators remain mandatory.

Participant action ingress may retain its pre-effect transaction that binds the
crossing history, policy authorization audit, and `RUNNING` record before the
backend call. That is part of the write-ahead claim, not the terminal audit; its
history-head and snapshot-revision checks remain atomic, and the later terminal
transaction still owns the final snapshot, record, and outcome audit.

Admission denial is deliberately different: CP-1 defines it as an
`accepted=False` receipt plus the bounded denial audit and no stored operation.
The phrase “rejected records” in the parent design does not authorize a
`REJECTED` operation state or a claim/terminal lifecycle for an unaccepted
request. General authentication/read audit remains the existing append-only
operational evidence channel; it is not terminal operation audit and must not
be presented as satisfying terminal atomicity. Admission-denial,
authentication, read, and pre-routing rejection audits do not derive a mutable
state cut, so they remain on the existing independent append path rather than
waiting behind a long-running operation permit; they must not create, complete,
or duplicate an accepted operation.

## Atomic persistence boundary

`RuntimeDurabilityMixin` remains the runtime's single commit, reload, and cache
publication owner. The store terminal capability must accept the terminal
`AuditEvent` with the record and enforce, inside the same in-memory lock or
SQLite transaction, that the event's `operation_id` and identity match the
record and its immutable admission actor. `AuditEvent.allowed` continues to
mean an authorization/policy decision, not backend success; stable action,
reason, and bounded details distinguish `SUCCEEDED`, `FAILED`, `CANCELLED`, and
`INDETERMINATE` outcomes. The trusted core derives one completion timestamp for
the terminal status and terminal audit. It must not reuse a pre-backend crossing
timestamp or accept identity, outcome, or time from an HTTP route.

There are two explicit terminal commit modes:

- **Snapshot-bearing:** commit snapshot, incremented logical revision, terminal
  record, and audit. Backend results and state-changing workflow or participant
  transitions use this mode even when canonical snapshot bytes happen to be
  unchanged.
- **Operation-only:** preserve the snapshot and revision while atomically
  committing the terminal record and audit. Already-satisfied cancellation,
  timeout with no state change, and other truly pre-computed/no-op outcomes use
  this mode. Snapshot equality must never select the mode implicitly.

An exact terminal persistence retry is a no-op only when its mode, snapshot
expectation, terminal record, and terminal audit all match what is already
durable. It neither advances the revision nor appends a second terminal audit;
a partial or conflicting match fails closed.

Participant control and crossing commits keep their existing expected-head
guards in addition to snapshot revision CAS. Those are semantic history
preconditions, not another mutation authority and not substitutes for the
whole-snapshot state-cut check.

No runtime path may terminalize an operation through `save_record()` alone.
`ControlPlaneStoreCommitAdapter` has removed the ordered
`save_snapshot()`/`save_record()` fallback; do not restore it as a
mutation-capable profile. A provider lacking the complete atomic claim and
terminal capability must fail capability admission (or be explicitly outside mutable
control-plane guarantees); compatibility and consumer guidance must follow the
repository's evolution/deprecation policy rather than silently weakening CP-2.

Startup/error reconciliation would also be a terminal writer. The removed
record-only `reconcile_interrupted_records()` path must stay removed;
`control_plane_recovery.py` is a compatibility tombstone. CP-2
does not need to implement CP-3 effect classification, but it must ensure that
an uncertain commit is first read back as one authoritative cut: a complete
terminal triple may be published, while a remaining `RUNNING` operation stays
claimed for governed recovery/fail-closed handling. It must never be sealed by
a record-only write, infer backend success, or replay the backend.

## Canonical incumbents

- `RuntimeMutationAuthority`, `control_plane_mutation()`, `mutation_entry()`,
  `external_control_plane_call()`, and `SubordinateMutationGate` in
  `raes_runtime/control_plane_mutation.py` own the existing permit, admission
  probe, callback guard, and subordinate entry conventions.
- `OperationState`, `OperationKind`, `OperationAdmissionContext`, the closed
  transition matrix, terminal diagnostic helpers, and published operation
  carriers from CP-1 own lifecycle vocabulary. Do not create a parallel
  mutation state machine, rejection state, or generic public mutation DTO.
- `operation_admission_context()` owns canonical request commitments, immutable
  actor/scope/target/run binding, and credential-safe projections.
- `RuntimeDurabilityMixin`, `SnapshotState`, `SnapshotRevisionConflict`, and the
  CP-4 `expected_revision` contract own atomic commit, CAS, reload, and derived
  cache publication. Do not distribute terminal persistence among operation
  families.
- `ControlPlaneStore`, `AtomicControlPlaneStore`, and
  `ControlPlaneStoreCommitAdapter` remain the provider capability boundary.
  `InMemoryControlPlaneStore` uses its existing short `RLock` critical section;
  `LocalControlPlaneStore` uses `_transaction()` and the admitted SQLite WAL,
  synchronous, migration, and ownership rules.
- `commit_control_transition()` and `commit_participant_transition()` are the
  existing snapshot/record/audit atomicity examples. Their participant
  history-head checks remain intact while their lifecycle is routed through
  the same provider-neutral terminal capability and mutation authority rather
  than remaining family-specific persistence workflows.
- `_validate_runtime_target_shape()`, `_submitted_plan_diagnostics()`,
  `_call_backend_diagnostics()`, `_has_error_diagnostic()`,
  `_call_backend_apply()`, and the observation,
  snapshot-transition, participant state/history, realization-authority, and
  credential sanitizers remain the validation path for backend-facing work.
- `runtime_owned`, `RuntimeLifecycleMixin`, and `RuntimeOwnerLease` remain the
  public-call drain, close, poison, and process ownership boundary. The mutation
  authority composes with them; it does not replace them.
- `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig.strict_defaults()`,
  `RequestSizeLimitMiddleware`, closed FastAPI request/response models, shared
  response/error helpers, and `_ControlPlaneCallExecutor` remain the P2 auth,
  shape, event-loop isolation, and bounded-overload owners.
- `AuditEvent`, `Diagnostic`, the module logger pattern, and ADR-066 remain the
  operational audit, safe diagnostic, and logging vocabulary. Audit is not
  participant observation, durable run provenance, or tamper-evident evidence.
- `RuntimeManager` remains the deliberately direct, in-memory execution facade.
  It does not receive a `ControlPlaneStore`, persist control-plane operations,
  or share the mutation authority, and its calls retain none of the
  control-plane durability/idempotency/audit guarantees.

## Cross-cutting gates

- **Contract and persisted shape:** HTTP payloads continue through closed
  `ContractModel` carriers. Operations continue through
  `_OperationRecordModel` and the exhaustive durable snapshot codecs. The
  internal audit codec must be equally lossless and strict, reusing the closed
  model and `Rfc3339DateTimeString`: no `.get()` defaults or `str()`/`bool()`
  coercion may turn corrupt actor, operation, allowed, timestamp, action,
  target, reason, or details data into plausible provenance. This is an
  internal persistence validation rule, not a reason to publish a second audit
  schema.
- **Authentication and authorization:** P2 derives identity only through
  `_ControlPlaneApiAuth`'s constant-time bearer validation or explicitly
  enabled verified-proxy mode, then enforces exact target, role, participant,
  and operation binding before mutation or receipt disclosure. The same typed
  identity is passed into the core and frozen in
  `OperationAdmissionContext`; a route-supplied string, idempotency key,
  operation id, or prior receipt never replaces it. P0/P1 embedders must supply
  that typed actor context at their trust boundary.
- **Semantic and backend-return validation:** local target/manifest,
  base-snapshot, planner-authorization, workflow timestamp/duration, and
  participant-policy checks retain their present owners. Every backend result
  still passes `_call_backend_apply()` and its result type, snapshot transition,
  workflow/evaluation/proposition, participant history, realization, and
  credential gates before terminal commit. Revision CAS and the mutation permit
  add concurrency safety; neither duplicates semantic validation.
- **Secrets and configuration:** bearer tokens, account credentials, raw
  request bodies, paths, backend exception text, and provider-native data stay
  out of operation context, audit details, diagnostics, logs, and receipts.
  Value-free diagnostic and account-credential sanitizers remain mandatory.
  CP-2 adds no environment variable, secret resolver, configuration key, serve
  command, or process argument, so it creates no new environment or argv
  exposure surface. Existing `ControlPlaneSecurityConfig` validation remains
  the HTTP composition shape, and `require_single_worker_configuration()`
  remains the worker-count environment gate (`WEB_CONCURRENCY` and
  `UVICORN_WORKERS`); neither is a place to configure mutation semantics.
  For plans passing through CP-2, retain `control_plane_plan_diagnostics()`
  and its planner-authority, account-credential, generated-artifact,
  service-materialization, domain-topology, and observation-demand gates.
  `raes/runtime_environment.py::RuntimeEnvironmentVariable` owns environment
  value/value-source exclusions and observed-value redaction;
  `raes_processor/planner/stateful_admission.py` owns generated-artifact
  admission. These are scenario payload contracts, not service credential
  configuration. Preserve them through the existing carriers; do not flatten
  bindings into strings, resolve secrets into durable context, or introduce a
  token-bearing subprocess command or argv. Account sanitization remains in
  `backend_account_credentials.py` and canonical
  `raes_contracts.account_credentials`.
- **Persistence and OS exposure:** the SQLite provider retains owner-only
  directory/database permissions, symlink/non-regular-file rejection,
  identity-pinned opens, WAL and full-synchronous admission, integrity and
  migration checks, and the runtime owner lease. No database path, SQL/WAL
  coordinate, lease identity, transaction detail, or provider exception enters
  an API error, audit record, diagnostic, or log.
- **Error envelopes:** reuse `Diagnostic`, `SnapshotRevisionConflict`, lifecycle
  errors, and the shared HTTP `409`, `422`, `500`, and bounded-queue `503`
  behavior. Add no family-specific exception hierarchy or per-route conflict
  vocabulary: the API boundary should map core outcomes once. New
  store/authority failures must map to stable, coarse messages rather than
  `str(exception)`; backend/provider text and expected/current internal values
  remain redacted. A caller disconnect or timeout never reports or records that
  the worker or backend effect was cancelled. In particular, the current
  per-route `detail=str(exc)` conversions are not safe templates for this
  path. `_resynchronize_after_store_error()` now uses a constant safe note;
  preserve it. The redacted handlers in `control_plane_api/_operation_routes.py`
  must still produce their coarse envelope if their secondary audit attempt
  fails because the runtime is poisoned or the store is unavailable. The
  rejection middleware's `_LOGGER.exception()` is also not a safe template for
  logging provider failures: exception chains can disclose paths and values
  despite a constant message. Do not copy raw request paths into new audit fields.
- **Observability:** terminal audit is created by the trusted core and committed
  once, not appended post hoc by each HTTP route. Optional logs use bounded,
  value-free operation id/kind/phase/outcome fields and do not duplicate the
  audit sink. Wall-clock operational time, not scenario `TimeRuntime`, supplies
  claim, terminal, audit, timeout, and recovery timestamps.
- **Repository workflow:** a public schema change would require
  `schema_bundle()`, `contracts/schema-publication-manifest.json`, generated
  schema checks, and ADR-061 governance; CP-1 already published the operation
  carriers, so CP-2 should not need one. Store capability or SQLite schema
  evolution follows the existing migration/deprecation policy. The canonical
  completion graph remains `.ground-control.yaml`, `.gc/plan-rules.md`,
  `noxfile.py`, `tools/check_repo_policy.py`,
  `tools/check_requirement_governance.py`, and `tools/verify_all.py`;
  release-please owns `CHANGELOG.md`.

## Extension seam

The required internal seam is an operation-family-neutral mutation scope keyed
by the existing `OperationKind` and a terminal commit artifact with an explicit
mode (`snapshot-bearing` or `operation-only`), immutable admission context,
expected snapshot revision, and optional existing participant history-head
preconditions. New operation families should supply those values and their
validated candidate outcome without adding another lock, claim flow, terminal
save sequence, audit writer, or public schema. A future P3 coordination/fencing
provider composes beneath the same seam; it does not turn the in-process permit
into a distributed lock.

## Ownership and failure handoffs

- `_ControlPlaneCallExecutor.mutate()` probes a core call and invokes it again
  after reservation. Pre-permit admission must therefore be repeatable and
  must not claim, invoke a backend, append crossing history, or emit an accepted
  lifecycle audit. Re-evaluate state-dependent authorization, base revision,
  participant heads, and idempotency after acquiring the permit. A completed
  denial uses the existing single denial path and does not enter the second pass.
- A direct caller can pass `_runtime_call()` and then wait behind another
  mutation. After permit acquisition, recheck durability health and lease
  ownership before claiming or invoking; a prior mutation may have poisoned
  the runtime while this caller waited. Preserve `RuntimeLifecycleMixin`'s
  draining semantics for already-admitted calls during close, while refusing
  new admission. Poison is not an ordinary draining close.
- Cancellation before reservation grant must remove the waiter; after worker
  dispatch, logical ownership must survive until that worker actually exits.
  Verify both ASGI cancellation and direct task cancellation at the grant and
  dispatch boundaries; a threadpool call continuing in a thread alone does not
  prove the awaiting task retains its reservation. Backends still own bounded
  I/O timeouts. A hung backend must not be bypassed by granting another permit.
- Reservation context and thread-local callback guards are internal authority,
  not delegation credentials. Extension callbacks must not spawn and join a
  nested control-plane mutation, or copy reservation context into another
  task/thread to share the permit. Same-thread re-entry rejection alone does
  not establish safety against those patterns; this is a trusted in-process
  extension boundary, not isolation from malicious Python code.
- Every exit after `RUNNING` needs an authoritative disposition, including
  failed CAS after an effect, interrupted extension work, and failure in
  `_publish_committed_state()` after a successful transaction. Reloading a
  snapshot alone does not resolve an external effect. Read back the complete
  committed outcome under ownership, or preserve the claim and fail closed;
  neither retry the backend nor admit a successor from an unresolved cut.
  Terminal persistence retry is distinct from client idempotent submission;
  neither can use a redacted commitment as proof of equal secret values.

The existing test owners are `test_issue_1181_unified_control_plane_mutations.py`
(authority and atomic outcomes), `test_issue_1092_control_plane_crash_consistency.py`
(durability and ownership), `test_issue_1180_snapshot_revision_cas.py` (stale
cuts), and `test_issue_1093_request_rejection_offload.py` (bounded HTTP rejection).
Extend those boundaries with deterministic interleavings; entry decorators,
signature inspection, and structural design tests do not prove behavioral
store capability, crash atomicity, or the handoffs above.

Review evidence (2026-09-12): the initial preflight run timed out in
`test_http_mutation_waits_for_core_authority_without_occupying_worker`. A
follow-up isolated run before remediation passed, and the focused responsiveness
and cancellation pair then passed in five consecutive fresh-process runs after
remediation. The executor now shields dispatched mutation work and retains its
logical reservation through caller cancellation until the worker actually
exits; `test_cancelled_http_mutation_retains_reservation_until_worker_exits`
locks that handoff. The wider CP-2 and tooling-policy suites also pass.

## Verification boundary

The acceptance suite needs deterministic barriers and store failpoints at:
before and after claim; before and after backend validation/apply; before the
terminal transaction; after each staged snapshot, record, and audit write; and
after commit but before cache/receipt publication. Before claim leaves no
operation; after claim and before terminal leaves one durable `RUNNING` record;
any injected terminal-transaction failure rolls back the whole terminal cut;
after commit all snapshot/revision (when applicable), terminal status, and
actor audit are visible together. The contract runs against both the in-memory
and SQLite stores and covers snapshot-bearing and operation-only commits.

Concurrency tests must contend direct core and HTTP calls across generic
execution, workflow cancel/timeout, participant action/control, and governed
ingress/egress crossings while denial/read/auth audit traffic remains bounded
and independent. A backend spy must observe the durable `RUNNING` claim before
both validation and apply and prove no store transaction,
operation/participant/cache mutex, or HTTP serialization mutex is held while it
runs. Pending HTTP mutations must wait without consuming worker threads.
Exactly one logical mutation may own the state cut; reads that do not mutate
remain responsive. Backend re-entry into mutation fails closed.

Provenance tests must prove that every terminal record is visible iff its one
terminal audit is visible, the audit operation id and actor equal the immutable
record context, and a stale CAS or failed transaction changes none of snapshot,
revision, operation, idempotency, participant history, or audit state. A
post-commit cache/response failure must read back the committed triple without
backend replay. Existing tests that treat legacy ordered writes or record-only
interruption sealing as acceptable behavior no longer establish a conforming
mutation profile.

## Gotchas and anti-patterns

- Do not hold `_operation_lock`, `_participant_control_lock`, an SQLite
  transaction, an in-memory store lock, or `_ControlPlaneCallExecutor`'s async
  lock while invoking backend or other untrusted extension code.
- Do not release logical mutation ownership merely to release its bookkeeping
  mutex; that would permit overlapping backend effects derived from one state
  cut. Conversely, do not use thread-local re-entrancy to admit a backend
  callback as a nested mutation.
- Do not overlook backend `validate()`, participant runtime methods,
  observation callbacks, cleanup/stop work, policy/final-sink resolvers, or
  governed transformers as external callbacks that must run outside a physical
  mutex. Any backend-owned validation or execution before the durable claim
  violates write-ahead; pure policy resolution does not authorize a backend
  effect.
- Do not append the accepted operation audit in HTTP after the core returns.
  Transport audit cannot repair a missing transactional terminal audit and can
  duplicate or misclassify it.
- Do not append a second terminal audit on an exact persistence retry, or count
  a pre-effect authorization/read/denial event as the operation's terminal
  audit.
- Do not use `save_record()`, startup reconciliation, a compatibility fallback,
  or a special workflow/participant helper as a terminal backdoor.
- Do not infer operation-only commit from equal snapshot bytes. Do not advance
  revision for a true operation-only outcome, and do not suppress an advance
  for a snapshot-bearing commit whose bytes happen to be equal.
- Do not conflate operation state, workflow status, participant lifecycle,
  participant history heads, snapshot revision, lease ownership, idempotency,
  backend effect state, audit `allowed`, or HTTP queue state. Each retains its
  existing owner and meaning.
- Do not pre-publish an in-memory candidate or retain it after failed CAS. Do
  not run uncertain I/O failures through automatic reconciliation that writes a
  terminal record, and never replay a backend automatically.
- Do not serialize only HTTP calls. Embedded/direct `RuntimeControlPlane`
  callers and read-shaped crossing mutations must obey the same core authority.
- Do not coordinate `RuntimeManager` by quietly sharing a store or cache. A
  caller that points direct and governed facades at the same backend accepts
  that external-effect collision risk; only the control plane writes its store.

## Non-goals and implementation boundaries

- No CP-3 recovery classification, observation protocol, resolution operation,
  or automatic replay. CP-2 only removes terminal persistence bypasses and
  preserves `RUNNING`/fail-closed state for the governed recovery boundary.
- No CP-5 lease-order redesign, CP-7 actor-scoped idempotency/cache work, CP-8
  full read authorization/served-configuration work, or P3 distributed/HA
  claim. Existing safeguards still compose with CP-2 and must not regress.
- No exactly-once backend-effect guarantee and no inference that a timeout,
  disconnect, Python cancellation, process loss, or failed terminal write undid
  an external effect.
- No changes to SDL authoring, processor/compiler behavior, backend protocols,
  realization semantics, public operation/snapshot schemas, participant
  evidence, durable run provenance, or audit's evidentiary status.
- No new service/container, general scheduler, public mutation abstraction,
  audit subsystem, logging framework, environment/configuration surface, CLI,
  TLS/proxy policy, or multitenant store model.
