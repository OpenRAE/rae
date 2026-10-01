# Operation Supervision and Recovery Semantics

Status: design authority under ADR-104, issue #1348 and API-404.
Classification: FM3. This specification defines obligations for implementation;
it does not publish a wire schema or assert deployed interruption, bounded
shutdown, checkpoint continuation, or physical containment.

The [operation model](README.md) owns the persisted state matrix and atomic
store invariants. The [decision](../../../docs/decisions/issue-1348-operation-lifecycle.md)
records canonical requirement dispositions and current implementation gaps.

## S1 — Authority and admission

RAE is the shared product runtime driving backend execution. Authors select
required semantics through the owning workflow, time, realization and trial
contracts. The processor preserves them in admitted plans; the runtime admits,
drives, supervises and classifies operations. Backends own concrete realization,
effect observation and contextual willingness. Embedders own process deployment.

For an operation, let `R` be its exact admitted requirements, `C` the effective
capabilities of the installed backend for that operation kind and context, and
`W` its current willingness. Admission requires `C satisfies R` and `W`.
Manifest declarations, installed protocol support, willingness and evidence of
satisfaction are independent facts. Recheck context after queueing and before
dispatch; prior willingness is not an irrevocable promise. Missing, unsupported,
contradictory or refused required guarantees prevent invocation. Never silently
shorten a required duration, weaken a requirement, substitute another backend,
or interpret absence of support as best effort. An authored alternative needs
fresh admission and preserved provenance.

Admission and supervision use existing authentication, role/subject checks,
bounded request admission, closed value/config/manifest validators and safe
diagnostics. The original actor, target/run, kind and request commitment remain
immutable. Every supervisor is independently authorized for the exact operation
and records its own actor and request identity; it cannot replace the original
actor or widen scope. Operational audit, participant observation and archival
evidence retain their existing authorities. No credentials, raw input, native
exception text, process arguments or environment dumps enter these records.

## S2 — Three boundaries, one state authority

| Boundary | Required action | What it establishes |
| --- | --- | --- |
| Admission/claim | Validate requirements and authority; atomically claim scoped identity and record intent. | `ACCEPTED`, not an external effect. Denial before claim remains audit only. |
| Dispatch | Revalidate admission and willingness; reserve the conflicting-effect scope and record `RUNNING` before invoking. | Permission for this invocation, not its success. P1/P2 persist before invocation; P0 orders in process only. |
| Settlement | Validate effect evidence and all required result/release gates, then commit snapshot, terminal record and actor-bound audit atomically with revision CAS. | One authoritative outcome, not universal external rollback or exactly-once effects. |

One owner still serializes **state mutations**, including supervision records.
External calls must not hold the logical permit needed to record supervision.
The owner releases that short state permit after dispatch while retaining an
execution reservation that excludes conflicting effects. This is not admission
of another writer or store. A completion reacquires the same authority and
checks operation identity, execution generation, current terminal state and
snapshot revision before publication. A stale revision requires reconciliation
against current state, never blind snapshot merge or backend re-invocation.

Use target/run-wide exclusion unless narrower independence is established by
the admitted contract. Reads and bounded supervisory requests remain serviceable
while an external invocation is blocked. Reserve bounded control capacity across
HTTP admission, workers and audit queues, as well as the core authority; putting
a cancel request behind a saturated effect queue does not satisfy supervision.
Control overload has a bounded, explicit rejection and cannot silently discard
an acknowledged request. No callback gains authority to mutate the store.

An execution generation fences stale **state publication**. It does not fence
a remote effect. Release the conflicting-effect reservation only when the
admitted backend guarantee establishes cessation and a known reconciled effect
boundary. Otherwise retain quarantine, even after a terminal `INDETERMINATE`
record. A direct `RuntimeManager` or new control-plane instance targeting the
same resources cannot be used to bypass this exclusion.

## S3 — Supervision is orthogonal to operation state

The persisted states remain `ACCEPTED`, `RUNNING`, `SUCCEEDED`, `FAILED`,
`CANCELLED`, `INDETERMINATE`. No `CANCELLING`, `TIMED_OUT` or `PARTIAL` operation
state is introduced. Queue residence before a claim is not an operation state.
The conceptual supervision dispositions are request recorded, backend accepted,
backend refused/unsupported, and cessation established. They need correlated,
ordered evidence; they are not new published enum values in this issue.

- Stop admission: reject new effect work and prevent queued work from dispatching
  after the stop boundary. It does not stop work already dispatched. Continue
  authorized status, supervision and reconciliation during drain.
- Cancel before dispatch: serialize cancellation against dispatch. The winner
  determines whether invocation is possible. An unclaimed waiter leaves no
  operation; a claimed `ACCEPTED` operation can atomically become `CANCELLED`.
  Contextual refusal after claim but before dispatch withdraws that acceptance
  through `CANCELLED` with a refusal diagnostic; it is not a pre-claim denial.
  If write-ahead `RUNNING` was already recorded but no call occurred, classify
  the proven absent effect through the ordinary running settlement boundary.
- Cancel after dispatch: record and deliver a scoped request through the
  admitted backend control capability. Acceptance means the backend undertakes
  the request, not that effects ceased. Refusal/unsupported leaves the executing
  operation running until observed settlement or the supervision budget expires.
- A proven cancellation requires scoped evidence that no further prohibited
  effects can occur and that residual effects satisfy the cancellation contract.
  `CANCELLED` can retain known partial effects; it never means universal rollback.

Cancellation and completion race through one terminal-commit boundary. If
success commits first, cancellation observes the terminal result. If a request
is accepted first but work completes before cessation, the valid result may
still be `SUCCEEDED`; the request disposition is retained separately. Once
cancellation or indeterminacy commits, a late result cannot rewrite the parent.
Record admissible late evidence for linked resolution through the same authority.
Repeated requests with the same scoped request identity are idempotent; they do
not multiply interrupts, reset deadlines or create another execution attempt.

Workflow cancellation, participant episode termination, stopping a backend,
operation completion and verified cleanup are distinct outcomes. A successful
operation that records a workflow cancellation proves only its admitted action.
A disconnect, cancelled future or killed local process proves no remote cessation.

## S4 — Deadlines and shutdown

Operational budgets use local apparatus monotonic elapsed time. Each admitted
budget is positive, finite, validated and bound to its stage and origin:

| Budget | Starts | Expiry consequence |
| --- | --- | --- |
| Admission/queue, including lease acquisition | Receipt into the bounded queue or start of the admission attempt | Reject unclaimed work; cancel a claimed but undispatched operation. Never dispatch an expired waiter. |
| Execution, including contextual provider calls | Before the first external call of the stage | Close dependent admission, request supported interruption, and begin bounded settlement. Expiry supplies no effect evidence. |
| Interruption/observation | First control request or reconciliation observation | Retain exclusion and classify unknown effects as indeterminate; do not wait forever for an observer. Duplicate requests do not renew the budget. |
| Commit/readback | Start of the store transaction attempt or its bounded readback | Stop admission; use atomic readback. Unknown acknowledgement poisons readiness and publication until authoritative state is established. |
| Drain/close | Stop-admission boundary | Escalate to the embedder with unresolved operations and retained exclusion; never report successful shutdown solely because the budget expired. |

Nested calls consume the remaining enclosing budget; bounded retries or fan-out
cannot renew it. Store waits and audit publication are covered too: if the
single state authority itself cannot make progress, supervision reports inability
to establish settlement rather than claiming a persisted terminal outcome.
Liveness is conditional on the admitted store/control/backend capabilities;
there is no universal hard real-time claim.

Authored deadlines retain the shared time model's clock, domain, segment and
mapping semantics. Scenario pause/reset cannot pause apparatus supervision.
When an operational ceiling is incompatible with an authored guarantee, reject
admission; do not silently reinterpret the authored deadline. Use the owning
policy's existing defaults when no additional guarantee is selected.

Monotonic readings are not portable restart timestamps. Durable records use the
incumbent strict UTC format plus the selected budget and origin evidence.
Restart must establish clock continuity/elapsed bounds or classify them unknown;
it cannot restart a full execution budget or resume from a raw monotonic value.
Keep existing strict workflow timestamp validation and inclusive expiry rules.

Shutdown stops admission, requests supported cessation, settles or quarantines
operations, closes the store provider, then releases the owner lease. If store
close is unconfirmed, retain the lease while the process lives. If the embedder
must terminate the process, that is a declared loss boundary: a restart acquires
the store lease but remains unready until external work is reconciled. Local
lease release or process death is never an external fence. Restore obeys the
same rule because the database can be older than backend effects.

## S5 — Effects, terminal publication and reconciliation

Classify knowledge of effects separately from the requested outcome:

| Established evidence | Terminal classification |
| --- | --- |
| Quiescent, known absent; the operation did not meet its contract | `FAILED`, or `CANCELLED` for established cancellation under its contract. |
| Quiescent, all admitted requirements/results/release gates satisfied, including a validated no-op | `SUCCEEDED`; a no-op need not change the snapshot revision. |
| Quiescent, known partial or otherwise known nonconforming effects | `FAILED`, or `CANCELLED` if the cancellation contract is established; retain validated residual state. |
| Unknown residual effects, unproved cessation, malformed/untrusted result, or inconclusive observation | `INDETERMINATE`; preserve trusted state and quarantine the affected scope. |

An effect-absent observation at one instant is insufficient while a worker can
still act. A generic backend exception or `success=false` with the predecessor
snapshot proves neither absence nor known failure. ASR-532 still rejects unsafe
results and preserves the trusted predecessor; that preservation does not assert
the external world is unchanged. Observed effects do not imply satisfaction of
the complete operation contract, including final disclosure/release gates.

Commit a validated partial snapshot only through existing domain/result
validation and atomic terminal publication. If existing carriers cannot express
that evidence or its residual scope losslessly, use indeterminacy, not free-form
metadata or a fabricated success. Compensation is separately admitted work under
SEM-204; compensation failure and SCE-007 cleanup results never erase the primary
outcome or certify environmental reversal.

Reconciliation is bounded **observation and classification**, not replay. It
uses immutable operation/actor/request/backend context, scoped effect identity,
validated state and evidence of cessation. Missing observation capability is
permitted in existing P1/P2 compositions, whose fallback is indeterminacy. It
does not satisfy an operation explicitly requiring provable interruption,
recovery or continuation; such an operation must fail admission.

Lost commit acknowledgement is uncertainty about the store, distinct from
uncertainty about the backend. Read back the complete atomic cut before exposing
a terminal result or releasing exclusion. If the cut cannot be established,
preserve the last trusted projection as stale, poison readiness and refuse new
effect work. Do not write a second terminal outcome to compensate for a timeout.
After restart, read the authoritative operation before any recovery classification.

An `INDETERMINATE` parent is immutable. A separately authorized linked resolution
operation can establish new evidence and disposition, with its own audit and
idempotency claim. Administrative acceptance of a snapshot acknowledges a choice;
it does not establish cessation, retry safety, a clean range or scientific
validity. Quarantine is discharged only by the required effect/cessation evidence
and applicable admission rules, not by the existence of the child receipt.

## S6 — Author-directed subsequent work

Use the existing authored policies and their normative defaults. Durability adds
none of the permissions below. Fresh authorization and current backend
willingness are required whenever subsequent work can produce effects.

| Action | Authority and necessary evidence |
| --- | --- |
| Transport retry | Same actor-scoped idempotency claim returns the same operation; no invocation. Credential-sensitive retry still needs its existing exact ephemeral proof; use status retrieval when that proof is unavailable after restart. A fresh key alone authorizes nothing. |
| Workflow retry | SEM-203's retry graph, attempt bounds, guards and history. It is not a store-recovery retry loop. |
| Another trial execution attempt | SCE-007 `ExecutionRetryPolicyModel`: remaining attempts, selected after-effect posture, and established idempotence or required reset/compensation evidence. New `execution_attempt_id`, same admitted entry and archival `run_id`. |
| Resume | Explicit permitted continuation, a compatible checkpoint/continuation boundary, reconciled effects, preserved workflow/participant/time state and valid inputs/authority. Same run and preserved history; any new control operation links to the original. A snapshot alone is insufficient. |
| Terminate | Authorized policy ends the relevant control flow and closes admission; separately report backend cessation, episode outcome, cleanup and trial validity. Emergency administrative stop can contain work but cannot silently change authored success/validity criteria. |
| New trial | Authorized allocation under EXP-706/SCE-002, distinct admitted trial coordinate/run identity, clean or declared reusable initial state and SCE-006/007 isolation/cleanup evidence. Preserve the failed/interrupted trial and its invalidation evidence. |

No resumed or repeated effects enter a quarantined scope. An independently
isolated new trial may be admitted only with evidence that old work cannot reach
its resources; changing an operation id, run id, backend name or store path is
not isolation. If required cleanup fails, deny reuse and preserve its independent
failed/partial/unverified result. Failure requiring a new trial cannot be
converted into continuation, and permission for a new trial does not allocate it
automatically. For executions without an experiment, no trial wrapper is required.

Before effects, inability to establish a required guarantee means refusal.
After dispatch, classify known non-satisfaction as failure and uncertainty as
indeterminate, record the requirement violation and applicable trial deviation
or invalidation, and stop dependent admission. A refusal is not permission to
retry, substitute, replan or weaken requirements. Selectable future physical-OT
protections follow these same admission rules; ordinary simulations and CTFs
do not inherit them or gain a safety-certification claim.

## Bounded verification and implementation boundary

`implementations/python/tests/operation_supervision_model.py` is a finite
abstract oracle. `test_issue_1348_operation_supervision.py` checks S1–S6 through
admission refusal, cancellation/completion order, 64 effect-evidence
combinations, late/stale completion, atomic publication uncertainty, monotonic
expiry and continuation counterexamples. Evidence booleans are assumptions
supplied by the modeled boundary; they do not implement or prove those witnesses.
The model covers one operation and one conflicting-effect scope. It is not a
thread scheduler, storage implementation, wire codec, unbounded proof or runtime
refinement. Existing lifecycle/profile and cleanup contract tests retain their
separate claims. No new profile capability is claimable from these model tests.
