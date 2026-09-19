# Issue 1186 Control-Plane Recovery Operations Preflight

Date: 2026-09-19

Issue: #1186. Requirement: API-404. Decision: ADR-104. Work package: CP-12.
The issue body and ADR-104 remain authoritative. This note fixes the
operator-facing boundaries that are not already fixed by CP-3, CP-5, and CP-6;
it does not define another lifecycle, persistence profile, or implementation
program.

## Decision

CP-12 composes the existing runtime lifecycle and local-store guarantees into
operator procedures. It does not add a recovery daemon or a second state
machine. Keep three surfaces distinct:

- live runtime lifecycle: startup reconciliation, admission, mutation drain,
  provider close, and lease release owned by `RuntimeControlPlane`;
- offline P1 maintenance: integrity checking, backup, restore, and upgrade
  migration performed only while holding the same local-store ownership lease;
  and
- deployment responsibilities: target/backend backup alignment, TLS, proxy
  identity, service accounts, process supervision, secret resolution, and
  retention or off-host copying of backup artifacts.

The current repository has no control-plane serve command, maintenance CLI,
health endpoint, or general SQLite backup/restore operation. The timestamped
legacy JSON copy made during first import is migration rollback material, not a
supported operator backup. The existing operational-apparatus summary is an
authorized, value-bearing view and is not a health or diagnostics response.
The current request-path audit targets, `_conflict_detail()` fall-through to
`str(error)`, exception-class audit reasons, and rejection logger are known
redaction gaps to close in this work; they are not precedents for new surfaces.

## Recovery procedures and immutable history

The runbook uses the CP-3 closed classification and existing carriers. It does
not infer outcomes from process exit, request cancellation, timeout, retry, or
an operator's expectation.

| Durable outcome | Operator meaning | Permitted next action |
| --- | --- | --- |
| `FAILED`/`CANCELLED` with `runtime.control-plane.recovery-effect-absent` | The admitted effect is known absent. | Submit new work through ordinary admission with a fresh idempotency key if the effect is still wanted. Do not edit or delete the original. |
| `SUCCEEDED` with `runtime.control-plane.recovery-effect-applied` | Recovery observation established and validated the effect. | Treat the committed snapshot and operation as authoritative. Do not repeat the effect. |
| `INDETERMINATE` with `runtime.control-plane.recovery-effect-unobservable` | The effect cannot be established and the target/run is quarantined for new effects. | Inspect through authorized status and backend-specific deployment procedures, then create a separately authorized linked resolution operation. Never rewrite the parent or reuse its idempotency key. |

`OperationState`, `OperationKind`, `OperationAdmissionContext.parent_operation_id`,
`IndeterminateResolutionDisposition`, and
`resolve_indeterminate_operation()` are the only incumbent resolution
vocabulary. The current administrative disposition accepts the stored snapshot
through an `INDETERMINATE_RESOLUTION` child. An explicitly authorized new
backend attempt is ordinary work with a fresh claim and full validation; it
must gain parent linkage through the same admission context rather than being
called an administrative disposition or silently replaying the parent. A
future additional disposition belongs in the existing closed enum and codec,
not in free-form runbook text or `AuditEvent.details`.

Resolution requires the current typed operator identity and exact target/run
and subject scope. Possession of a database, operation id, receipt, or
idempotency key is not authority. The parent remains terminal, its claim
remains reserved, and its actor, timestamps, commitment, diagnostics, and audit
remain unchanged.

## Startup, readiness, and shutdown

The P1/P2 startup order remains one indivisible readiness gate:

1. validate trusted typed composition and the single-worker posture;
2. secure and identity-pin the store root, then acquire and verify the owner
   lease;
3. open the provider and verify immutable target/run scope, WAL mode, schema,
   supported migration, strict codecs, payload digests, and SQLite integrity;
4. load authoritative state and validate target/manifest/component and
   persisted runtime semantics;
5. reconcile every `ACCEPTED` and `RUNNING` operation under the mutation
   authority without replay; and
6. publish committed derived state and only then report ready.

Construction failure is the current pre-readiness behavior: an app must not be
composed around a partially initialized control plane. A served health surface
therefore cannot claim an intermediate runtime is ready merely because its
process or HTTP stack is reachable. A later composition that creates the
runtime inside ASGI lifespan must expose the same ordered phases rather than
inventing weaker readiness semantics.

Readiness is false when the lease is absent or lost, startup admission has not
finished, reconciliation or authoritative reload failed, durability is
poisoned, shutdown has started, or an unresolved indeterminate operation keeps
the target/run quarantined. Liveness reports only that the process and health
handler can respond; it does not touch the store, authenticate a backend, or
imply readiness. Health probes do not append audit events, because probe
traffic must not make readiness depend on a writable audit sink or create an
unbounded audit stream.

Normal shutdown preserves this order:

1. stop HTTP and core admission;
2. drain queued and admitted calls, including the logical mutation owner and
   any backend call whose cancellation did not stop the worker;
3. allow the existing terminal commit/readback discipline to settle the
   operation; unknown effects remain governed recovery work, not guessed
   success or cancellation;
4. close provider resources; and
5. release the owner lease only after close succeeds.

Reuse `_ControlPlaneCallExecutor.close()`, `RuntimeLifecycleMixin.close()`,
`runtime_owned`, `RuntimeMutationAuthority`, and `RuntimeOwnerLease`. Do not add
a route-local drain flag, a second active-call counter, or a signal handler
that closes the store directly. If provider close cannot be confirmed, retain
the lease and fail closed.

## Backup, restore, upgrade, and migration

Operator backup and restore are P1 local-provider maintenance operations, not
portable `ControlPlaneStore` methods and not control-plane mutations. P0 has no
durable backup claim. P2 uses the same P1 store procedure after served
admission is stopped and drained. Custom providers own equivalent procedures
and claims outside the local reference implementation.

The supported local backup boundary must:

- stop and drain the owning runtime, or enter a provider maintenance session
  that holds the same exclusive lease and admits no runtime owner;
- verify the expected normalized target/run scope before copying;
- use SQLite's consistent backup mechanism through an admitted connection,
  not copy the main database, `-wal`, `-shm`, or `-journal` paths as an
  independently meaningful file set;
- validate the resulting database with the incumbent schema, scope, strict
  record/snapshot/audit codecs, payload digests, and SQLite integrity checks;
- write to a private temporary regular file, synchronize file content, publish
  by same-filesystem atomic replacement, and synchronize the destination
  directory; refuse an existing destination unless the operator selected an
  explicit replacement policy; and
- report only a stable success/failure code. The selected source or destination
  path does not enter audit, logs, diagnostics, health, or machine-readable
  output.

A backup preserves the database's target/run metadata, snapshot revision,
operations, idempotency claims, and audit sequence as one state cut. It does
not back up external backend state, credentials, TLS material, proxy
configuration, or archival experiment evidence. Backup retention, encryption,
off-host transfer, access control outside the private local directory, and
target-native backups are deployment responsibilities.

Restore is offline and fail-closed. The maintenance tool holds the destination
lease before inspecting or replacing provider state, validates the staged
backup and exact expected target/run scope before publication, and performs any
supported schema migration on a private working copy rather than the supplied
backup or authoritative destination. It retains or creates a recoverable
pre-restore copy when replacing an existing database without changing the
authoritative database's journal mode, closes its own destination connections,
and verifies that no stale destination
`-wal`, `-shm`, or `-journal` file can be associated with the replacement
before the atomic replace and file/directory synchronization. Publication
failure retains the previous store; a failure after publication rolls back the
replacement, and an unconfirmed rollback retains the exclusive lease. Sidecar
safety uses descriptor/type/identity checks and the exclusive lease; it is not
a glob or best-effort unlink. Restore never copies an owner file, adopts scope
from a filename, rewrites operation history, drops idempotency claims, mutates
the supplied backup, or restores into a live provider. After publication,
ordinary provider admission repeats WAL/schema/integrity/codec checks and CP-3
startup reconciliation before readiness.

A database backup alone cannot prove that an external target is at the same
cut. Before restoring a previously used target/run, the deployment must restore
or independently establish the matching backend state. Where that cannot be
established, the operator must keep the service unready and use the existing
indeterminate-resolution boundary; the core must not fabricate successful
operations or infer target state from the restored snapshot. The runbook must
state this nonclaim next to the restore procedure.

Upgrade procedure ordering is: drain and close; take and verify a pre-upgrade
backup with the old admitted code; install the new code; start with the same
explicit target/run scope; acquire the lease; run the existing transactional
schema migration and integrity/codec gates; reconcile; then become ready.
Unknown or newer schema versions fail without mutation. Downgrade is not a
restore procedure. A migration failure leaves the old database or transaction
authoritative and the service unready; it does not trigger destructive cleanup
or automatic backup deletion.

## Health, diagnostics, audit, and logging

Health output is a small closed projection. It may contain only a closed status
(`live`, `ready`, or `unready`) and a bounded, deduplicated list of stable reason
codes such as lease, startup, recovery, poisoned, or draining. It contains no
target/run/actor/operation identities, timestamps, revision values, resource
counts, paths, schema or SQL text, provider/backend names, exception classes or
messages, credentials, request data, or snapshot values. The unready response
uses a fixed service-unavailable status and does not distinguish authorization
or existence details. Do not reuse `operational_apparatus_summary()` or return
`AuditEvent`, `Diagnostic`, or exception objects from health.

Operational diagnostics continue through `Diagnostic`/`DiagnosticModel` and
stable namespaced codes with bounded messages and JSON-Pointer locations.
Provider, migration, restore, observation, and close failures collapse to
coarse fixed messages at CLI and HTTP boundaries. `str(exception)`, Pydantic
input echoes, SQLite statements, tracebacks, native backend output, and
exception chaining in logs are prohibited disclosure sources.

`AuditEvent` remains the one append-only operational audit carrier. Tighten its
existing strict persisted codec and creation boundary rather than publishing a
second audit schema. Every string, collection, and `details` payload needs
explicit count/length/depth/encoded-size bounds, and details must be limited to
allowlisted value-free scalars, stable identifiers/digests, counts, booleans,
and closed codes already required by the owning operation family. Route audits
must use the immutable target scope and stable action; `request.url.path` and
ASGI `scope["path"]` are not audit targets. Append-only audit is not tamper
evidence, captured evidence, participant observation, or run provenance.
Tightening the persisted carrier is a local-store format change: advance
`LOCAL_OPERATION_SCHEMA_VERSION`, validate every predecessor event under the
lease, and fail closed on an event that cannot satisfy the bounded carrier.
Never truncate, sanitize in place, or silently drop historical events to make
an upgrade pass.

Module logging remains optional operational telemetry. Replace the current
rejection warning that formats request path/reason values and the
`_LOGGER.exception()` rejection-audit persistence-failure path with fixed event
codes and bounded counts/outcomes, without exception info. Logs do not
duplicate audit records or emit actor scope, operation ids, paths, SQL, raw
requests, tokens, credentials, backend/provider text, snapshot values, or
scenario data.

All lease waits, drain bounds, provider busy timeouts, backup timestamps,
operation/audit timestamps, readiness age, and recovery time use the apparatus
wall/monotonic clock. `RuntimeSnapshot.time_model_state`, `TimeRuntime`, SDL
timelines, participant clocks, and caller-authored scenario time are never
clock inputs to these operations. Reuse `_utc_now()` for the incumbent UTC
timestamp format and monotonic elapsed time for bounded waits; test-only clock
injection must remain explicitly operational and cannot accept a `TimeRuntime`.

## Canonical incumbents

- ADR-104 and `specs/formal/runtime-control-plane/README.md` own profiles,
  lifecycle, immutable indeterminacy, linked resolution, authority, and time
  separation.
- `control_plane_recovery.py`, the recovery-observation backend protocol and
  manifest capability, and `_validated_backend_result()` own classification,
  neutral observation, candidate validation, quarantine, and resolution.
- `OperationState`, `OperationKind`, `OperationAdmissionContext`, operation
  receipts/statuses, and their closed published models own public lifecycle
  shape. CP-12 adds no recovery DTO family.
- `ControlPlaneConfiguration`, `PlanScope`, `RuntimeTarget`, and
  `_validate_runtime_target_shape()` own trusted target/run composition and
  component validation. `runtime_target_scope()` owns the incumbent bounded
  target-scope normalization. No CLI or request selects scope from store
  contents.
- `RuntimeLifecycleMixin`, `RuntimeMutationAuthority`,
  `_ControlPlaneCallExecutor`, and FastAPI lifespan own admission, drain,
  cancellation settlement, close, and lease-release ordering.
- `LocalControlPlaneStore`, `RuntimeOwnerLease`, the existing metadata table,
  SQLite transaction/migration helpers, strict codecs, snapshot CAS, WAL/full
  synchronous admission, `PRAGMA quick_check`, and
  `control_plane_store_paths.py` own local persistence and filesystem safety.
  Backup/restore must reuse these checks rather than shelling out to `sqlite3`
  or duplicating them in the CLI.
- `ControlPlaneSecurityConfig.strict_defaults()`, `_ControlPlaneApiAuth`,
  `RequestSizeLimitMiddleware`, closed FastAPI request models, and the shared
  response helpers own P2 authentication, authorization, request shape/size,
  overload, and error-envelope placement. The current `_conflict_detail()`
  fallback, per-route `detail=str(exc)`, dynamic exception-class audit reason,
  and unguarded secondary-audit failure are remediation sites, not approved
  coarse-envelope behavior.
- `AuditEvent`, `_AuditEventModel`, `Diagnostic`/`DiagnosticModel`, module
  loggers, ADR-066, and the existing account-credential/value-free projection
  helpers own operational observability and redaction. The apparatus summary
  remains a separate authorized view.
- `raes_cli.main` and Typer sub-app registration are the incumbent operator CLI
  composition. Any local maintenance commands delegate to runtime-owned
  maintenance functions; CLI callbacks do not open SQLite, migrate rows, or
  implement redaction themselves. The ADR-104 amendment narrows ADR-036's
  module boundary to permit only this closed public maintenance import; other
  CLI-to-runtime imports remain forbidden.
- `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and
  `tools/verify_all.py` remain the workflow gates. ADR-015's 500-line
  non-test-source cap requires the cohesive maintenance implementation to stay
  out of already-large route/store modules. Release-please owns the changelog.

## Cross-cutting gates

- **Authentication and authorization:** ordinary status and resolution retain
  bearer/verified-proxy authentication, constant-time token comparison, exact
  target binding, roles, and subject scopes. A public health probe exposes only
  the constant safe projection above and performs no state-changing work.
  Offline maintenance is authorized by host access plus exclusive lease and
  explicit expected target/run scope; it is not authorized by a database path.
- **Secrets and configuration:** use `ControlPlaneConfiguration` and
  `ControlPlaneSecurityConfig` as explicit in-memory shapes. Add no token,
  credential, encryption key, secret reference, proxy trust, or service-account
  value to a command argument, environment variable, portable schema, health
  response, log, audit, or diagnostic. `RuntimeEnvironmentVariable` remains a
  scenario payload contract, not service configuration. A store/backup path is
  an operator-selected locator, never derived from request or scenario values,
  and must not be echoed after parsing.
- **Persisted shape and semantic validation:** every restored or migrated row
  passes the same `_OperationRecordModel`, `_AuditEventModel`, snapshot codec,
  operation transition/context, target/run scope, participant-history,
  realization, information-state, and credential gates used at startup.
  SQLite `quick_check` and payload hashes complement these validators; neither
  replaces them.
- **Filesystem and OS exposure:** retain private directory/file modes,
  ownership/type/link/reparse checks, directory and database identity pinning,
  SQLite-owned sidecars, same-filesystem staging, file-before-directory fsync,
  and the owner lease. Do not put secrets in argv or subprocess environments,
  and do not invoke a database shell. The path locator may be visible to the
  local process supervisor, so it is not a secret channel.
- **Error envelopes:** reuse stable `401`/`403`/`404`/`409`/`422`/`503`/`500`
  HTTP behavior and a small fixed CLI exit taxonomy. No maintenance exception
  hierarchy, provider-specific HTTP status, or `detail=str(exc)` conversion is
  needed. Tighten the shared conversion boundary rather than adding another
  route-local mapper. Failed secondary audit must not replace the original
  coarse error or escape to the framework's default handler.
- **Contract workflow:** internal health and maintenance status models stay
  private unless the implementation intentionally publishes them. A public
  contract change requires `schema_bundle()`, the schema-publication manifest,
  generated-schema parity, fixtures, and ADR-061 governance. SQLite evolution
  continues through `LOCAL_OPERATION_SCHEMA_VERSION`; it is not a portable
  JSON schema.

## Extension seam

The required seam is one lease-admitted local maintenance session, selected by
a closed operation (`check`, `backup`, or `restore`) and parameterized by the
explicit expected target/run scope and operator-selected source/destination.
Backup also carries an explicit destination-conflict policy whose safe default
is refusal. It reuses the local provider's path, scope, connection, codec,
integrity, migration, and synchronization helpers and returns only a closed
value-free result. The CLI is an adapter over that seam. A future storage
provider may implement a different atomic snapshot mechanism without changing
operation DTOs, health, HTTP authentication, or the runbook's ordering
invariants.

The health seam is a separate read-only projection of lifecycle milestones and
unresolved-recovery state. It must not become a generic metrics dictionary.
One obvious future deployment may mount the same projection on another probe
transport; keeping the projection transport-neutral avoids re-deriving
readiness in each adapter.

## Verification guardrails

Executable smoke coverage must record ordering, not only final success:

- backup/restore: lease before inspection, no runtime owner, exact scope,
  consistent SQLite backup, strict decode and integrity checks, file then
  directory fsync, no sidecar copying or stale destination sidecars, source
  backup immutability, explicit destination-conflict behavior, failed-stage
  rollback, and restart reconciliation before ready;
- upgrade/migration: pre-upgrade backup, supported predecessor success,
  unknown/newer schema refusal, injected transaction/fsync failure, unchanged
  authority after failure, and same target/run identity;
- readiness/drain: every startup failure remains unready, unresolved
  indeterminacy remains unready, admission stops before draining, backend and
  mutation settlement precede provider close, and close precedes lease release;
- recovery: each CP-3 classification, no replay counters, operator-only linked
  resolution, immutable parent, fresh child key, and quarantine until resolved;
  and
- redaction: seed bearer tokens, credentials, request bodies and paths, SQL,
  provider/backend exception text, and snapshot values, then assert absence
  across health, audit serialization, diagnostics, logs, CLI stdout/stderr, and
  HTTP errors, including audit/store failure paths.

Use real processes for lease contention and process-visible shutdown tests.
Use instrumented providers for event ordering and injected failures. Do not
make wall-clock sleeps the ordering oracle.

## Gotchas and anti-patterns

- Do not call `operational_apparatus_summary()` health or expose it without its
  existing authorization; it includes value-bearing identities, timestamps,
  addresses, and scenario/runtime classifications.
- Do not make health readiness a database query that can migrate state, append
  audit, acquire a second lease, invoke a backend, or block behind mutation.
- Do not copy an open WAL database with ordinary file copy, copy SQLite
  sidecars as a backup format, or validate only `quick_check` while skipping
  strict payload codecs and scope checks.
- Do not replace the main database while a prior `-wal`, `-shm`, or `-journal`
  can still bind to that pathname, mutate the supplied restore artifact during
  validation/migration, or overwrite a backup destination implicitly.
- Do not let backup/restore bypass the lease because it is "read only," infer
  target/run from a filename or newest operation, restore over a live or
  identity-pinned connection, or release the lease after an uncertain close.
- Do not describe the legacy JSON migration copy as disaster recovery, delete
  it automatically, or make an incomplete failed backup authoritative.
- Do not turn `INDETERMINATE` into mutable status, delete/reassign its claim,
  reuse the parent key, replay automatically, or encode operator judgment in a
  free-form audit detail.
- Do not duplicate schema migration, codec, validation, filesystem, fsync,
  auth, redaction, clock, exception, or shutdown logic in a CLI or runbook
  script.
- Do not tighten `_AuditEventModel` under the existing local schema version,
  truncate legacy details, or rewrite append-only audit history during
  migration.
- Do not log exception chains, request paths, raw Pydantic errors, SQL, native
  provider output, or supposedly safe values merely because they are length
  bounded. Bounding is not redaction.
- Do not use scenario time for operational deadlines or timestamps, and do not
  use wall-clock jumps as elapsed-time measurement where monotonic time is
  available.
- Do not make TLS, proxy-header stripping, secret resolution, service units,
  backup encryption, retention, or backend-native restore part of the core.

## Non-goals and implementation boundaries

- No P3 coordination, multi-worker/shared-owner service, leader election,
  fencing, replication, remote store, automatic takeover, or high-availability
  claim.
- No exactly-once backend effects, automatic replay, compensation, rollback,
  target-state reconstruction, or proof that a database backup matches an
  external target.
- No cross-target/run backup merge, store cloning under a new identity,
  tenant multiplexing, request-selected store, or rewriting of durable history.
- No replacement for experiment-run archives, captured evidence, provenance,
  participant observation, or scenario-native observability.
- No core serve command, TLS terminator, reverse proxy, identity provider,
  secret manager, process supervisor, service-account policy, scheduler, or
  retention/encryption system.
- No new portable recovery, audit, snapshot, health, or maintenance schema
  unless a concrete external interoperability requirement separately clears
  the repository's schema-governance gates.
