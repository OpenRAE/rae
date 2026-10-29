# Runtime control-plane setup architecture

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
effects; `RuntimeTarget` binds a backend to a runtime. The control plane sits between the host and those boundaries.
It accepts requests for a target and records their state.
It holds the sole runtime snapshot.
It controls participant transitions and emits audit evidence. It owns bookkeeping and admission — never backend effect
semantics, plan compilation, or SDL meaning. ADR-104 §11 and the
[issue #1660 preflight](../../decisions/issue-1660-runtime-lifetime-controller-preflight.md)
replace the earlier independent-manager disposition: the manager's lifecycle
work must use this same authority. Direct backend calls do not inherit profile
guarantees or provide an alternate continuation path around the runtime owner.

## 2. The contract and its providers

`RuntimeControlPlane` is the portable contract: submit an operation, obtain
an idempotent receipt, read snapshots, drive participant transitions, and
observe audit events. Conforming providers differ only in the
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

A profile states which guarantees apply.
P1 and P2 use the same core.
P2 adds the HTTP adapter.
P0 uses the in-memory store under the same contract.
P3 is not implemented.
Its seams are the lease, revision, and coordination hooks used by the lower profiles.

Every P0--P2 setup is one `RuntimeControlPlane`, one `RuntimeTarget`, and
one isolated target/run store scope. The target owns backend identity and
capabilities; the control plane owns operations and live participant state;
the embedder owns the mapping from scenario/run/caller context to that
setup. "Many clients" at P2 is not target, run, or service-tenant
multiplexing. ADR-087 deployment tenants remain authored scenario topology and
are not API tenants. A durable store pins the target and embedder-supplied run
scope at creation and refuses a mismatched reopen.

## 4. State authority

The store is the source of truth for snapshots, operations, claims, and participant records.
These records change only through store transactions.
In-memory maps and indexes are derived views.
Rebuild them from the store and invalidate them when a commit changes their revision.
A cache must not grant admission or return a receipt on its own authority.

Audit records are append-only facts with actor provenance.
A terminal audit commits with the state it describes.
ADR-066 keeps this audit distinct from participant observations and captured evidence.
The archival `experiment-run-v1` record remains under ADR-065.
Append-only storage alone does not prove that records were not changed.

Backend effects live outside the store.
The owner records intent and observed outcome.
If the outcome cannot be proved, it records indeterminacy.
A store read never proves an external effect.

## 5. Operation lifecycle and control flow

1. **Admission**: check the target, request, and actor scope.
   Take a unique idempotency claim in the store.
   Its scope includes the store, actor, and operation kind.
   An exact duplicate returns the retained receipt after access checks.
   It never calls the backend again.
2. **Write-ahead claim**: store `RUNNING` before calling the backend.
3. **Invocation**: call the backend outside the store transaction.
   Do not hold a database lock over external work.
4. **Terminal commit**: check the revision and commit one atomic cut.
   That cut contains the snapshot, final operation, and actor audit.
   Use the same boundary for workflow control, rejection records, participant actions, and crossings.
   Do not split snapshot and record writes by operation family.
5. **Receipt**: read final state from the store.
   A cache may answer only under its explicit coherence rule (CP-7).

## 6. Failure and recovery behavior

CP-3 checks unfinished work after process or storage loss, cancellation, or timeout.
It classifies each operation from the available proof:

- **effect-absent**: proof shows that the backend did not act.
  Fail the operation with a stable diagnostic.
- **effect-applied**: backend observation proves the effect.
  Commit the observed state atomically.
- **indeterminate**: neither result can be proved.
  Retain the terminal record, claim, and exclusion.
  Require an explicit linked resolution before more effects.

Nothing replays automatically.
P0–P2 have one owning process.
Host loss and network partitions use that process-loss boundary.
Cross-process coordination remains the P3 nonclaim.

Each external callback has a bounded budget.
This includes recovery observation.
An absent-effect report is conclusive only if no late effect remains possible.
Keep checked residual state for known partial effects.
Use indeterminacy if carriers lack the needed detail or cessation is unproved.
A lost store acknowledgement instead requires atomic readback.
Poison readiness if that cut cannot be established.
Neither case grants another invocation.

A cancel request does not kill a worker or prove that effects stopped.
A caller timeout or broken connection leaves the retained operation in force.
The caller must use the same scoped key for an exact retry.
A restored backup can be older than backend effects.
Keep readiness closed until recovery checks that state.
An indeterminate parent is immutable.
A deliberate resolution adds its own linked operation and audit.
It does not rewrite the parent.

Credential-bearing retries still need the exact live proof after restart.
Use authorized status reads when that proof is lost.
A fresh key grants no retry permission.
Accepting a snapshot does not prove cessation or permit reuse.
Workflow retry and SCE-007 attempt rules govern repeated work.
Resume needs an admitted continuation boundary.
A new trial needs its own allocation.

## 7. Concurrency control

One `RuntimeMutationAuthority` controls each state-write path.
Path-local gates and the HTTP lock stay subordinate to it.
During an external call, the owner releases the short state permit.
It retains the effect reservation, so conflicting work stays excluded.
The bounded control path can still record supervision.
A timeout does not prove remote interruption.
Release exclusion only after the required effect and cessation checks.

The store lease admits one process (CP-5).
A second process must fail admission.
Revision CAS (CP-4) also rejects stale writes.
CAS does not fence external effects.
Unique store claims provide deduplication.
Caches remain advisory.

## 8. Persistence and coordination seams

The store contract needs transactions, unique claims, revisions, a lease, audit, and recovery observation.
Check the granted journal mode and sync level.
A request alone does not prove the setting took effect.
Issue #1092's WAL checks establish that rule.

Clocks, audit sinks, leases, and future coordination providers are separate seams.
The core must not encode one deployment topology.
Backend observation uses the existing target, protocol, and manifest pattern.
A store provider must not call native backend APIs.
If a provider lacks required support, construction fails.
Profiles must not degrade silently.

## 9. Security boundaries

API-404 defines access at the profile boundary.
P0/P1 trust the host process to identify callers.
They use the store's file protections.
These include owned folders, private modes, and identity-pinned databases under PR #1136.
P2 adds HTTP authentication and target binding under #1090 and #1133.
It uses the same core.
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
supervision remain deployment duties.

## 10. Lifecycle, settings, and operations

The host owns process lifecycle, settings, upgrade order, and backup timing.
The control plane owns schema versions and one-time store migration.
It keeps durable, fsynced backups during migration.
It checks store integrity at startup.
It refuses to open state it cannot verify.
Configuration enters as explicit typed setup input; the core does not
parse environment variables or secrets, and the current repository has no
serve command. Startup acquires the owner lease before schema inspection,
migration, cache loading, or reconciliation, and becomes ready only after all
four succeed. Shutdown stops admission, drains mutation, commits or records
indeterminacy, closes the provider, then releases the lease. Scenario time is
not the operational clock used for leases, deadlines, audit, or recovery.
Operational health and the indeterminate-operation runbook are CP-12.

## 11. What this setup does not do

P3 remains a nonclaim.
Two workers cannot share the database as coordinated owners.
P0 has no durability.
The HTTP adapter cannot scale writes beyond its one owner.
This design does not choose a storage engine.
CP-6 supplies the P1 reference store.
Another provider may replace it if it meets the contract. This design adds no tenant, cross-target, or cross-run store.
It does not promise exactly-once effects or automatic replay.
It adds no durable broker, TLS endpoint, or secret resolver.
Archival run provenance and evidence keep their own contracts.
