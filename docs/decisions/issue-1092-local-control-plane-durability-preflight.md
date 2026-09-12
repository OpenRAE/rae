# Issue 1092 Local Control-Plane Durability Preflight

Date: 2026-08-11

Issue: #1092. Requirement: API-404.

## Decision

`LocalControlPlaneStore` remains the single-host reference persistence owner,
but its JSON read-modify-replace files are replaced by one SQLite database.
The database uses WAL journaling, full synchronous commits, an explicit busy
timeout, unique indexed idempotency keys, and transactions that commit the
snapshot and terminal operation record as one unit. Participant transitions
continue to commit their snapshot, operation record, and audit event as one
unit.

This closes four incumbent gaps without changing the public snapshot or
operation contracts:

- two processes can no longer overwrite each other's operation updates;
- an idempotency lookup and claim is one atomic database operation;
- a failed participant transition cannot expose a partial snapshot, record, or
  audit append; and
- operation and idempotency lookup no longer reparses a growing JSON array.

The operation claim is durable before a backend call starts. On success or a
handled failure, the resulting snapshot and terminal operation record are
committed atomically. If the process exits after the claim but before that
terminal commit, startup converts the orphaned `ACCEPTED` or `RUNNING` record
to `FAILED` with the stable
`runtime.control-plane.operation-interrupted` diagnostic. That diagnostic
states that backend effects may be indeterminate. The runtime never replays
such a record automatically, and its retained idempotency key prevents a
client retry from blindly invoking the backend again.

Stored JSON payloads retain canonical serialization and a SHA-256 integrity
digest. Reads verify that digest before contract reconstruction, and store
startup runs SQLite's database integrity check. These checks detect accidental
corruption; they are not a substitute for filesystem access control or an
authenticated external ledger.

On POSIX, the store creates or tightens its owned directory to `0700` and its
main SQLite database to `0600`. SQLite creates its main database, WAL,
shared-memory, and rollback-journal files inside that owned directory. The
application validates SQLite-managed paths through descriptor-free metadata
inspection and never independently opens or closes them. Existing main
databases are tightened with
path-based, no-follow `chmod` before SQLite opens them; a new database is
created by SQLite and validated before schema work. Directory paths retain
descriptor identity checks. SQLite-managed paths fail closed when stable
metadata identifies a symlink/reparse point, wrong filesystem type, foreign
owner, non-private POSIX mode, a hard-linked SQLite alias, or main-database
identity replacement. The store pins the database identity established at
initialization and requires that same object on every later connection; an
operator restore by pathname therefore requires a runtime restart rather than
silently switching the live cache to another database. Windows
reparse/type checks remain enforced, while deployment ACLs are the authority
for permissions that POSIX mode bits cannot express.

The durable snapshot codec enumerates every `RuntimeSnapshot` dataclass field
in both directions and fails its verification guard when the contract and codec
drift. This includes participant episode-closure records; a successful local
commit and reload must preserve them rather than silently restoring the field's
empty default.

Existing `snapshot.json`, `operations.json`, `audit.jsonl`, and
`control-transition-state.json` files are imported once. Source files remain
untouched, and a timestamped, fsynced backup is created before the database
transaction commits. A failed import may leave an additional backup but cannot
silently discard the legacy source.

## WAL And Backup Durability Admission

The durability claim depends on two admission results, not merely on requesting
them. SQLite's
[`journal_mode` PRAGMA](https://sqlite.org/pragma.html#pragma_journal_mode)
returns the mode that the connection actually entered, and a request can leave
the prior mode in place. Store initialization therefore requires the exact
`wal` result before it creates schema objects, records a schema version, or
starts legacy migration. Any other result fails construction with the legacy
sources untouched. This keeps every initialized store inside the WAL topology
assumed by the transaction and cross-process tests.

The prior backup sequence copied each legacy file and then synchronized only
the backup and parent directories. Directory synchronization persists names;
it does not establish that the copied file data reached stable storage.
Following SQLite's distinction between flushing file content and the directory
entry that names it in its
[atomic-commit protocol](https://sqlite.org/atomiccommit.html#_flushing_changes_to_mass_storage),
the store now synchronizes every copied regular backup file before the backup
directory and store directory. A file-sync failure aborts and rolls back the
migration transaction. The untouched source remains authoritative, and a
subsequent startup can retry even when the failed attempt left an incomplete,
timestamped backup directory.

The existing-surface audit covered initialization order, transaction rollback,
legacy-source retention, backup publication, the store's directory-identity
boundary, SQLite's WAL response contract, and the repository's existing OCI
directory-publication helper. Three alternatives were rejected: retaining
best-effort directory sync would silently convert real I/O failures into
success; trusting a `journal_mode=WAL` invocation without its returned value
would admit a different journal topology; and deleting a failed backup would
add destructive recovery work without strengthening the retained legacy
source. The chosen boundary admits unsupported directory sync only on platforms
without that facility, or for the narrowly established `EINVAL`, `ENOTSUP`,
and `EOPNOTSUPP` results. Open or sync failures such as `EIO` propagate. Regular
backup-file synchronization is never downgraded because without it the store
cannot claim that the backup content is durable.

This does not make a filesystem stronger than its documented guarantees. On a
platform without directory synchronization, the backup content is flushed but
crash persistence of its name remains a deployment property. The local-store
boundary still excludes filesystems whose locking or durability behavior is
weaker than SQLite requires. Deterministic tests enforce WAL admission before
schema/migration, file-before-directory sync ordering, rollback and restart
after backup-file `EIO`, the narrow portability errno set, and propagation of
all other directory open/sync failures.

## Boundary

This is a local durability mechanism, not a distributed control-plane claim.
SQLite serializes writers on one shared filesystem. Multi-host execution,
leader election, durable work queues, remote replication, disaster recovery,
and cryptographic audit-log authenticity remain outside this issue. Callers
must not place the database on a filesystem whose locking or durability
semantics are weaker than SQLite requires.

SQLite serialization alone does not make `RuntimeControlPlane`'s cached
snapshot a cross-process compare-and-swap. Until that protocol exists, a local
store permits exactly one live runtime owner. Startup takes a non-blocking,
process-scoped filesystem lease and fails fast if another owner exists;
inherited use after `fork()` also fails. Deployments must therefore run one
ASGI worker and disable development reload for a local control-plane store.
`WEB_CONCURRENCY` or `UVICORN_WORKERS` values other than `1` are rejected at
construction, while the lease catches multiworker launchers that do not expose
their count through either variable.
Independent `LocalControlPlaneStore` maintenance/read instances remain valid,
but they do not grant another process authority to execute target mutations.
`RuntimeControlPlane` is a context manager and also exposes `close()`; callers
must release the first owner before constructing an intentional in-process
restart against the same local store.

On POSIX the lease also holds an advisory lock on the private store directory.
That stable guard remains locked if the human-readable owner file is unlinked or
replaced, while each admitted call still verifies that the path names the
original locked file. Main databases and owner files with multiple hard links
are rejected so two store directories cannot acquire independent owner paths
for one SQLite object. Windows retains its native byte-range owner-file lock and
path-identity validation; the deployment ACL remains responsible for preventing
same-owner replacement of that file.

Public runtime calls take lifecycle admission before reading cached state,
calling a backend, or touching the store. `close()` first stops new admission,
waits for every admitted call (including a blocked backend effect and its
terminal commit), and only then releases the runtime-owner lease. Reads remain
concurrent with an active mutation; the lifecycle counter is distinct from the
mutation lock. Closing from inside an active call fails rather than deadlocking
or releasing authority underneath that call. A call already admitted before
shutdown may re-enter another lifecycle-guarded runtime surface; shutdown blocks
only new outermost calls, so it cannot interrupt an admitted composite action.

The lease and store directory are opened with `O_NOFOLLOW` where the platform
exposes it and are rejected unless pre-open, descriptor, and post-open metadata
identify the same owned filesystem object. No application-owned descriptor is
opened for the main database or its sidecars. The main path is checked before
and after `sqlite3.connect`, uses URI `mode=rw` for every existing database so a
concurrent disappearance cannot recreate it, and is checked again after close.
Only the initial absent path uses URI `mode=rwc`; SQLite creates it before mode,
owner, type, and identity validation and before any schema work. URI paths are
absolute and percent-encode filename delimiters. The store directory is an
owned, non-reparse directory tightened to private POSIX permissions; defending
a Windows path against an attacker who can continuously replace directory
entries requires a native handle-relative ACL boundary outside this local
reference store.

## WAL Sidecar Lock Remediation

The cross-process regression exposed a process-ending `SIGBUS` in SQLite's
`walIndexReadHdr` path. The operating-system report identified a 32 KiB mapped
file whose page-in failed past end-of-file. The incumbent hardening helper was
opening, applying `fchmod`, and closing each `-wal`, `-shm`, and `-journal`
path, including while a WAL connection was live.

That is not a harmless permission check on POSIX. Closing any independent file
descriptor for a file cancels all advisory locks that the process holds on
that file, including locks acquired through SQLite's own descriptor. SQLite's
VFS works around this rule for descriptors it owns, but it cannot account for
an application descriptor. Another process can then treat the WAL shared-memory
file as unlocked and truncate it while the first process still has the WAL
index mapped. SQLite documents this failure mode in
[How To Corrupt An SQLite Database File, section 2.2](https://sqlite.org/howtocorrupt.html#posix_close_bug),
and its [WAL documentation](https://sqlite.org/wal.html) makes the `-wal` and
`-shm` files part of SQLite's own coordination protocol.

The existing-surface audit covered the owned `0700` directory, the `0600` main
database, every application-owned database and sidecar descriptor, connection
lifetime, thread and process writer tests, and SQLite's WAL/VFS ownership. No
schema, operation contract, store topology, or public API change is needed.
The gap is confined to the filesystem boundary bypassing SQLite's lock owner.

Three alternatives were considered:

1. Remove only the live sidecar check. This leaves raw main-database closes able
   to cancel another same-process connection's POSIX locks.
2. Serialize every store connection behind a process-global path lock while
   retaining application database descriptors. This reduces read concurrency,
   adds alias and fork-safe registry state, and still duplicates VFS ownership.
3. Keep descriptor identity on the owned directory, make every SQLite-managed
   path application-descriptor-free, and compare the main database's identity
   around SQLite's own connection. This removes the lock-canceling operation
   while retaining type, owner, mode, no-recreation, and same-file checks. It is
   the chosen design.

Sidecars therefore fail closed when stable metadata shows a symlink/reparse
point, wrong type, foreign owner, or non-private POSIX mode. Their normal
creation or deletion is ephemeral, so disappearance during validation is not
an error. A concurrent unlink may surface as link count zero after pathname
lookup; that state is treated as disappearance, while multiple links remain a
hard failure. The application never raw-opens, closes, or `fchmod`s any
SQLite-managed path. The main database remains fail-closed through metadata
identity comparisons and URI open mode under the descriptor-verified `0700`
directory.

The in-memory store gains the same atomic idempotency-claim behavior under a
re-entrant lock so reference semantics do not depend on which store is
selected. `RuntimeControlPlane` persists a claim before caching it locally;
another process that already owns the key wins, and a different request
fingerprint still fails closed.

The JSON operation and snapshot schemas do not change. The 3.x
`ControlPlaneStore` structural contract remains source-compatible with custom
Python adapters written before crash-atomic terminal commits were added. When
an adapter does not implement the complete optional set
`claim_record(record)`,
`commit_terminal_operation(snapshot, record)` and
`reconcile_interrupted_records(records)`, one compatibility seam emits a
deprecation warning and preserves a lookup-then-save idempotency claim, the
former ordered `save_snapshot` then `save_record` commit, and per-record
startup recovery. Those fallbacks are explicitly not atomic across custom
store instances and will be removed in version 4; partial atomic
implementations also use the coherent legacy mode rather than mixing commit
semantics. If either ordered terminal write raises, the runtime reloads the
adapter's durable snapshot and operation records so both caches reflect the
actual compatibility boundary. The same reconciliation runs when a built-in
atomic method reports an error after its transaction may already have committed.
If either durable reload fails, the runtime is poisoned and rejects every new
call until it is closed and restarted; it never continues from an unknown cache.
Canonical value-free snapshot projection is applied before an idempotent
terminal retry is compared, so deliberate credential redaction does not turn an
exact retry into a false mismatch. The built-in in-memory and local SQLite
stores implement the complete atomic set and never enter the fallback.

## Verification

Acceptance requires regression coverage for:

1. concurrent writers using independent store instances without lost records;
2. exactly one winner for a shared idempotency key;
3. rollback after an injected write failure;
4. restart persistence and indexed lookup;
5. legacy import with retained source, file-before-directory synchronization,
   rollback after backup-sync failure, and verified restartable backup;
6. payload corruption and semantically invalid durable state; and
7. unchanged participant expected-head conflict behavior;
8. injected exits before, during, and after the atomic terminal transaction,
   followed by restart and same-key retry without another backend call;
9. deterministic recovery of orphaned `ACCEPTED` and `RUNNING` records; and
10. rejection of a second runtime owner and post-fork inherited use; and
11. exhaustive snapshot-field coverage and round-trip preservation, including
    participant episode-closure records; and
12. blocked-backend close/reacquisition ordering and closed-state rejection on
    every public runtime surface; and
13. private store/database/sidecar modes plus rejection of unsafe existing
    directory and SQLite paths; and
14. absence of application-owned descriptors for every SQLite-managed path,
    encoded create-versus-existing URI modes, repeated multiprocess writes,
    and the original cross-process API regression; and
15. exact WAL admission before schema or legacy migration plus fail-closed
    directory synchronization outside the narrow portability boundary; and
16. database identity replacement between calls, hard-linked aliases,
    owner-file replacement, admitted-call re-entry during close, post-commit
    cache reconciliation/poisoning, and canonical value-free retry comparison.

The repository policy, API-404 requirement trace, unit/integration suites, and
full verification remain release gates. Issue #1093 separately owns event-loop
offload and bounded execution. Recovery here is deliberately conservative: it
records an indeterminate non-success outcome, not background-job resumption.
