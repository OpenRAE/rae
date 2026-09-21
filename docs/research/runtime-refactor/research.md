**Runtime foundations: initial research record**

Research recorded: 2026-09-21.
Scope and owner clarifications: [initial architectural exploration](README.md).
Tracking: [OpenRAE/rae#1348](https://github.com/OpenRAE/rae/issues/1348).

**Scope and limits**

The initial question was whether established approaches from game engines, simulation, workflow orchestration, robotics, and related systems could supply useful foundations instead of further custom runtime machinery. The subsequent inquiry examined warnings relevant to combining robotics concepts with durable execution.

This is an initial source review, not a systematic literature review or a framework evaluation. It contains no implementation comparison, deployment experiment, performance measurement, licensing assessment, or adoption decision. Sources were consulted on 2026-09-21; documentation links may change. Historical ROS design documents describe particular semantics and design concerns, not a verified account of every current implementation.

The source findings below are separate from RAE requirements. Questions record matters raised during exploration; they do not prescribe an answer. The owner's later clarifications limit the earlier OT discussion: operational-OT safeguards are not universal requirements for current worlds, and concrete contextual execution decisions are largely the backend's responsibility.

**Initial reference map**

The following references identify different mechanisms. They are neither a ranking nor a proposed stack. Compatibility with RAE has not been established.

| Approach | Mechanism described by the source | Primary reference |
| --- | --- | --- |
| Robotics action protocols | Goals, acceptance or rejection, progress feedback, results, and cancellation. | [ROS 2 actions](https://design.ros2.org/articles/actions.html) |
| Behavior trees | Composed control flow with action status and halting; the cited research examines differences in execution semantics. | [Execution Semantics of Behavior Trees in Robotics Applications](https://arxiv.org/pdf/2408.00090) |
| Durable execution | Workflow and step checkpoints, recovery, and step retry; the cited implementations expose different execution mechanisms. | [DBOS architecture](https://docs.dbos.dev/architecture), [Temporal activities](https://docs.temporal.io/activities) |
| Statecharts | State-machine execution with nested states, parallel states, events, and transition semantics. | [W3C SCXML Recommendation](https://www.w3.org/TR/scxml/) |
| Actor supervision | Configurable handling of actor failures, including stopping, restarting, and resuming. | [Akka fault tolerance](https://doc.akka.io/libraries/akka-core/current/typed/fault-tolerance.html) |
| Reconciliation controllers | Observe current state and act to bring it toward declared desired state. | [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/) |
| Discrete-event simulation | Processes and events advanced as quickly as possible, against wall time, or through manual stepping. | [SimPy overview](https://simpy.readthedocs.io/en/latest/) |
| Game-engine update loops | Separate per-frame updates and physics updates scheduled at fixed intervals. | [Godot processing loops](https://docs.godotengine.org/en/stable/tutorials/scripting/idle_and_physics_processing.html) |

Statecharts, actor supervision, reconciliation, simulation, and game-loop references received only an initial documentation inspection. The more detailed notes below concern the robotics/durable-execution question. No conclusion excludes the other approaches.

**Recovery and recorded observations**

DBOS records workflow inputs and step outputs. During recovery it reuses completed step outputs and executes the first step without a completed checkpoint. Its documentation requires deterministic workflow control flow and recommends idempotent steps because interrupted steps can execute again. It also documents compatibility constraints when upgrading workflow code. [DBOS architecture, recovery and upgrades](https://docs.dbos.dev/architecture)

Question raised: if an earlier observation or permission is recorded, what establishes whether later execution may still rely on it after an interruption? The discussion considered changed circumstances and backend refusal; it did not decide where each check occurs or define a recovery protocol.

The owner's clarification is narrower and authoritative for this exploration: durable operation must not impose resumption when the authored use requires the failed trial to end. No candidate has been evaluated against that requirement yet.

**Retries and external effects**

Temporal recommends idempotent activities to avoid duplicate effects when attempts are retried. Its activity documentation describes retry policy and the use of heartbeat details to retain progress between attempts. These mechanisms do not specify the meaning of a RAE operation. [Temporal activities](https://docs.temporal.io/activities)

AWS identifies non-idempotent retries and retries multiplied across application layers as anti-patterns. It recommends bounded retries and using existing retry mechanisms where appropriate. [AWS REL05-BP03: control and limit retry calls](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_mitigate_interaction_failure_limit_retries.html)

Questions raised: what happens when an effect occurred but its acknowledgement was lost; which component decides whether repeating it is appropriate; and how does authored failure handling constrain recovery? The answer cannot be read directly from the presence of a framework retry feature. No retry ownership model has been agreed.

**Compensation**

Microsoft's compensating-transaction pattern distinguishes compensation from restoration of the original state. Compensation can require application-specific logic and must account for concurrent changes. [Compensating Transaction pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction)

Question raised: which RAE operations have a meaningful compensating action, and which do not? The discussion did not establish a common rollback or compensation contract for digital or physical effects.

**Cancellation and execution outcomes**

ROS actions distinguish a cancellation request, acceptance into `CANCELING`, and subsequent completion in `CANCELED`. The server may reject the request. The protocol therefore distinguishes requesting cancellation from completing it. [ROS 2 action goal states and cancellation](https://design.ros2.org/articles/actions.html)

Question raised: what information does RAE require from a backend to interpret interruption and its effects accurately? This connects to the audit's cancellation findings, but adopting ROS states or any other outcome taxonomy has not been agreed.

The later owner clarification establishes a need for contextual backend refusal. It does not establish that refusal and cancellation share a protocol or have the same consequences.

**Clocks and timing**

ROS's time design distinguishes system, steady, and ROS time. ROS time can support simulated time that pauses, changes rate, or moves backwards. The document discusses the implications of discontinuities and communication latency. [ROS clock and time design](https://design.ros2.org/articles/clock_and_time.html)

ROS's real-time background explains deadline-related requirements and sources of nondeterministic delay, including allocation, page faults, and blocking synchronization. It does not establish timing guarantees for RAE or a proposed integration. [ROS real-time background](https://design.ros2.org/articles/realtime_background.html)

Questions raised: which clock governs a particular operation; what pause or reset means; and what changes when simulation interacts with physical equipment. No clock architecture, scheduler, deadline class, or physical-control responsibility has been selected.

**Operational OT**

NIST SP 800-82 Rev. 3 describes application-dependent OT timing requirements, availability constraints, safety considerations, and consequences of communication loss. It notes that ordinary IT practices such as stopping or restarting a system can be inappropriate for an operating process. Relevant discussion appears on printed pages 29 and 79. [NIST SP 800-82 Rev. 3](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf)

This material informed the discussion of eventual physical OT. It does not justify imposing those operating conditions on CTFs or simulations. The owner explicitly limited that interpretation. The review did not determine a safety standard, certification obligation, or allocation of physical safety functions for RAE or any backend.

**Behavior-tree semantics**

Ghiorzi et al., in the April 10, 2025 version of *Execution Semantics of Behavior Trees in Robotics Applications*, identify differences across implementations and versions, including how halting is specified. They propose a precise execution model. Their criticism concerns the lack of a shared reference semantics; it should not be restated as a claim that no formal work on behavior trees exists. [Research paper](https://arxiv.org/pdf/2408.00090)

Question raised: if behavior trees are considered, which exact semantics would be evaluated? Neither behavior trees nor a particular implementation or subset has been selected. Robotics concepts, behavior trees, and ROS middleware are distinct subjects of evaluation.

**Execution history and change over time**

Temporal documents limits on individual workflow histories and outstanding operations. Those limits concern particular execution records; they are not measurements of RAE workloads or a conclusion that Temporal cannot support them. [Temporal workflow execution limits](https://docs.temporal.io/workflow-execution/limits)

Questions raised: what needs to be durable, how much history a world generates, and what happens when execution definitions change. No storage split, event model, migration strategy, or performance requirement has been agreed.

**Recovery of infrastructure and intentional in-world faults**

Kubernetes controllers provide an example of machinery that acts to converge current state toward desired state. [Kubernetes controller pattern](https://kubernetes.io/docs/concepts/architecture/controller/)

A question raised in the discussion was whether automatic recovery could undo a fault deliberately introduced into a world. This is an exploration question, not an observed defect in a candidate framework or an agreed RAE failure taxonomy. The owner established the broader need for author choice; the detailed semantics remain open.

**What the research establishes so far**

The reviewed sources describe reusable mechanisms and specific limits. They do not establish that a combination of robotics and durable execution is suitable for RAE, or that it is categorically unsuitable. No source reviewed here validates the proposed combination against RAE's requirements.

The earlier suggestion to separate durable orchestration, reactive behaviour, and deadline-bound execution was a possible direction raised during discussion. It has not been accepted as the architecture. The same applies to proposed capability profiles, retry ownership rules, detailed refusal states, and physical safety boundaries.

The current record supports continued investigation. The owner has since replaced PRD development with [diagnosis of conceptual problems and their affected dependencies](diagnosis.md). This research has not selected a framework or established its requirements.
