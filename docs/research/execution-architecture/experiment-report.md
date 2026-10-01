# Experiment report — 2026-09-23

Status: bounded mechanism evidence supporting
[ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md). The raw
[evidence](evidence.json) contains counters, event ordering, observed PIDs,
framework results, versions, and SHA-256 digests of all thirteen executed source
files. Those digests were checked against the retained source after retrieval.
This is one final complete run, preceded by setup/debug runs; it is not a
statistical performance study.

## Interpretation for the design

Backend cooperation is a prerequisite, including truthful refusal when a
request exceeds capability or contextual limits. Deliberately non-interrupting
fixtures test the meaning of cancellation signals; they do not establish a
disadvantage of needing backend participation. Runtime responsibility for
requirements, supervision and settlement remains unchanged.

The observations identify limits to manage in a composition. For example, DBOS
successfully returning an indeterminate domain result can be correct: RAE must
retain the uncertainty and decide the permitted next action. Likewise, duplicate
effects under configured recovery identify where repeat permission must be
enforced. These results do not by themselves reject either engine.

The missing evidence is a complete cooperating runtime/backend interaction.
The [selected design](../../decisions/adrs/adr-113-reusable-execution-machinery.md)
names the next vertical slice and
its checks. Further investigation should resolve a specific design uncertainty;
no candidate is expected to remove every limitation.

The declared federated workload changes the architectural recommendation, not
these measurements. No probe tested 15 tenants or the stated scenario scale.
Temporal's selected use rests on the fit of its distributed execution mechanisms;
capacity, isolation and the RAE integration still need their own evidence.

## Environment and measurement

AWS profile `catalyst-dev`, region `us-east-2`, one `t3.xlarge` with standard CPU
credits, Ubuntu 24.04 image `ami-00adec9774170bad2`, Python 3.12.3, and one encrypted
40-GiB gp3 root disk. A dedicated `172.31.240.0/24` subnet was created in the
default VPC. Systems Manager provided access; the security group had no inbound
rules and only outbound TCP 80/443. Existing default routes were reused without
modification. No NAT gateway, EIP, load balancer, bucket or production backend
was created. The host had IMDSv2 required and a temporary SSM-only instance role.

Python versions: AnyIO 4.15.1, DBOS 3.0.0, Temporal SDK 1.33.0, Ray 2.58.0,
SimPy 4.1.2. Temporal's SDK started CLI 1.9.1 / server 1.32.0 with **in-memory
persistence**. ROS used Jazzy rclpy 7.1.12 and action tutorial interfaces 0.33.11;
BehaviorTree.CPP was 4.10.0, built with GNU C++ 13.3.0. The ROS base image was
`ros@sha256:c3706ef0a0aa45413c07803cf433602f543b22e45b4855f6fca955c2d8ecc4e8`.
Full Python/ROS package versions are retained in the evidence. Container-local
image builds added the documented packages; the base digest alone does not pin
every apt dependency. A complete supply-chain lock was not produced.

Most probes send synthetic HTTP requests to a loopback service in a separate
process. That witness counts receipt separately from effect application and
continues after caller loss. It is outside the candidate worker but on the same
host: this tests a process/acknowledgement boundary, not network partitions or
independent machine failure. Its state is not crash-durable. The BehaviorTree
probe instead uses an independently running thread and atomic counter; it does
not claim the stronger separate-process witness boundary.

Each candidate command had a host-side timeout, plus an SSM execution timeout.
Cloud lifecycle ownership had a two-hour deadline and teardown in `finally`;
the host also had a 150-minute shutdown/termination timer. Deadline expiry is a
cost/cleanup backstop, not a result or proof of backend cessation. The cleanup
record is retained separately in [cloud-cleanup.json](cloud-cleanup.json).

## Observations and their limits

| Probe | Observed result | What follows, and what does not |
| --- | --- | --- |
| AnyIO thread abandonment | Cancellation returned with zero effects observed; later the witness counted one effect. Caller process remained alive. | Waiting can be abandoned; the thread/remote work must not be classified as stopped from that return. |
| AnyIO cancellable process | Cancellation returned; the recorded caller PID no longer existed; the witness later counted one effect. | Local process termination was established in this run and still did not fence the dispatched external request. |
| AnyIO occupied capacity | A status callback sharing the sole occupied limiter expired at the chosen 100-ms bound. An independent limiter returned status before the effect. | Separate capacity is a useful mechanism. This does not test RAE HTTP admission, store locks, audit queues, CPU starvation or end-to-end bounded supervision. |
| DBOS unguarded recovery | Worker exited with code 73 after one effect but before step checkpoint. Restart recovered the workflow and produced a second effect; engine status was `SUCCESS`. | Recovery works; a non-idempotent unfinished step can repeat. It does not authorize that repetition under RAE rules. |
| DBOS experimental guard | Same crash boundary, but a retained invocation marker prevented the second external call. Returned value was `indeterminate-no-second-invocation`; DBOS status was still `SUCCESS`. | An application guard can prevent replay in this scenario. Engine success and RAE operation success cannot be equated. The marker is test scaffolding, not a complete admission/reconciliation protocol, durable power-loss proof, or multi-owner fence. |
| DBOS cancellation | Status became `CANCELLED` before the in-flight synchronous step's effect. The effect subsequently occurred; the following step did not execute. | Cancellation prevented further steps, not the already running effect. Preemptible async steps were not tested. |
| Temporal worker crash, two attempts allowed | First worker died after one effect. Replacement worker processed the retried activity; total effects became two and the workflow completed. | Durable dispatch survived worker loss with the service alive. This is configured retry, not an unavoidable behavior and not service crash-recovery evidence. |
| Temporal worker crash, one attempt allowed | Effect count remained one; workflow retrieval raised `WorkflowFailureError`. | Retry configuration prevented repetition. Failure status alone still did not describe the externally applied effect. |
| Temporal uncooperative cancellation | With `WAIT_CANCELLATION_COMPLETED`, no heartbeats, and a pending effect, the request did not stop work. The effect occurred and the workflow ended `COMPLETED`. | Cancellation request and final completion are distinct. This configuration is not evidence about all SDK activity types or cancellation policies. |
| Temporal cooperative cancellation | The driver waited for an actual heartbeat before requesting cancellation. Workflow ended `CANCELED`, with no synthetic effect invoked. | Heartbeat/cooperative interruption is useful when the activity participates. This zero-effect activity does not prove interruption after a remote effect was dispatched. |
| Ray configured actor restart/retry | `max_restarts=1`, `max_task_retries=1`: crash after effect led to actor replacement and two effects. | Reuse of actor recovery is real, but RAE must control repeat invocation. Ray actor defaults were not being tested. |
| Ray blocked regular actor | A ping on the same actor did not complete within the selected 100-ms observation. Killing that actor did not prevent the witness's later effect. | Same-mailbox control can queue behind work; actor death is not a downstream fence. Threaded/async actors and concurrency groups were not tested. |
| ROS accepted cancel | The action client observed one cancelling goal while effects were still zero. The deliberately non-interrupting server later applied the effect and reported terminal status 5 (`CANCELED`). | Protocol acknowledgement and server-declared terminal status are not independent effect evidence. Known residual effects are possible. This is not a defect claim against ROS. |
| ROS refused cancel | The callback rejected cancellation, the cancelling-goal list was empty, and the operation later reported status 4 (`SUCCEEDED`) with one effect. | Contextual refusal can be carried. In this run the response's numeric return code was zero in both cases: inspect the complete response, not that field alone. |
| SimPy time/interrupt | Virtual time remained zero while approximately 100 ms of apparatus time passed. An interrupt was processed at virtual time zero. A blocking callback held `step()` until explicitly released. | Cooperative virtual-time control can be reused; apparatus supervision needs independent progress. No multi-clock integration or restart model was tested. |
| BehaviorTree.CPP halt | Tree initially returned `RUNNING`; `haltTree()` invoked the action's halt hook once. The deliberately non-stopping hook returned before a background effect incremented the counter. | The hook supplies lifecycle control, not automatic interruption of arbitrary work. An application-specific stopping hook remains possible. |
| SQLite publication race | Competing success/cancel updates used one conditional transition and atomic audit transaction. One won; one terminal state and its matching audit persisted. A simulated lost acknowledgement after a separate commit was resolved by reopening and reading the committed row. | Demonstrates a small storage mechanism. It is not RAE's production store, an unbounded race proof, an injected disk failure or an external-effect fence. |

The two race contenders were both admissible in the storage fixture. It does
not implement the preceding domain question of whether cancellation has enough
evidence to be admissible. Raw monotonic timestamps are host-relative event
coordinates, not portable restart timestamps. Reported durations are observations
on a burstable host, never latency guarantees or comparative benchmarks.

## Verification and setup corrections

Three witness unit tests establish distinct request/effect counts, independently
counted duplicate invocations, and an effect occurring after caller timeout. The
tests first failed because the witness implementation did not exist, then passed
locally and on the experiment host. Candidate scripts assert their specific
measurement expectations and fail if those observations differ. The final run
completed all seven candidates plus the publication probe, including a real
BehaviorTree.CPP compile and actual ROS action client/server exchanges.

The initial DBOS probe incorrectly passed a `timeout` keyword to a polling
handle; its public call was corrected and the outer process watchdog retained.
The ROS-packaged BehaviorTree.CPP exports `behaviortree_cpp::behaviortree_cpp`,
not the initially assumed CMake target. That fixture was corrected. Neither
setup failure was treated as an architectural finding. The final run used a
fresh directory and fresh synthetic state. Worker code, witness instrumentation,
and final source hashes correspond to the retained evidence.

## Outstanding evidence before any stronger claim

No production RAE adapter was implemented. No real backend was interrupted.
Multi-host partitions, machine/store loss, credential handling through framework
checkpoints, tenant isolation, code/schema upgrade recovery, production service
operations, broad workload coverage and full HTTP/store/audit saturation remain
untested. No deployment-cost or throughput ranking follows from these probes.
They are sufficient to expose the selected semantic distinctions and inform the
architecture selection, not to certify its production realization.

## Independent local recheck during delivery

On 2026-09-23 the same source bytes were executed locally with Python 3.14.4,
AnyIO 4.15.1, SimPy 4.1.2, DBOS 3.0.0 and Temporal SDK 1.33.0. A fresh disposable
directory and virtual environment were used; each command had a 160-second
outer timeout. All three witness tests and the AnyIO, SimPy, DBOS, Temporal and
SQLite publication assertions passed. [local-recheck.json](local-recheck.json)
records commands, versions, source hashes and actual observations independently
of the earlier cloud run. Temporal again used CLI 1.9.1/server 1.32.0 with
in-memory persistence. Its worker fixture uses UnsandboxedWorkflowRunner for
this synthetic probe, not an isolation demonstration. No paid service or cloud
resource was used for the recheck.

ROS, Ray and BehaviorTree.CPP were not rerun locally; their observations are the
original retained evidence. Neither run measured PostgreSQL crash persistence,
distributed ownership, tenant isolation or a real OT process. The probes expose
mechanism limits under named configurations; they do not choose a failure
response for an experiment, twin, IT or OT deployment. That response belongs to
the admitted contextual author policy, independently of technical retry safety.

The delivery review identified an assertion gap in the Temporal collector:
`outcome()` records exceptions rather than failing, and zero effects alone can
also result from the cooperative fixture finishing normally. The added
`verify_temporal.py` entry point preserves the original source and validates
terminal status, result/error type and effect count on fresh output. Negative
controls first demonstrated that effect-only checks accepted four injected
timeouts and a cooperative completion without cancellation; all four regression
tests pass with the stronger verifier. A fresh live Temporal run also passed.
The `verified_temporal_followup` record in `local-recheck.json` binds that run to
its source hashes separately from both earlier evidence records.

The publish hook classified the synthetic `dbos-r2-cancel` workflow identifier
as a generic API key. The repository scanner exception matches only that exact
value in `experiments/probe_dbos.py` under that one rule, preserving the original
source hash. A regression invokes the real scanner and verifies that a different
credential-shaped value and a different rule still trigger in the same file,
and that the fixture identifier still triggers outside that file. The test
failed before the exception and passes after it; no actual credential is used.
