# Workflow state machine

## State variables

- `current`: active control locations, identified by workflow invocation and branch
- `steps[step].lifecycle`: `pending | running | completed`
- `steps[step].outcome`: `none | succeeded | failed | exhausted`
- `steps[step].attempts`: non-negative integer
- `workflow.status`: portable workflow execution status, separate from step lifecycle and outcome

The portable workflow result contract exposes only workflow-visible step state
through a wire-safe plain-data envelope. Language-native runtime models may be
derived from that envelope after validation.

## Step kinds

- `objective`
  - observable outcomes: `succeeded`, `failed`
  - attempts: exactly `1` once running or completed
- `retry`
  - observable outcomes: `succeeded`, `exhausted`
  - attempts: total number of tries performed
- `parallel`
  - observable outcomes: `succeeded`, `failed`
  - attempts: exactly `1` once running or completed
- `decision`
  - not step-state observable
- `switch`
  - not step-state observable
- `join`
  - not step-state observable
- `call`
  - observable outcomes: `succeeded`, `failed`
  - attempts: exactly `1` once running or completed
- `end`
  - not step-state observable

## Transition rules

These rules define portable control meaning, independent of backend scheduling.
Each workflow invocation starts at its declared `start` step.
Only observable kinds have portable lifecycle, outcome, and attempt state.
Pending observable steps have zero attempts and no outcome.
Running observable steps have no outcome.
Unselected steps can remain pending.

### Shared observable steps

Each named observable step has one execution and one state entry per workflow invocation.
The first branch arrival starts the step from `pending`.
An arrival while the step is `running` waits for that execution's result.
An arrival after completion reuses the stored outcome without restarting the step.
Each arriving branch retains its identity and takes the continuation selected by that outcome.

Reusing a result does not increment `attempts` or create another execution completion.
Shared retry arrivals use one attempt budget.
Shared call arrivals use one callee invocation.
Shared parallel arrivals use one fanout activation.
Each successful parallel arrival continues at that parallel's join `next` target after barrier release.
Its failure arrivals use the parallel failure rule.

The join releases the fanout activation once; each arriving branch separately consumes that activation's result.
Control-only decisions and switches evaluate on each visit.
Successful shared compensable steps register compensation once, at execution completion.
These rules describe required meaning; existing contract checks do not establish backend enforcement of shared execution.

### Objective

On first entry, `pending -> running` and `attempts = 1`.
Execute the declared `objective` using its admitted realization mode.
Success gives `running -> completed`, outcome `succeeded`, and control moves to `on-success`.
Failure gives `running -> completed` and outcome `failed`.
Control then moves to `on-failure` when that target is present.
Otherwise, the failure is unhandled.

### Decision

Evaluate `when` using the state visible at this control location.
If true, move control to `then`; otherwise, move control to `else`.
Choose exactly one successor.
This transition creates no observable step result.

### Switch

Evaluate `cases[].when` in authored list order using the visible predicate state.
For the first true predicate, move control to that case's `next` target.
Do not take another case, even if its predicate is also true.
If no case matches, move control to the required `default` target.
Choose exactly one successor and create no observable step result.

### Parallel

On first entry, `pending -> running` and `attempts = 1`.
Replace the incoming control location with one branch location for each declared branch root.
Each branch retains its identity until it reaches this activation's declared `join`.
Advance branches using the [interleaving rule](#parallel-interleaving).

Successful barrier release gives `running -> completed` and outcome `succeeded`.
An unhandled branch failure prevents successful barrier release.
Parallel failure gives `running -> completed` and outcome `failed`.
Take the parallel's `on-failure` target when present; otherwise, propagate the unhandled failure.
The failed activation cannot later release its join.
A handled branch-local failure can still converge successfully.

### Join

A branch that reaches its owning `join` waits there.
Release the barrier only when every explicit branch of that parallel activation has arrived.
Complete the owning parallel successfully and replace its waiting branch locations with one continuation at the join's `next` target.
Release that activation once.
The join creates no observable step result.

### Retry

On first entry, `pending -> running` and the first objective attempt sets `attempts = 1`.
Each failed attempt starts another attempt while `attempts < max-attempts`.
Increment `attempts` when the next attempt starts; keep lifecycle `running`.

The first successful attempt gives `running -> completed`, outcome `succeeded`, and control moves to `on-success`.
Failure of the final permitted attempt gives `running -> completed` and outcome `exhausted`.
Move control to `on-exhausted` when present; otherwise, the exhaustion is unhandled.
The attempt count is the total number of tries performed.

### Call

On first entry, `pending -> running` and `attempts = 1`.
Start a separate invocation of the declared `workflow` at its `start` step.
Suspend this caller location until that invocation returns.
Callee control locations and step state belong to that invocation.
Internal callee attempts do not increase the caller's attempt count.

A successful callee return gives `running -> completed`, outcome `succeeded`, and control moves to the caller's `on-success`.
A failed callee return gives `running -> completed` and outcome `failed`.
Move control to the caller's `on-failure` when present; otherwise, the failure is unhandled.
A handled failure inside the callee does not itself make the call fail.
The call graph and the combined call/compensation graph remain acyclic.

### End

An `end` has no successor and creates no observable step result.
It terminates control in its workflow invocation.
Successful completion of a called invocation returns to the suspended call.
It does not terminate the caller or its sibling branches.
An `end` cannot replace a required parallel branch arrival at its join.

### Unhandled failure and termination

An unhandled failure in an explicit parallel branch fails that parallel activation.
Otherwise, an unhandled failure terminates the workflow invocation unsuccessfully.
Follow the enclosing parallel or caller failure rule when failure propagates.
Workflow cancellation, timeout, and compensation remain separate from step outcomes.
These rules add no cancellation cascade or timeout inheritance.
See the [result contract](../runtime-contracts/workflow-results.md) and [compensation semantics](compensation.md).

## Parallel interleaving

Let `B` map active branch identities to control locations, and let `S` contain the workflow's observable step state.
Branch identity includes its workflow invocation and enclosing parallel activations.
Different branches can occupy the same step without becoming one branch.
This notation is abstract state, not an additional portable envelope field.

If branch `b` has an enabled local transition, the global transition can select it:

```text
local:   (B[b], S) -> (location', S')
global:  (B, S)    -> (B[b := location'], S')
```

The transition changes no other branch's control location.
State changes follow the selected step's rule and the predicate visibility rules.
A fork replaces the selected location with its branch locations.
A barrier release replaces only its activation's arrived locations with one continuation.
A nested parallel must release its own join before its enclosing branch can arrive at the outer join.
Additional arrivals at a shared parallel wait or reuse its completed result without creating another activation.

Every execution preserves each branch's local transition order.
Cross-branch order, fairness, and physical simultaneous execution are unspecified.
Arrival at the join disables further transitions for that branch until barrier release.
A parallel failure bypass does not count as successful arrival or expose abandoned branch state.
Successful compensable steps retain their actual completion order across branches.

For branches `a1 -> a2 -> j` and `b1 -> j`, both arrival orders below are permitted:

```text
a1, b1, a2, release(j)
b1, a1, a2, release(j)
```

Here, each step name denotes its completed local transition toward the next location.
`a2, a1, b1, release(j)` violates branch order.
`a1, a2, release(j), b1` releases the barrier before every branch arrives.
These examples illustrate the rule; they do not prove all backend schedules.

### Overlapping branch example

For branches `a -> x -> j` and `b -> x -> j`, let `x` be one shared objective step.
This trace has two branch arrivals and one execution of `x`:

```text
A: a -> x
A: enter x; pending -> running; attempts = 1
B: b -> x
B: wait at x while running
complete x: running -> completed; outcome = succeeded; attempts = 1
A: x -> j using the stored outcome
B: x -> j using the stored outcome
release(j)
```

If branch B reaches `x` after completion, it takes the same successor immediately.
Neither arrival resets `x` to `pending` or starts a second execution.
The join still requires both branch identities to arrive.

## Join semantics

- each `join` has exactly one owning `parallel`
- the owning parallel defines the legal branch roots
- only nodes in the owning parallel's branch closure may directly enter the join
- every explicit branch path must converge on the join

## Predicate visibility

- step-state predicates may target only observable step kinds
- a predicate may reference only step state guaranteed to be known on every path before that predicate executes
- after a `join`, the visible set includes:
  - the owning `parallel`
  - branch-local step state guaranteed on every path within each branch before the join

## Implementation mapping

- authored step kinds and fields: `implementations/python/packages/raes/orchestration/_steps.py`
- semantic contract definitions: `implementations/python/packages/raes_contracts/workflow/semantics.py`
- join convergence and guaranteed state: `workflow_join_states()` in the semantic contract definitions
- dependency ordering and cycle checks: `implementations/python/packages/raes_contracts/graphs.py`, using Python `graphlib`
- validation and visibility checks: `implementations/python/packages/raes/validator/`
- compiled step contracts: `implementations/python/packages/raes_processor/compiler/`
- typed runtime envelopes and result validation:
  - `implementations/python/packages/raes_processor/models/`
  - `implementations/python/packages/raes_runtime/manager.py`
