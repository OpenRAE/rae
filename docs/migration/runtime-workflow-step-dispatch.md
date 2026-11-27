# Migrate a backend to runtime workflow step dispatch

The runtime now selects every workflow step from the admitted compiled graph.
The backend executes only the current dispatch.
This changes the backend orchestration protocol.
SDL syntax and authored transition rules stay the same.


## Declare and install support

Declare both `workflow-step-dispatch-v1` and `workflow-step-response-v1` in
`manifest.supported_contract_versions`.
Install `Orchestrator.dispatch_step(request)` on the injected target.
The registry checks the installed method when the manifest declares these contracts.
Planning refuses workflows when the contracts are absent.


Keep `Orchestrator.start(plan, snapshot)` for non-workflow resources.
It receives events, scripts, stories, and other admitted orchestration resources.
It must not interpret an SDL workflow graph.
The runtime does not fall back to autonomous backend graph execution.


## Execute and report one step

Accept a `WorkflowStepDispatch` from `raes_contracts.contracts.workflow_dispatch`.
It names the root operation and workflow invocation.
It binds the branch, step, and attempt.
It also binds the program digest and prior revision.

It carries the current realization references and selected execution policy.
It contains no successor graph.

For `objective` and `retry`, return the portable outcome `succeeded` or `failed`.
For `decision`, `switch`, `parallel`, `join`, `call`, and `end`, acknowledge the
command with no executable outcome.
The runtime evaluates predicates.
It creates branches and calls, then joins their arrivals.

It selects retry attempts and completes each invocation.

Return a `WorkflowStepResponse` or its plain-data mapping.
Echo the dispatch identity, digest, and admitted observation digest map.
A response cannot supply a successor or workflow result envelope.
Governed executable modes also require the existing attempt provenance.

Successful governed attempts must resolve accepted objective assertion truth
and evidence; a participant report alone cannot establish success.
The stub fails governed attempts because it supplies no native evidence.

For an operation provider, the existing `BackendOperationRequestModel` carries
this command in `workflow_step` and identifies `workflow-step-dispatch-v1`.
The result artifact identifies `workflow-step-response-v1`.
The existing evidence resolver must return that typed response.
It must check the content digest and native effect evidence.

Provider and Temporal delivery retain their existing one-use invocation claims.
Transport retries do not acquire authored workflow retry authority.

## Progress and recovery

Use the existing runtime run driver to advance asynchronous operations.
An embedded caller can call `advance_orchestration(operation_id)` on the same
runtime owner with the original actor and authorization scope.
This method adds no HTTP route.
Synchronous backends can complete a workflow during submission.


The runtime commits dispatch authority before effects.
It commits the response before it selects the next step.
An uncertain effect blocks progress under its original operation claim.
Restart does not redispatch that effect.

The existing reconciliation path must establish absence and cessation before
compensation can proceed.

Checkpoint recovery requires its recorded predecessor revision.
A changed predecessor cancels the unused checkpoint before another backend call.
Recovery uses committed state and current cancellation or timeout facts.
Resubmit the original admitted plan if interruption left resource installation
unsubmitted; `advance_orchestration` cannot reconstruct non-workflow bodies.

Existing idempotency keys retain their original meaning.

Workflow timeouts and apparatus budgets remain separate.
The selected policy stays intact in the dispatch.
A separate remaining allowance prevents workflow-level apparatus budgets from
restarting at each step or after recovery.
The runtime checks cancellation and expiry again before native admission.

Compensation dispatches its actual target workflows in reverse accepted
completion order and waits for their outcomes.

## Inspect execution evidence

The workflow-address result is the latest invocation's current view.
Durable continuations retain each invocation separately, including overlapping calls.
History retains all invocations and correlates them with `invocation_id`.
Each runtime `step_started` and backend `step_reported` event includes
`dispatch_id`, `attempt`, and `origin`.

Control steps appear in this history without becoming observable step results.
Legacy history without correlation remains readable.

The new schemas are draft publication entries.
Existing backend-operation requests omit `workflow_step` when it is absent,
which preserves their previous digest input.
An older consumer that rejects unknown fields cannot consume the new dispatch.
Interoperation requires both declared contracts and an installed implementation.

Repository fixtures test payload shape.
Runtime tests check the behavior in this tree.
Each external backend release needs its own adoption evidence.
It also needs conformance evidence.


See the [runtime architecture](../explain/sdl/runtime-architecture.md) and
[workflow result contract](../../specs/formal/runtime-contracts/workflow-results.md).

A proven step-operation failure can have no step-response artifact.
History then records its operation identity and terminal state.
The workflow stops.
Its original ledger keeps the diagnostics.
It also keeps cessation evidence.

Uncertain resource setup appears as indeterminate run progress.
A known setup failure stops the workflow before any step runs.

Legacy result envelopes grant no new dispatch permission.
Cancellation can mark their compensation pending.
The runtime needs an admitted continuation.
It must execute the compensation work before it can report completion.
