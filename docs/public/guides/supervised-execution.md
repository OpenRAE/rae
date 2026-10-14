# Supervise runtime execution

`RuntimeControlPlane` separates short state writes from native phase execution.
Provisioning, orchestration and evaluation retain a target/run effect reservation
while their backend calls run outside the state writer. Authorized stop and
control requests can use the writer during those calls.

## Local composition

Local execution uses AnyIO with separate effect, control and store capacity.
Configure apparatus bounds through `OperationSupervisionConfiguration` in
`raes_runtime.operation_supervision_configuration` and pass it as `supervision=`.
Defaults are 2 seconds for admission, observation, store calls and drain,
30 seconds for execution, and capacities of 1 effect, 2 control and 4 store calls.
Budgets are strict positive integer milliseconds, up to 2,147,483,647; capacities
are strict integers from 1 to 64. Authored apparatus budgets can reduce the
execution limit. Progress and duplicate requests do not renew it.

The admitted request retains its original actor, target/run, command digest,
invocation/attempt, deployment and owner generations, predecessor revision,
effect scope and budget origin. The ledger consumes dispatch permission before
calling a backend. Losing that write's acknowledgement supplies no permission.
SQLite schema 7 persists these facts; P0 keeps them only for the process lifetime.

Opaque command commitments use HMAC-SHA256 with a random key held only by the
live artifact owner. The ledger and engine history retain neither that key nor
an unkeyed native-plan digest that depends on account credential material.
The owner recomputes the protected commitment before dispatch and finalization.
Native plan and snapshot projections keep their existing digest conventions;
restart cannot reconstruct the private command authority from the ledger.

Native phase methods still return `ApplyResult`. Validation refusal before
dispatch withdraws acceptance as `CANCELLED`. An unsuccessful dispatched call,
timeout or malformed result becomes `INDETERMINATE` and retains exclusion.
Native success still passes the existing predecessor, plan/domain, disclosure
and release checks before atomic snapshot/status/audit publication. A stale
candidate never replaces the current snapshot.

Install the optional protocol through `RuntimeTarget.operation_provider`, with
all four contract IDs declared and all six methods installed. See the
[backend integration reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/backend-operation-supervision.md).
Supply a trusted `OperationEvidenceResolver` as `operation_evidence=`. It must
resolve authorized, content-bound witnesses and establish their effect scope,
cessation and result meaning. A backend assertion is insufficient. RAE checks
the resolved native snapshot digest and its existing native validation gates.
Complete result finalization, including archive callbacks and authored
observation collection, protection and retention, runs inside one shrinking
allowance. Prepared observation results join the atomic terminal cut.

This phase integration enforces single-invocation, apparatus-clock `terminate`
policies with preserved validity. It refuses unsupported recovery, semantic
clock, repetition, continuation and fresh-trial choices before dispatch. Existing
participant, workflow, time and trial controllers retain their semantic owners.
They receive the shared state writer and bounded served admission; this guide
makes no new interruption or continuation guarantee for those controllers.

## Stop, cancellation and reconciliation

P0/P1 embedders call `stop_admission()` or `cancel_operation()` through their
trusted host. P2 uses the existing administrative identity boundary:

| Route | Required authority and behavior |
| --- | --- |
| `POST /execution/stop` | Operator; persistently closes new effect admission. |
| `POST /operations/{operation_id}/controls` | Operator; accepts the published `BackendOperationControlModel`, with that operator's actor/scope, exact binding and bounded budget. |
| `GET /operations/{operation_id}/controls/{control_id}` | Administrative read admission plus core supervision authorization; returns retained disposition or `null`. |
| `POST /operations/{operation_id}/absence-resolution` | Operator and a fresh `Idempotency-Key`; body names `control_id` for a verified reconciliation witness. |

Control intent and its own actor audit commit before delivery. An identical
control repeats its retained intent; changed content is a conflict. Cancellation
acceptance does not establish cessation. A validated completion can win a race
with cancellation. Once terminal, a parent keeps its outcome.

Controls retain their original budget and use one local deadline across the
intent write, delivery claim and provider call. Workers receive a separate
remaining allowance and deduct grant-delivery time. Expired controls and
controls reopened without that clock continuity cannot obtain delivery grants.
Externally authored controls require a current UTC origin; a future origin or
clock skew that prevents continuity causes refusal rather than fresh time.

Each invocation retains at most 128 automatic observations, 64 operator
observations, 32 cancellations and 32 reconciliations. Automatic polling waits
at least 250 milliseconds, increasing the interval for longer execution budgets
to fit its 128-observation allowance. Exhausting automatic or operator
observation capacity preserves the separate cancellation and reconciliation
slots, including after reopening. Stop admission uses no invocation slot.

Ordinary responses have a separate 768-entry limit, leaving room for operator
recovery dispositions and a terminal outcome. A control can retain one response
of each message kind; an exact sequence/content retry is idempotent. A new
attempt needs a fresh control identity and remaining capacity in its category.
These limits are finite: the runtime refuses excess intent or responses and
never discards consumed identities or rewrites history to make space.

An indeterminate parent remains reserved after administrative snapshot
acceptance. A separate linked resolution can discharge exclusion when the
operator obtains and independently verifies scoped absence and cessation.
Unknown, partial or complete effects do not qualify for this absence-only
resolution. Their native outcome evidence remains subject to its own validation;
the runtime does not infer rollback, clean state or replay permission.

Stop leaves status, control and reconciliation available. It has no automatic
resume command. Restore closes admission even if the backup contains no active
grant: missing records cannot prove that old effects stopped. Keep the restored
scope closed while the deployment inventories and fences outstanding effects.
Never remove the stop marker merely to retry an uncertain invocation.

HTTP effects, reads, authentication and supervision use independent bounded
capacity. Disconnecting an HTTP caller releases its wait; the internal actor
retains an acquired mutation until its physical worker settles. Queue overload
and deadlines return bounded unavailable responses. Every response remains
uncacheable and redacted. Store failure can make liveness conditional.

`close()` bounds drain. If callbacks or store close remain unresolved, it raises
and retains ownership for another drain attempt. It does not claim that a
cancelled future stopped a backend. A completed close classifies outstanding
distributed grants conservatively and preserves their durable reservations.
Reopening never reissues consumed permission or creates a fresh budget when
clock/command continuity is unavailable.

## Optional distributed delivery

Install the `distributed` Python extra for the Temporal SDK and PostgreSQL
client. The local composition does not require either service. The host
configures and operates an approved self-hosted Temporal service and a separate
RAE ledger database/role; this package provisions neither.

Construct `PostgreSQLControlPlaneStore(PostgreSQLStoreConfiguration(...))` from
host-owned connection settings. The default TLS mode is `verify-full`.
Credentials use `SecretStr`, never a request, URL or process argument.
`initialize_schema()` is an explicit bootstrap action under a schema-owning
credential. The runtime role needs access only to the ledger tables/sequences
and its own owner-lock session. Keep it separate from Temporal history,
visibility and workload credentials. Database backup/restore is an operator
procedure: restored ledgers must start with effect admission closed and require
external inventory/fencing, including effects absent from the backup.

`TemporalExecutionAdapter` accepts `TemporalExecutionConfiguration` and an
async `client_factory` that returns an authenticated SDK client on its owning
loop. Pass the adapter as `distributed_execution=`. Namespace and worker
identity are explicit. Workflow, effect and control queues must be distinct.
The host configures endpoint approval, mTLS, authorization and network policy
following the [self-hosted service guide](https://docs.temporal.io/self-hosted-guide).

`TemporalOperationActivities` takes the installed provider, worker identity and
separate effect/control `RemoteOperationAuthority` clients. Each client has its
own bounded HTTP pool and a protected P2 bearer credential. Configure HTTPS;
the explicit insecure-loopback option is only for isolated local test sockets.
The configured worker must have the BACKEND role and the exact target binding.
Use `create_temporal_workers()` to construct the three SDK workers and run them
under the host's lifecycle manager. Their whole activity jobs and physical
backend calls drain independently of the service owner's lifecycle.

Workers retrieve the exact admitted request, recheck capability/willingness,
and ask P2 for a current one-use grant immediately before invocation. Private
RPCs under `/operations/{operation_id}/invocation` require existing declared
administrative authorities plus the exact configured worker identity. Duplicate
delivery, stale ownership and lost grant replies cannot repeat an effect.
Engine history contains versioned opaque bindings, digests and queue/budget
configuration, excluding native plans, credentials and live resolver objects.
RAE retains command identity and authority; missing admitted native artifacts
close dispatch rather than trigger replanning.

Temporal workflows use SDK time and single-attempt effect activities. Separate
supervision workflows remain deliverable after an effect workflow completes.
Stable workflow identities deduplicate delivery; they confer no permission and
do not provide exactly-once backend effects. The selected ledger has one live
owner for one target/run. PostgreSQL transactions preserve the same revision,
history-head, idempotency and atomic-audit gates as the local store.

The host must bind all access to the same backend resources to this authority.
An in-process component claim prevents another control plane/store or direct
`RuntimeManager` from reusing installed components. It complements external
resource fencing; different processes, proxies or database paths cannot prove
ownership of shared physical resources merely by holding unrelated leases.
P0/P1/P2 guarantees remain unchanged, and P3 remains unavailable.

## Verification boundary

Targeted tests cover blocked calls, control capacity, one-use grants, stale
completion, loss/reopening, actor-bound intent, reconciliation and the actual
SDK sandbox. CI's `runtime-supervision` job runs real Temporal delivery through
P2 against PostgreSQL, including blocked effects and duplicate delivery. Its
development engine uses a separate SQLite history file; production service
persistence remains host configuration. Repository-wide, service integration
and fuzz suites run in CI/CD. The tests supply scoped synthetic no-op witnesses;
they do not certify interruption or cessation for arbitrary backends.
