# Execute assigned trials

A coordinator can admit an experiment once.
It can send the plan entries to separate workers.
RAE keeps the original scenario, settings, and run IDs.
It also owns attempts, cleanup, and replacement policy.
The application supplies hosts, trusted identities, and transport.

## Compose the owners

Each host needs an explicitly installed `RuntimeTarget` and `TrialRuntimeServices`.
The coordinator needs a `TrialOutcomeVerifier` to ingest remote facts.
That verifier reads original native execution records and resolves evidence through authorized owners.
It checks request commitments and checked state changes.
It checks applied settings, cessation, capture, and cleanup.
A matching digest or remote success assertion does not establish those facts.
Verification returns `None` on success and raises on unavailable, changed, or unverified evidence.
Other return values are refusals.

The coordinator admits the complete original `TrialRealizationInputs` once:

<!-- example-skip: Requires a host-owned coordinator, original inputs, installed services, evidence reader, and trusted identity. -->
```python
experiment_id = coordinator.admit_experiment(
    inputs,
    services=coordinator_services,
    outcome_verifier=native_evidence_reader,
    identity=coordinator_identity,
)
```

`coordinator`, the services, identities, and evidence reader above are trusted application composition.
Actor names and assignment IDs carry no authority.
The application checks each caller through its own trusted identity system.
The application checks access to the whole handoff before it sends data.
This includes private trial history in execution snapshots.
It resolves secret references only through existing authorized backend sinks.

## Assign an original entry

`plan_batch_schedule(inputs.plan)` exposes the original canonical entry order.
`assign_trial()` admits assignments in that order and atomically checks occupied capacity.
Serial execution is the default.
Parallel execution requires an explicit downstream `AllocatorGrant`.
The SDL `trial_parallelism` value sets the admitted floor and ceiling.
The grant's `effective_parallelism` must be inside them.

<!-- example-skip: Requires the retained coordinator admission, selected entry, authenticated owner, and allocator grant. -->
```python
assignment = coordinator.assign_trial(
    experiment_id,
    plan_entry_id,
    owner_id=execution_owner_id,
    grant=allocator_grant,
    identity=coordinator_identity,
)
assignment_json = assignment.model_dump_json()
```

An assignment keeps the full sealed plan.
It also keeps the exact processor and scenario commitments.
They retain the original attempt ID and UTC deadline.
An uncertain assignment keeps its capacity after recovery.
Redelivery returns the same assignment and cannot renew its allowance.
A different owner or grant for an existing attempt is refused.

## Bind and advance on the execution host

The worker reads the assignment with `TrialAssignmentModel.from_json()`.
It reads the original pinned inputs through existing portable carriers.
Only authorized readers can open those sources.
For example, public SDL family admission uses `parse_sdl()` and `admit_scenario_family()`.
The handoff contains no Python objects or credentials.
Targets, stores, and capabilities stay in the host process.

<!-- example-skip: Requires a host runtime, original pinned inputs, delivered assignment, installed services, and authenticated worker identity. -->
```python
from raes_contracts.assigned_trial import TrialAssignmentModel

binding = worker_runtime.bind_assigned_trial(
    TrialAssignmentModel.from_json(assignment_json),
    original_inputs,
    services=worker_services,
    identity=authenticated_worker_identity,
)
progress = binding.advance(identity=authenticated_worker_identity)
```

The binding realizes only the selected original entry.
It checks the whole plan and its sources before effects.
It checks the installed target, settings, capture needs, controls, and cleanup support.
It creates no worker experiment or run identity.
Replacement assignments retain the original root commitment and use the same source inputs.
The worker does not allocate replacements.

`binding.request` is a detached `TrialUnitRequest`.
`binding.execute_trial(request, identity=...)` provides the existing in-process trial-unit handoff.
The protocol form `binding.execute_trial(request)` uses the adapter's originally bound local identity.
It returns a `TrialUnitResult` when execution and cleanup observations exist.
It raises `TrialPending` when more evidence is needed.
The caller must check the original ledger before a retry.
Neither that exception nor a lost reply authorizes another attempt.

Each host uses the existing scoped runtime ledger and budgets.
Native result checks and resource claims remain in force.
Binding two entries to one shared target does not make their resources independent.
After verified cleanup, `worker_runtime.retire_run("run:" + binding.request.run_id)` releases its target reservation.
Later work on that target waits for this retirement.
Durable hosts need a durable engine store and an explicit durable run-store factory.
Recovery uses those original stores and installed owners.
Redelivery reads the retained terminal decision after retirement or retry preparation.
Concurrent deliveries return the same fully attached binding.

## Return original facts

`binding.outcome(identity=...)` exports `TrialOutcomeModel` at any lifecycle cut.
An incomplete outcome can have no execution or cleanup fact.
It needs no fabricated receipt, end time, or successful result.
The carrier keeps original timestamps and evidence.
It also keeps checked snapshots, receipts, and operation states.
It includes operations that are still running or indeterminate.
The caller can read those facts while an advance waits for native work.
A completed outcome requires both execution and cleanup facts.

<!-- example-skip: Requires the live worker binding and original coordinator admission with its installed evidence verifier. -->
```python
from raes_contracts.assigned_trial import TrialOutcomeModel

outcome_json = binding.outcome(identity=authenticated_worker_identity).model_dump_json()
coordinator.ingest_trial_outcome(
    experiment_id,
    TrialOutcomeModel.from_json(outcome_json),
    identity=coordinator_identity,
)
```

Ingestion checks the stored assignment first.
It then calls the installed evidence verifier.
It refuses another run, attempt, owner, configuration, or commitment.
It checks the result and cleanup joins before it stores terminal facts.
New reports can add facts.
They cannot change accepted evidence or settled operations.
Duplicate delivery reconciles the same cut.
If the ledger changed, ingestion can return a conflict.
The caller reads current progress and retries the same delivery.
Evidence checks do not hold the lock for the whole plan.

Accepted facts feed `experiment_results()` and `experiment_records()`.
Run and study records keep their existing content checks and fixed versions.
The scientific eligibility rules still apply.
Started work remains visible even without a result.
Execution, capture, cleanup, and scientific outcomes stay separate.
Incomplete capture keeps failed evidence validation visible in run and study records.
Indeterminate work retains its observed evidence without an invented end time or cleanup receipt.
Completed execution with failed cleanup does not release occupied capacity.

## Deliver controls and advance policy

`cancel_experiment()` records intent and closes new assignment admission.
It cannot deliver a network message to a remote host.
The application reads `assigned_trial_control(experiment_id, assignment.content_digest, identity=...)`.
It sends that carrier through its trusted transport.
The host passes it as `binding.advance(control=control, identity=...)`.
Cancellation is retained locally; a later stale control cannot undo it.
Stop acknowledgement does not establish cessation or permit cleanup to be reported as complete.

`advance_trial(experiment_id, plan_entry_id, identity=...)` advances only that entry's coordinator policy.
It shares the existing terminal, retry, archive, and replacement rules.
It never dispatches another entry's native phases.
Required reset or compensation is requested through `control.prepare_retry`.
The worker performs that preparation through the existing supervised lifecycle and returns its original evidence.
Only the coordinator can then authorize a new attempt.
A pending retry keeps its slot.

A `ready` progress result can identify an authorized attempt or a newly allocated replacement entry.
The coordinator uses `assign_trial()` to assign that work.
The original lineage and dispatch order still apply.
Owner generation is fixed at one.
This interface does not reassign an uncertain attempt to a new owner.
Host placement and its release remain downstream responsibilities.

## Supported versions and bounds

The composition publishes `assigned-trial/v1`, `assigned-trial-control/v1`, and `trial-outcome/v1`.
Their schema IDs are `assigned-trial-v1`, `assigned-trial-control-v1`, and `trial-outcome-v1`.
Child plans, snapshots, receipts, evidence, and cleanup carriers keep their existing versions.
Unsupported versions and unknown fields are refused.
Portable conformance checks the carrier shape and its internal joins.
It makes no claim about live permission or native effects.
JSON ingress refuses duplicate members and non-finite numbers.
It also bounds nesting, total size, and collection size.
The existing trial/runtime value limits apply before copying or hashing.
The maximum JSON input is 16 MiB, with stricter aggregate scalar and collection limits.

The normal feature release publishes the API and these artifacts.
Package versions and release notes remain owned by the release workflow.
