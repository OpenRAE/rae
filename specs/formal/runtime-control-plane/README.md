# Runtime Control-Plane Abstract Operation Model

Status: design authority for ADR-104; no executable profile guarantee is
claimed until the corresponding implementation issue lands with tests.

## Scope

This FM3 artifact defines the abstract operation lifecycle and the safety,
concurrency, recovery, identity, authorization, and provenance properties that
P0--P2 implementations must preserve. It models one store scope
`S = (target_id, run_id)`, one lease-admitted mutation authority, and operations
within that scope. P3 coordination and exactly-once backend effects are outside
the model.

An operation is the tuple
`O = (operation_id, kind, actor, authorization_scope, idempotency_key,
request_commitment, state, parent_operation_id?)`. The store fixes `S` at
creation. `actor`, `authorization_scope`, `kind`, and `request_commitment` are
immutable after admission. The request commitment is a value-free,
domain-separated canonical digest; it is not a raw request body or bearer
credential. It covers every execution-affecting semantic input, including an
explicit base snapshot through the same value-free projection. A separate
ephemeral exact fingerprint binds credential-bearing input for in-process
idempotency collision detection; that fingerprint never enters the operation
store, receipts, statuses, diagnostics, or audit records. After restart its
proof is intentionally unavailable, so a credential-bearing retry under an
already-durable idempotency key fails closed and the caller must use a new key.

## Abstract states and transitions

The proposed portable lifecycle is:

```text
UNRECORDED --admit/claim--> ACCEPTED --start--> RUNNING
UNRECORDED --deny---------> DENIED (audit outcome only; no operation record)
ACCEPTED  --cancel-------> CANCELLED
RUNNING   --commit-------> SUCCEEDED | FAILED | CANCELLED | INDETERMINATE
```

`REJECTED` is not an `OperationState`; denial is an audit outcome produced
before any operation or idempotency claim exists. The `DENIED` label above is
therefore not a stored lifecycle state.

The closed persisted transition relation is the following matrix. Every cell
not marked legal is illegal; implementations must not maintain a second,
store-specific transition table.

| From \\ To | `ACCEPTED` | `RUNNING` | `SUCCEEDED` | `FAILED` | `CANCELLED` | `INDETERMINATE` |
| --- | --- | --- | --- | --- | --- | --- |
| `ACCEPTED` | illegal | legal: start | illegal | illegal | legal: cancel before invocation | illegal |
| `RUNNING` | illegal | illegal | legal: commit observed success | legal: commit observed failure or known-absent effect | legal: commit proven cancellation or known-absent effect | legal: commit outcome that cannot be established |
| `SUCCEEDED` | illegal | illegal | illegal | illegal | illegal | illegal |
| `FAILED` | illegal | illegal | illegal | illegal | illegal | illegal |
| `CANCELLED` | illegal | illegal | illegal | illegal | illegal | illegal |
| `INDETERMINATE` | illegal | illegal | illegal | illegal | illegal | illegal |

An exact retry of an already-persisted carrier is an idempotent persistence
no-op, not a self-transition, and is valid only when the complete immutable
operation context and terminal carrier are identical. `UNRECORDED` is not a
persisted state and remains governed by the admission rules above.

`OperationReceipt.accepted` is an admission acknowledgement, not a projection
of `OperationState.ACCEPTED`. A false acknowledgement does not imply a
`FAILED` operation: a denial receipt retained for transport compatibility has
no persisted operation, claim, or subsequent status resource. A true
acknowledgement identifies an operation governed by the matrix above.

Lifecycle diagnostics use the existing closed `DiagnosticModel` contract.
Invalid transition attempts and non-success terminal classifications carry
stable namespaced codes and bounded, value-free messages; `INDETERMINATE` has
a distinct code and must not be represented by a generic failed/cancelled
diagnostic. Provider exception text, request content, credentials, paths, and
authorization values never enter the diagnostic. Public diagnostic locations
use the shared model's safe JSON-Pointer address shape.

`SUCCEEDED`, `FAILED`, `CANCELLED`, and `INDETERMINATE` are terminal.
Implementations may combine `admit/claim` and `start` into one durable
transaction, but `RUNNING` must be authoritative before backend invocation.
`RUNNING` reaches `CANCELLED` only when the effect is known absent or the
backend contract proves cancellation; an unobservable cancellation is
`INDETERMINATE`. No terminal state transitions to another state. In particular,
resolving an `INDETERMINATE` outcome creates a new linked operation; it never
rewrites the original.

The abstract operations are:

| Operation | Precondition | Atomic store effect | External effect |
| --- | --- | --- | --- |
| `deny` | admission or authorization fails before claim | append one bounded, value-free denial audit; create no operation or idempotency claim | none |
| `claim` | actor is authorized for `S`, kind, and referenced subjects; scoped idempotency claim absent | create immutable claim and non-terminal operation | none |
| `start` | operation is `ACCEPTED` and owned by the mutation authority | transition to `RUNNING` | none |
| `invoke` | operation is durably `RUNNING` | none; no store transaction is held | backend may apply, reject, or become unobservable |
| `cancel` | actor is authorized and operation is `ACCEPTED`, or operation is `RUNNING` with the effect proven absent or cancelled | preserve the snapshot revision and write `CANCELLED` plus actor-bound audit together | none; any backend cancellation or observation precedes this transition |
| `commit` | expected snapshot revision matches and operation is `RUNNING` | write snapshot revision, one terminal operation, and actor-bound audit together | none |
| `reconcile` | operation is non-terminal after restart | classify observed effect and perform one terminal commit | observation only; never replay |
| `resolve` | original is terminal `INDETERMINATE` and actor is authorized | create a linked operation and audit; preserve original | explicit operator/embedder action only |
| `read` | actor is authorized for the operation and `S` | none | none |

Reconciliation classification is closed:

- effect known absent → `FAILED` or `CANCELLED`, according to the admitted
  operation contract;
- effect observed and semantically valid → `SUCCEEDED` with the observed
  snapshot;
- effect cannot be established → `INDETERMINATE`.

## Invariants

1. **Scope invariant.** A P0--P2 store has one immutable `(target_id, run_id)`;
   opening it with a different scope fails before state is read or migrated.
2. **Single-authority invariant.** Every control-plane mutation family enters
   one mutation authority. P1/P2 acquire the owner lease before inspection,
   migration, cache load, reconciliation, or admission.
3. **Write-ahead invariant.** A backend is invoked only after its operation is
   durably `RUNNING` and bound to immutable actor and request context.
4. **Terminal atomicity invariant.** Snapshot revision, terminal operation, and
   actor-bound audit become visible together or not at all.
5. **Revision invariant.** Every snapshot mutation uses compare-and-swap
   against its observed revision; a stale revision has no state effect.
6. **Single-terminal invariant.** Each accepted operation has at most one
   terminal state, and terminal history is immutable.
7. **No-replay invariant.** Startup, retry, timeout, cancellation, and request
   disconnect do not automatically invoke the backend again.
8. **Idempotency invariant.** A claim is unique within
   `(store scope, actor, operation kind, idempotency key)`. A duplicate with a
   different request commitment, explicit base snapshot, admission context, or
   private exact fingerprint fails closed; a duplicate never bypasses
   authorization or discloses another actor's receipt.
9. **Authorization invariant.** Possession of an operation id, receipt, store,
   or idempotency key grants no authority. Every mutation and read is checked
   against the immutable actor, target/run, role, and relevant participant
   subject/audience scope.
10. **Provenance invariant.** Operational audit records stable action, actor,
    target, operation, outcome, and coarse reason fields without tokens, raw
    requests, host paths, credentials, backend exception text, or payload
    values. Audit is distinct from participant observations, captured evidence,
    and archival run provenance; append-only is not a tamper-evidence claim.
11. **Validation invariant.** Persisted and transported portable state passes
    one closed, lossless contract codec. Unknown, missing, or malformed state
    fails closed rather than being coerced or defaulted.
12. **External-effect invariant.** Store atomicity does not imply exactly-once
    backend effects. When observation cannot distinguish applied from absent,
    the only safe terminal classification is `INDETERMINATE`.

Pre-contract local-store schema v1 records cross this boundary only through the
transactional v1-to-v2 migration. Accepted records receive an explicitly
unattributed legacy context and canonical terminal classification; their
unclassified request fingerprints are replaced with the new value-free
commitment. Persisted legacy denials are removed from operation/idempotency
state and retained as denial-only audit dispositions. The one-time JSON import
uses the same migration function before the strict carrier codec. Malformed or
partially migrated records still fail closed.

## Concurrency and failure obligations

For two concurrent claims, at most one transaction wins a given scoped
idempotency key. For two terminal commits based on the same snapshot revision,
at most one compare-and-swap succeeds. Store transactions never span backend
calls. Process loss at each boundary therefore leaves either no claim, a
non-terminal operation eligible for classification, or one complete terminal
commit; it never makes a partial terminal record authoritative.

P0 may lose all state on process loss but must preserve the in-process safety,
identity, authorization, validation, and no-double-invocation properties while
alive. P1 adds crash-consistent persistence, lease admission, and startup
classification. P2 adds authenticated transport admission while retaining one
P1 owner and one target/run store. P3 requires a future model covering fencing,
distributed scheduling, partitions, cache coherence, and tenant isolation.

## Relationship to implementation and tests

CP-1 maps these states into the existing `OperationState`, `OperationStatus`,
and published control-plane DTO family. CP-2 implements the mutation authority
and atomic terminal commit. CP-3 implements reconciliation. CP-4 through CP-7
provide compare-and-swap, leases, transactional storage, scoped idempotency,
and coherent reads. CP-8 propagates authenticated actor context from the HTTP
adapter. CP-9 supplies transition, kill-point, concurrency, adversarial
authorization, cross-scope isolation, codec-corruption, and recovery tests.

The issue-1151 structural test pins this artifact and its required terms. Those
tests establish design-set completeness only; they do not demonstrate the
profile guarantees above.
