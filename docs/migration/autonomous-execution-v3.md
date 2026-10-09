# Autonomous Execution V3 Migration

`participant-autonomous-execution/v3` adds scoped participant resource budgets
to the v2 activity profile. Existing v1 and v2 documents keep their meaning
and require no edits. Their `max_action_attempts` and `max_in_flight` values
compile into canonical legacy demand records, but they do not opt into shared
pool capacity, fairness, isolation, or measured resource accounting.

## Opting In

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
`concurrent_actions` limit must equal `max_in_flight`. Parent budgets may
aggregate the same kind, unit, accounting mode, and meter across participant,
tenant, shared-service, and fleet owners, but the graph must remain acyclic and
a child cannot exceed its parent.

A participant-owned budget counts one participant's use. Validation therefore
rejects a v3 policy whose behavior specification governs more than one
participant, because the required participant-owned `concurrent_actions`
budget would count every governed participant's actions. The governed
participants include every agent that `participant_role_refs` selects, not
only the agents named in `participant_refs`. Use one behavior specification per
participant, and keep shared counters under tenant, shared-service, or fleet
owners. A budget of another owner cannot name a participant-owned budget as its
parent.

## Interaction Budgets

A v3 vector may add interaction dimensions next to the six required kinds:
`interaction_steps` (`steps`), `interaction_turns` (`turns`),
`tool_invocations` (`invocations`), and `scenario_time` (`ticks`). Token budgets
keep using `inference_tokens`. Each interaction dimension is an ordinary
dimension with an owner, pool, meter, limit, reservation, and reset, and it
needs a matching configured pool on the backend. The backend measures every
interaction dimension except `scenario_time`, which RAES meters from the
shared clock.

```yaml
      tool-calls:
        owner_ref: participant
        pool_ref: participant-pool
        resource_kind: tool_invocations
        unit: invocations
        accounting_mode: cumulative_counter
        meter_profile_ref: raes.tool-invocation/v1
        limit: 5
        reservation: 1
        reset: episode
        tool_affordance_refs: [portal-probe]
      scenario-time:
        owner_ref: participant
        pool_ref: participant-pool
        resource_kind: scenario_time
        unit: ticks
        accounting_mode: cumulative_counter
        meter_profile_ref: raes.shared-time-ticks/v1
        limit: 600
        reservation: 1
        reset: time_segment
```

A `tool_invocations` dimension names the behavior specification's tool
affordances in `tool_affordance_refs` and reserves only for attempts of the
dispatched action contracts they bind. A turn or step dimension's
`reservation` is the most one action may take.

A `scenario_time` dimension bounds the ticks the policy clock advances after
its last reset (`time_segment`) or after it started (`run`). It uses the
shared-time tick meter, so host or watchdog time is rejected. Each admitted
attempt is charged the ticks elapsed since the last charge, including ticks
with no attempt. Its `reservation` is the time an attempt needs left: in the
example above, attempts stop once 600 ticks have elapsed.

A quota stays hidden unless the policy's observation boundary declares the
dimension ref in `hidden_refs` and discloses it with a `resource_budget` view
rule:

```yaml
observation_boundaries:
  participant-view:
    hidden_refs:
      - behavior_specifications.participant-behavior.autonomous_execution.resource_budget.dimensions.tool-calls
    view_rules:
      - information_ref: behavior_specifications.participant-behavior.autonomous_execution.resource_budget.dimensions.tool-calls
        boundary_class: resource_budget
        disposition: disclosed
        visibility_basis: The participant is told its tool-budget usage when the budget refuses an attempt.
        disclosure_rule: task-brief.tool-budget
```

A disclosed quota is reported only in the observations of an attempt that the
dimension rejects.

## Backend Changes

A backend admitting v3 extends
`capabilities.participant_runtime.resource_budgets`. It declares support
strength and supported terms separately from `configured_pools`. Every demand
must match one configuration-bound pool entry by owner, pool, resource kind,
unit, accounting mode, and meter. The pool capacity must cover the authored
limit. Cross-range pools require `tenant_partitioned` isolation.

The backend also declares
`participant-resource-budget-state-v1` and
`participant-resource-budget-event-v1` as realization contracts. Those
runtime carriers report reservations, measured use, throttling, and reset
reconciliation; they are not mutable utilization fields in the manifest.

## Runtime and Consumer Changes

Runtime snapshots add `participant_resource_budget_states`,
`participant_resource_pool_states`, and
`participant_resource_budget_events`. Budget states are keyed by canonical
policy-scoped state reference; pool states are keyed by exact physical-pool
identity and contain the cross-policy allocation ledger. Consumers that
deserialize the current closed snapshot schema must regenerate against the
updated `runtime-snapshot-v1` schema. Execution-service state now includes
`resource_budget_state_refs`; for v3 its concurrency projection is validated
against the referenced authoritative budget.

Reservation is atomic across the full vector and occurs before native work.
The native result must return one measurement per measurement requirement
(every reserved dimension except `scenario_time`, which RAES meters from the
shared clock) with matching operation, generation, resource, unit, meter, and
evidence; absent or contradictory measurements release or roll back the
reservation rather than
committing its estimate. Commit and release are fenced to the reservation's
generation, idempotent by action identity, and mutually exclusive: a
reservation settles once. A shared-time reset advances every state generation,
clears `time_segment` dimensions and, when it reset the bound episodes,
`episode` dimensions, and preserves persistent storage and other independently
owned counters.

When the logical budget cannot admit a reservation, the runtime records a
`reject` event (counted in the state's `rejected` field) and a rejected
participant attempt with the `resource_exhausted` failure class, and the
policy's failure disposition applies. The runtime previously recorded this case
as a `throttle` event and failed the scheduler pass. `throttle` now means only that
a shared physical pool could not admit a quantity the logical budget allows.
