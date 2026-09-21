**Language and runtime diagnosis — working record**

Recorded: 2026-09-21. Tracking: [issue 1348](https://github.com/OpenRAE/rae/issues/1348).
Inspected revision: `ae2f3311` on `1348-runtime-architecture-exploration`.

**Purpose and method**

The owner has replaced PRD development with diagnosis of the conceptual problems and their affected dependencies. The working premise is that these problems can be corrected while retaining the language. The task is to establish the problems precisely, using intended lineage, external language-design sources, sound existing SDL semantics, and RAE's responsibilities. Language, processor, and runtime implementation changes remain deferred.

[OpenRAE/hub#3](https://github.com/OpenRAE/hub/issues/3) assigns semantics, contracts, and conformance to RAE; local realization to LilRAE; and organizational control-plane responsibilities to BigRAE. The owner's clarification remains authoritative: the shared RAE runtime drives these backends through execution. This does not make RAE responsible for inventing participant declarations or taking over concrete backend accountability.

This record separates owner statements, source findings, and diagnostic judgments. It begins with the environment/interaction/inject question discussed below. The broader milestone-67 diagnosis remains unfinished. When a conceptual point needs owner feedback, ask and end the turn; do not continue investigating other topics while awaiting the answer.

**Owner clarifications: environments, interaction, and injects**

- SDL expresses and implements the author's intent. It must not impose arbitrary authoring obligations, including obligations based on assumptions about an application's purpose. This is an existing language principle, not a newly proposed feature.
- An author may describe an environment, its authentication/access arrangements, and entry points such as MCP services without describing participants. There may be no participants, or people and agents may use the environment later without the author specifying who or what they are.
- The runtime need not know those users as scenario participants unless authored semantics require relevant information, for example to share information when participants arrive. The discussion has not selected an arrival, registration, or recipient-binding protocol.
- The owner identifies APTL/TechVault as an example: its environment and MCP services need not imply agent declarations. This is the owner's use-case statement; the source checks below concern the local RAE examples, not a deployed APTL system or MCP service.
- A researcher reaching into the world can supply an inject like another external source. The owner accepted investigating researcher approval through an externally triggered world effect rather than assuming it belongs to mixed-control.

**Diagnosis 1: an environment does not require authored participants**

The general language and compiler already preserve this separation. `ScenarioContent.agents` and `behavior_specifications` default to empty maps. Participant compilation iterates over declared agents; it does not synthesize participants from nodes, services, accounts, or injects. General orchestration compiles injects, events, scripts, and stories separately. [Scenario declarations](../../../implementations/python/packages/raes/scenario.py), [participant compilation](../../../implementations/python/packages/raes_processor/compiler/participant_behaviors.py), [orchestration compilation](../../../implementations/python/packages/raes_processor/compiler/orchestration.py).

The runtime target also permits an absent participant-runtime component. Participant execution capability checks depend on selected behavior specifications. General provisioning and orchestration have separate resource and execution paths. These source observations establish separation at the inspected boundaries; they do not demonstrate a particular backend deployment. [Target components](../../../implementations/python/packages/raes_runtime/registry.py), [planner checks](../../../implementations/python/packages/raes_processor/planner/core.py), [resource collection](../../../implementations/python/packages/raes_processor/planner/resources.py), [runtime phase execution](../../../implementations/python/packages/raes_runtime/manager.py).

Four read-only parser/instantiation/compiler checks completed with no diagnostics:

| Input | Declared agents | Compiled participants | Other compiled objects |
| --- | ---: | ---: | --- |
| One compute node exposing a service endpoint | 0 | 0 | One node |
| Same environment with a general inject and event | 0 | 0 | One node, inject, and event |
| Same with a script and story scheduling the event | 0 | 0 | The above plus one script and story |
| Existing `techvault-defensive-min.sdl.yaml` | 0 | 0 | Six compute nodes and the example's environment declarations |

The diagnostic service was named `mcp-entry` and declared TCP port 8000. This tests service declaration without participants; it does not establish MCP protocol implementation. The inject source was an inert artifact reference. No backend was invoked. Inputs and invocation are retained in the [focused reproduction note](environment-inject-check.md).

Conclusion: the inspected general path supplies counterevidence to a blanket diagnosis that RAE requires participants to create or govern an environment. Existing participant-specific operations requiring participant identity do not establish such a blanket requirement.

**Diagnosis 2: general injects and participant-directed delivery already differ**

The normative [SDL section specification](../../../specs/sdl/sections.md#narrative-chain) explicitly preserves an inject without a participant-delivery binding as ordinary orchestration input. The general `Inject` model permits both entity endpoints to be absent; if supplied, they must be paired. Entity references are not participant-controller references. [Inject model](../../../implementations/python/packages/raes/orchestration/_events.py), [reference validation](../../../implementations/python/packages/raes/validator/_sections.py).

`ParticipantInjectDelivery` is a narrower relation: it requires a declared participant in the owning behavior specification, an observation boundary, and a particular event/script/story occurrence. Its `external-direction` and `intervention` alternatives additionally require a compatible mixed-control transition and controller agreement. Ordinary disclosure does not carry those control fields. [Delivery model](../../../implementations/python/packages/raes/participant_inject_delivery.py), [delivery validation](../../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py).

These restrictions are facts about an explicitly participant-directed relation. They are not evidence that every external world effect requires mixed-control. Whether they are unnecessarily strong for some participant-directed interventions remains a separate diagnostic question. Changing a condition that affects a participant does not, merely by that consequence, establish a change in who controls the participant.

The audit's F02 reasoning therefore needs correction: inability to name an out-of-world researcher as an ACT-617 controller does not itself prove that the controller type is inadequate. The original recommendation to expand controller references was premature. First establish whether the intended interaction is ordinary orchestration, participant-visible delivery, or an actual controller/authority transition.

**Diagnosis 3: declaring an inject does not establish a live triggering path**

The general `Event` model carries inject references and precondition assertions. `Script` carries an authored schedule. An event can compile without a script, as the checks show. None of those facts establishes how a researcher supplies a fresh external occurrence during execution.

The inspected public orchestration protocol exposes `start`, `status`, `results`, `history`, and `stop`. `RuntimeControlPlane.submit_orchestration` submits a plan to `start`; it is not a separately defined per-inject input operation. The inspected reference orchestrator records inject bindings and queued event/script/story state, without executing an external-input handler or the referenced inject artifact. [Protocol](../../../implementations/python/packages/raes_backend_protocols/protocols.py), [submission](../../../implementations/python/packages/raes_runtime/control_plane.py), [reference orchestrator](../../../implementations/python/packages/raes_reference_backend/orchestrator.py).

This identifies an unestablished execution connection, not a demonstrated ban on external triggers in every backend. A backend could implement behavior behind its orchestration source or another interface. The shared runtime's portable trigger, occurrence, and outcome contract must be located and assessed before such behavior can be claimed as supported. A plan-start receipt, queued event, or returned participant status view does not establish that a requested world effect occurred. This connects the present investigation to audit F12.

For the researcher's approval example, the distinctions to preserve are: the supplied input, the authored condition or effect it changes, any participant-visible information, and any actual transfer of control authority. Their meanings must follow the scenario. This record does not introduce a new signal API, approval primitive, or controller type.

**External comparison and intended lineage**

The [lineage map](../../explain/sdl/lineage.md) and [design precedents](../../explain/sdl/precedents.md) identify OCR orchestration ancestry, workflow/state-machine influences, and separation of authored intent from execution and evidence. Source influence does not imply compatibility or mandatory adoption.

| Source inspected | Relevant established behavior | Application to this diagnosis |
| --- | --- | --- |
| [W3C SCXML, external events and communications](https://www.w3.org/TR/scxml/#SCXMLEvents) | External events carry data and origin information and are processed according to declared transition semantics. | An external source can affect modeled behavior without being represented as an internal state or controller. This is an analogy to RAE's boundary, not a shared participant ontology. |
| [Temporal, approval signal and wait condition](https://docs.temporal.io/develop/typescript/workflows/message-passing#wait-for-a-signal-or-update-to-arrive) | The documented `approve` handler changes state; the workflow waits for the resulting approval condition. | An external approval can affect continuation without implying transfer of controller identity. |
| [AWS Step Functions, callback tasks](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html#connect-wait-token) | A task can wait for an external callback, including human approval. | The external input is associated with particular waiting work. This does not prescribe a RAE token or approval protocol. |
| [Mernik, Heering, and Sloane, section 2.4](https://inkytonik.github.io/assets/papers/compsurv05.pdf) | DSL design can specialize or extend existing languages; integrating extensions with the remaining language is a design concern. | Evaluate the affected participant-control extension against existing general orchestration and authoring semantics before inventing a separate controller solution. |

These primary sources were inspected during the dialogue on 2026-09-21. The RAE applications in the last column are review judgments.

**Affected scope and unresolved points**

The current evidence directs investigation toward the connection between general orchestration and live external inputs, its overlap with participant-directed delivery and mixed-control, and the resulting occurrence/evidence contracts. It does not justify changing general node/service declarations, requiring agents for environment authoring, or weakening participant-specific identity checks indiscriminately.

Two points remain unestablished: how the shared runtime represents and drives a fresh externally triggered general inject, and how authored information-sharing intent applies to later arrivals without unnecessary participant declarations. The owner has not been asked to choose protocols for either. Continue diagnosis within this topic before implementation design.
