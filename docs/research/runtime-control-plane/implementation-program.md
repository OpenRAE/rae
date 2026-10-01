# Runtime Control-Plane Implementation Program

Date: 2026-08-17

Parent issue: [#1151](https://github.com/OpenRAE/rae/issues/1151)

Milestone: `Runtime Control-Plane`

The machine-readable authority is
[`implementation-program.json`](implementation-program.json).

## Definition delivered by issue 1151

Issue #1151 delivers ADR-104, the current-state assessment, the profiled
composition architecture, the requirement and surface disposition, and this
dependency-ordered program. It does not implement any work package below;
each package is filed as its own linked issue in the Runtime Control-Plane
milestone, and no guarantee is claimable before its package lands with tests.

## Dependency graph

```text
 CP-1 lifecycle contract
   |         \
   v          v
 CP-2 atomic  CP-4 revision CAS      CP-5 store lease
 terminal        |                      |
 commit          |                      |
   |             +----------+-----------+
   v                        |
 CP-3 startup               v
 reconciliation        CP-6 transactional local store (re-lands PR #1136)
   |                        |
   |                        v
   |                   CP-7 idempotency claims in store
   |                        |
   +------------+           v
                |      CP-8 served profile (HTTP adapter)
                v           |
          CP-9 crash/profile conformance suite
                |
                v
          CP-10 profile declaration and capability discovery
                |
                +--> CP-11 API-404 requirement update
                +--> CP-12 recovery runbook and operator tooling
```

## Work packages

Each package below is one milestone issue with bounded scope, ordering,
acceptance criteria, and verification expectations. Requirement traceability
is `API-404` throughout; packages touching snapshot semantics also cite
`SEM-222`. All packages cite ADR-104 and its
[FM3 abstract operation model](../../../specs/formal/runtime-control-plane/README.md).

### [CP-1 — Operation lifecycle contract](https://github.com/OpenRAE/rae/issues/1182)

Define the operation lifecycle in contracts: states including the explicit
indeterminate terminal outcome, the stable diagnostics that accompany each
transition, immutable actor/authorization and target/run context, and the
state-transition table. Reuse the existing portable carrier family. Update
`contracts/schemas/control-plane` accordingly. Verification: contract tests
enumerate every legal and illegal transition, malformed carrier, and attempted
identity mutation. Depends on: nothing.

### [CP-2 — Atomic terminal commit](https://github.com/OpenRAE/rae/issues/1181)

Rework every control-plane mutation family so the running claim is durable
before backend invocation and the terminal transition commits snapshot,
terminal record, and actor-bound audit event in one store transaction,
matching the participant transition path. Generic execution, workflow
cancellation and timeout reconciliation, rejection/pre-computed records,
participant actions, and crossings all enter one mutation authority. Direct
`RuntimeManager` execution remains outside this boundary. Verification:
kill-point tests at every step boundary show no observable partial terminal
state; concurrent in-process tests cross operation families. Depends on: CP-1.

### [CP-3 — Startup reconciliation](https://github.com/OpenRAE/rae/issues/1179)

Classify every non-terminal operation at startup as effect-absent,
effect-applied, or indeterminate, using backend observation where the
backend offers it; never replay automatically; park indeterminate outcomes
behind the CP-1 diagnostic and an embedder-visible surface. Resolution creates
a separately authorized linked operation and never rewrites the original.
Verification: restart tests per classification, including the no-observation
backend, plus authorization tests for resolution. Depends on: CP-1, CP-2.

Implemented by issue #1179 with recovery observation kept independent from
EXP-715 experiment capture/retention/export. The runtime classifies and commits
before readiness through the existing mutation and durability authorities;
unresolved indeterminate outcomes quarantine only their target/run until an
operator or trusted embedder records a fresh linked administrative resolution.

### [CP-4 — Snapshot revision compare-and-swap](https://github.com/OpenRAE/rae/issues/1180)

Version every snapshot commit; a writer holding a stale revision fails
closed. Demote in-memory maps to rebuildable derived state with an explicit
coherence rule. Verification: interleaved-writer tests and cache-rebuild
tests. Depends on: CP-1.

### [CP-5 — Store lease admission](https://github.com/OpenRAE/rae/issues/1183)

Contract a store ownership lease; exactly one owner per store at P1/P2.
A durable store also pins one immutable target/run scope and refuses a
mismatched reopen. Lease admission precedes schema inspection, migration,
cache loading, reconciliation, and state reads. Local implementation follows
the PR #1136 lease module. Verification: concurrent-process, mismatched-scope,
filesystem-race, and lifecycle-order tests. Depends on: nothing (integrates
with CP-4).

### [CP-6 — Transactional local store](https://github.com/OpenRAE/rae/issues/1092)

Re-land the PR #1136 store work — already implemented across
`API-404-durable-store-successor`, `API-404-fsync-wal`, and
`integration-openrae-current-dev` (atomic `claim_record`,
`AtomicControlPlaneStore` with `commit_terminal_operation` and
`reconcile_interrupted_records`, `RuntimeOwnerLease`, fsync path
discipline, compatibility adapter) — under the CP-1/CP-2/CP-4/CP-5
contracts: WAL admission by returned result, unique idempotency claims,
path and permission hardening, integrity digests, one-time migration with
durable backups. Recovery behavior conforms to CP-3 instead of blanket
interrupted-to-failed conversion. The dataclass, published envelope, store,
and HTTP projections converge on one strict, lossless codec so durable state
cannot be coerced or silently dropped. Verification: the absorbed
crash-consistency suite, store-contract conformance, round-trip coverage, and
corrupt-carrier rejection. Depends on: CP-1, CP-2, CP-4, CP-5.

### [CP-7 — Atomic idempotency claims and cache demotion](https://github.com/OpenRAE/rae/issues/1184)

Make the idempotency lookup-and-claim one atomic store operation (unique
claim scoped by target/run store, immutable actor, operation kind, and request
commitment). A receipt is returned only after authorization against the
original actor and scope. Demote the permanent status and snapshot caches behind
`get_operation`/`get_snapshot` to rebuildable derived state with an
explicit coherence rule. Verification: concurrent and multi-restart retries,
cross-actor/cross-scope adversarial cases, changed-request rejection, and
stale-cache injection. Depends on: CP-6.

### [CP-8 — Served profile alignment](https://github.com/OpenRAE/rae/issues/1188)

Bring the reference HTTP adapter to profile P2: single owning service
process, owner-serialized mutations, and reads carrying the snapshot revision
they observed. Derive typed actor context from authenticated identity and pass
it into core admission; authorize target, participant, and operation references
without trusting transport-supplied identity; and let the core transaction own
terminal audit rather than appending it post hoc. Move API-408 retrieval off
the mutation lock through an ordered evidence path. Verification: extend the
#1133 admission suite with cross-principal receipt/idempotency, proxy-spoofing,
audit atomicity, multi-worker, and redacted-error tests. Depends on: CP-4, CP-7.

### [CP-9 — Crash and profile conformance suite](https://github.com/OpenRAE/rae/issues/1187)

One suite that runs each profile's guarantee set: kill-point injection at
every commit boundary, restart reconciliation assertions, lease contention,
revision conflicts, actor-scoped idempotency, target/run isolation, strict
codec rejection, authorization boundaries, and P0's explicit nonclaims.
Absorbs the 115-test crash suite from PR #1136. Depends on: CP-2, CP-3, CP-6,
CP-7, CP-8.

### [CP-10 — Profile declaration and capability discovery](https://github.com/OpenRAE/rae/issues/1189)

Embedders select a profile and can interrogate its guarantees and nonclaims
programmatically through one typed definition, including target/run scope,
actor boundary, and required persistence/coordination capabilities;
`docs/explain/sdl/runtime-architecture.md` gains the profile model. Missing
capabilities fail construction and P3 cannot be selected. Depends on: CP-1
through CP-8.

### [CP-11 — API-404 requirement update](https://github.com/OpenRAE/rae/issues/1185)

Rewrite API-404 traceability to the profiled contract, recording which
clauses each profile satisfies and P0's durability waiver; sync Ground
Control. Depends on: CP-10.

### [CP-12 — Recovery runbook and operator tooling](https://github.com/OpenRAE/rae/issues/1186)

Operator flow for indeterminate operations, backup/restore, upgrade and
migration sequencing, lease-ordered startup/shutdown, value-free health and
observability, and deployment-owned security responsibilities. Depends on:
CP-3, CP-6.
