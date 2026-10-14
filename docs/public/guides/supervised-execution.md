# Supervise runtime execution

`RuntimeControlPlane` separates short state writes from native phase execution.
Each phase keeps its target/run effect reservation. Its backend calls run outside
the state writer. Authorized stop and control requests can use the writer during
those calls.

## Local composition

Local execution uses AnyIO with separate effect, control and store capacity.
Worker interruptions leave independent controls and drain available. HTTP
callers receive a redacted failure.
Use one runtime owner for each backend component. A direct `RuntimeManager`
supports `with` and `close()`. Close refuses while a synchronous callback is
active. It stops the internal clock driver before releasing ownership. Later
effect or time calls through that manager are refused. This allows a host to
hand the components to a control plane after close. It does not destroy backend
resources or prove that external effects stopped.

Configure apparatus bounds through `OperationSupervisionConfiguration` in
`raes_runtime.operation_supervision_configuration` and pass it as `supervision=`.
The default execution limit is 30 seconds. Admission, observation, store calls
and drain each have a 2-second limit. Default capacity is 1 effect, 2 control
and 4 store calls. Budgets must be positive integer milliseconds, up to
2,147,483,647. Capacity must be an integer from 1 to 64. Neither accepts booleans
or coerced values. Authored apparatus budgets can reduce the execution limit.
Progress and duplicate requests do not renew it.

The admitted request keeps its original actor and target/run. It also keeps the
command digest, invocation/attempt, deployment and owner generations, predecessor
revision, effect scope and budget origin. The ledger consumes dispatch permission
before calling a backend. A lost reply to that write grants no permission.
SQLite schema 7 stores these facts. P0 keeps them only while the process lives.

Opaque command commitments use HMAC-SHA256. Only the live artifact owner holds
the random key. The ledger and engine history store neither that key nor an
unkeyed native-plan digest that depends on account credentials. The owner checks
the protected commitment before dispatch and result validation. Native plan and
snapshot projections keep their existing digest rules. Restart cannot restore
the private command authority from the ledger.

Native phase methods still return `ApplyResult`. Validation refusal before
dispatch withdraws acceptance as `CANCELLED`. An unsuccessful dispatched call,
timeout or malformed result becomes `INDETERMINATE` and retains exclusion.
Native success still passes the existing predecessor, plan/domain, disclosure
and release checks. The snapshot, status and audit then commit together.
A stale candidate never replaces the current snapshot.

Install the optional protocol through `RuntimeTarget.operation_provider`, with
all four contract IDs declared and all six methods installed. See the
[backend integration reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/backend-operation-supervision.md).
Supply a trusted `OperationEvidenceResolver` as `operation_evidence=`. It must
resolve authorized witnesses bound to their content. It must establish their
effect scope, cessation and result meaning. A backend assertion alone cannot
prove these facts. RAE checks the resolved native snapshot digest and the existing
native validation gates. The whole result path runs within one shrinking limit.
This includes archive callbacks and authored observation collection, protection
and retention. Prepared observation results commit with terminal state.

The phase path enforces single-invocation, apparatus-clock `terminate` policies
with preserved validity. It refuses unsupported choices before dispatch. These
include recovery, semantic clock, repetition, continuation and fresh trials.
Existing participant, workflow, time and trial controllers keep their semantic
owners. They use the shared state writer and bounded served admission. This
guide makes no new interruption or continuation promise for those controllers.

## Stop, cancellation and reconciliation

P0/P1 embedders call `stop_admission()` or `cancel_operation()` through their
trusted host. P2 uses the existing administrative identity boundary:

| Route | Required authority and behavior |
| --- | --- |
| `POST /execution/stop` | Operator; persistently closes new effect admission. |
| `POST /operations/{operation_id}/controls` | Operator; accepts the published `BackendOperationControlModel`, with that operator's actor/scope, exact binding and bounded budget. |
| `GET /operations/{operation_id}/controls/{control_id}` | Administrative read admission plus core supervision authorization; returns retained disposition or `null`. |
| `POST /operations/{operation_id}/absence-resolution` | Operator and a fresh `Idempotency-Key`; body names `control_id` for a verified reconciliation witness. |

Control intent and its actor audit commit before delivery. An identical control
returns its retained intent. Changed content is a conflict. Accepting cancellation
does not prove cessation. A validated completion can win a race with cancellation.
Once terminal, a parent keeps its outcome.

Controls retain their original budget and use one local deadline across the
intent write, delivery claim and provider call. Workers receive the remaining
allowance in a separate grant. They deduct the time spent receiving it. Expired
controls cannot get delivery grants. Neither can reopened controls whose clocks
lack continuity. Externally authored controls need a current UTC origin. A future
origin or clock skew that prevents continuity causes refusal. It grants no fresh
time.

Each invocation retains at most 128 automatic observations, 64 operator
observations, 32 cancellations and 32 reconciliations. Automatic polling waits
at least 250 milliseconds. Longer execution budgets use a longer interval to fit
the 128-observation allowance. Filling observation capacity leaves the separate
cancellation and reconciliation slots free. This also holds after reopening.
Stop admission uses no invocation slot.

Ordinary responses have a separate 768-entry limit. This leaves room for operator
recovery dispositions and a terminal outcome. A control can retain one response
of each message kind. An exact sequence/content retry is idempotent. A new attempt
needs a fresh control identity and space in its category. These limits are finite.
The runtime refuses excess intent or responses. It never drops consumed identities
or rewrites history to make space.

An indeterminate parent remains reserved after administrative snapshot
acceptance. An operator can obtain and independently verify scoped absence and
cessation. A separate linked resolution can then discharge exclusion. Unknown,
partial or complete effects do not qualify for this absence-only resolution.
Their native outcome evidence still needs its own validation. The runtime does
not infer rollback, clean state or replay permission.

Stop leaves status, control and reconciliation available. It has no automatic
resume command. Restore closes admission even if the backup contains no active
grant. Missing records cannot prove that old effects stopped. Keep the restored
scope closed while the deployment inventories and fences outstanding effects.
Never remove the stop marker merely to retry an uncertain invocation.

HTTP effects, reads, authentication and supervision use independent bounded
capacity. Disconnecting an HTTP caller releases its wait; the internal actor
retains an acquired mutation until its physical worker settles. Queue overload
and deadlines return bounded unavailable responses. Every response remains
uncacheable and redacted. Store failure can prevent progress.

`close()` bounds drain. If callbacks or store close remain unresolved, it raises
and retains ownership for another drain attempt. It does not claim that a
cancelled future stopped a backend. A completed close keeps durable reservations
for uncertain distributed grants. Reopening never reissues consumed permission.
It grants no fresh budget when clock/command continuity is unavailable.

## Optional distributed delivery

Install the `distributed` Python extra for the Temporal SDK and PostgreSQL
client. The local composition does not require either service. The host sets up
and runs an approved self-hosted Temporal service. It also owns a separate RAE
ledger database and role. This package provisions neither.

Construct `PostgreSQLControlPlaneStore(PostgreSQLStoreConfiguration(...))` from
host-owned connection settings. The default TLS mode is `verify-full`.
Credentials use `SecretStr`, never a request, URL or process argument.
Call `initialize_schema()` explicitly with a schema-owning credential to bootstrap
the store. The runtime role needs access only to the ledger tables/sequences and
its own owner-lock session. Keep it separate from Temporal history, visibility
and workload credentials. Operators own database backup and restore. Restored
ledgers must start with effect admission closed. External inventory and fencing
must also account for effects absent from the backup.

`TemporalExecutionAdapter` accepts `TemporalExecutionConfiguration` and an
async `client_factory`. The factory returns an authenticated SDK client on its
owning loop. Pass the adapter as `distributed_execution=`. Namespace and worker
identity are explicit. Workflow, effect and control queues must be distinct.
The host owns endpoint approval, mTLS, authorization and network policy
following the [self-hosted service guide](https://docs.temporal.io/self-hosted-guide).

`TemporalOperationActivities` takes the installed provider, worker identity and
separate effect/control `RemoteOperationAuthority` clients. Each client has its
own bounded HTTP pool and a protected P2 bearer credential. Configure HTTPS.
The explicit insecure-loopback option is only for isolated local test sockets.
The configured worker must have the BACKEND role and the exact target binding.
Use `create_temporal_workers()` to construct the three SDK workers and run them
under the host's lifecycle manager. Their whole activity jobs and physical
backend calls drain separately from the service owner's lifecycle.

Workers retrieve the exact admitted request, recheck capability/willingness,
and ask P2 for a current one-use grant before invocation. Private
RPCs under `/operations/{operation_id}/invocation` require existing declared
administrative authorities plus the exact configured worker identity. Duplicate
delivery, stale ownership and lost grant replies cannot repeat an effect.
Engine history stores versioned opaque bindings, digests and queue/budget
settings. It excludes native plans, credentials and live resolver objects.
RAE keeps command identity and authority. Missing admitted native artifacts
close dispatch. They do not trigger replanning.

Temporal workflows use SDK time and single-attempt effect activities. Separate
supervision workflows remain deliverable after an effect workflow completes.
Stable workflow identities deduplicate delivery. They confer no permission and
do not provide exactly-once backend effects. The selected ledger has one live
owner for one target/run. PostgreSQL transactions preserve the same revision,
history-head, idempotency and atomic-audit gates as the local store.

The host must bind all access to the same backend resources to this authority.
An in-process component claim prevents another control plane/store or direct
`RuntimeManager` from reusing installed components. It complements external
resource fencing. Different processes, proxies or database paths cannot prove
ownership of shared physical resources by holding unrelated leases.
P0/P1/P2 guarantees remain unchanged, and P3 remains unavailable.

## Verification boundary

Targeted tests cover blocked calls, control capacity, one-use grants, stale
completion, loss/reopening, actor-bound intent, reconciliation and the actual
SDK sandbox. CI's `runtime-supervision` job runs real Temporal delivery through
P2 against PostgreSQL, including blocked effects and duplicate delivery. Its
development engine uses a separate SQLite history file. The host still owns
production service persistence. Repository-wide, service integration and fuzz
suites run in CI/CD. The tests supply scoped synthetic no-op witnesses.
They do not certify interruption or cessation for arbitrary backends.
