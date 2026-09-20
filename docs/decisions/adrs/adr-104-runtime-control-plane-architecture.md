# ADR-104: Runtime Control-Plane Architecture

## Status

accepted

## Date

2026-08-17

## Classification

Classification: FM3

Required artifacts: an evidence-backed current-state assessment, a profiled
composition architecture with explicit state authority and failure semantics,
a requirement and surface disposition, a dependency-ordered implementation
program, an explicit abstract operation-state model with safety and security
invariants, and a structural test pinning the design set. The state model is
[`specs/formal/runtime-control-plane/README.md`](../../../specs/formal/runtime-control-plane/README.md).

Waivers: issue #1151 is design authority. It does not implement or select a
storage engine by code change, publish new portable schemas, change runtime
execution behavior, claim a distributed or highly available topology, or
report any coordination, consistency, or recovery result as demonstrated;
every profile guarantee named here becomes binding only when its
implementation issue lands with tests. No TLA+, Alloy, theorem-proved
linearizability, exactly-once external-effect proof, distributed refinement,
or universal recovery proof is claimed; those are disproportionate while P3
and all executable contract changes remain outside this design-only issue.

## Context

`raes_runtime` exposes `RuntimeControlPlane` with an in-memory default store,
an optional local JSON store, and a reference HTTP adapter. The repository
has never decided what the control plane is: an in-process facade, an
embedded component, a deployable service, or a family of implementations.
Issue #1092 and PR #1136 exposed the gap by introducing SQLite durability,
recovery behavior, single-process ownership, and store-compatibility rules
inside what appeared to be a local storage change; both were deferred to this
decision.

The integration review of that work recorded two structural findings that
bound this design. First, the generic operation path performs independently
durable steps — claim `RUNNING`, invoke the backend, save the snapshot, save
terminal status — with no lock of its own and the in-memory snapshot mutated
before the durable write, so concurrent in-process submissions race and a
process exit can strand an applied backend effect behind stale state, while
an idempotent retry after restart returns the stale record without
reconciling. Second, each `RuntimeControlPlane` permanently caches snapshot
and operation maps while HTTP mutation serialization is application-local,
so a shared database alone cannot make multiple application workers
coherent.

Expected RAES use spans hermetic tests, single-user local execution, embedded
RAE/env-pack/ETV consumers, air-gapped deployments, and long-lived services.
One deployment topology cannot serve all of these, and `RuntimeControlPlane`
must not silently promise the strongest one.

## Decision

### 1. The control plane is a contract with profiled implementations

`RuntimeControlPlane` names a portable contract — operation submission,
idempotent receipts, snapshot access, participant transitions, audit — that
conforming implementations provide under declared operating profiles. RAES
ships reference implementations; it does not define one universal deployment
model or a mandatory service.

### 2. Operating profiles declare guarantees and nonclaims

- **P0 ephemeral**: in-memory store, one process, no durability claims.
  Intended for tests and single-scenario embedding. Loss of the process is
  loss of the run. One control plane owns one target and one run-scoped store.
- **P1 local durable**: one owning process admitted by a store lease;
  crash-consistent authoritative state through a transactional local store;
  startup reconciliation of interrupted operations. Intended for local
  tools, embedded consumers, and air-gapped single-host use. The durable store
  pins one immutable target/run scope and refuses a mismatched reopen.
- **P2 served**: the reference HTTP adapter fronting a P1 core; many
  clients, exactly one owning service process; mutations serialized by the
  owner; reads carry the snapshot revision they observed. Many clients do not
  imply target, run, or tenant multiplexing: P2 retains P1's one-target,
  one-run store scope.
- **P3 coordinated**: multi-process or multi-host ownership. Explicitly a
  nonclaim of this decision: the extension seams (lease provider, revision
  compare-and-swap, coordination provider) are contracted now, and no P3
  implementation or guarantee is asserted until a future ADR accepts one.

### 3. State is classified by authority

Authoritative state — runtime snapshots, operation records, idempotency
claims, participant transition records — lives only in the profile's store
and changes only through its transactions. Derived state — in-memory maps,
indexes, receipt caches — must be rebuildable from authoritative state and
must never answer a request in a way that contradicts it; any cache kept
across a mutation boundary carries an explicit coherence rule. Audit events
are append-only evidence with provenance and are never rewritten in place.
Each accepted operation binds its immutable actor, target/run scope, operation
kind, and request commitment; these fields are authoritative and cannot be
replaced by transport metadata on a later read or retry. External backend
effects are not control-plane state: the control plane records intent and
observed outcome, and where neither is available it records indeterminacy
rather than inferring success or absence.

### 4. Operations are durable work with atomic terminal commits

An operation's lifecycle is recorded before its effects: the claim that an
operation is running is durable before the backend is invoked, and the
terminal transition commits the resulting snapshot, the terminal operation
record, and an actor-bound audit event in one store transaction, extending the
pattern participant transitions already use to every operation. This applies
to every mutation family, including workflow cancellation and timeout
reconciliation, rejected and pre-computed operation records, participant
actions, and participant crossings; none may retain an independent persistence
workflow. After process loss, startup reconciliation classifies each
non-terminal operation as
effect-absent (safe to fail closed), effect-applied (state is advanced from
observation), or indeterminate — an explicit terminal outcome with a stable
diagnostic that requires operator or embedder action. Interrupted work is
never replayed automatically, and retained idempotency claims keep client
retries from blindly re-invoking the backend.

### 5. Concurrency control is ownership-first

Exactly one writer owns a store at a time in P1 and P2, admitted through a
store lease. Snapshot commits carry a revision and commit by
compare-and-swap, so a stale writer fails closed instead of overwriting.
Idempotency keys are unique claims scoped by store, immutable actor, and
operation kind in the authoritative store, not cache entries. Within a
process, one mutation authority serializes every control-plane mutation path;
path-local participant locks and the HTTP adapter lock remain subordinate.
`RuntimeManager` is a separate direct-execution facade and does not coordinate
with a control plane aimed at the same backend. Across processes, admission is
the lease, not advisory locking.

### 6. Boundaries against the rest of RAES

SDL authoring, processor compile and plan behavior, `RuntimeTarget`
attachment, backend contracts, and realization semantics are unchanged and
outside control-plane authority. The control plane consumes compiled plans
and backend interfaces; backends remain responsible for their own effect
semantics. Embedding applications select a profile and own process
lifecycle, configuration, and upgrade sequencing; persistence and
coordination providers implement the store, lease, and clock contracts; the
control plane owns operation bookkeeping, receipts, snapshots, transitions,
and audit.

The P1 offline store-maintenance command is a narrow operator exception to
ADR-036's CLI import boundary: `raes_cli` may call only the closed public
`raes_runtime.control_plane_store_maintenance` interface for scope-bound
check, backup, and restore. No other CLI-to-runtime import is authorized;
SQLite validation, migration, and publication stay within the runtime owner.

### 7. Identity, authorization, and isolation

P0 and P1 trust the embedding process to authenticate its caller, but the
embedder must still supply a typed actor/principal context for every mutation.
P2 derives that same context only from the authenticated HTTP identity and
passes it into the core; caller-supplied identity headers, operation ids,
idempotency keys, and persisted receipts are never authority. Authorization
binds the actor's role and subject scope to the selected target and any
participant or operation reference before core mutation or receipt disclosure.

The accepted operation persists the resulting actor and authorization scope.
All later status, retry, reconciliation, resolution, and audit paths use that
immutable context. A duplicate idempotency claim can return a receipt only to
the same authorized actor and scope. A successful or failed terminal mutation
commits its actor-bound audit record atomically with its terminal record and
snapshot revision. Admission denials that create no operation are recorded by
the existing bounded rejection-audit path and never include tokens, request
bodies, paths, backend exceptions, or other secret-bearing values.

For P0--P2, a store is an isolation boundary for exactly one target and one
embedder-supplied run. One store must not mix targets, runs, or service tenants,
and authored `deployment_tenants` are scenario topology rather than API
tenants. Multitenancy, cross-target stores, cross-run scheduling, and shared
authorization namespaces are P3 nonclaims requiring a future ADR and explicit
coordination, fencing, cache-coherence, and tenant-isolation contracts.

### 8. Disposition of the incumbent surfaces

`RuntimeControlPlane`, the store protocol, the in-memory store, and the
reference HTTP adapter are retained and brought under this contract. The
local JSON store is superseded by the P1 transactional store and retained
only as a migration source. Issue #1092 is re-scoped into the P1
implementation program; PR #1136 and its successor branches are its
principal input — the atomic claim, single-transaction terminal commit,
owner lease, WAL admission, path hardening, and migration work already
implemented there converge with this decision and are re-landed as the P1
store issues, while their recovery semantics are reworked to the
reconciliation classification above instead of a blanket
interrupted-to-failed conversion. The full disposition table, including
every store module and test surface, lives in the design set's requirement
disposition.

### 9. Profile declarations separate guarantees from provider facts

The runtime package owns one immutable, typed declaration for the P0--P3
profile vocabulary, guarantees, nonclaims, scope, actor boundary, and required
composition capabilities. It is in-process composition metadata, not a new
portable DTO, persisted record, backend manifest block, or HTTP discovery
document. P3 remains queryable only as an unavailable future coordination seam:
it has no guarantees and cannot be selected.

Stores and adapters declare the facts they provide; they do not declare that
they *are* a profile. The composition boundary validates those facts against
the selected profile before lease acquisition, store inspection, route
registration, or backend work. Missing capabilities fail construction with
stable, value-free identifiers. A richer provider does not silently strengthen
the selected profile, and a deficient provider never causes fallback to a
weaker profile. Existing store-shape checks, target-manifest validation, lease
admission, and HTTP security validation remain the authorities for their own
layers rather than being copied into the profile catalog.

P0 and P1 are core library compositions. P2 is the reference HTTP composition
over a successfully admitted P1 core; only the HTTP composition may claim P2's
authenticated actor boundary. Backend recovery observation remains the
optional capability already declared by the target manifest and paired with a
validated recovery observer. P1 and P2 require startup reconciliation, but
absence of backend observation support resolves unknown effects to
`INDETERMINATE`; it is not a reason to downgrade or reject an otherwise valid
composition.

Profile interrogation is an embedder API. It does not add an unauthenticated
profile endpoint, a health signal, capability negotiation, or deployment
configuration. TLS, proxy header stripping, secret loading, worker count,
filesystem permissions, process supervision, and backup policy remain
deployment responsibilities. The detailed CP-10 boundary is recorded in the
[issue #1189 preflight](../issue-1189-control-plane-profile-declaration-preflight.md).

## Alternatives Considered

### One mandatory control-plane service

Rejected: hermetic tests, embedded consumers, and air-gapped single-host use
cannot depend on a deployable service, and a mandatory service would move
RAES's default posture from library to infrastructure.

### A single durable store with implicit multi-process sharing

Rejected: the #1092 integration review showed that shared storage without
revision CAS and lease admission leaves workers acting on stale caches;
correctness would rest on deployment discipline the contract cannot see.

### Desired-state reconciliation as the only operation model

Rejected for now: RAES operations wrap backend calls whose effects are not
uniformly observable or idempotent; a reconciler that assumes re-application
is safe would replay indeterminate effects. The reconciliation classification
in this decision leaves room for a future declarative profile without
asserting one.

### Extending the JSON store in place

Rejected: whole-file read-modify-replace cannot express atomic multi-record
commits, unique idempotency claims, or lease admission, and #1092 already
demonstrated its lost-update and partial-state failures.

## Consequences

- Positive: embedders get explicit, testable guarantees per profile instead
  of an implicit strongest-case promise; the #1092/#1136 work regains a
  home with its architectural questions answered; indeterminate outcomes
  become first-class instead of silent.
- Negative: the operation lifecycle and store contracts change, which
  touches the runtime execution path, the HTTP adapter, and every store
  implementation; migration and compatibility work is unavoidable.
- Risk: reconciliation classification depends on backend observability;
  where backends cannot report effect state, operations will park as
  indeterminate and require embedder policy, which is safe but may be
  operationally noisy until backends improve observation surfaces.
- The implementation program in the design set orders this work into
  bounded issues in the Runtime Control-Plane milestone; no guarantee named
  here is claimable before its issue lands.

## Amendments

| Date | Commit/PR | Summary |
|---|---|---|
| 2026-09-03 | #1151 | Reclassified the stateful control-plane design as FM3 and added the abstract lifecycle, actor-bound audit, authorization, idempotency, and target/run isolation invariants required before implementation. |
| 2026-09-19 | #1186 | Permitted the operator CLI to call only the closed public P1 offline-maintenance interface while keeping runtime validation and publication ownership intact. |
| 2026-09-20 | #1189 | Made profile declarations runtime-owned composition metadata, separated provider facts from guarantees, and fixed P2 and recovery-observation boundaries. |
