# Execute an externally triggered inject

An authorized operator can trigger one authored inject against explicit live
node bindings through `RuntimeControlPlane.submit_inject(request, identity=...)`
or P2 `POST /injects/trigger`. The runtime uses its existing orchestration
operation, invocation ledger, supervision and authoritative store. A queued
snapshot or accepted receipt alone proves no world effect.

## Configure the reference OCI realization

OCI here means the existing Docker/Podman container driver. Execution is opt-in;
the default reference and stub targets refuse occurrence commands. The host
installs these backend-owned objects from `raes_reference_backend`:

1. Provision the scenario's selected nodes using `OciDeploymentDriver` and the
   ordinary reference target. Retain their live snapshot and target/run scope.
2. Admit an `OciInjectProgram`: the actual scenario and canonical instantiated
   scenario reference, exact planner-produced orchestration plan, associated
   source manifest and checksummed descriptor bytes, concrete `OciInjectProbe`
   bindings, and trusted `OciInjectPermit` order/admission decisions.
3. The descriptor is closed JSON: `profile: reference-oci-entrypoint/v1`,
   `image`, and `image_config_digest`. Associate its artifact ID and manifest
   version with the authored `Inject.source.name` and `.version`. The operator
   approves the local image through `ImageTrustPolicy`; execution never pulls
   it. The image configuration digest must match independently inspected
   content, and images declaring volumes are refused.
4. Create `ReferenceOciInjectExecutor(driver, programs=(program,))` and pass it
   as `inject_execution` to `create_reference_backend_target` using that same
   driver. Pass it as both `inject_execution` and `operation_evidence` to the
   control plane, with the retained snapshot/store. Bind its record reader to
   that plane's authoritative store and register the original planner-produced
   execution plan through `register_planner_produced_plan`.

The executor is the configured operation provider for this composition; it
refuses non-occurrence commands. Provision the targets before selecting it.
The host owns source authenticity, permit issuance and scope isolation. Keep
one authoritative ledger/owner for the driver's workspace. Do not expose the
store, executor configuration or record-reader callback to trigger callers.
`reference_inject_integration_support.py` in the Python tests is a complete
CI composition example, including provisioning and durable reopening.

The supported program runs the admitted image's authored entrypoint in the
selected target's network namespace. It receives no request command, arguments,
environment, mounts or host socket. It runs as UID/GID 65534 with dropped
capabilities, a read-only root, bounded CPU/memory/processes, no privileges and
a small temporary filesystem. The local CLI has a shrinking deadline, bounded
output and no inherited credentials. Killing the CLI proves no remote cessation.

Each probe pins one explicit target path and approved, non-secret before/after
bytes. The backend checks native ownership and target revision, reads the before
state, starts the source, independently inspects source cessation/exit status,
and reads the target again. Only a verified after state with cessation establishes
application. The host admits synchronous programs for which this probe contract
establishes the required effect and cessation; arbitrary asynchronous programs
are outside this realization's contract.

## Trigger and read back

Send a strict `inject-trigger-request-v1` body using the exact plan, inject,
bindings, target/run, placement, fresh occurrence and retry key. The trusted
permit binds that exact request and its predecessor/order position. The first
head is `inject-order:genesis`; subsequent heads are produced by
`raes_runtime.inject_claims.inject_order_head`. Arrival order does not issue a
permit or repair a stale head. A repeated key with identical actor/context and
content returns the original receipt without dispatch or a new budget. A fresh
repeat requires a fresh occurrence/key and a newly admitted permit and world
precondition.

P2 authenticates before body decoding, counts at most 256 KiB, limits JSON depth
to 16 and rejects duplicate members, nonfinite values and unknown fields. An
optional `Idempotency-Key` header must equal the body's `request_key`. Mutation
requires target-bound operator/backend authority. All responses use
`Cache-Control: no-store`; unknown and unauthorized operation reads both return
404. P0/P1 SDK hosts supply trusted caller identity themselves.

| Read | Meaning |
| --- | --- |
| `GET /operations/{id}` | Existing operation state and diagnostics. |
| `GET /operations/{id}/inject-occurrence` | The committed request, actor admission, source/plan/realization and ordering pins. |
| `GET /operations/{id}/inject-outcome` | Validated per-binding world-effect facts, independently of participant results. |
| `GET /operations/{id}/inject-result` | The retained checksummed associated-artifact manifest. |
| `GET /operations/{id}/inject-artifacts/{artifact_id}` | Retained approved evidence bytes as a binary attachment; the ID is never a filesystem path. |
| `GET /operations/{id}/inject-correlation` | The exact successful occurrence/outcome/result join, only after verified application and successful settlement. |

The corresponding SDK methods are `get_inject_occurrence`, `get_inject_outcome`,
`get_inject_result`, `get_inject_artifact` and `get_inject_correlation` with
optional trusted `identity`. They apply the existing actor/scope read policy.
Evidence manifests and bytes are committed with the outcome, so later target
changes and restart do not change historical readback. Keep them non-secret;
this realization does not implement secret-bearing inputs or output storage.

## Failure, recovery and supported scope

Admission refusal creates no accepted occurrence or dispatch. A refusal after
the atomic claim withdraws acceptance through the existing cancelled state and
retains that claim. A nonzero entrypoint can leave a verified applied world
effect while its operation fails; it yields no success correlation. An unknown
binding, unverified cessation, readback failure or crash cannot become success.
Unknown effects retain the invocation reservation and consumed dispatch authority.

P0 holds process-lifetime state. P1 and served P2 retain claims, ordering,
evidence and startup classification in the existing store. Local records
migrate to schema 9; PostgreSQL records use schema 2 under the existing exclusive
owner admission. Older records gain no fabricated occurrence or readback.
Reopening never automatically reruns an effect. Existing reconciliation can
append independently checked linked facts; it does not rewrite an immutable
indeterminate outcome or supply another dispatch grant. Cancellation is explicitly
unsupported by this OCI provider; the runtime never treats an accepted control
request or local timeout as established native cessation.

This initial realization supports independent bindings and assertion-free event
placement with no runtime parameters. It refuses schedules, assertion-bearing
events, `Inject.environment`, source builds/artifact requirements, distributed
delivery, native snapshot results/residual state, and plans requiring observation
demands, augmentation or materialization. Those obligations require their own
admitted realization and existing native finalizers. The portable contracts
remain broader; the store still enforces occurrence, schedule-slot and complete
order-chain uniqueness even when another executing provider supplies admission.
Retained occurrence history is bounded to 1024 claims and is never truncated to
admit more work. P3, multi-owner coordination and exactly-once backend effects
are unavailable.

Participant declarations are unnecessary for world execution. Correlation grants
no participant disclosure, delivery, observation or controller authority; existing
participant consumers must separately authorize their exact join and final sink.
Legacy plan-start receipts, authoring and participant anchors retain their
original meaning. See the [contract reference](../../explain/reference/inject-occurrence-contracts.md)
and [control-plane guide](control-plane.md) for the transport/host boundary.

## Evidence

The issue-1367 unit tests use an executing local file fixture or a substituted
daemon; they establish runtime and binding behavior, not concrete OCI support.
The existing `test_reference_backend_docker_integration.py` CI family executes
real container entrypoints, reads changed world bytes independently, exercises
the public P2 trigger, duplicates, refusal, failed entrypoint and actual process
loss before commit with reconciliation and no redispatch. Its PR Docker job is
required to succeed and fails if runtime/image admission is unavailable. The
existing release gate separately requires concrete-container evidence for the
exact release SHA. Full integration runs remain in CI/CD.
