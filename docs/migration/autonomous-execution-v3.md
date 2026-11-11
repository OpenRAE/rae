<a id="autonomous-execution-v3-migration"></a>

# Adopt scoped participant resource budgets

## Versions and purpose

Source: `participant-autonomous-execution/v2`.
Target: `participant-autonomous-execution/v3`.

## Before you start

Keep a validated v2 policy and the exact configured pool declarations.
Obtain authority from the participant, tenant, shared-service, and fleet resource owners you name.
Do not infer shared capacity from a manifest's general support claim.

1. Preserve the v2 source and its original apparatus records.
2. Select v3 and supply the complete six-kind resource vector described below.
3. Match each dimension to one configuration-bound pool and its governed unit and meter.
4. Validate parent limits, acyclicity, and the concurrency limit before admission.
5. Install the budget state and measurement owners before native execution.

`participant-autonomous-execution/v3` adds scoped resource budgets to v2 participant activity. Existing v1 and v2 documents keep their meaning.
They need no edits. Their `max_action_attempts` and `max_in_flight` values
compile into canonical legacy demand records, but they do not opt into shared
pool capacity, fairness, isolation, or measured resource accounting.

## Opting in

Start with a valid v2 policy, change its profile to v3, and add one complete
`resource_budget`:

```yaml
autonomous_execution:
  profile: participant-autonomous-execution/v3
  # All v2 fields remain required.
  max_in_flight: 2
  resource_budget:
    policy_id: green-shared-capacity
    owners:
      participant:
        kind: participant
        ref: participant-agent
      range:
        kind: deployment_tenant
        ref: range-a
      inference:
        kind: shared_service
        ref: nodes.inference.services.http
      fleet:
        kind: fleet
        ref: fleet.primary
    fairness:
      policy: weighted_fair
      priority_class: background
      weight: 1
      protected: false
      borrowing: lendable_only
      reclaim: yield
      max_queue_ticks: 20
      starvation_bound_ticks: 100
    dimensions:
      participant-actions:
        owner_ref: participant
        pool_ref: participant-pool
        resource_kind: action_rate
        unit: actions
        accounting_mode: windowed_counter
        meter_profile_ref: raes.action-attempt/v1
        limit: 24
        reservation: 1
        reset: time_segment
        window_ticks: 100
      concurrency:
        owner_ref: participant
        pool_ref: participant-pool
        resource_kind: concurrent_actions
        unit: actions
        accounting_mode: reservable_gauge
        meter_profile_ref: raes.concurrent-action/v1
        limit: 2
        reservation: 1
        reset: reconciled
      # Also declare storage_growth, inference_tokens, image_generations,
      # and accelerator entries with their governed units and meters.
```

The vector must contain all six initial resource kinds. The participant-owned
`concurrent_actions` limit must equal `max_in_flight`. Parent budgets may combine matching demands across participant, tenant, shared-service, and fleet owners.
Kind, unit, accounting mode, and meter must match.
The graph must remain acyclic. A child cannot exceed its parent.

## Backend changes

A backend admitting v3 extends
`capabilities.participant_runtime.resource_budgets`. It declares support
strength and supported terms separately from `configured_pools`. Every demand must match one configuration-bound pool entry.
The match covers owner, pool, resource kind, unit, accounting mode, and meter. The pool capacity must cover the authored
limit. Cross-range pools require `tenant_partitioned` isolation.

The backend also declares
`participant-resource-budget-state-v1` and
`participant-resource-budget-event-v1` as realization contracts. Those
runtime carriers report reservations, measured use, throttling, and reset
reconciliation; they are not mutable utilization fields in the manifest.

## Runtime and consumer changes

Runtime snapshots add `participant_resource_budget_states`,
`participant_resource_pool_states`, and
`participant_resource_budget_events`. Budget states use canonical policy-scoped state references as keys.
Pool states use exact physical-pool identities as keys.
They contain the cross-policy allocation ledger. Consumers that
deserialize the current closed snapshot schema must regenerate against the
updated `runtime-snapshot-v1` schema. Execution-service state includes `resource_budget_state_refs`.
For v3, its concurrency projection is checked against that authoritative budget.

Reservation is atomic across the full vector and occurs before native work.
The native result must return one measurement per reservation.
Its operation, generation, resource, unit, meter, and evidence must match.
Absent or contradictory measurements release or roll back the reservation.
They cannot commit its estimate. Commit is generation-fenced and idempotent by action
identity. A shared-time
reset advances every state generation, clears only `time_segment` dimensions,
and preserves persistent storage and other independently owned counters.

## Check the result and recover

Success is an admitted v3 demand vector with configuration-bound capacity and measurement support.
A missing kind, inconsistent concurrency limit, unsupported pool, or missing measurement cannot become successful accounting.
Correct the declaration or installation before re-admission.
Keep existing reservations and generations when reconciling native work.
The source edit needs no native cleanup; execution requires the resource owner's verified cleanup procedure.
Read [autonomous execution semantics](../../specs/formal/participant-semantics/autonomous-execution.md)
and [runtime supervision](../public/guides/supervised-execution.md).
