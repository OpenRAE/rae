# Ledger, execution and recovery protocol

Integration rules adopted by [ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md).
These describe the selected design and implementation obligations, not a shipped
PostgreSQL provider, wire protocol or P3 conformance result. The existing
[supervision model](../../../specs/formal/runtime-control-plane/supervision.md)
continues to own operation outcomes. Internal claim phases below are not new
portable operation states.

## Admission and dispatch

1. The authenticated RAE admission boundary resolves the authored policy and
   verifies the selected composition, plan, actor, target/run, capability and
   willingness. The scoped state writer atomically records the immutable
   operation/request commitment and admitted command reference. This is ledger
   authority, not a second scheduler or a replacement broker.
2. Start Temporal using a stable identity bound to that admitted operation and
   execution generation. Reject duplicate/reused identities; an existing
   execution must match the ledger binding. A timeout starting the workflow
   triggers readback or resubmission of that same identity, not a new operation.
   Start reconciliation uses the ledger's retained nonterminal commands and
   Temporal's duplicate-start controls, not a custom durable delivery queue.
3. The trusted effect worker decodes a bounded versioned command and authenticates
   to RAE's state authority. Fetch and verify the admitted commitment, artifact
   digest and selected capability there. An opaque engine ID, replayed activity
   output, process-local planner registration or possession of a secret
   reference cannot establish worker authority. Resolve credentials only after
   authorization through the backend's scoped secret mechanism.
4. Immediately before external execution, ask the current state writer to
   consume a **one-use invocation claim**, tied to operation, authored attempt,
   worker identity, expected owner generation and conflicting-effect scope.
   The transaction rechecks policy/budget and admission state, records the
   invocation and retains its effect reservation. Cancellation committed before
   this cut prevents dispatch. The first confirmed consumer alone may invoke;
   duplicated delivery can observe the existing claim, never receive another
   invocation permission for it. No database transaction remains open across
   the backend call.
5. A lost claim acknowledgement is not a reusable grant. Fail closed and
   reconcile unless the protocol proves that this exact live consumer received
   and has not used a valid grant. In the initial conservative design, ambiguous
   grant delivery admits no invocation. A confirmed grant can still outlive a
   caller or owner: retain its reservation until cessation/effect evidence
   accounts for it. This deliberately trades liveness for honest effect scope.
6. Workers return correlated backend results/evidence to the state authority;
   they do not write snapshots. Validate against the trusted predecessor,
   admitted policy and native result/release validators. Atomically commit the
   permitted snapshot change, terminal operation and matching audit, using
   revision comparison. Engine acknowledgement happens after that cut. Repeated
   terminal-commit requests resolve through the same immutable identity/readback.

Temporal replay may repeat bookkeeping activities and may redeliver an effect
task, but it cannot consume the same invocation claim twice. An explicitly
permitted retry needs a new admitted attempt/invocation and the
[resolved author policy](authored-retry-policy.md). It is not forbidden merely
because it is a retry. Conversely, backend idempotency alone cannot authorize it.

## Failure windows

| Lost boundary | Recovery action; effect authority |
| --- | --- |
| Before admission commit | Read by scoped request identity to resolve commit uncertainty; do not enqueue an unconfirmed operation. |
| Admission committed, start absent/ack lost | Reconcile/start the same engine identity from the ledger. No effect exists solely from this command record. |
| Start recorded, invocation not consumed | Redelivery still needs the current claim gate. A cancellation or owner change can deny it. |
| Claim consumed, worker dies before or after backend call | Treat the effect as unknown until validated observation plus cessation establishes otherwise. Do not infer absence from missing engine result. |
| Effect applied, worker/result acknowledgement lost | Observe using the same invocation identity; never replay it to discover the answer. A different authorized retry follows the policy and retained reservation rules. |
| Result received, ledger commit uncertain | Close mutation readiness, read the ledger's atomic cut, and reconcile. No receipt says success before a confirmed commit. |
| Ledger terminal committed, engine acknowledgement lost | Return the committed outcome to a duplicate bookkeeping request; never invoke the backend to regenerate it. |
| Cancel and completion race | Serialize their admissible state cuts. A control receipt records a request; only evidence permits cancellation settlement. A validated completion can win. |
| Late result after terminal or owner replacement | Validate scope/generation and attach through the existing linked-resolution authority where admissible. Do not rewrite the immutable terminal parent or allow a stale writer to commit. |
| Engine history expired/reset/manually redriven | Consult retained ledger identity/claims first. History absence is no new permission. Missing or inconsistent binding closes admission for that scope. |

The probe evidence covers representative duplicate effects, cancellation and
publication cuts, not this entire end-to-end protocol. The claim mechanism
requires a transactional provider and tests against the actual engine/backend
composition before it can be advertised.

## Supervision and bounded ownership

An independently authorized supervisor binds its own actor and unique request
identity to the original operation scope. Persist the request at the same state
authority, then dispatch it through the separate control workers. Backend
refusal is a disposition; timeout is uncertainty; neither is cessation. Stop
admission immediately where permitted while separately accounting for active
effects. An observation/control callback must not acquire the blocked effect
worker's capacity or long-lived permit.

Provision independent bounded admission, worker, store-connection and rejection-
audit capacity for control. Give every callback/commit/drain a finite stage
budget and retain unresolved reservations after budget expiry. Service/store
unavailability can prevent semantic mutation; it must still yield a bounded
unavailable response. No service queue promises physical interruption during its
own outage. Use backend containment evidence when a stronger admitted guarantee
requires it, or refuse that operation before execution.

Exactly one current state writer owns each admitted target/run scope. For the
future remote provider, owner admission/renewal uses PostgreSQL transactions and
a monotonically changing generation; every mutation compares it. A partitioned
writer that cannot validate current ownership cannot commit or issue a new
grant. This is a store fence only. A worker holding an earlier confirmed grant
may still act, so ownership replacement preserves all consumed claims and
effect reservations. A new owner may reconcile/control those invocations, but
cannot admit conflicting effects until the required cessation or isolation is
established. No lease timeout alone releases them.

Federated homes cannot both own the same effect scope. Migration requires an
explicit admission-stop and ownership handoff, retained state/claims, scoped
credential revocation, and reconciliation of outstanding effects. If a backend
cannot establish a required fence/cessation, keep the scope quarantined. Parallel
execution uses the existing admitted independence/resource-reservation rules;
it cannot be enabled simply by adding workers.

## Restore, retention and upgrades

Temporal and the ledger have independent persistence transactions and backups,
even when hosted on one PostgreSQL installation. Restore into **closed effect
admission** with fresh deployment authority. Establish backend inventory and
effect scope, restore compatible command/history bindings, and reconcile each
potentially active invocation before reopening. A ledger rolled back before a
consumed claim is especially dangerous: its apparently absent record is not
absence of an external effect. Reconcile the whole affected deployment scope,
including resources no longer represented in the backup. If that inventory or
containment cannot be established, do not reopen that scope.

Do not allow restored engine tasks to dispatch against an empty/new ledger.
Mismatch of deployment generation, operation commitment or version fails closed.
Backend state backups, trial evidence and semantic-clock continuity have their
own restore obligations; an orchestration restore cannot certify them. Fresh
trials require their own isolation/clean-state admission after recovery.

Retain deduplication/claim and resolution records at least as long as any
possible effect, replay or admitted recovery requires them. Engine history
retention alone cannot govern their deletion. Unsupported recovery windows are
refused, not bridged by blind execution. Versioned workflow workers and ledger
carrier migrations must preserve these bindings and remaining budgets. Do not
roll over a history until pending controls and claimed effects have an explicit
handoff; retain old workers for outstanding compatible histories.
