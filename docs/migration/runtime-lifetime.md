# One runtime owner for an interaction

Issue #1629 separates engine lifetime from fixed run contexts.
See the [shared-runtime design](../decisions/issue-1629-shared-runtime-design.md) for ownership and data flows.
Keep one engine open across successive runs on its target.
Each run owns a separate scope-bound store, snapshot, and operation history.
All runs share the engine's execution capacity and backend resource claim.
The original single-run methods still select the fixed default context.

Issue #1660 uses one `RuntimeControlPlane` for each run.
Both public names select the same class.
Keep one instance open for apply, later evaluation, state access, and teardown.
It holds one claim and keeps one snapshot.
Its ledger stores each operation and audit record.
Closing releases resources after drain.
`destroy()` performs explicit backend teardown.
Synchronous `apply()`, `destroy()`, and `refresh_inventory()` require local execution.
They refuse a distributed configuration before dispatch.
Use the same owner's operation API and receipts for distributed work.
The receipt from `evaluate()` can also identify pending distributed work.

## Run identity

Set the same run identity on the runtime and its plans.
The existing control-plane scope remains immutable.
For `PlanScope(run_id="trial-1")`, construct the runtime with `run_scope="run:trial-1"`.
The default remains `run:default` for work without an explicit plan run identity.
Use `open_run(run_scope="run:trial-2", store=trial_store)` for another run in the same engine.
The new store must differ from every other context store.
First, prove that cleanup or allowed reuse is complete, then call `retire_run()` for the prior context.
Retirement retains its records and leaves shared services open.
Changing a plan's run identity does not retarget an existing runtime.

```python
from raes_contracts.planning import PlanScope
from raes_runtime import RuntimeManager

with RuntimeManager(target, run_scope="run:trial-1") as runtime:
    execution = runtime.plan(scenario, run_scope=PlanScope(run_id="trial-1"))
    applied = runtime.apply(execution)
    # Continue only after inspecting the apply outcome.
    if applied.success:
        refreshed = runtime.evaluate(execution, idempotency_key="later-evidence-1")
        outcome = runtime.get_operation(refreshed.operation_id)
        # Inspect the outcome before dependent work or teardown.
```

Fresh evaluation uses the original compiled model and current committed snapshot.
It keeps the original run and generated-value bindings.
It reuses the original compiled input and resolved apparatus defaults.
It keeps the original profile, selected processor, and mixed-control planning context.
It does not apply provisioning or restart orchestration.
Use a new key for each fresh `evaluate()` call.
Use the original key only to retry that same call.
The stored receipt survives teardown and reopening.
A receipt shows that the request was accepted.
Check its final state before starting more work.
Synchronous provider results retain validated disclosures and materialization output.
This output remains available after a known failure when it describes committed effects.

## Experiments and durable driving

`admit_experiment(inputs, services=services)` checks every admitted entry before configuration effects.
Inputs use the existing `TrialRealizationInputs` contract.
The installed `TrialRuntimeServices` applies and reads participant settings, observes execution, captures evidence, and performs authored cleanup.
Its verifier must resolve evidence and probe actual state.
A manifest declaration or a nonempty evidence reference cannot replace these checks.
Each callback returns its own disposition; the engine owns sequencing and attempt allocation.
The engine derives each trial's required operation guarantees from its authored controls and retry policy.
It retains those guarantees with the run and sends them through local and Temporal operation admission.
The provider must accept the exact command before execution.
Reopening a run cannot weaken its retained guarantees.
A successful `ApplyResult` means the module operation completed with a validated state.
The separate capture observation can still report incomplete capture.
An unsuccessful operation result retains uncertainty under existing supervision rules.

Call `advance_experiment(experiment_id)` until it returns a terminal result or needs observation.
`experiment_results()` returns retained per-attempt results.
`cancel_experiment()` records cancellation intent; cleanup still needs cessation evidence.
Durable experiments require an explicit `store_factory(run_id)` with a separate durable store for each run.
Restore the same input artifacts, services, and stores before continuing after a restart.
An authored replacement policy also requires an `ExperimentReplacementBinding` with the original compilation request and an immutable archive owner.

For an ordinary run, `run.advance_plan(plan, execution_id=...)` advances the existing application phases.
Keep the same execution ID and exact inputs when resuming progress.
For Temporal, bind these artifacts with `engine.bind_workflow()` and submit the returned reference through `TemporalExecutionAdapter.submit_runtime()`.
Install the run workflows and a state activity worker with `create_runtime_state_worker()`.
The state worker uses its own `RemoteOperationAuthority` and bounded HTTP connection pool.
Its RPC budget must fit inside the activity budget and allow the configured runtime step to finish.
The default activity budget is 60 seconds; a 45-second state RPC budget covers the default HTTP call allowance.
The existing effect and control workers remain separate.

Temporal repeats progress observation after transport loss or unknown effects.
It reuses the same RAE identity; it does not allocate another authored attempt.
Cancel an experiment through RAE so its authored cancellation and cleanup rules run.
Stopping a Temporal workflow only stops that delivery process.

## Store migration

The local store advances from schema 11 to 12 on scoped admission.
PostgreSQL advances from schema 4 to 5 through explicit `initialize_schema()`.
Both add private append-only runtime decisions and preserve existing operations and snapshots.
Back up durable stores through the existing operational procedure before upgrade.
Older runtimes refuse the new store version.
No portable schema changes.

## Failure and recovery

The [existing execution policy](../../specs/sdl/execution-recovery.md) remains authoritative.
The [supervision rules](../../specs/formal/runtime-control-plane/supervision.md) govern unknown effects and later work.
The runtime keeps the authored policy.
It refuses a choice that its profile cannot enforce.
The current profile can call each operation once.
Its supported policy is `terminate` with validity `preserve`.
It does not substitute this profile for another authored response.

Unconditional manager rollback after a failed start is removed.
Dependent deletion after a failed stop is also removed.
A failed result or exception does not prove that external effects stopped.
If effects are unknown, their final record stays in force.
The owner keeps new work out of that scope.
Use the existing linked resolution path and its proof checks.
Compensation requires its existing separate admission.
Required cleanup failure prevents resource reuse.
An unexpected participant clock-driver failure closes admission.
The committed snapshot records degraded services and pacing evidence.
Reopening retains this state.

## Component selection and state reads

`scenario_component_options(scenario)` supplies existing factory selection options.
The stub factory accepts `scenario=` and constructs only the required services.
Other factories can accept these options through their existing settings.
Their manifest must describe exactly the installed components.
Scenario requirements still pass normal capability admission.
The participant scheduler starts only when the scenario needs it.
HTTP, PostgreSQL, and distributed work remain optional.
Each needs explicit setup.

Status results and history come from the committed snapshot.
Use public processor planning when only a plan is needed.
Planning alone does not require another runtime owner.

The runtime records concern provenance for resources added through admitted backend preparation.
These records use open explicitness and backend origin.
Original author and processor origins remain intact.
Retained resources keep their records across later operations and store reloads.
Accepted updates replace affected records.
Accepted deletion removes the resource's current records.
Preparation refusal or failed native delivery creates no successful records.
Materialization reporting preserves these first-party records without descendant ancestry.
Provenance does not prove independent observation or complete capture.

## Compatibility evidence

The public manager constructor and methods remain available.
Run-bound callers must supply the matching runtime scope.
Callers must not depend on implicit compensation.
They must not retarget an owner to another run.
No published DTO or schema discriminator changes.
Targeted tests check these rules.
They cover the manager, stored state, materialization, participants, and linked recovery.
Stub tests do not prove that a native backend works with this release.
