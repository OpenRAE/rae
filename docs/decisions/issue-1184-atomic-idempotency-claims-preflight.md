# Issue 1184 Atomic Idempotency Claims Preflight

Date: 2026-09-18

Issue: #1184. Requirement: API-404. Decision: ADR-104. Work package: CP-7.

## Decision

The authoritative store owns idempotency resolution. One store operation must
either create the candidate operation claim or return the exact incumbent; no
runtime path may perform `find_by_idempotency()` followed by a later claim.
The in-memory provider performs this operation under its existing `RLock`, and
the local provider performs it in its existing `BEGIN IMMEDIATE` transaction.
No transaction spans validation callbacks or a backend invocation.

For P0--P2, target and run are already fixed by store admission. Within that
store, the unique claim identity is `(actor_id, operation_kind,
idempotency_key)`. The incumbent's authorization scope, target/run context,
request commitment, parent-operation relation, and other immutable operation
context are exact-match replay conditions. They are not additional uniqueness
dimensions: in particular, putting `request_commitment` in the unique key
would incorrectly turn reuse of one key for a changed request into a second
operation instead of a fail-closed conflict. An empty client key creates no
deduplication claim.

The same non-empty key used by another actor or operation kind is an independent
claim and cannot reveal whether another claim exists. A target or run uses a
different admitted store and cannot select another scope through a request.
When the composite identity matches, the store returns the incumbent only if
the complete immutable replay conditions match. Otherwise it returns one
coarse conflict without the incumbent record, operation id, state, actor, or
commitment. The runtime rechecks the returned incumbent before exposing its
receipt; possession of a key, operation id, or old receipt is never authority.

`OperationAdmissionContext` remains the sole immutable authority and semantic
context carried by receipts and statuses. Request commitment construction stays
in `control_plane_operation_context.py` and uses
`raes_contracts.canonical.canonical_json_digest()` over a value-free semantic
projection with a stable, versioned, operation-specific domain separator. The
projection includes every execution-affecting input, including an explicit
base snapshot and, for participant operations, the applicable policy/support
resolution and state-cut coordinates. The digest is stored; the raw request
projection is not. Caller-supplied `request_fingerprint` values are not
authority and must not create a parallel commitment convention.

The sensitive exact-retry proof defined by the formal model remains ephemeral.
It uses the same canonicalizer over the exact in-memory projection, is indexed
by the full claim identity or operation id rather than a bare client key, and
never enters SQLite, portable carriers, audit, diagnostics, logs, or responses.
After restart, a credential-bearing retry whose equality cannot be proven
continues to fail closed with a new key required.

## Boundaries and canonical incumbents

- `raes_contracts.operation_lifecycle.OperationAdmissionContext`,
  `OperationKind`, `OperationReceipt`, and `OperationStatus` remain the
  portable contract owners. Their existing closed Pydantic carriers and
  published control-plane schemas are not duplicated or widened for a
  store-private claim key.
- `control_plane_operation_context.py` and
  `raes_contracts.canonical` own semantic projection, RFC 8785/JCS bytes, the
  `sha256:` representation, value-free credential projection, and exact
  ephemeral retry proof. Operation families supply their semantic payload to
  this boundary; they do not hash JSON independently.
- `RuntimeAdmissionMixin` owns claim/replay interpretation and denial audit.
  `ControlPlaneStore`, `AtomicControlPlaneStore`, and
  `ControlPlaneStoreCommitAdapter` own the provider capability. The incumbent
  atomic claim method must be strengthened rather than adding a repository,
  service, or cache-side deduplicator.
- `InMemoryControlPlaneStore` and `LocalControlPlaneStore` remain the two
  reference providers. The former uses its existing lock and the latter its
  WAL/full-synchronous transaction, admitted immutable scope, strict record
  codec, integrity digests, and schema migration boundary.
- `RuntimeMutationAuthority` remains the single in-process mutation authority.
  Atomic store claims are the correctness primitive and do not justify a
  route-local key lock, per-operation-family lock, process-global registry, or
  lock held over backend work.
- Generic provisioning/orchestration/evaluation execution, workflow
  cancellation and timeout reconciliation, participant actions, supervisory
  control, crossings and final-sink dispositions, and indeterminate resolution
  all use the same claim semantics. The direct idempotency lookups and custom
  SHA-256/scoped-key conventions in `participant_control_mediation.py`,
  `participant_crossing_mediation.py`, and
  `participant_crossing_records.py` are incumbents to converge, not precedents
  for another idempotency layer. Unrelated history-head and evidence digests
  remain distinct concepts.
- `RuntimeDurabilityMixin`, `SnapshotState`, and `_project_snapshot_read()` own
  derived-state publication and revision-bound projections. `_snapshot_state`
  and `_operations` are rebuildable views only. Status, observation-result,
  operational-summary, snapshot, and snapshot-derived participant reads must
  read the store or use the existing pinned projection rule; none may trust a
  construction-time or prior-request map.
- `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig.strict_defaults()`, the
  closed request models, `RequestSizeLimitMiddleware`, and
  `_ControlPlaneCallExecutor` remain the P2 authentication, authorization,
  shape, size, offload, overload, and cancellation boundaries. Idempotency does
  not create a second HTTP security policy.

## Authorization and disclosure

A duplicate receipt is disclosed only after the current typed identity has
been authenticated, exactly target-bound, role/subject authorized for the
requested operation, and matched to the original immutable actor and
authorization scope. A privileged operation-status read, where allowed by the
existing operator/auditor policy, is separately authorized in the core against
the persisted context; route-level possession of an operation id is
insufficient. Participant operations retain their control-subject or
audience-subject checks.

`get_operation()` must load the authoritative record and apply that core read
policy before returning status. Unknown and unauthorized operation ids use an
indistinguishable coarse response so the endpoint is not an existence oracle.
`get_snapshot()` and every snapshot-derived route continue to require an
authenticated target-bound read role and return the revision of the exact
projected state cut. The fixed store scope is not a substitute for actor or
participant authorization.

Core P0/P1 calls retain the trusted-embedder identity supplied by the existing
identity boundary. They must not silently treat an arbitrary caller string,
operation id, or idempotency key as that embedder authority.

## Persistence and migration

The local SQLite uniqueness rule must represent the composite claim identity,
not the current bare `idempotency_key` index. This is an internal provider
schema change governed by `LOCAL_OPERATION_SCHEMA_VERSION` and the existing
transactional migration/rollback path; it is not a portable JSON Schema
change. The record codec remains strict and lossless, and store admission still
precedes schema inspection or migration.

Existing records already carry target/run, actor, authorization scope,
operation kind, and request commitment in their immutable context. Migration
must derive claim scope only from those validated fields and the admitted store
metadata. It must not infer actor or kind from an operation id, audit entry,
path, latest snapshot, or HTTP data. Ambiguous, malformed, duplicate, or
cross-scope predecessors fail startup without reassignment or deletion.

Some participant records persist a one-way, pre-CP-7 derived key rather than
the original client key. That information cannot be reconstructed. Migration
must preserve those claims as explicit legacy opaque identities and keep exact
legacy retries fail-closed or compatibility-resolvable at one bounded store
boundary. It must not reinterpret the digest as a raw client key, silently
mint a new operation, or retain participant-specific lookup logic in the live
claim path. Durable terminal and indeterminate claims are never discarded to
simplify migration.

The duplicated private `request_fingerprint` column/payload cannot acquire a
second meaning. For ordinary operations it currently duplicates
`context.request_commitment`; participant code currently overloads it with a
different semantic hash. The private migration must converge these meanings
on the canonical context commitment while retaining any additional
participant state-cut coordinates in their existing typed fields. No public
receipt/status schema change is expected. If implementation discovers a real
portable carrier change, ADR-009/ADR-061, `schema_bundle()`, the schema
publication manifest, fixtures, and generated-schema parity apply in full.

## Cross-cutting gates

### Security, shape, and secrets

- HTTP size admission remains before body parsing. FastAPI/Pydantic closed
  request models validate the request before domain reconstruction, and the
  core validates one bounded non-empty key shape (empty remains the explicit
  no-idempotency case). HTTP, direct-core, participant, and workflow paths use
  that one validator; no route-only length or character policy is introduced.
- Bearer tokens continue through constant-time resolution; proxy identities
  remain opt-in and trusted only when the proxy strips caller-supplied identity
  headers. Exact target binding, role checks, participant control-subject
  bindings, and audience bindings all precede receipt disclosure.
- `ControlPlaneConfiguration` and `PlanScope` continue to validate trusted
  target/run composition. No header, request body, query value, environment
  variable, operation id, or idempotency key selects a store, target, run, or
  tenant.
- Credential material remains behind
  `value_free_account_placement_payload()`, exact sensitive proof remains
  memory-only, and backend output still passes the incumbent validators and
  sanitizers. Tokens, raw keys, raw requests, exact fingerprints, credentials,
  host paths, SQL, and provider exception text do not enter diagnostics,
  audit details, logs, fixtures, health output, or portable state.
- CP-7 introduces no environment binding, secret resolver, serve command, or
  process argument. The only relevant environment gate remains the incumbent
  single-worker validation for `WEB_CONCURRENCY` and `UVICORN_WORKERS`; secrets
  and keys are never placed in argv.

### Error envelopes and observability

One narrow claim-conflict signal maps through the existing HTTP conflict path
to a fixed, value-free `409` response. It must not be wrapped in a new public
exception hierarchy, and the submission routes must not use
`detail=str(provider_exception)` for this or an unexpected store error.
Authentication/authorization, redacted validation `422`, overload
`503`/`Retry-After`, and redacted unexpected `500` behavior remain unchanged.
Unauthorized and absent status reads disclose the same coarse result.

The existing terminal transaction remains the only successful-operation audit
authority, so concurrent retries cannot append multiple terminal audits.
Admission denials stay on the bounded rejection-audit path. Optional logs and
metrics use module loggers and bounded outcome labels such as new/replay/
conflict; they contain no raw key, commitment, actor scope, request material,
operation status, path, SQL, or provider exception. Audit, logs, participant
observations, captured evidence, and archival run provenance remain separate
surfaces under ADR-065 and ADR-066.

### Filesystem and runtime layers

The local store continues to require its owner lease, private directory and
database permissions, no symlink/reparse/hard-link aliases, identity-pinned
opens, SQLite-owned sidecars, admitted WAL mode, full synchronous writes,
integrity checks, and provider-before-lease shutdown. Atomic idempotency does
not make multiple ASGI workers or multiple control-plane owners supported, and
the database index is not a P3 coordination or fencing mechanism.

## Coherence and failure semantics

A store claim is authoritative before any backend call. The winning operation
alone may invoke the backend; every exact concurrent loser returns its receipt
after authorization and never invokes. A process loss after claim retains the
claim and follows CP-3 reconciliation; retry never replays an unclassified
effect. Store transactions do not imply exactly-once external effects.

Successful claims and commits refresh or invalidate derived maps under the
existing short publication mutex. Claim conflict, revision conflict, and known
rollback reload derived state without reconciliation or backend replay.
Unknown commit outcomes retain the existing readback-and-poison discipline.
The ephemeral sensitive-proof map is not a durable cache and its intentional
loss on restart must not be "repaired" by persisting secret-bearing equality
material.

Authoritative-read tests must cover `get_operation()`, `observation_execution()`,
`get_snapshot()`, the operational summary, and snapshot-derived participant
views. A response projection owns one exact snapshot/revision cut until it is
complete; a refresh cannot splice records or content from a later revision
into that response.

## Verification guardrails

Exercise the same claim contract against the in-memory and local providers.
Concurrent equal claims must produce one operation id, one backend invocation,
one terminal record, one terminal audit, and one snapshot transition. Repeat
the assertion after clean restarts and at claim/invocation/terminal kill
boundaries. Local provider concurrency tests must use real transactions;
runtime profile tests still respect the one-owner lease.

Adversarial cases cover same key with a different commitment, authorization
scope, parent relation, actor, operation kind, target, and run. Changed
commitment or scope fails without revealing the incumbent; actor/kind and
target/run isolation neither collide nor disclose. Guessing an operation id,
presenting another actor's receipt, and replaying through a participant route
must not return cross-actor status. Credential-bearing retries prove exact
same-process success, changed-secret rejection, restart rejection, and absence
of raw/exact material from all durable and observable surfaces.

Inject stale `_operations`, stale `_snapshot_state`, and forged receipt-cache
entries, then prove all public status/snapshot projections use the store or the
pinned revision rule. Rebuild tests cover successful commit, conflict,
uncertain store error, restart, and migration. Migration tests cover generic
raw-key predecessors, participant opaque derived keys, duplicate composite
claims, corrupt context, scope mismatch, rollback, and retained terminal and
indeterminate claims.

## Extension seam

The extension seam is one provider-neutral atomic claim capability driven by
the existing immutable `OperationAdmissionContext`, a validated client key,
and an operation-specific canonical semantic projection. Adding another
`OperationKind` supplies a new domain-separated projection and authorization
policy but does not add a table, index convention, cache, serializer, or claim
workflow. A future P3 provider implements the same outcome under its accepted
coordination/fencing contract; it does not change claim identity or make a
shared database alone sufficient.

## Non-goals and anti-patterns

- No P3, multi-owner service, remote shared database, tenant multiplexing,
  leader election, fencing, distributed cache, durable broker, automatic
  backend replay, or exactly-once external-effect claim.
- No new public idempotency DTO, receipt/status version, snapshot metadata,
  schema family, repository layer, exception hierarchy, authorization stack,
  serializer, digest convention, operation state, or audit/evidence carrier.
- No uniqueness on a bare key, on `(key, request_commitment)`, or on a
  participant-composed hash that hides actor/kind policy from the store.
- No lookup-then-save path, cache-first receipt, check protected only by the
  GIL/application lock, or SQLite transaction held across policy/backend work.
- No use of operation ids, receipts, keys, commitments, snapshot revisions,
  history heads, audit sequences, or database row ids as authorization.
- No raw-body hashing, `json.dumps(..., default=str)` commitment, caller-owned
  fingerprint authority, unversioned domain separator, or persisted exact
  sensitive fingerprint.
- No silent deletion/rekeying of legacy claims, defaulting malformed context,
  or migration that lets a formerly claimed key invoke the backend again.
- No weakening of planner authorization, backend-result validation, credential
  sanitization, mutation authority, revision CAS, lease admission, startup
  reconciliation, strict codecs, filesystem hardening, bounded queues, or
  redacted errors in the name of idempotency.
- No change to SDL authoring, processor compilation, backend effect semantics,
  `RuntimeManager`, experiment-run provenance, captured evidence, TLS, secret
  resolution, backup scheduling, or deployment supervision.
