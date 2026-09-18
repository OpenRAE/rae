# Issue 1183 Store Ownership Lease Preflight

Date: 2026-09-18

Issue: #1183. Requirement: API-404. Decision: ADR-104. Work package: CP-5.

## Decision

P1 and P2 admit one `RuntimeControlPlane` owner for one immutable
`(target_scope, run_scope)` before the durable provider inspects or creates its
schema, migrates data, loads derived caches, reconciles operations, or reads
state. The scope comes from trusted runtime composition: `target_scope` is the
existing `RuntimeTarget.name` projection and `run_scope` is supplied once by
the embedder through `ControlPlaneConfiguration`. A request, plan, identity
header, operation record, database payload, or pathname cannot select or
change the store scope.

`LocalControlPlaneStore` remains the P1 provider, `RuntimeOwnerLease` remains
its local process lease, and the existing SQLite `metadata` table remains the
authority for internal provider metadata. Scope binding is internal metadata,
not a new portable DTO or published JSON Schema. Persist the same normalized
`target:<name>` and `run:<id>` identities already carried by
`OperationAdmissionContext`; reuse the bounded run-identity validation in
`raes_contracts.run_scope` rather than introducing another identifier grammar.
`PlanScope.instantiation_id` is not store identity.

The local-store object must be inert with respect to durable contents until
admission. Path preparation needed to acquire the lease may validate or create
the private store directory, but opening SQLite, setting or inspecting WAL,
checking schema/integrity, importing legacy JSON, or reading metadata/state is
post-lease work. A new store records its immutable scope during creation. An
existing unscoped store may be adopted exactly once under the exclusive lease
using the trusted composition scope, before payload reads or legacy migration;
after that, mismatch is a non-mutating startup failure. Scope is never inferred
from the newest operation, snapshot metadata, a plan, or legacy payload.

The durable provider itself must reject access without its live lease. The
runtime lifecycle check is defense in depth, not the provider's only guard:
direct calls to `load_*`, mutation methods, migration helpers, or maintenance
reads cannot bypass admission. The prior issue-1092 allowance for independent
unleased maintenance/read instances is superseded. Offline tooling must use the
same lease and scope admission or remain outside the store.

## Ownership and lifecycle boundary

Keep four authorities distinct:

- `RuntimeOwnerLease` excludes another process and rejects inherited post-fork
  use. It is not the mutation lock, a SQLite transaction, or revision CAS.
- `RuntimeLifecycleMixin` stops new outermost calls and drains every admitted
  read or mutation. It does not grant filesystem ownership.
- `RuntimeMutationAuthority` serializes in-process mutation state cuts. It does
  not replace the lease or provider transaction.
- `SnapshotRevisionConflict` and expected-revision commits catch stale writes.
  They do not make multiple owners supported.

Startup ordering is a contract:

1. validate typed composition and the configured single-worker posture;
2. secure and identity-pin the store directory and acquire the owner lease;
3. open/admit the provider, verify or establish immutable scope, then perform
   WAL, schema, integrity, and migration work;
4. load authoritative state and derived caches;
5. run startup reconciliation; only then may P2 become ready.

Every failure after step 2 closes any opened provider resources before
releasing the lease. Normal shutdown first stops new API/core admission, drains
queued or admitted mutation work and other active calls, closes the provider,
and only then releases the lease. Provider close is idempotent and centrally
owned; operation families and HTTP routes must not close it. If provider close
cannot confirm that its resources are closed, retain the lease and fail closed
rather than admit a replacement owner. Process exit remains the last-resort OS
cleanup, not the ordinary lifecycle.

For P2, compose this order through the FastAPI lifespan and the existing
`_ControlPlaneCallExecutor`; do not rely on garbage collection or on a caller
remembering to close the core after ASGI shutdown. The local profile remains
one application worker with reload disabled. Reuse
`require_single_worker_configuration()` for `WEB_CONCURRENCY` and
`UVICORN_WORKERS`, while the lease remains the authoritative guard for
launchers that do not expose their process count through those variables. Do
not add a second service configuration loader or infer safety from an ASGI
server brand.

## Canonical incumbents

- `control_plane.py`, `ControlPlaneConfiguration`, and
  `control_plane_operation_context.py` own composition, target identity,
  fixed run context, and operation context. Every operation must use the
  control plane's admitted run scope; a request carrying another `run_id`
  fails before claim or disclosure.
- `ControlPlaneStore`, `AtomicControlPlaneStore`, and
  `adapt_control_plane_store()` remain the provider capability boundary. CP-5
  should formalize the existing lease capability there rather than continue
  unconstrained `getattr()` discovery or create a parallel repository/service
  layer. P0's `InMemoryControlPlaneStore` remains non-durable and needs no OS
  lease, but its owning control plane still has one target/run context.
- `LocalControlPlaneStore` and its existing `metadata` table own scope binding,
  schema admission, migration, connections, and provider close. Do not add a
  scope sidecar, second database, snapshot metadata field, or public store DTO.
- `control_plane_store_lease.py` owns the local lease and the worker-environment
  gate. `control_plane_store_paths.py` owns filesystem type, ownership, mode,
  hard-link, same-file, SQLite sidecar, and fsync policy. Keep these checks out
  of `RuntimeControlPlane` and the HTTP adapter.
- `RuntimeLifecycleMixin`, `runtime_owned`, `RuntimeMutationAuthority`, and the
  API call executor own admission/drain behavior. Extend their one lifecycle;
  do not add another lock, active-call counter, or route-local shutdown path.
- `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig.strict_defaults()`,
  `RequestSizeLimitMiddleware`, closed request models, `Diagnostic`, and the
  redacted exception handlers remain the P2 authentication, authorization,
  shape, overload, diagnostic, and error-envelope owners.
- The strict local codecs, SQLite transaction helper, WAL/full-synchronous
  admission, quick check, schema migration, digest validation, snapshot CAS,
  and startup classifier remain mandatory after lease admission. A lease does
  not weaken any of them.

## Cross-cutting gates

### Security and validation

- **Trusted composition:** validate a non-empty bounded target and a value-free
  bounded run identity before filesystem mutation. Normalize once and compare
  exact strings. Do not silently trim, case-fold, stringify, default a corrupt
  persisted value, or let a per-operation `run_id` widen the fixed store scope.
- **Authentication/authorization:** P2 continues to derive identity only from
  constant-time bearer matching or explicitly trusted verified-proxy headers,
  then applies exact target/role/subject checks. Store scope is selected before
  HTTP admission, so no new header, body field, query parameter, token claim,
  or operation id chooses it. One app/store already fixes the run boundary; CP-5
  does not create an HTTP tenant or add a second authorization schema.
- **Secrets:** target/run scope is a value-free identity. Bearer tokens,
  credentials, raw requests, generated values, and backend/provider exception
  text never enter scope metadata, the owner file, audit, diagnostics, logs, or
  receipts. Add no environment variable, secret resolver, command-line token,
  or scope value in process argv.
- **Persisted shape:** scope keys and values are strictly decoded from the
  existing metadata table and must be both present or both absent during the
  one-time adoption case. Partial, duplicate, malformed, or conflicting scope
  metadata fails closed before state payload decoding or migration. This is an
  internal migration rule, not a reason to publish a JSON Schema.
- **Filesystem/OS:** apply the existing private-directory, regular-file,
  current-owner, POSIX `0700`/`0600`, no-symlink/reparse, no-hard-link, and
  `samestat` checks to the directory, owner file, main database, SQLite
  sidecars, legacy migration inputs, and backups as appropriate. Directory and
  owner-file identity must remain tied across acquisition; a path swap cannot
  move the lease to one directory while SQLite opens another. Continue to let
  SQLite own database/sidecar descriptors. On Windows, reparse/type/identity
  checks remain code-enforced and deployment ACLs remain the documented
  permission authority; do not claim POSIX-mode equivalence.
- **Error envelopes:** ownership, scope, path, and provider failures are startup
  or lifecycle failures, not operation receipts. If one reaches a live P2 call,
  reuse the coarse redacted `409`/`500` handling and never use
  `detail=str(exc)`. Public errors, audit, and logs must not expose store paths,
  persisted scope values, PIDs, SQL, lock coordinates, tracebacks, or provider
  exception chains. Do not create a CP-5 exception hierarchy solely for route
  mapping.
- **Observability:** successful ownership is not an audit event and the PID in
  the private owner file is diagnostic only, not authority. Optional lifecycle
  logging uses stable phase/outcome fields with no paths or scope values.
  Operational audit remains distinct from logs, participant observations,
  evidence, and archival run provenance.

### Repository and contract workflow

CP-5 changes an internal provider/lifecycle contract and SQLite metadata, not a
portable wire carrier. It therefore should not edit generated control-plane
schemas or create fixtures for a store-only DTO. If implementation discovers a
real public carrier change, ADR-061, `schema_bundle()`, schema publication,
generated-schema parity, and fixture validation all apply. SQLite scope
adoption follows the existing `LOCAL_OPERATION_SCHEMA_VERSION` migration and
rollback discipline. Repository verification continues through
`.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and
`tools/verify_all.py`; release-please owns `CHANGELOG.md`.

## Verification guardrails

Use real spawned processes for second-owner tests; thread-only tests do not
exercise OS lease semantics. Pin event ordering with instrumented providers:
no schema/migration/load/reconcile event before lease acquisition, and no lease
release before provider close after admitted calls and mutations drain. Cover
new store, same-scope reopen, target mismatch, run mismatch, partial/corrupt
scope metadata, one-time unscoped adoption, every startup failure boundary,
clean handoff, close retry/failure, post-fork use, and P2 lifespan shutdown.

Filesystem tests must cover symlink/reparse points, FIFOs/directories/devices in
file positions, hard links, foreign ownership where observable, permissive
modes, database and owner-file replacement, directory replacement between
validation and open, disappearing paths, and SQLite sidecar races without
opening or closing SQLite-managed files. Preserve the existing WAL, fsync,
rollback, codec-corruption, and database-identity suite while moving its setup
through admitted access.

## Extension seam

The seam is one explicit leased-store admission capability parameterized by
the already-normalized target and run scopes and returning process-bound
authority with `assert_owner()`/`close()` behavior. The local implementation
uses filesystem locks; a future P3 provider may add fencing and distributed
coordination behind a new ADR. Do not add TTL, renewal, leader election, fencing
tokens, multi-owner cache coherence, or distributed clock semantics to CP-5.
Keeping scope input and lease-provider behavior explicit lets a later provider
vary without changing operation DTOs, HTTP authentication, or store payloads.

## Non-goals and anti-patterns

- No P3, high availability, multi-host store, remote database, shared-worker
  service, leader election, automatic takeover, or exactly-once backend claim.
- No target/run/tenant multiplexing, request-selected store, cross-run
  scheduling, or use of authored `deployment_tenants` as API tenants.
- No new public scope schema, duplicate run-id regex, scope sidecar, lease row
  polled from SQLite, global process lock registry, or second exception tree.
- No inference of scope from snapshots, operations, plans, paths, environment,
  authenticated actor, backend manifest contents, or the first HTTP request.
- No unleased read-only/maintenance escape hatch and no method that quietly
  opens the provider on first read.
- No release of the lease before provider close, no shutdown in route handlers,
  no reliance on `__del__`, and no swallowing close failures to make a second
  owner appear available.
- No weakening of filesystem checks, WAL/full-synchronous admission, strict
  codecs, migration rollback, revision CAS, mutation authority, authentication,
  redaction, or startup reconciliation because exclusive ownership exists.
- No change to `RuntimeManager`, backend effect semantics, CP-3 recovery
  classification, CP-6 transaction design, CP-7 idempotency semantics, or
  CP-12 operator health/runbook scope beyond the lifecycle ordering CP-5 needs.
