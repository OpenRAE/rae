# Bounded temporal profiles

These portable scenarios declare intent. They contain no native HTTP runner,
monitor, calendar or backend-specific scheduler.

- `user-deadline.sdl.yaml`: one ordinary participant completes an HTTP probe
  by tick 5. A second cadence attempt at tick 10 is rejected before dispatch.
- `automation-dwell.sdl.yaml`: automation may probe at tick 10 only with
  continuous evidence that `portal-present` held throughout `[0, 10)`.
  Sleeping or observing the two endpoints does not satisfy this contract.

Both use a shared simulated clock, v1 ordered cadence and the opt-in action
binding `participant-shared-time/v1`. `attempts` is an integer parameter with
default 1; setting it to 2 exposes the deadline example's late-attempt case.
User versus automation is a selected implementation, not another actor kind.

| Authoring concern | Existing authority |
| --- | --- |
| Role and participant scope | `entities`, `agents`, behavior specification |
| Activity, application and protocol | Action contract, target service and selected implementation |
| Fixed cadence and ordering | Autonomous v1 |
| Work/pause windows, weighted actions, intervals, dependencies, retries, cooldowns | Autonomous v2 |
| Explicit resource budgets and fairness | Autonomous v3, preserving v2 activity semantics |
| Deadline event or continuous dwell | Action temporal contract plus shared clock/constraint |
| Reusable profiles | Namespaced module imports and typed parameters |

Supported whole-field integer parameters (`${name}`) include attempt and
occurrence limits (1–1,000,000), in-flight bounds (1–1,024), timing ticks,
weights and burst size (1–1,000,000,000), retry counts (0–1,024) and cooldown
ticks (0–1,000,000,000). Cross-field limits and stepped-clock reachability are
checked after binding. Booleans, fractional numbers and interpolated strings
are not integers. Module parameters bind separately in each import's
`parameters` mapping; omitted required values fail import expansion.

## Admission and evidence

The backend manifest must cover the exact action, targets, implementation,
limits, clock capabilities and compiled temporal digests in one execution
offer. That offer is a claim, not execution evidence. A serial implementation
with no native lifecycle controls is sufficient if it supports the requested
combination; unrelated workloads do not require these temporal capabilities.

Deadline success requires evidence for the selected completion event on the
bound clock. Dwell requires the named condition and boundary with continuous
interval coverage. Evidence is bound to the action, episode, segment and
execution generation. Reset requires fresh evidence. A missed or
indeterminate guarantee does not mean native effects were cancelled or undone.

On a disposable reference target, call
`raes_conformance.conformance.participant_temporal_probes.participant_temporal_scenario_case`
with a parsed scenario. For dwell, pass
`clock_advances=(("time.clock.scenario-clock", 10),)`.
The probe checks admission, execution, assessments and durable-history
consistency. It stops its local clock driver before returning and fails the
case if shutdown is unconfirmed. The caller owns native setup/cleanup; do not
clean up native resources while the report identifies residual work.
Generic registration probes
cannot reconstruct a scenario from manifest digests. Fixture success proves
neither native application fidelity nor a continuous monitoring service.
