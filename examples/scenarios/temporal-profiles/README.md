# Bounded temporal profiles

Inspect a deadline and a continuous dwell requirement.
The files supply no native HTTP runner, monitor, calendar, or backend scheduler.

| File | Purpose | Required support |
| --- | --- | --- |
| [User deadline](user-deadline.sdl.yaml) | Require an ordinary participant's HTTP probe to complete by tick 5. | Matching temporal execution offer and completion-event evidence. |
| [Automation dwell](automation-dwell.sdl.yaml) | Allow a probe at tick 10 only with continuous `portal-present` evidence throughout `[0, 10)`. | Matching execution offer and continuous interval evidence; endpoint observations are insufficient. |

Both use a shared simulated clock and v1 ordered cadence.
They select the opt-in action binding `participant-shared-time/v1`.
The integer parameter `attempts` defaults to 1.
Set it to 2 to add a second attempt at tick 10.
The deadline example must reject that attempt before dispatch.
User and automation select different implementations.
They do not add an actor kind.

## Admission and evidence

The file parser and processor can check declarations without executing HTTP requests.
The execution offer must cover the exact action, targets, implementation, and limits.
It must also cover clock capabilities and compiled temporal digests.
An offer is a claim, not execution evidence.
A serial implementation is sufficient if it supports the requested combination.
Native lifecycle controls are not mandatory.
Unrelated workloads do not require these capabilities.

Deadline evidence must identify the selected completion event on the bound clock.
Dwell evidence must cover the named condition and boundary continuously.
Evidence is bound to the action, episode, segment, and execution generation.
A reset needs fresh evidence.
A guarantee can be missed or indeterminate.
Neither result proves that native effects were cancelled or undone.

See the [temporal example reference](../../../docs/explain/reference/example-library.md#temporal-profile-support) for parameter limits, capability ownership, and the conformance probe.
The [temporal-profile tests](../../../implementations/python/tests/test_act_614_temporal_profiles.py) check compilation and parameter binding.
The [time model](../../../specs/formal/time-model/README.md) defines the shared time concepts.
A passing fixture proves neither native application fidelity nor a continuous monitoring service.
