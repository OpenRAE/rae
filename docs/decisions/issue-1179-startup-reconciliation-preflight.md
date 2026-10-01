# Issue 1179 Startup Reconciliation Preflight

Date: 2026-09-17

Issue: #1179. Requirement: `API-404`. Parent decision: ADR-104. Work
package: CP-3.

## Decision

Startup reconciliation belongs to `RuntimeControlPlane`, between validated
store admission and public readiness. It is not a persistence-provider
responsibility. The runtime loads the authoritative snapshot and operation
records through their strict codecs, finds every `ACCEPTED` or `RUNNING`
record, obtains a backend-neutral effect observation when one is available,
and closes each record through the existing atomic terminal-commit seam.

The store remains responsible for integrity, migration, codecs, atomic
records, revision compare-and-swap, and audit persistence. `RuntimeTarget`
remains responsible for composing backend components and matching them to the
backend manifest. A store must never import a backend package, call a native
API, or interpret backend effect state.

Reconciliation is classification, not resumption. Startup, timeout,
cancellation, a disconnected client, and an idempotent retry must never call
an apply, start, stop, reset, participant action, or other effect method for an
existing operation. Only the narrow recovery-observation method may run, and
its contract is read-only.

## Startup and readiness boundary

The current construction boundary is the readiness boundary: a
`RuntimeControlPlane` must not escape its constructor, and a FastAPI app must
not be composed around it, until reconciliation has completed or startup has
failed closed. The required order is:

1. validate the typed target and explicit control-plane configuration;
2. acquire and verify the one runtime-owner lease using only the minimum
   provider admission needed to identify and lock the store;
3. complete the remaining provider filesystem, schema, migration, WAL, and
   integrity admission;
4. load and strictly decode the snapshot, operation records, and immutable
   operation contexts;
5. validate persisted runtime semantics and target/manifest/component shape;
6. reconcile every non-terminal record under the one mutation authority; and
7. publish only the committed store state as derived caches, then become
   ready.

No recovery callback runs before the lease and the validated record load.
Failure in migration, integrity, codec, target shape, or lease admission aborts
startup; it is not converted into an `INDETERMINATE` operation. A failed or
uncertain reconciliation commit also aborts readiness and releases the lease.
It never leaves a partially initialized control plane available to callers.

ADR-104 requires lease admission before schema inspection and migration. The
current `LocalControlPlaneStore` performs some provider initialization in its
own constructor, before `RuntimeControlPlane` acquires the runtime lease. CP-3
must not claim that this earlier CP-5 ordering gap is solved merely because its
own observer runs later. It does, however, require a positive lease check and
all provider/codec gates to have completed before the first observation.

## Closed classification and persistence

The recovery vocabulary is one closed enum with exactly `effect-absent`,
`effect-applied`, and `indeterminate`. It is not another operation lifecycle,
workflow state, participant state, evidence status, or provider exception
hierarchy.

| Classification | Terminal result | Commit mode | Required diagnostic |
| --- | --- | --- | --- |
| effect absent | `FAILED`, or `CANCELLED` only where the admitted lifecycle proves cancellation before invocation | operation-only | `runtime.control-plane.recovery-effect-absent` plus the canonical terminal diagnostic |
| effect applied | `SUCCEEDED` after the observed candidate passes the incumbent backend-result and snapshot-transition gates | snapshot-bearing | `runtime.control-plane.recovery-effect-applied` at `INFO` severity |
| indeterminate | `INDETERMINATE` | operation-only | `runtime.control-plane.recovery-effect-unobservable` plus `runtime.control-plane.operation-indeterminate` |

The core owns the mapping from classification and prior lifecycle state to the
terminal state. A backend observer does not choose `SUCCEEDED`, `FAILED`, or
`CANCELLED`. A post-CP-2 `ACCEPTED` record proves that invocation never began
and may take the known-absent path; a `RUNNING` record requires observation or
becomes indeterminate. Records whose migration provenance cannot establish the
write-ahead invariant are indeterminate rather than assumed absent.

Every classification uses `RuntimeDurabilityMixin._commit_terminal_operation`
and the provider's `commit_terminal_operation()` transaction. The resulting
snapshot, terminal record, and `terminal_operation_audit()` become visible as
one cut. The original operation identity, context, request commitment,
idempotency key, receipt, and submission time remain unchanged. In particular,
`INDETERMINATE` is terminal and immutable, and its idempotency claim is neither
deleted nor reassigned.

Observation happens outside a store transaction. Records are processed in one
stable order under `RuntimeMutationAuthority`; derived caches are rebuilt only
from committed store state. A snapshot revision conflict or unknown commit
outcome is not evidence about the backend effect and must not trigger another
observation or an effect call in the same failure path.

An indeterminate record is terminal history, but it does not establish that
the stored snapshot matches the target. Until a separately authorized linked
resolution succeeds, the safe default is to reject new effectful mutations for
that target/run while continuing to allow authorized reads and resolution.
The repository has no operation-impact independence proof that would justify
silently admitting unrelated mutations from an uncertain state cut.

## Backend-neutral observation seam

Recovery observation extends the existing optional component pattern:

- `raes_backend_protocols` owns a narrow read-only observer protocol and typed,
  backend-neutral request/result carriers;
- `BackendCapabilitySet`, `BackendManifest`, and `BackendManifestV2Model` own a
  first-class optional recovery-observation declaration, including the closed
  set of supported `OperationKind` values;
- `RuntimeTarget`, `RuntimeTargetComponents`, `BackendRegistry.create()`, and
  `_validate_runtime_target_shape()` own component composition, signature
  checks, and exact manifest/component agreement; and
- `RuntimeControlPlane` owns invocation, classification, validation, and the
  terminal commit.

The existing `ObservationCapabilities`, `ObservationRuntime`, observation
demands, capture offers, and evidence contracts implement EXP-715 experiment
observation. They are not crash-recovery effect observation and must not gain
overloaded flags or synthetic capture records for CP-3. Likewise, cleanup
verification and realization observations do not prove an interrupted
control-plane operation's outcome.

A recovery-observation request exposes only the minimum value-free context
needed to bind readback: operation id and kind, immutable target/run and
request commitment, the validated baseline snapshot, and any governed neutral
effect locator admitted with the original claim. It does not expose bearer
tokens, idempotency keys, raw plans or request bodies, account credential
values, store paths, SQL/WAL coordinates, authorization secrets, or provider
exceptions. Native handles and credentials remain private to the configured
backend component.

An `effect-applied` result must bind to the requested operation and commitment
and carry a neutral candidate `RuntimeSnapshot`/changed-address result. Before
commit, that candidate passes the same bounded `ApplyResult`, snapshot shape,
changed-address, entry/effect transition, workflow/evaluation/participant,
realization-authority, information-state, and credential-sanitization gates
used by `_validated_backend_result()` and `_finalize_backend_apply()`. Factor
the reusable validation part if necessary; do not copy a reduced validator
into recovery. A malformed, mismatched, unsupported, timed-out, or failed
observation becomes `indeterminate` with a stable value-free diagnostic. Raw
exception text never becomes status, audit, HTTP detail, or log data.

The current durable record retains a commitment, not the original semantic
request. Therefore an observer may claim `effect-applied` only when it can bind
readback to the operation and the runtime can validate the resulting state
without reconstructing facts it does not possess. Otherwise the honest result
is `indeterminate`. Do not solve this by persisting raw credential-bearing
plans. If a future operation family needs extra recovery input, the extension
point is one bounded, strict, value-free recovery descriptor attached to the
existing operation record and covered by migration and codec validation.

No-observation backends remain valid targets. Absence of both the manifest
capability and component deterministically produces the unobservable
classification. A manifest/component mismatch or invalid observer signature
is a target-shape error. A valid observer may support only a declared subset of
`OperationKind`; other kinds are unobservable. The runtime never falls through
to a native method guessed by name.

## Linked resolution and authorization

Resolution never changes the original `INDETERMINATE` record. It creates a new
operation with a fresh idempotency claim, new immutable resolver actor/scope,
and `parent_operation_id` equal to the original operation id. The original and
child must share the same target/run scope, and the parent must still be
terminal `INDETERMINATE` at the authoritative read used for the child claim.

Administrative disposition and a new backend attempt are different concepts.
If the child only records a closed resolution disposition, it needs one
dedicated value in the existing `OperationKind` enum and a typed, closed
disposition; reusing the original backend operation kind would make its audit
and request commitment false. If the operator explicitly authorizes a new
effect attempt, the child uses the ordinary operation kind and full normal
admission, write-ahead claim, validation, and terminal-commit path. It is never
an automatic replay of the parent.

P0/P1 embedders supply the typed resolver identity at their trust boundary.
P2 derives it through `_ControlPlaneApiAuth`; only an authenticated
target-bound `OPERATOR` identity may resolve an indeterminate operation.
`BACKEND` and `AUDITOR` roles, possession of the operation id, an idempotency
key, or access to the store are insufficient. Authorization runs again against
the parent target/run and any participant subject scope before the child claim.
A denied resolution creates no operation or idempotency claim and uses the
existing bounded denial-audit path.

The trusted core, not an HTTP route or backend callback, creates the linked
operation and its audit. The child's terminal audit uses the child actor and
operation id; the parent actor remains unchanged. A route must not append a
second success audit after the core returns.

## Canonical incumbents

- `OperationState`, `OperationKind`, `OperationAdmissionContext`,
  `OperationStatus`, `operation_terminal_diagnostic()`, and the published
  operation carriers own lifecycle vocabulary and immutable linkage.
- `RuntimeMutationAuthority`, `control_plane_mutation()`, and
  `external_control_plane_call()` own mutation serialization and trusted
  extension re-entry guards. Startup recovery does not add another lock.
- `RuntimeDurabilityMixin`, `SnapshotState`, `TerminalCommitMode`,
  `SnapshotRevisionConflict`, and `terminal_operation_audit()` own atomic
  terminal publication, revision outcomes, cache rebuild, and audit binding.
- `ControlPlaneStore`, `AtomicControlPlaneStore`,
  `ControlPlaneStoreCommitAdapter`, `InMemoryControlPlaneStore`, and
  `LocalControlPlaneStore` remain the persistence boundary. The
  `control_plane_recovery.py` tombstone may host the runtime coordinator again;
  the removed store-side `reconcile_interrupted_records()` workflow must not
  return. `INTERRUPTED_OPERATION_DIAGNOSTIC_CODE` is retained only as a legacy
  negative-test sentinel; it is not the CP-3 classification or diagnostic
  authority and may be removed once those compatibility assertions migrate.
- `_OperationRecordModel`, `OperationReceiptModel`, `OperationStatusModel`,
  `_record_payload()`, `_record_from_payload()`, and
  `migrate_sqlite_schema()` own strict persisted shape and migration. Do not
  add a permissive recovery JSON decoder.
- `RuntimeTarget`, backend protocols, `BackendCapabilitySet`,
  `BackendManifestV2Model`, manifest render/parse helpers, and
  `_validate_runtime_target_shape()` own backend capability discovery.
- `_validated_backend_result()`, `_finalize_backend_apply()`, and their
  snapshot, transition, realization, participant, workflow, and credential
  gates own acceptance of backend-produced state.
- `ControlPlaneConfiguration`, `ControlPlaneSecurityConfig.strict_defaults()`,
  `_ControlPlaneApiAuth`, `RequestSizeLimitMiddleware`, and
  `_ControlPlaneCallExecutor` own typed composition, HTTP authentication,
  request shape, bounded admission, and offload.
- `Diagnostic`, `AuditEvent`, module loggers, and ADR-066 own public failures,
  operational audit, and telemetry. Recovery does not create evidence or run
  provenance.

## Cross-cutting gates

- **Contract and persistence shape:** recovery-related public fields continue
  through closed `ContractModel(extra="forbid")` DTOs and generated schemas.
  Internal operation fields use the same strict, bounded record codec and
  digest. Unknown classifications, operation kinds, descriptor members, or
  missing linkage fail closed. A backend-manifest or operation-carrier schema
  change requires `schema_bundle()`, the matching entry under
  `contracts/schema-publication/entries/`, generated-schema parity, fixtures,
  and ADR-061/plan-rule governance.
- **Semantic validation:** target/component agreement passes
  `_validate_runtime_target_shape()`. An applied candidate passes the incumbent
  backend-return and snapshot-transition gates before it is authoritative.
  Recovery classification does not bypass planner authority, participant
  history heads, realization authority, information-flow policy, or
  credential sanitization when those concerns are present in the candidate.
- **Authentication and authorization:** P2 retains constant-time bearer
  matching, explicit verified-proxy opt-in, exact target binding, and closed
  roles. Resolution adds operation/run/parent and subject checks in the core.
  Startup reconciliation is trusted internal work bound to the original
  immutable operation actor; an observer is not granted resolver authority.
- **Secrets, environment, and process exposure:** recovery adds no secret
  resolver, environment loader, CLI flag, subprocess, or argv value.
  `ControlPlaneConfiguration` and `RuntimeTarget` remain explicit in-memory
  composition shapes. `RuntimeEnvironmentVariable` remains an SDL/runtime
  payload contract and is not a service-credential channel. Existing
  `WEB_CONCURRENCY`/`UVICORN_WORKERS` validation remains the only local-store
  worker environment gate. Backend credentials stay inside their configured
  adapter and never enter the observer carrier, operation record, diagnostic,
  audit, log, fixture, or process arguments.
- **Filesystem and OS exposure:** the local provider retains owner-only
  directory/database modes, symlink and non-regular-file rejection,
  identity-pinned opens, WAL/full-sync admission, integrity checks, durable
  migration backups, and `RuntimeOwnerLease`. Recovery creates no side file,
  lock file, native-handle serialization, or second database connection model.
- **Error envelopes:** observer failure and unavailability become stable
  diagnostics, not `str(exception)`. Startup store/codec failures remain
  construction failures. HTTP resolution maps authentication, not-found,
  conflict, invalid-shape, overload, and unexpected failures through the
  existing coarse `401`/`403`/`404`/`409`/`422`/`503`/`500` behavior. The
  existing per-route `detail=str(exc)` conversions are not safe templates.
- **Observability:** one core terminal audit accompanies each reconciled or
  linked operation. Optional logs contain only bounded operation id, kind,
  phase, classification, and stable reason code. They exclude paths, native
  identifiers, actor scopes, request content, exception chains, and backend
  payloads. Wall-clock time supplies recovery and audit timestamps; scenario
  `TimeRuntime` does not.
- **Repository workflow:** `API-404` traceability, backend-manifest fixtures,
  operation fixtures, store migrations, and focused restart/security tests
  move together with their changed contracts. The canonical gates remain
  `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and
  `tools/verify_all.py`. Release-please owns `CHANGELOG.md`.

## Verification guardrails

Restart coverage must exercise absent, applied, explicit unobservable, missing
observer, malformed observer result, observer exception/timeout, and terminal
commit failure against both authoritative store behavior and cache rebuild.
Tests must prove that apply/effect method counters stay at zero during restart,
timeout, cancellation, request disconnect, and same-key client retry.

Authorization coverage must include operator success, backend/auditor denial,
cross-target and cross-run denial, participant-subject denial where relevant,
parent-not-indeterminate conflict, fresh child idempotency, immutable parent,
retained parent idempotency claim, and exactly one child terminal audit. Target
shape tests must cover manifest/component mismatch and supported-operation-kind
dispatch. Redaction tests seed secrets and provider exception text and prove
they do not appear in records, diagnostics, audits, logs, HTTP bodies, or
fixtures.

## Gotchas and anti-patterns

- Do not resurrect `reconcile_interrupted_records()` in a store or terminalize
  records with `save_record()` alone.
- Do not call an apply method to "check" whether it is idempotent. Idempotence
  is not evidence that replay is authorized or that the first effect was absent.
- Do not treat an HTTP timeout, task cancellation, thread cancellation, process
  restart, or missing terminal record as proof that the effect is absent.
- Do not map every interrupted operation to `FAILED`; that erases the
  distinction between known absence and unknown external state.
- Do not accept a backend boolean or native status object directly. Require the
  neutral closed result and validate an applied snapshot through the shared
  result gates.
- Do not reuse EXP-715 observation/evidence, cleanup verification,
  `RealizationObservationDisclosure`, or participant observation carriers for
  recovery effect classification.
- Do not add recovery flags to manifest `constraints`; capability and supported
  operation kinds need typed first-class fields with exact component matching.
- Do not persist raw plans, credentials, native handles, exception text, or an
  unbounded provider payload to make recovery easier.
- Do not make `INDETERMINATE` mutable, delete its idempotency key, reuse that
  key for the child, or let a linked child overwrite the parent.
- Do not use the original backend operation kind for a purely administrative
  disposition, and do not call an explicitly authorized new attempt a
  "resolution" without the ordinary effect workflow.
- Do not let constructor failure leak a lease, expose a partially reconciled
  cache, or create an app that can accept requests.

## Non-goals and boundaries

- CP-3 does not provide exactly-once backend effects, automatic replay,
  background job resumption, compensation, rollback, or desired-state
  convergence.
- It does not implement P3 coordination, fencing, leader election,
  multi-worker ownership, remote persistence, or cross-target/cross-run
  scheduling.
- It does not replace the operation lifecycle, snapshot schema, backend
  manifest, audit model, EXP-715 evidence plane, participant observation,
  cleanup contracts, or archival run provenance with a recovery-specific
  parallel family.
- It does not add a serve command, health API, secret loader, environment
  binding, TLS/proxy deployment, OS service unit, backup scheduler, or operator
  runbook. CP-12 owns operational health and runbook work.
- It does not make direct `RuntimeManager` or direct backend calls durable or
  reconcile them; only operations admitted through `RuntimeControlPlane` have
  the required record and linkage.
- It does not claim observation support for an operation kind a backend cannot
  bind and validate. Such work terminates honestly as indeterminate.
