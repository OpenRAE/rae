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
schema 10. PostgreSQL records use schema 3 with one owner. Older records gain no
invented occurrence or readback. Reopening never reruns an effect on its own.
Reconciliation can append checked, linked facts. It cannot rewrite an immutable
indeterminate outcome or grant another dispatch. This OCI provider does not
support cancellation. An accepted control request or local timeout does not
prove that native effects stopped.

This initial realization supports independent bindings and assertion-free event
placement with no runtime parameters. It refuses assertion-bearing
events, `Inject.environment`, source builds/artifact requirements, distributed
delivery and native snapshot results/residual state. It also refuses plans with
uninstalled observation demand, augmentation or materialization. Those obligations need
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

## Compose an explicit participant delivery

World execution and participant delivery use separate operations. Install
`ParticipantInjectRuntimeBinding(model=compiled_model, resolver=owner)` as the
control plane's `inject_delivery` option, alongside its crossing-policy owner
and `behavior_specifications=compiled_model.behavior_specifications`.
The model must retain the original instantiated compiler context. The projection
owner implements `resolve_delivery(delivery, application, correlation, snapshot)`
and returns `ParticipantInjectResolution`: a governed content carrier, crossing
evidence and the trusted logical-order cut. The carrier pins the declared result
item, observation boundary and disclosure basis. It supports bounded UTF-8 or
base64 content with an explicit media type. The owner approves the entire carrier,
including correlation references; world read authorization alone grants no
participant disclosure.

After `submit_inject` has settled, submit a
`ParticipantInjectApplicationModel` through
`deliver_participant_inject(application, identity=...)` or
`POST /injects/deliver`. Pin the world operation, compiled delivery address and
original authored-binding digest, participant, episode and expected snapshot
revision. Disclosure carries no control reference and needs no controller
binding. The caller needs both world read authority and an authenticated audience
binding for the authored audience. The return value names the delivery operation
and its governed carrier. `GET /operations/{id}/inject-delivery` and
`get_inject_delivery` read that retained carrier under current authorization.

External direction and intervention additionally pin the exact accepted API-409
v2 event ID, occurrence revision and digest. Install the matching
`MixedControlRuntimeBinding`; its owner implements `resolve_delivery_cut(policy,
application, snapshot)` using the same admitted logical order as the projection
owner. The runtime checks the original episode policy, exact edge/kind/controller,
state and target history, live grants, evidence and validity. Audience authority
and source-controller authority remain separate. Delivery and control policy
revisions can differ. To plan this opt-in composition, pass
`mixed_control_admission=plane.mixed_control_planning_admission()` to `plan`.
Plan registration independently checks the installed compiler context. Planning
without this explicit context retains its refusal of unsupported reusable paths.

The existing crossing, IFC and modular-control gates apply at delivery, including
after transformation. API-424 owner contexts supply `inject_applications` and
`inject_coordinates` alongside the original `inject_deliveries` binding; these
are trusted owner resolutions, never provider-supplied indexes. A generated inject
effect requires distinct authored source/result items and the exact compiled
coordinates. Its owner operation supplies `inject_application`. Required
predecessors continue to withhold their parent through the existing API-424
rules. A successful world operation does not satisfy that delivery obligation.

Each control-event/binding pair authorizes at most one logical delivery across
actors, world operations and retry keys. The existing stores claim that pair
before returning content. An exact authorized retry reads its original operation;
it cannot execute the world again. An unsettled claim remains withheld after
restart. Delivery failure preserves accepted control and the settled world
outcome. The recorded delivery boundary is the governed local return of the
carrier. It proves no external transport acknowledgement, consumption or
participant observation; no observed occurrence is synthesized for this path.

## Scheduled execution and capture

The reference OCI executor now admits fixed scheduled placements when the exact
compiled event/script/story chain resolves, there are no unevaluated assertions,
and one shared clock gives an unambiguous event cut. The supported mapping uses
a `scenario_start` epoch, unit script/story speed, the initial clock segment and the authored event time
inside its script window. It revalidates before dispatch. Missing clocks,
ambiguous mappings, reset segments, changed membership and expired cuts refuse.
Existing schedule-slot claims still prevent replay. This support adds no scheduler
or automatic world repetition.

When a plan has authored observation demands, install a target observation runtime
with the required capture offers, selector capabilities, protection and retention
policies. The runtime admits required capture before dispatch and executes capture
through the existing observation lifecycle after world readback. It preserves
authored mandatory and optional selectors. World effects and capture are separate
facts: required capture failure retains the actual world outcome and withholds
dependent delivery; optional unavailability or failure does not veto execution
or delivery. `get_inject_capture` or
`GET /operations/{world_id}/inject-capture` reads the retained capture result.
Capture, emission and participant observation have distinct evidence. This does
not relax the generic atomicity guard for native mutating plans.

The delivery reader in this version requires the original authored schedule
anchors. An independent world occurrence remains valid without participants, but
its participant join is explicitly refused. A future schedule-free authored join
needs its own discriminated contract and reader admission; no anchors are
fabricated. Legacy flat-control bindings retain their original interpretation
and are not silently converted to reusable occurrences. Local stores migrate to
schema 10 and PostgreSQL ledgers to schema 3; older readers refuse the new records.
