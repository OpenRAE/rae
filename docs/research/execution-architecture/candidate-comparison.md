# Candidate comparison

Status: supporting comparison for the selection in
[ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md).
Sources checked 2026-09-23; exact tested
versions are recorded in [evidence](evidence.json). Integration assessments below
are engineering inferences from those sources, the probes, and RAE's existing
contracts. They are not throughput measurements or a complete package audit.

## Criteria

RAE must discharge its duties: authored retry, continuation, trial, time, refusal
and cleanup rules; one operation-state authority; bounded supervision; and
validated external-effect evidence. Backend cooperation is expected. Backends
retain realization, observations and contextual limits under the
[responsibility boundary](../../decisions/adrs/adr-113-reusable-execution-machinery.md#2-keep-the-ecosystem-and-runtime-boundaries).

Every candidate has limits. Evaluate the complete composition: useful mechanism,
remaining runtime duty, backend obligation, required handling and residual limit.
A limitation alone is not a rejection; an unfulfilled required duty is. Keep
untested handling distinct from demonstrated handling. Maintenance and deployment
work must be recorded, but cannot override the separation of duties. The bounded
probes do not justify a numerical ranking or prove any composition complete.

P0 remains an in-process library profile. An optional external worker does not
by itself introduce multiple state owners, but a mandatory remote orchestration
service would change that deployment contract. P1/P2 preserve their existing
declared authority boundaries. Neither distributed workers nor framework HA
establish RAE's unavailable P3 profile.

The earlier evaluation uses a design case of 15 federated tenants, hundreds of
nodes and tens of agents per scenario, without measured capacity evidence.
Local profiles are compatibility obligations, not the
platform's ceiling. The distributed design must extend the currently missing
coordination and tenant guarantees explicitly. Prefer established components
for distributed execution; custom code should implement RAE-specific semantics
and integration, not replace a mature queue, scheduler or recovery engine.

## Mechanisms and responsibilities

| Candidate | State and worker ownership; supervision/scheduling | Persistence and failure isolation | Reuse and retained RAE duties |
| --- | --- | --- | --- |
| Python asyncio/AnyIO | RAE retains its owner; task groups, capacity limiters and worker APIs manage execution. Control capacity must be separated from occupied effect capacity. | No new durable history. Existing RAE stores retain operation authority. Threads share the host process; process workers isolate local execution but not already dispatched remote effects. | Reuse concurrency and process primitives. RAE still implements dispatch/reservation lifecycle, scoped cancellation, bounded observation, truthful outcome mapping and startup reconciliation. Small dependency surface does not make that work trivial. |
| DBOS | An embedded engine owns workflow/step bookkeeping and queues. RAE would bind those records to its admitted operation rather than equate their states. | SQLite or Postgres system DB; interrupted steps can run again on recovery. Application process loss was tested, not machine power loss or a distributed deployment. | Reuse checkpoints, queueing and workflow management. RAE must guard each effect against unauthorized replay, classify uncertainty and reconcile engine history with its operation store. Reusing SQLite does not make their transactions automatically atomic together. |
| Temporal | Service history and task queues coordinate application workers. Workflow and activity state remain engine execution state, distinct from RAE's operation outcome. | Service persistence is separate from worker memory. Worker loss was tested with a live, in-memory development server; service/storage loss and production HA were not tested. | Reuse durable dispatch, workflow history, retry controls and heartbeat cancellation. RAE still owns effect admission, outcome evidence, quarantine and cross-store reconciliation. Disable or guard retries where repetition is unauthorized. |
| Celery/task queue (source comparison only) | Task routing and workers provide mature dispatch. Acknowledgement, retry and revocation settings require deliberate configuration. | A broker/result store adds operations; task status is not a durable RAE semantic history or effect witness. No Celery experiment was run. | Reuse at an existing backend task boundary; building the complete orchestration/recovery layer around it leaves more general machinery for RAE to implement than the selected composition. |
| ROS 2 actions | Backend action server owns goal handling; executor/callback configuration governs responsiveness. Client receives goal/cancel acknowledgements, progress and results. | The tested action protocol is not RAE's durable operation store. Node/middleware loss needs separately defined recovery and effect observation. | Reuse an action protocol and clients/servers at suitable backend boundaries. RAE must correlate goal/control identities, validate backend claims and map results. An action status cannot replace domain evidence. |
| Ray actors | Ray schedules actor processes; actor methods can serialize work. Same-actor control can queue behind a blocked method. Alternate concurrency/control arrangements need separate tests. | Configurable restart and task retries; application state recovery is the application's responsibility. Actor death is distinct from cessation of downstream effects. | Reuse placement, process actors and worker recovery. RAE retains durable authority, retry permission and reservations. Value increases if distributed computation is a real workload requirement, which these probes did not establish. |
| SimPy | Cooperative, deterministic event processing can provide a semantic-time scheduler under RAE's declared time authority. | In-memory event queue is not durable operation history. A blocking callback blocks event stepping. | Reuse event ordering and process interrupts. RAE retains multi-domain time interpretation, external execution, independent apparatus supervision and any restart representation. |
| BehaviorTree.CPP | Tick-driven reactive composition with lifecycle/halting hooks. Action implementations supply nonblocking execution and actual interruption behavior. | Tree state and an action's worker/effects are distinct. Persistence and RAE settlement are not supplied by the tested halt operation. | Reuse behavior composition where semantics match. Translating SDL workflows would need semantic validation, not just an API adapter. Backend-local use has a narrower integration boundary. |

## Deployment obligations

| Candidate | Added deployment responsibility if selected | Initial license observation |
| --- | --- | --- |
| AnyIO | Python library; local child processes where selected; packaging/IPC and host supervision. Existing HTTP offload already uses AnyIO indirectly. | MIT |
| DBOS | Python library plus system database. SQLite is supported; vendor recommends Postgres for production. Distributed recovery adds coordination choices. | MIT |
| Temporal | Python workers plus the selected self-hosted service and its persistence. Version compatibility and workflow upgrades become operational concerns. | Python SDK and server: MIT |
| ROS 2 | ROS distribution, client libraries, generated action types and selected middleware; discovery/executor configuration and upgrades. | rclpy: Apache-2.0; not an audit of the ROS distribution |
| Ray | Ray runtime processes, worker resource configuration and potentially a cluster; application checkpoint/upgrade policy. | Apache-2.0 |
| SimPy | Python library; RAE integration with semantic time and execution boundaries. | MIT |
| BehaviorTree.CPP | C++ library/build toolchain or backend process boundary; behavior-node integration. | MIT |

License identifiers were checked against upstream repository metadata, not
assumed from the category. Transitive licenses, vulnerability posture, supported
platforms across RAE's Python range, production operations and total ownership
cost remain adoption checks. No candidate's documentation benchmark is treated
as a RAE performance measurement. No production dependency was added.

## Selection rationale and alternatives

Select Temporal Server/Python SDK/PostgreSQL for the connected distributed
composition, with the authority and failure rules in ADR-113. Its service/worker
separation, durable execution history, queues and operational tooling match that
composition directly. Preserve existing AnyIO/SQLite local compositions; do not
build a distributed scheduler from those primitives. Local library suitability
and distributed execution suitability are different selection questions.

DBOS is a credible alternative, including distributed queues; neither the probes
nor this assessment establish a throughput ranking or show it incapable. Its
embedded orchestration model offers a smaller service footprint. Temporal's
separate execution service and worker lifecycle are the selected operational
trade-off. Celery is established task machinery, but would leave more durable
orchestration/history/recovery integration to RAE. Reopening the decision needs
a concrete unsupported requirement or measured operational problem.

ROS actions, Ray actors, SimPy and BehaviorTree.CPP address complementary needs.
Adopt them at a backend seam only when its effect, compute, time or control
contract needs them; their presence cannot create a second scenario interpreter.
No package is selected because all digital twins are assumed to be robots, all
AI research requires Ray, or all failures should trigger workflow recovery.

[Contextual policy](authored-retry-policy.md) is common admission machinery with
different author-selected responses: experiment invalidation/fresh trials,
twin time/state reconciliation, OT safe-process response, and IT restoration or
retry where appropriate. Defaults resolve by scenario and lexical scope;
idempotency does not imply author permission. The candidate's own retry defaults
must implement that resolved policy or be disabled for the effect concerned.

Deployment cost is a trade-off, not grounds to move RAE responsibilities into a
backend. The selected components require no paid software or hosted service.
Transitive dependencies and platform support remain package-admission checks;
no claim that every ecosystem package or optional commercial feature is free
follows from the directly checked licenses.

## Primary sources

- AnyIO: [threads](https://anyio.readthedocs.io/en/stable/threads.html),
  [processes](https://anyio.readthedocs.io/en/stable/subprocesses.html),
  [repository](https://github.com/agronholm/anyio).
- DBOS: [architecture/recovery](https://docs.dbos.dev/architecture),
  [Python databases](https://docs.dbos.dev/python/tutorials/database-connection),
  [cancellation](https://docs.dbos.dev/python/tutorials/workflow-management),
  [repository](https://github.com/dbos-inc/dbos-transact-py).
- Temporal: [activities](https://docs.temporal.io/activities),
  [service](https://docs.temporal.io/temporal-service),
  [Python cancellation](https://docs.temporal.io/develop/python/workflows/cancellation),
  [SDK](https://github.com/temporalio/sdk-python),
  [server](https://github.com/temporalio/temporal).
- ROS: [action protocol](https://design.ros2.org/articles/actions.html),
  [callback groups](https://docs.ros.org/en/ros2_documentation/kilted/How-To-Guides/Using-callback-groups.html),
  [rclpy](https://github.com/ros2/rclpy). The action design document is historical;
  executable observations use the recorded Jazzy packages, not an assumed latest distribution.
- Ray: [actors](https://docs.ray.io/en/latest/ray-core/actors.html),
  [fault tolerance](https://docs.ray.io/en/latest/ray-core/fault_tolerance/actors.html),
  [cancellation](https://docs.ray.io/en/latest/ray-core/api/doc/ray.cancel.html),
  [repository](https://github.com/ray-project/ray).
- SimPy: [scheduling](https://simpy.readthedocs.io/en/stable/topical_guides/time_and_scheduling.html),
  [repository](https://github.com/simpx/simpy).
- BehaviorTree.CPP: [asynchronous actions](https://www.behaviortree.dev/docs/tutorial-basics/tutorial_04_sequence/),
  [repository](https://github.com/BehaviorTree/BehaviorTree.CPP).
- Celery (source-only): [task execution and acknowledgements](https://docs.celeryq.dev/en/stable/userguide/tasks.html),
  [worker revocation](https://docs.celeryq.dev/en/stable/userguide/workers.html).
- PostgreSQL: [license](https://www.postgresql.org/about/licence/).
