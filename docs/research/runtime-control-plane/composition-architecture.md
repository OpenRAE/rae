# Runtime Control-Plane Composition Architecture

Date: 2026-08-17

Parent issue: [#1151](https://github.com/OpenRAE/rae/issues/1151)

This document expands ADR-104 into component boundaries, ownership, data and
control flow, lifecycle, persistence and coordination interactions, security
boundaries, and failure and recovery behavior. Nothing here is claimable
before its implementation work package (see the
[implementation program](implementation-program.md)) lands with tests.

The [issue #1348 decision](../../decisions/issue-1348-operation-lifecycle.md)
and [formal supplement](../../../specs/formal/runtime-control-plane/supervision.md)
refine supervision and recovery. RAE remains the shared product runtime driving
backends; profiled control-plane storage is one component of that runtime.

## 1. Position in the RAES stack

SDL authoring and the processor produce compiled plans; backends realize
effects; `RuntimeTarget` binds a backend to a runtime. The control plane
sits between an embedding application and those boundaries: it accepts
operation submissions against a target, records their lifecycle, holds the
authoritative runtime snapshot, mediates participant transitions, and emits
audit evidence. It owns bookkeeping and admission — never backend effect
semantics, plan compilation, or SDL meaning. Direct `RuntimeManager.apply()`
and direct backend calls bypass this boundary and carry none of the profile's
durability, idempotency, audit, or recovery guarantees.

## 2. The contract and its implementations

`RuntimeControlPlane` is the portable contract: submit an operation, obtain
an idempotent receipt, read snapshots, drive participant transitions, and
observe audit events. Conforming implementations differ only in the
guarantees their operating profile declares. The contract carries a
capability surface (work package CP-10) so an embedder can interrogate the
active profile's guarantees and nonclaims instead of assuming them.

## 3. Operating profiles

| Profile | Ownership | Durability | Intended embedders |
| --- | --- | --- | --- |
| P0 ephemeral | one process, no admission | none — loss of process is loss of run | hermetic tests, single-scenario embedding |
| P1 local durable | one process, lease-admitted | crash-consistent authoritative store | local tools, RAE/env-pack/ETV embedding, air-gapped hosts |
| P2 served | one owning service process, many clients | P1 core | shared local services |
| P3 coordinated | multiple processes or hosts | seam only | none — explicit nonclaim pending a future ADR |

A profile is a declaration, not a mode switch: P1 and P2 are the same core
with the adapter in front; P0 is the in-memory store under the same
contract; P3 exists only as the lease, revision, and coordination seams the
lower profiles already exercise.

Every P0--P2 composition is one `RuntimeControlPlane`, one `RuntimeTarget`, and
one isolated target/run store scope. The target owns backend identity and
capabilities; the control plane owns operations and live participant state;
the embedder owns the mapping from scenario/run/caller context to that
composition. "Many clients" at P2 is not target, run, or service-tenant
multiplexing. ADR-087 deployment tenants remain authored scenario topology and
are not API tenants. A durable store pins the target and embedder-supplied run
scope at creation and refuses a mismatched reopen.

## 4. State authority

- **Authoritative**: runtime snapshots, operation records, idempotency
  claims, participant transition records. They live in the profile's store
  and change only inside its transactions.
- **Derived**: in-memory snapshot and operation maps, receipt caches,
  indexes. Rebuildable from authoritative state on demand; each cache that
  survives a mutation boundary carries an explicit coherence rule
  (invalidate-on-commit under revision CAS). A derived structure never
  answers admission or receipt queries on its own authority.
- **Evidentiary**: append-only audit events with provenance. Never
  rewritten; terminal audit events commit in the same transaction as the
  state they describe. They are operational audit under ADR-066, not
  participant observations, captured evidence, or the ADR-065 archival
  `experiment-run-v1` record. Append-only is not a tamper-evidence claim.
- **External**: backend effects. The control plane records intent and
  observed outcome; where neither is observable it records indeterminacy.
  No control-plane read infers an external effect.

## 5. Operation lifecycle and control flow

1. **Admission**: the submission is validated against the target and an
   idempotency claim is taken — a unique insert in the authoritative store,
   scoped by store, authenticated actor, and operation kind. A duplicate claim
   returns the recorded receipt only after the same authorization checks; it
   never re-invokes the backend.
2. **Write-ahead claim**: the operation record becomes durably `RUNNING`
   before the backend is invoked.
3. **Invocation**: the backend call executes outside any store transaction;
   the store never holds locks across external effects.
4. **Terminal commit**: exactly one transaction writes the resulting
   snapshot (revision-checked), the terminal operation record, and the
   actor-bound audit event. This discipline covers generic execution, workflow
   cancellation and timeout reconciliation, rejection records, participant
   actions, and participant crossings; an operation family may not keep a
   separate save-snapshot/save-record workflow.
5. **Receipt**: idempotent reads return the committed terminal state from
   the store or a coherence-ruled cache (CP-7).

## 6. Failure and recovery behavior

After process loss, storage loss short of media failure, cancellation, or
timeout, startup reconciliation (CP-3) classifies every non-terminal
operation:

- **effect-absent**: the claim exists but the backend verifiably did not
  act; the operation fails closed with a stable diagnostic.
- **effect-applied**: backend observation confirms the effect; state is
  advanced from observation and committed atomically.
- **indeterminate**: neither is establishable; the operation terminates in
  the explicit indeterminate state, its idempotency claim is retained so
  client retries cannot blindly re-invoke, and the embedder-visible surface
  requires a deliberate resolution action.

Nothing replays automatically. Host loss and network partition reduce to
process loss at P0–P2 because ownership is single-process; the partition
cases that require distributed reasoning are exactly the P3 nonclaim.

For the supervision design, every external callback, including recovery
observation, consumes a bounded operational budget. An absent-effect observation
is conclusive only when no late effect remains possible. Known partial effects
require validated residual state; missing carrier support or unproved cessation
requires indeterminacy. Store acknowledgement loss instead uses atomic readback
and poisoned readiness. Neither case authorizes another invocation.

Request cancellation does not cancel a worker thread or prove that a backend
effect stopped. A client-side timeout or broken connection leaves the durable
operation authoritative; the caller retries with the same scoped idempotency
key. Restoring a backup can make control-plane state older than external
effects, so readiness stays closed until the same recovery classification
completes. An indeterminate terminal record is immutable; deliberate operator
resolution creates a linked operation and audit event rather than rewriting
history.

Credential-bearing retries after restart still fail closed when the existing
ephemeral exact-input proof is unavailable; authorized status retrieval remains
separate. A fresh key does not authorize repeated work. Administrative snapshot
acceptance cannot establish cessation or discharge evidence required for reuse.
Workflow retry and SCE-007 attempt policy govern repeated work; resumption needs
an admitted continuation boundary, and a new trial needs its own allocation.

## 7. Concurrency control

- **In-process**: one control-plane mutation authority serializes every
  mutation path within the owner. Path-local locks and the HTTP adapter lock
  are subordinate safeguards, not separate consistency domains.
  The supervision design separates short state commits from retained execution
  reservations so a blocked external call cannot monopolize supervisory access.
  Current code still retains its logical permit across those calls; the design
  is not evidence of deployed bounded interruption. Conflicting effects stay
  excluded until cessation and reconciliation are established.
- **Cross-process**: the store lease (CP-5) admits exactly one owner; a
  second process fails closed at admission rather than corrupting state.
- **Optimistic safety net**: snapshot commits carry a revision and commit
  by compare-and-swap (CP-4), so even an ownership bug cannot silently
  overwrite; the stale writer errors.
- **Idempotency**: unique claims in the store are the concurrency-safe
  dedup primitive; caches are advisory.

## 8. Persistence and coordination seams

The profile composition requires transactions, unique claims, revisions, a
lease, audit, and recovery observation through explicit provider capabilities.
Providers must verify granted admission results (journal mode, sync level)
rather than trusting requests — the WAL admission finding from issue #1092,
generalized. The clock, audit sink, lease provider, and a future coordination
provider are separate seams so `RuntimeControlPlane` never encodes a deployment
topology. Backend effect observation extends the existing
`RuntimeTarget`/backend protocol and manifest pattern; a persistence provider
never calls backend-native APIs. A provider that cannot supply a required
capability fails construction; profiles never degrade silently.

## 9. Security boundaries

Authenticated and authorized access (API-404) terminates at the profile
boundary: P0/P1 inherit the embedding process's identity and the store's
filesystem protections (owned directories, tightened modes, identity-pinned
databases per the PR #1136 hardening); P2 adds the HTTP adapter's
authentication and target binding (#1090, #1133) in front of the same core.
P2 retains strict defaults, bounded pre-parser request admission, bearer or
explicitly trusted proxy identity, role checks, and participant subject/audience
bindings. The proxy must strip caller-supplied identity headers, and the store
must not treat operation ids or idempotency keys as authorization.

P0/P1 trust their embedding process to authenticate callers, but the embedder
still supplies a typed actor context for each mutation. P2 derives that same
context from authenticated identity before calling the core; transport routes
must not call identity-less mutation methods or append successful audit after
the core returns. Admission persists immutable actor, authorization, target/run,
operation-kind, and request-commitment context. Retry, receipt, status,
reconciliation, and resolution paths authorize against that context, and the
terminal audit becomes visible in the same transaction as terminal state.
Admission denials with no operation use the bounded rejection-audit path.

Bearer tokens, storage credentials, host paths, raw request bodies, backend
exception text, and encryption material are operator data. They never enter
snapshots, operation records, audit details, diagnostics, logs, migrations,
fixtures, or health output, and never travel in process argv. Scenario
credential egress continues through the existing account-credential
sanitizers. Stable redacted HTTP 422/500 envelopes remain authoritative;
provider failures map to coarse response or `Diagnostic` codes rather than
exposing exception strings. P2 is one application worker unless and until P3
exists. TLS termination, proxy trust, service-account privileges, and process
supervision remain deployment responsibilities.

## 10. Lifecycle, configuration, and operations

The embedder owns process lifecycle, configuration, upgrade sequencing, and
backup scheduling; the control plane owns schema versioning, one-time
migration from superseded stores (with durable, fsynced backups), integrity
verification at startup, and refusing to open state it cannot verify.
Configuration enters as explicit typed composition input; the core does not
parse environment variables or secrets, and the current repository has no
serve command. Startup acquires the owner lease before schema inspection,
migration, cache loading, or reconciliation, and becomes ready only after all
four succeed. Shutdown stops admission, drains mutation, commits or records
indeterminacy, closes the provider, then releases the lease. Scenario time is
not the operational clock used for leases, deadlines, audit, or recovery.
Operational health and the indeterminate-operation runbook are CP-12.

## 11. What this composition does not do

It does not make two application workers coherent over a shared database
(P3 nonclaim), does not give P0 any durability, does not let the HTTP
adapter scale writes beyond its single owner, and does not decide a
specific storage engine here — CP-6 lands the P1 reference store under the
contract, and any conforming provider may replace it. It also does not provide
multitenancy, cross-target or cross-run stores, exactly-once backend effects,
automatic replay, a durable broker, a TLS endpoint, a secret resolver, or a
replacement for archival run provenance and evidence contracts.
