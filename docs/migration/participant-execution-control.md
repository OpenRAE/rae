<a id="participant-execution-control-and-temporal-bindings"></a>

# Declare participant execution controls

## Versions and purpose

Source: `Backend manifest without the selected execution controls`.
Target: `Exact execution_bindings and optional participant-shared-time/v1 offers`.

## Before you start

Use RAES 11.0.2 and the selected backend distribution's manifest and installed provider.
You need permission to change that distribution's advertised support.
A manifest edit does not install native lifecycle methods.

1. Enumerate the exact action, target, and participant-implementation combinations the provider implements.
2. Publish finite limits and only the native controls that have execution and readback evidence.
3. Add every required temporal-contract digest to the same matching offer when selecting shared-time bindings.
4. Validate the manifest and check admission before invoking native work.

Backend capabilities are optional. Declare what the backend can realize.
The processor checks the selected scenario against that manifest. A serial backend need not implement concurrency.
It need not implement native lifecycle controls.

For autonomous execution, publish exact `execution_bindings` and finite limits.
Bind each action, target, and implementation combination. Independent action and target lists
do not establish support for every combination. Declare only implemented
`start`, `pause`, `resume`, `drain`, `reset` and `teardown` controls. Each claimed control needs native execution, readback, and evidence.
Unclaimed operations are rejected before invocation. Conformance probes only claimed controls.
It requests concurrent work only when concurrency is declared.

Action requests are generation-bound. Reset and shared-clock reset increment the generation.
Stale native completions cannot commit. Pause stops new admission.
Drain requires zero reserved/in-flight work.
Teardown releases resources. These rules govern claimed operations, not a required backend
feature baseline.

Issue #216 adds opt-in `participant-shared-time/v1` action bindings for bounded
deadline and dwell guarantees. Existing v1/v2/v3 policies keep their meanings.
One manifest offer must include all compiled `temporal_contract_digests` to admit a bound action.
That offer must also bind the action, targets, implementation, and limits. A matching claim permits admission.
Event or continuous-coverage evidence establishes the runtime result. No cancellation or rollback is
implied by a missed guarantee.

The reference runtime implements these bindings through autonomous policies,
not manual action ingress. Externally paced and backend-owned wall-clock policies remain valid SDL.
They need another transition driver. These limits do not invalidate a backend.
They do not limit a richer implementation.

See the [formal contract](../../specs/formal/participant-semantics/autonomous-execution.md#bounded-action-guarantees-act-614)
for bounds, evidence, reset and persistence rules.

## Check the result and recover

Success is an exact offer that the selected scenario can use at admission.
Missing combinations, controls, or temporal digests remain unsupported.
Keep unknown outcomes and generation fences through recovery; a stale completion cannot commit.
Live control checks require an authorized disposable target and verified cleanup.
Read the [backend task guide](../public/backends.md) and the formal contract below.
