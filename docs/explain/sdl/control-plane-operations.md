# Control-Plane Recovery Operations

This runbook covers the reference runtime control plane's supported recovery,
health, shutdown, backup, restore, and upgrade procedures. It composes the
existing CP-3, CP-5, and CP-6 lifecycle rules; it does not introduce a second
recovery state machine or infer an operation outcome from process failure.

The durability profiles have different boundaries:

- P0 is in-memory and has no durable backup or restore claim.
- P1 is the single-host local SQLite provider described here.
- P2 uses the same P1 store procedure only after HTTP admission has stopped and
  drained. A custom provider must supply its own equivalent procedure.

All commands require an explicit expected target and run scope. A database path
is a locator, not authority and not a source of scope. Run the commands as the
same operating-system identity that owns the private store and backup
directories. Do not expose command output, paths, or database contents as run
evidence.

## Classify Recovery Before Acting

Inspect the operation through the authenticated status API and use only its
durable terminal state and recovery diagnostic:

| Durable result | Meaning | Operator action |
| --- | --- | --- |
| `FAILED` or `CANCELLED` with `runtime.control-plane.recovery-effect-absent` | The admitted effect is known absent. | If the effect is still wanted, submit ordinary new work with a fresh idempotency key. Preserve the original operation. |
| `SUCCEEDED` with `runtime.control-plane.recovery-effect-applied` | Neutral observation established and validated the effect. | Treat the committed snapshot and operation as authoritative. Do not repeat the effect. |
| `INDETERMINATE` with `runtime.control-plane.recovery-effect-unobservable` | The effect could not be established. New effects for the target/run remain quarantined. | Use backend-specific inspection, then create a separately authorized linked resolution operation. Never rewrite the parent or reuse its idempotency key. |

Timeout, request cancellation, process exit, and an operator's expectation are
not evidence of an effect. The parent operation, its claim, timestamps,
commitment, diagnostics, and audit history remain immutable. Administrative
resolution uses the existing `INDETERMINATE_RESOLUTION` child operation and an
operator identity bound to the exact target.

## Health and Startup

The public probes are deliberately value-free:

- `GET /health/live` returns `200` with `{"status":"live","reasons":[]}`
  when the HTTP health handler can answer. It does not inspect a backend or
  imply readiness.
- `GET /health/ready` returns `200` only after admission, store validation, and
  startup reconciliation finish. Otherwise it returns `503` and a bounded list
  of stable reason codes.

Neither probe authenticates a caller or appends audit events. Probe output never
contains target, run, actor, operation, timestamp, revision, count, path,
provider, exception, SQL, credential, or snapshot values.

Readiness remains false when startup is incomplete, the owner lease is absent
or lost, durability is poisoned, shutdown is draining or complete, or an
unresolved indeterminate operation requires recovery. A successful startup
follows this order:

1. Validate trusted composition and the one-worker configuration.
2. Secure the store root and acquire its owner lease.
3. Verify target/run scope, schema, supported migrations, codecs, digests, and
   SQLite integrity.
4. Load and validate authoritative runtime state.
5. Reconcile admitted operations without replaying unknown effects.
6. Publish derived state, then report ready.

Construction failure is pre-readiness failure. Do not put a partially
initialized control plane behind a ready HTTP listener.

## Stop and Drain

Before P1 maintenance or a deployment change:

1. Remove the instance from readiness-based traffic and stop new HTTP/core
   admission.
2. Drain queued and admitted calls, including backend work whose request was
   cancelled but whose worker is still active.
3. Let terminal commit and readback settle. Unknown effects become recovery
   work; do not guess success or cancellation.
4. Close provider resources.
5. Release the owner lease only after provider close succeeds.

The runtime lifecycle and ASGI lifespan implement this order. Do not delete the
owner file, close the store directly from a signal handler, or run maintenance
against a live service. If close cannot be confirmed, retain the lease and fail
closed.

## Check and Backup

With the owning runtime stopped and drained, validate a store:

```console
raes runtime store check STORE_DIR --target TARGET --run-scope RUN_SCOPE
```

Create a consistent backup in a private directory:

```console
raes runtime store backup STORE_DIR BACKUP.sqlite3 --target TARGET --run-scope RUN_SCOPE
```

An existing destination is refused. Replace it only as an explicit policy:

```console
raes runtime store backup STORE_DIR BACKUP.sqlite3 --target TARGET --run-scope RUN_SCOPE --replace
```

The operation acquires the same exclusive lease as the runtime, verifies the
exact target/run scope, uses SQLite's backup API, validates the resulting
schema, records, audit history, payload digests, and integrity, synchronizes the
private temporary file, publishes it atomically, and synchronizes its
directory. Never copy the main database and `-wal`, `-shm`, or `-journal` files
as an independently meaningful set.

Success and failure output are fixed codes such as
`control-plane-store-backup-succeeded`; paths and provider errors are not
echoed. A backup contains the local store's scope metadata, snapshot revision,
operations, idempotency claims, and audit sequence as one cut. It does not
contain or establish matching external backend state, credentials, TLS/proxy
configuration, or archival experiment evidence. Encryption, retention,
off-host transfer, and target-native backups remain deployment
responsibilities.

## Restore

Restore only into an offline destination whose expected target and run scope
are known independently:

```console
raes runtime store restore BACKUP.sqlite3 STORE_DIR --target TARGET --run-scope RUN_SCOPE
```

An existing destination is refused unless `--replace` is present. Replacement
first retains a validated `pre-restore-*.sqlite3` copy in the private store
directory. The supplied backup remains immutable: the tool copies it to a
private working database, applies only supported transactional migrations to
that copy, validates the complete store, rejects stale SQLite sidecars, then
atomically publishes and synchronizes the destination.

Do not start the service merely because the database restore succeeded. A
database backup cannot prove that an external target is at the same state cut.
Restore or independently establish the matching backend state first. If that
cannot be established, keep the service unready and use the indeterminate
recovery boundary; never fabricate successful operations from the restored
snapshot.

After publication, start normally with the same explicit scope. Runtime
admission repeats schema, integrity, codec, lease, and reconciliation checks
before readiness. Preserve the supplied backup and any pre-restore copy until
the deployment's retention policy confirms recovery.

## Upgrade and Migration

Use this order for an upgrade:

1. Stop admission, drain, close, and release the owner lease.
2. With the old admitted code, create and verify a pre-upgrade backup.
3. Install the new code.
4. Start with the same explicit target and run scope.
5. Let normal admission acquire the lease, run the supported transactional
   schema migration, validate the store, reconcile, and only then become ready.

Unknown or newer schemas fail without mutation. A failed migration leaves the
old database or transaction authoritative and the service unready; it does not
delete the backup or sanitize history. Downgrade is not a restore procedure.
Use a tested backup plus the corresponding backend-state procedure instead.

All lease waits, drains, SQLite timeouts, backup timestamps, and recovery
timestamps use apparatus wall or monotonic time. SDL timelines, participant
clocks, `TimeRuntime`, and caller-authored scenario time never drive these
operations.

## Deployment Responsibilities

The deployment owner must provide TLS termination, proxy identity trust,
service accounts, secret resolution, one-worker process supervision,
readiness-based routing, private filesystem access, backup encryption and
retention, off-host copies, and backend-native backup or state alignment. Logs
and health are not audit evidence. The append-only operational audit is not
tamper evidence, participant observation, run provenance, or captured
experiment evidence.

For the underlying invariants and ownership boundaries, see
[Runtime Architecture](runtime-architecture.md) and
[ADR-104](../../decisions/adrs/adr-104-runtime-control-plane-architecture.md).
