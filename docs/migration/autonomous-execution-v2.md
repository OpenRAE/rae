<a id="autonomous-execution-v2-migration"></a>

# Adopt autonomous execution v2

## Versions and purpose

Source: `participant-autonomous-execution/v1`.
Target: `participant-autonomous-execution/v2`.

## Before you start

Keep a validated v1 source, its exact manifest, and the installed participant runtime.
Obtain the author decision to change activity timing and selection.
Editing SDL changes intent only; installing and executing it needs the backend owner's authority.

1. Preserve the v1 file under its original version.
2. Replace cadence and order fields with the explicit v2 policy below.
3. Supply apparatus randomness outside SDL through the existing authorized owner.
4. Validate the new file and compare every required feature with the selected manifest.
5. Admit the new policy only after installing matching windows, limits, and runtime support.

Select `participant-autonomous-execution/v2` explicitly to govern ordinary participant activity.
It supports work windows, bounded timing variation, and weighted candidates.
It also supports dependencies, retries, cooldowns, and bursts.
It does not change the meaning of existing
`participant-autonomous-execution/v1` documents.

## Existing v1 scenarios

No migration is required. Keep the v1 cadence constraint, `action_order`,
`ordered_cycle`, and existing finite attempt/in-flight limits. Omitting
`profile` continues to select v1. A v1 backend declaration must list the exact `participant-autonomous-execution/v1` policy profile.
It must also list occurrence, retry, and burst limits for common admission accounting.

## Opting into v2

Replace v1 cadence/order fields with the explicit v2 shape:

```yaml
autonomous_execution:
  profile: participant-autonomous-execution/v2
  participant_implementation_ref: participant-implementation-manifests.green-worker.v1
  clock_ref: scenario-clock
  progression_policy_ref: scenario-progression
  work_window_refs: [work-window]
  pause_window_refs: [break-window]
  observation_boundary_ref: participant-view
  stochastic_control_ref: green-activity-policy
  selection_strategy: weighted
  timing:
    minimum_ticks: 10
    maximum_ticks: 30
  outside_window_disposition: next_opening
  empty_eligible_disposition: complete
  action_candidates:
    portal-login:
      action_ref: probe-customer-portal-login
      weight: 3
      depends_on: []
      retryable_failure_classes: [target_unavailable, timeout]
      max_retries: 2
      cooldown_ticks: 20
  max_occurrences: 8
  max_action_attempts: 24
  max_burst_size: 2
  max_in_flight: 1
  failure_policy: continue
  evaluation_authority:
    mode: none
```

Work and pause refs must resolve to finite shared-time `window` constraints on the policy clock.
Their subjects must name the behavior specification or every governed participant. Windows are half-open `[start, end)`. On stepped
clocks, timing bounds must be multiples of `step_ticks`.

The SDL contains only `stochastic_control_ref`.
Run apparatus must supply an exact `agent-policy` control bound to `blake3-xof-participant-v1`.
It must supply a namespace and a public seed or resolvable governed entropy. Seeds do not belong in SDL.
The reference runtime currently fails closed for governed entropy because no
authorized resolver is installed.

Backends must explicitly declare the v2 profile and all activity features.
They must declare weighted selection, the participant random-stream profile, and window support.
They must also declare finite occurrence, retry, and burst limits. Existing v1 capability claims do not
implicitly admit v2.

Runtime snapshots gain typed v2 continuation fields, and participant behavior
history gains safe activity occurrence provenance. Consumers should preserve
unknown optional fields when forwarding current contract payloads. No new API
endpoint or private scheduler state surface is introduced.

## Check the result and recover

Success is a validated v2 policy with independently admitted apparatus support.
Existing v1 sources need no conversion.
Missing support or an unresolved entropy source refuses admission; do not insert a seed into SDL.
On refusal, retain v1 and correct the named requirement before new admission.
File conversion creates no resources. Native execution and cleanup remain the backend owner's responsibility.
Read [autonomous execution semantics](../../specs/formal/participant-semantics/autonomous-execution.md)
and [participant-control explanation](../public/participant-control-explanation.md).
