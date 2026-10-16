# Execute an externally triggered inject

An operator with the right role can trigger one authored inject against chosen
live nodes. Use `RuntimeControlPlane.submit_inject(request, identity=...)` or
P2 `POST /injects/trigger`. The runtime uses its existing operation ledger,
supervision and store. A queued snapshot or accepted receipt proves no world
effect on its own.

## Configure the reference OCI realization

OCI here means the existing Docker/Podman container driver. The host must opt in.
The default reference and stub targets refuse occurrence commands.
Set up these objects from `raes_reference_backend`:

1. Provision the scenario's selected nodes using `OciDeploymentDriver` and the
   ordinary reference target. Retain their live snapshot and target/run scope.
2. Admit an `OciInjectProgram`. Supply the actual scenario and its canonical
   instantiated reference. Pin the exact plan from the planner. Include the
   source manifest and its checksummed descriptor bytes. Add concrete
   `OciInjectProbe` bindings and trusted `OciInjectPermit` order decisions.
3. The descriptor is closed JSON: `profile: reference-oci-entrypoint/v1`,
   `image`, and `image_config_digest`. Associate its artifact ID and manifest
   version with the authored `Inject.source.name` and `.version`. The operator
   approves the local image through `ImageTrustPolicy`. Execution never pulls
   it. Inspect the local image and pin its configuration digest. Images that
   declare volumes are refused.
4. Create `ReferenceOciInjectExecutor(driver, programs=(program,))` and pass it
   as `inject_execution` to `create_reference_backend_target` using that same
   driver. Pass it as both `inject_execution` and `operation_evidence` to the
   control plane, with the retained snapshot/store. Bind its record reader to
   that plane's store. Register the original execution plan through
   `register_planner_produced_plan`.

The executor acts as this target's operation provider. It refuses other commands.
Provision the targets before selecting it. The host checks who supplied the
source, issues permits and keeps scopes apart. Use one ledger and owner for the
driver's workspace. Keep the store, executor setup and record reader private.
`reference_inject_integration_support.py` in the Python tests is a complete
CI composition example, including provisioning and durable reopening.

The program runs the admitted image's authored entrypoint. It shares the chosen
target's network namespace. The request supplies no command, arguments,
environment, mounts or host socket. The process runs as UID/GID 65534.
It drops capabilities and has a read-only root. CPU, memory, process count and
temporary storage have fixed limits. The local CLI has a shrinking deadline and
bounded output. It inherits no credentials. Killing the CLI does not prove that
remote effects stopped.

Each probe pins one explicit target path and approved, non-secret before/after
bytes. The backend checks native ownership and target revision. It reads the
before state, starts the source and checks its exit status. Then it reads the
target again. An applied effect needs the expected after state and proof that
the source stopped. Admit only synchronous programs whose probes prove both
facts. This contract does not cover arbitrary asynchronous programs.

## Trigger and read back

Send a strict `inject-trigger-request-v1` body using the exact plan, inject,
bindings, target/run, placement, fresh occurrence and retry key. The trusted
permit binds that exact request and its predecessor/order position. The first
head is `inject-order:genesis`. Get later heads through
`raes_runtime.inject_claims.inject_order_head`. Arrival order does not issue a
permit or repair a stale head. An exact retry returns the original receipt.
It grants no dispatch or new budget. A fresh repeat needs a fresh occurrence
and key. It also needs a new permit and a valid world precondition.

P2 authenticates before body decoding, counts at most 256 KiB, limits JSON depth
to 16 and rejects duplicate members, nonfinite values and unknown fields. An
optional `Idempotency-Key` header must equal the body's `request_key`. Mutation
requires target-bound operator/backend authority. All responses use
`Cache-Control: no-store`. Unknown and unauthorized operation reads both return
404. P0/P1 SDK hosts supply the trusted caller identity.

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
The store commits evidence manifests and bytes with the outcome. Later target
changes and restart do not change that record. Keep evidence non-secret.
This realization does not accept secret inputs or store secret outputs.

## Failure, recovery and supported scope

Admission refusal creates no accepted occurrence or dispatch. A refusal after
the atomic claim cancels the operation and keeps that claim. An entrypoint that
exits with an error may still change the world. Such an operation fails and
yields no success correlation. Unknown bindings, unproven cessation, readback
failure and crashes cannot become success. Unknown effects keep their invocation
reservation. They never restore consumed dispatch authority.

P0 holds process-lifetime state. P1 and served P2 retain claims, ordering,
evidence and startup state in the existing store. Local records migrate to
schema 9. PostgreSQL records use schema 2 with one owner. Older records gain no
invented occurrence or readback. Reopening never reruns an effect on its own.
Reconciliation can append checked, linked facts. It cannot rewrite an immutable
indeterminate outcome or grant another dispatch. This OCI provider does not
support cancellation. An accepted control request or local timeout does not
prove that native effects stopped.

This initial realization supports independent bindings and assertion-free event
placement with no runtime parameters. It refuses schedules, assertion-bearing
events, `Inject.environment`, source builds/artifact requirements, distributed
delivery and native snapshot results/residual state. It also refuses plans with
observation demands, augmentation or materialization. Those obligations need
their own admitted realization and the existing native finalizers. The portable
contracts cover more cases. The store still checks unique occurrences, schedule
slots and the full order chain for other admitted providers. History holds at
most 1024 claims. It is never truncated to admit more work. P3, multiple owners
and exactly-once backend effects are unavailable.

World execution needs no participant declaration. Correlation grants no
participant disclosure, delivery, observation or controller authority. Existing
consumers must authorize their exact join and final sink on their own.
Legacy plan-start receipts, authoring and participant anchors retain their
original meaning. See the [contract reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/inject-occurrence-contracts.md)
and [control-plane guide](control-plane.md) for the transport/host boundary.

## Evidence

The issue-1367 unit tests use an executing local file fixture or a substituted
daemon. They check runtime and binding behavior, not concrete OCI support.
The existing `test_reference_backend_docker_integration.py` CI family executes
real container entrypoints and reads changed world bytes. It tests the public
P2 trigger, duplicates, refusal and failed entrypoints. It also tests process
loss before commit, reconciliation and no redispatch. Its PR Docker job must
succeed. Missing runtime/image admission makes it fail. The existing release
gate also needs container evidence for the exact release SHA. Full integration
runs remain in CI/CD.
