# Participant execution control and temporal bindings

Backend capabilities are optional. Declare what the backend can realize;
the processor checks the selected scenario against that manifest. A serial
backend need not implement concurrency or any native lifecycle control.

For autonomous execution, publish exact action/target/implementation
`execution_bindings` and finite limits. Independent action and target lists
do not establish support for every combination. Declare only implemented
`start`, `pause`, `resume`, `drain`, `reset` and `teardown` controls. Each claimed
control needs native execution, readback and evidence; unclaimed operations
are rejected before invocation. Conformance probes only claimed controls and
requests concurrent work only when concurrency is declared.

Action requests are generation-bound. Reset and shared-clock reset increment
the generation; stale native completions cannot commit. Pause stops new
admission, drain requires zero reserved/in-flight work, and teardown releases
resources. These rules govern claimed operations, not a required backend
feature baseline.

Issue #216 adds opt-in `participant-shared-time/v1` action bindings for bounded
deadline and dwell guarantees. Existing v1/v2/v3 policies keep their meanings.
To admit a bound action, one manifest offer must include all its compiled
`temporal_contract_digests` alongside its action, targets, implementation and
limits. A matching claim permits admission; event or continuous-coverage
evidence establishes the runtime result. No cancellation or rollback is
implied by a missed guarantee.

The reference runtime implements these bindings through autonomous policies,
not manual action ingress. Externally paced and backend-owned wall-clock
policies remain valid SDL but need another transition driver. These reference
limitations neither invalidate a backend nor limit a richer implementation.

See the [formal contract](../../specs/formal/participant-semantics/autonomous-execution.md#bounded-action-guarantees-act-614)
for bounds, evidence, reset and persistence rules.
