# Issue 1180 Snapshot Revision CAS Preflight

Date: 2026-09-07

Issue: #1180. Requirement: `API-404`. Parent decision: ADR-104. Work
package: CP-4.

## Decision

The store owns one provider-neutral, non-negative logical snapshot revision.
An empty or migrated store begins at revision zero. Every successful
snapshot-bearing commit advances the revision exactly once, including a
terminal commit whose canonical snapshot bytes happen to equal its predecessor;
an exact idempotent persistence retry and an operation- or audit-only write do
not advance it. The revision is a state-cut concurrency token, not a content
digest.

Snapshot content and revision travel through the runtime and store as one
paired read value. A mutation captures that pair from the authoritative store,
derives and validates its candidate snapshot from the captured content, and
passes the captured revision to the existing store commit method as
`expected_revision`. A successful commit returns the resulting paired value so
the runtime never combines content from one read with a revision from another.
An explicitly supplied `base_snapshot` is semantic input and idempotency
commitment material; it is not revision evidence. It may be used for a mutation
only when it is bound to the exact observed store revision and content.

All snapshot-bearing store methods participate in the same rule:
`save_snapshot`, `commit_terminal_operation`, `commit_control_transition`, and
`commit_participant_transition`. The participant history-head expectations
remain additional semantic guards; whole-snapshot revision CAS does not replace
them. Claim, operation-only recovery, idempotency lookup, and audit append do
not mint a snapshot revision because they do not commit a snapshot.

The built-in stores enforce the comparison inside the same lock or SQLite
transaction that writes the snapshot, operation record, and audit event. The
SQLite logical revision belongs beside the state row, not inside its portable
JSON payload, the database schema-version metadata, the payload digest, an
audit sequence, a row id, or WAL/provider metadata. The v2 local-store schema
requires a governed v2-to-v3 migration that assigns the existing snapshot the
zero baseline without rewriting portable content. A custom mutable store that
cannot atomically persist and compare this revision must fail capability
admission; the compatibility adapter must not synthesize an in-memory revision
or silently retain the pre-CAS fallback.

This is an unavoidable compatibility boundary. The current 3.x documentation
promises that pre-atomic custom `ControlPlaneStore` adapters remain mutable
until version 4, but such an adapter cannot satisfy CP-4. The implementation
must reconcile that promise through the repository's evolution/deprecation
policy and consumer migration guidance; accepting the adapter and weakening CAS
is not a compatible outcome. `initial_snapshot` is also initialization input,
not a cache override: when a store is supplied it must be admitted through the
store's revisioned initialization rule or rejected, never substituted for the
store read only inside `RuntimeControlPlane`.

## Failure and cache semantics

A stale expected revision raises one stable runtime/store conflict condition.
It is a known non-commit result, not an uncertain I/O outcome. The rejected
transaction changes none of the snapshot, operation, idempotency, or audit
records. The runtime may reload its derived views, but it must not call
`reconcile_interrupted_operations()` from the failing commit path: that helper
seals a `RUNNING` operation and would itself change authoritative operation
state. The existing uncertain-store-error path remains for exceptions whose
commit outcome genuinely cannot be established. A stale conflict after a
backend call leaves the prior durable claim for the normal recovery boundary
and fails closed; it never retries the backend.

`RuntimeControlPlane._snapshot` and `_operations` are derived views. Mutation
admission and idempotent receipt lookup already consult the store and must keep
doing so. Public snapshot/status reads and the snapshot-derived operational and
participant views must not rely on a construction-time map. They either read
through the store or use a cache that is rebuilt/invalidate-on-commit and whose
revision is checked against the store. A successful commit publishes the
returned snapshot/revision and affected operation together; a failed or stale
commit discards the candidate and reloads without reconciliation. No mutation
may begin from a cache without first obtaining the authoritative observed
revision.

The HTTP adapter exposes the logical revision on every response whose body was
derived from a runtime snapshot through one documented
`X-RAES-Snapshot-Revision` response header. The value names the snapshot used
to construct that body, not a later snapshot produced by audit or governed-view
crossing work in the same request. Existing participant view
`source_snapshot_ref`/`derived_from_refs` values must likewise stop saying only
`runtime.snapshot.current` and bind the same logical revision. Operation status
responses that do not read snapshot content need no snapshot-revision header.
The current portable response bodies remain governed by their existing models;
do not fork or widen them merely to carry store metadata.

## Canonical incumbents

- `RuntimeDurabilityMixin` remains the single runtime commit/publication and
  store-error reconciliation boundary. Revision success, stale-conflict reload,
  and uncertain-outcome recovery belong there rather than in each operation
  family.
- `ControlPlaneStore`, `AtomicControlPlaneStore`, and
  `ControlPlaneStoreCommitAdapter` remain the provider capability boundary.
  `InMemoryControlPlaneStore` uses its existing `RLock`; `LocalControlPlaneStore`
  uses the existing `_transaction()`/SQLite WAL boundary and
  `migrate_sqlite_schema()`.
- `commit_control_transition()` and `commit_participant_transition()` remain the
  templates for atomic snapshot/record/audit publication. Their
  `_require_expected_control_head()` and `_require_expected_history_heads()`
  checks are retained alongside revision CAS.
- `RuntimeSnapshot`, `RuntimeSnapshotEnvelope`,
  `RuntimeSnapshotEnvelopeModel`, `_snapshot_payload()`/
  `_snapshot_from_payload()`, and `_snapshot_model()` remain the portable
  content and validation owners. Revision state must not create a second
  snapshot schema or serializer.
- `_call_backend_apply()` and its target-shape, backend-result, snapshot
  transition, participant-state/history, realization-authority, and credential
  sanitization checks remain the only acceptance path for backend-produced
  snapshot content. CAS validates concurrency; it does not duplicate semantic
  validation.
- `runtime_owned`, `_operation_lock`, `RuntimeOwnerLease`, and the HTTP
  `_ControlPlaneCallExecutor` remain lifecycle and serialization safeguards.
  Revision CAS is the store safety net and does not turn any of those into a
  distributed coordination mechanism.
- `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig.strict_defaults()`,
  `RequestSizeLimitMiddleware`, the shared FastAPI error handlers, `Diagnostic`,
  and `AuditEvent` remain the authentication, request-shape, failure, and
  observability incumbents.

## Cross-cutting gates

- **Contract and shape:** portable snapshot content continues through the
  closed `ContractModel`/`RuntimeSnapshotEnvelopeModel` surface, exhaustive
  durable codec field guard, and
  `require_participant_autonomous_runtime_snapshot()`. The logical revision has
  one runtime/store type and rejects booleans, negatives, coercion, missing
  values, and overflow/provider sentinels at the provider boundary. It is not
  added to `raes_contracts.versions.RUNTIME_SNAPSHOT_SCHEMA_VERSION` or the
  generated `runtime-snapshot-v1` body schema.
- **Authentication and authorization:** HTTP revision disclosure happens only
  after `_ControlPlaneApiAuth` authenticates the bearer or explicitly trusted
  proxy identity, enforces exact target binding, and authorizes a read role.
  Possession or guessing of a revision grants no read, mutation, receipt, or
  idempotency authority. Current HTTP mutations obtain the expected revision
  from the authenticated control-plane/store path, not from an untrusted
  caller header.
- **Secrets and configuration:** revision values are generated by the store and
  contain no target, run, actor, credential, path, request, or backend data.
  Existing account-credential/value-free request and backend-result sanitizers
  remain in force. CP-4 introduces no environment binding, secret resolver,
  configuration field, serve command, or process argument.
- **Persistence and OS exposure:** the SQLite revision uses the incumbent
  owner-only directory/database, identity-pinned opens, WAL admission, full
  synchronous transaction, integrity, and backup/migration rules. No revision,
  database path, SQL text, WAL coordinate, lease identity, or migration detail
  enters argv, portable JSON, diagnostics, audit details, or logs. CP-5 still
  owns moving lease acquisition ahead of store inspection and migration.
- **Error envelope:** use one narrow stale-revision conflict condition rather
  than a parallel exception hierarchy. HTTP maps it to a stable coarse `409`
  response without `str(provider_exception)`, expected/current values, SQL, or
  backend text. The stable redacted `422`, `500`, and overload `503` behaviors
  are unchanged. A stale conflict produces no success audit and no compensating
  audit mutation.
- **Observability:** optional operational logging uses the existing module
  logger pattern and bounded, value-free fields. The revision header is an
  observation token, not authorization, audit provenance, archival run
  provenance, or evidence. Cache rebuild and conflict metrics must not include
  snapshot payloads or provider exceptions.
- **Repository workflow:** any local database schema change uses the incumbent
  migration/version gate; any actual published-schema change would require
  `schema_bundle()`, the schema publication manifest, generated-schema checks,
  and ADR-061 handling. This decision intentionally avoids such a change. The
  canonical completion graph remains `.ground-control.yaml`, `noxfile.py`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and
  `tools/verify_all.py`; release-please, not the feature, owns `CHANGELOG.md`.

## Extension seam

The required seam is the paired logical snapshot read plus the
`expected_revision` keyword on every snapshot-bearing commit. It is independent
of the SQLite implementation and leaves future providers free to choose their
transaction mechanism while preserving one provider-neutral integer state-cut
sequence. A future coordinated profile adds fencing/ownership through ADR-104's
coordination seam; it does not reinterpret a lease token, content digest, ETag,
or provider transaction id as the snapshot revision. If a future HTTP mutation
accepts client CAS, it translates one authenticated, strictly parsed conditional
request value into this same parameter rather than creating a second revision
system.

## Verification boundary

The acceptance suite must exercise the same store contract against the
in-memory and local SQLite implementations. It must interleave two observed
reads and prove that only one distinct snapshot-bearing commit can consume the
shared revision, for terminal, control-transition, participant-transition, and
direct snapshot commits. Each stale case snapshots all authoritative tables or
collections before the attempt and proves snapshot, operation, idempotency, and
audit state are byte-for-byte/logically unchanged afterward. It must separately
prove exact terminal retry is a non-incrementing no-op.

Runtime tests must inject stale derived snapshot and operation maps, commit
through an independent store handle, and prove admission/receipt lookup and
public reads resolve from authoritative state. A CAS conflict must prove the
candidate is discarded, caches are refreshed without sealing the operation,
and no backend replay or success audit occurs. Migration tests must prove a v2
database receives one valid baseline revision while its portable snapshot
payload remains unchanged, and capability tests must reject a mutable legacy
adapter that cannot perform atomic CAS.

HTTP tests must cover every snapshot-derived GET, prove its response header and
participant source references identify the exact state cut used for projection,
and retain the existing authentication, target-binding, and redacted-error
behavior. Negative leakage tests must validate response bodies with their
existing closed models and inspect snapshot payloads/metadata, operation and
audit carriers, logs, and migration output for absence of logical or
provider-native revision fields.

## Gotchas and anti-patterns

- Do not put the revision in `RuntimeSnapshot.metadata`, entry payloads,
  operation details, audit details, or the published backend/conformance
  snapshot model.
- Do not use snapshot equality, canonical digest, SQLite row id, audit sequence,
  operation schema version, participant state revision, history head, lease
  generation, or WAL frame as the CAS token.
- Do not compare before opening the write transaction or perform
  check-then-write across two store calls. The comparison and every affected
  write must share one atomic boundary.
- Do not update an in-memory candidate before the store commits, and do not
  retain a candidate after a stale or failed commit.
- Do not let exact terminal retry increment the revision, and do not let two
  distinct terminal commits based on one revision both succeed merely because
  their snapshot bytes are equal.
- Do not replace participant history-head checks with snapshot CAS; they guard
  different concepts.
- Do not treat caller `base_snapshot`, a response header, an idempotency key, or
  an operation id as authority by possession.
- Do not route a stale conflict through uncertain-commit recovery, automatic
  backend replay, or post-hoc audit. CAS atomicity does not prove an external
  backend effect happened exactly once or did not happen.
- Do not preserve mutable legacy-store behavior by inventing a process-local
  revision. A non-atomic provider is an admission failure, not a degraded CAS
  profile.
- Do not let `initial_snapshot` shadow a different durable snapshot or create a
  cache/store split at construction.
- Do not stamp the revision observed after a governed read-side transition onto
  a response that was projected from the preceding state cut.

## Non-goals and boundaries

- CP-4 does not implement CP-2's actor-bound terminal audit transaction, CP-5's
  lease-ordering change, CP-7's actor-scoped idempotency redesign, or CP-8's
  broader served-profile authorization redesign. Its signatures and read seam
  must remain compatible with those additions.
- No P3, multi-host, multi-writer, leader-election, fencing, replication,
  scheduling, or highly available claim is introduced. CAS detects a stale
  writer; it does not admit one.
- No change is made to SDL, processor planning, backend protocols, runtime
  snapshot meaning, participant semantic revisions, evidence/run provenance,
  or exactly-once backend-effect semantics.
- No new database, cache service, environment/configuration loader, public
  snapshot body schema, exception hierarchy, audit schema, or deployment unit
  is justified by this issue.
