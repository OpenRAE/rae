# One runtime owner for an interaction

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
Use a new owner for a new trial.
First, prove that cleanup or allowed reuse is complete.
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

## Compatibility evidence

The public manager constructor and methods remain available.
Run-bound callers must supply the matching runtime scope.
Callers must not depend on implicit compensation.
They must not retarget an owner to another run.
No published DTO or schema discriminator changes.
Targeted tests check these rules.
They cover the manager, stored state, materialization, participants, and linked recovery.
Stub tests do not prove that a native backend works with this release.
