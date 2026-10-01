# Runtime Control-Plane Current-State Assessment

Date: 2026-08-17

Parent issue: [#1151](https://github.com/OpenRAE/rae/issues/1151)

Evidence below cites the `dev` tree at the time of assessment
(`701858d1`). Line-level behavior was verified by direct reading, not
inferred from documentation.

The pre-implementation refresh on 2026-09-03 also checked the current `dev`
tree (`cba73a81`). The original findings still hold. The refresh additionally
found the codec, workflow, and identity-scope gaps recorded below; these are
current-repository evidence, not claims imported from the deferred store work.

Post-assessment status: CP-1 and CP-2 subsequently established the closed
operation lifecycle and atomic mutation boundary. CP-3 issue #1179 closes the
startup-reconciliation gap identified here through the runtime-owned,
backend-neutral classification design recorded in the
[CP-3 preflight](../../decisions/issue-1179-startup-reconciliation-preflight.md).
This document remains the dated evidence snapshot; it is not an assertion that
the original gaps remain in the current tree.

## 1. The contract surface today

`raes_runtime/control_plane.py` defines `RuntimeControlPlane`. Its
constructor binds one `RuntimeTarget`, one `ControlPlaneStore` (default
`InMemoryControlPlaneStore`), then loads and permanently caches the
snapshot (`self._snapshot = … load_snapshot()`) and the full operation-record
map (`self._operations = self._store.load_records()`). Nothing invalidates
or rebuilds these caches after construction: a second process sharing the
same store is invisible to the first.

In-process locking is fragmented by entry path. `_participant_control_lock`
covers participant actions and control mediation, while `_operation_lock`
guards only operation-map access and not the generic mutation sequence. The
generic operation and workflow paths hold no control-plane mutation lock, so
concurrent direct library submissions race `_snapshot`, `_operations`, and
store writes even before any multi-process question arises. `RuntimeManager`
is a separate direct-execution facade with its own participant-execution lock;
that lock does not coordinate a manager and a control plane aimed at the same
backend. The HTTP adapter's mutation lock protects only callers entering that
one application instance.

## 2. The store protocol

`control_plane_store.py::ControlPlaneStore` (a `Protocol`) exposes
`load_snapshot`, `save_snapshot`, `load_records`, `save_record`,
`find_by_idempotency`, `append_audit`, `read_audit`, and two transition
commits: `commit_control_transition(expected_head=…)` and
`commit_participant_transition(expected_history_heads=…)`. The transition
commits are the one place the store contract already expresses atomic
multi-record commits guarded by expected-head compare-and-swap
(`_require_expected_control_head`, `_require_expected_history_heads`).
Snapshots and generic operation records have no revision or expectation
parameter: `save_snapshot` and `save_record` overwrite unconditionally.

Two implementations exist on `dev`:

- `InMemoryControlPlaneStore` — dictionaries, no durability, correct for
  profile P0.
- `LocalControlPlaneStore` (`control_plane_store_local.py`) — four JSON
  files (`snapshot.json`, `operations.json`, `audit.jsonl`,
  `control-transition-state.json`). Each write is atomic per file via a
  temporary file and `os.replace` with no fsync of the file or directory,
  but a logical commit spanning snapshot plus record plus audit is two or
  three separate file replacements; `operations.json` is a whole-file
  read-modify-replace (concurrent writers lose updates, idempotency lookup
  is a linear scan), `audit.jsonl` is an unlocked append, and
  `load_snapshot` arbitrates between `snapshot.json` and the committed
  transition blob by comparing a participant-transition count — a
  heuristic, not a version. Issue #1092 documented these failures and
  PR #1136 replaced this store with a transactional SQLite design; both
  are deferred to this decision.

## 3. The generic execution path

`control_plane_execution.py::execute_operation` performs, in order:

1. `_idempotent_receipt(...)` — `find_by_idempotency` against the store,
   while `get_operation` and `get_snapshot` answer from the permanent
   caches; in the JSON store the lookup and the later claim are separate
   steps, not one atomic unique claim;
2. `_persist_record(...)` with `OperationState.RUNNING`;
3. `_call_backend_apply(...)` — the external effect;
4. `control_plane._store.save_snapshot(...)`;
5. `_persist_record(...)` with the terminal `SUCCEEDED`/`FAILED` status.

Steps 2, 4, and 5 are independently durable, the in-memory snapshot is
reassigned before the durable write (a failed `save_snapshot` diverges
memory from disk), and no lock guards the sequence. A process exit after
step 3 leaves an applied backend effect with a `RUNNING` record and a stale
snapshot; after step 4, a new snapshot with a non-terminal record. On
restart the record loads unchanged, and step 1 returns it to an idempotent
retry without reconciliation. `OperationState.ACCEPTED` exists in
`raes_contracts.runtime_state` but is never used — the path claims straight
to `RUNNING`. The idempotency check itself is check-then-act: two
concurrent submissions with one key can both miss the lookup and both mint
operations, and a record persisted with an empty request fingerprint
disables the reuse-mismatch check for every later retry. This confirms the
first finding of the issue #1092 integration review and motivates ADR-104
§4 (write-ahead claim, one atomic terminal commit, startup reconciliation).
The participant transition path does not share the atomicity defect: it
commits through the store's transition-commit methods as one guarded unit
and is the template CP-2 generalizes.

The same independently durable pattern also exists outside the generic path.
`WorkflowControlMixin.cancel_workflow()` and
`reconcile_workflow_timeouts()` assign the in-memory snapshot, call
`save_snapshot`, and only then persist the operation record. Rejected
submissions and `persist_succeeded_operation()` persist records without a
transactional audit. The atomicity and lock boundary must therefore cover
every control-plane mutation, not only `execute_operation()`.

### Codec and validation drift

Live state currently has parallel representations: the
`raes_contracts.runtime_state.RuntimeSnapshot` dataclass, the published
`RuntimeSnapshotEnvelopeModel`, the hand-built store codec in
`control_plane_store.py`, and the hand-built HTTP projection in
`control_plane_api_models.py`. They already disagree:
`RuntimeSnapshot.participant_episode_closure_records` exists and participates
in snapshot updates and SEM-222 validation, but is absent from the published
envelope, store payload/from-payload functions, and HTTP projection. A P1
round trip can therefore silently drop that state.

The operation-record decoder similarly uses permissive `.get(...)` defaults
and `str(...)` coercions instead of validating a closed carrier before domain
reconstruction. That is unsuitable for authoritative durable state: malformed
or version-incompatible records can be normalized into plausible records
instead of failing startup. The P1 codec must reuse the closed contract-model
validation surface and treat lossy legacy import as an explicit migration
result, not duplicate schema logic inside SQL rows or repository classes.

## 4. The reference HTTP adapter

`control_plane_api/` implements the served surface behind one composition
boundary, `create_control_plane_app(control_plane, *, security=None)`.
`_offload.py` keeps blocking work off the event loop and serializes target
mutation through a single `asyncio.Lock` per application instance — correct
while exactly one service process owns the store, and exactly the
application-local serialization the #1092 review flagged: two service
processes over one store would each hold their own lock and their own stale
caches. The three API-408 participant-retrieval `GET` routes also go
through the mutation lock because they append evidence, coupling read
throughput to backend mutation latency (a CP-8 concern). Bearer
authentication and target binding come from #1090/#1133
(`control_plane_security.py`, `control_plane_api_guards.py`), and workflow
timeout reconciliation fails closed per #1132
(`control_plane_timeouts.py`). These surfaces are retained under P2.

`ControlPlaneSecurityConfig` is an explicit in-memory composition object; the
repository has no control-plane environment parser, serve command, TLS
terminator, or service-unit definition. `AuditEvent.details` is an unrestricted
dictionary, while request rejection is the only control-plane path using a
module logger. Those facts make configuration/secret injection, value-free
audit fields, deployment exposure, and operational health explicit P2/CP-12
boundaries rather than incumbent guarantees.

Authentication currently terminates at the route rather than becoming
authoritative operation context. `_operation_routes.py` obtains a
`_MutatingIdentity`, but calls `submit_provisioning`, `submit_orchestration`, or
`submit_evaluation` without it; those core methods and
`OperationExecutionRequest` have no actor/authorization field. The route then
appends the successful audit event only after the core returns. Operation
status reads likewise authorize a role/target at the route and call the
identity-less `get_operation(operation_id)`, so the persisted receipt cannot
enforce ownership or prevent an authorized client on the same target from
discovering another client's operation. CP-1/CP-2/CP-7/CP-8 must propagate and
persist immutable actor scope, bind receipt/idempotency access to it, and move
terminal audit into the atomic core commit.

Nothing in the repository runs the adapter: `create_control_plane_app` is a
factory, `uvicorn` is a declared but unused dependency, and there is no
serve entrypoint or CLI command. Every consumer today is an embedded ASGI
test client, so the served topology is asserted by documentation — the
issue #1093 preflight states plainly that the in-process lock "does not
create a distributed queue" and that "a future multi-host service must use
a durable broker/worker design with explicit leases and recovery" — which
is exactly the boundary ADR-104 records as profile P2 and the P3 nonclaim.

The persistent state has no first-class target, scenario, run, or service-
tenant namespace. `RuntimeControlPlane` binds one target in memory, and HTTP
identities are checked against that target, but `LocalControlPlaneStore` can be
reopened with a differently named target. Scenario/run selection is owned by
the embedding application; ADR-087 `deployment_tenants` are authored scenario
topology and are not control-plane tenants. P0--P2 must therefore remain one
target/run scope per store and refuse mismatched durable identity rather than
claim multiplexed isolation.

## 5. Test surfaces pinning today's behavior

- `test_runtime_control_plane.py`, `test_runtime_conformance.py` — the
  contract and in-memory behavior.
- `test_runtime_control_plane_api.py` — adapter admission, auth, offload
  serialization (#1133).
- `test_dsl_437_snapshot_durability_conformance.py`,
  `test_run_307_shared_operational_state.py` — snapshot durability and
  shared-state reads (#1148).
- PR #1136 and its successor branches additionally carry
  `test_issue_1092_control_plane_crash_consistency.py` (~1,250 lines):
  terminal-commit idempotence, per-write-boundary rollback, restart
  reconciliation, second-owner rejection with clean handoff, WAL and
  integrity guards, and legacy-migration rollback. The implementation
  program absorbs it into CP-9 as the acceptance bar the new lifecycle
  must keep meeting.

The durable-store implementation itself exists, unlanded, on three
branches (`API-404-durable-store-successor`, `API-404-fsync-wal`, and the
`integration-openrae-current-dev` integration branch): an atomic
`claim_record`, an `AtomicControlPlaneStore` capability protocol with
`commit_terminal_operation` and `reconcile_interrupted_records`, a
flock-based `RuntimeOwnerLease`, fsync-disciplined path helpers, a
compatibility adapter for legacy stores, and a unified `_operation_lock`.
Its shape converges with ADR-104 §§4–5; CP-6 reconciles and re-lands that
work rather than redesigning it.

## 6. Gap summary against ADR-104

| Gap | Evidence | Owning work package |
| --- | --- | --- |
| No explicit lifecycle contract; no indeterminate terminal state | `OperationState` lacks it (`ACCEPTED` exists unused); interrupted work stays `RUNNING` | CP-1 |
| Mutation paths have no shared authority | no mutation lock in `execute_operation` or workflow control; `_participant_control_lock` is path-local; a separate `RuntimeManager` does not coordinate with a control plane | CP-2, CP-4 |
| Non-atomic terminal effects on the generic path | `execute_operation` steps 2/4/5 above | CP-2 |
| No startup reconciliation | records load unchanged at construction | CP-3 |
| Unconditional snapshot/record writes | `save_snapshot`/`save_record` have no expected revision | CP-4 |
| No ownership admission | any process may open any store | CP-5 |
| Non-transactional durable store | `LocalControlPlaneStore` JSON files | CP-6 |
| Non-atomic idempotency claims; status and snapshot reads answered from permanent caches | `find_by_idempotency` + later `save_record`; `get_operation` over `self._operations`, `get_snapshot` over `self._snapshot` | CP-7 |
| Application-local mutation serialization | `_offload.py` `asyncio.Lock` | CP-8 |
| Workflow/rejection mutation paths bypass the generic terminal-commit shape | `control_plane_workflow_control.py`; `_reject_diagnostics`; `persist_succeeded_operation` | CP-2 |
| Parallel snapshot/operation codecs can silently coerce or drop state | `RuntimeSnapshot`; `RuntimeSnapshotEnvelopeModel`; `_snapshot_payload`/`_snapshot_from_payload`; `_snapshot_model`; `_record_from_payload` | CP-1, CP-6, CP-9 |
| Durable store is not pinned to a target/run authority | `LocalControlPlaneStore(base_dir)` carries no target or run identity | CP-5, CP-6 |
| No control-plane configuration/serve/deployment boundary | app factory exists, but there is no environment loader, serve command, TLS, or service unit | CP-8, CP-10, CP-12 |
| Audit/log/health planes are not fully specified | free-form `AuditEvent.details`; request rejection is the only logger-backed adapter path | CP-8, CP-12 |
| HTTP identity is not authoritative operation provenance | mutating routes call identity-less core submission methods, append success audit post hoc, and read status by operation id without original-actor binding | CP-1, CP-2, CP-7, CP-8 |
