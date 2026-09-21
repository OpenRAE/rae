**Runtime Refactor: initial architectural exploration**

Recorded: 2026-09-21.
Tracking: [milestone 71 — Runtime Refactor](https://github.com/OpenRAE/rae/milestone/71),
[issue 1348 — architectural exploration](https://github.com/OpenRAE/rae/issues/1348).
Branch: `1348-runtime-architecture-exploration`.

**Status and purpose of this record**

This work diagnoses conceptual problems and their affected dependencies. The owner replaced PRD development with a precise diagnostic review, on the working premise that conceptual problems can be corrected while retaining the language. The [completed diagnosis](diagnosis.md) assesses F01–F16, adds the applicability finding F17, and records the necessary repair scope and remaining design decisions. This exploration record supplies context and links to the research. No refactor architecture, backend protocol, or implementation plan has been selected.

The distinctions in this record are deliberate:

- Owner clarifications below record positions explicitly stated or accepted in the discussion.
- [Research notes](research.md) report source findings and identify questions. They do not turn external design patterns into RAE requirements.
- The [milestone-67 audit](../participant-control-audit/audit-2026-09-21.md) contains source findings and architectural judgments. Its repair recommendations and effort estimates have not been adopted as a plan.

No runtime foundation has been selected. Robotics and durable execution remain subjects of exploration. Interest in robotics did not end consideration of the other approaches.

**Current diagnostic scope**

The owner reports conceptual problems despite existing ADRs, architectural documents, and diagrams, and concerns about canonical requirements. The current task is to diagnose the problems before deciding how changes should be made through the language, processor, runtime, and other components:

1. Recover intended semantics and lineage, including applicable external language-design sources and sound existing SDL concepts.
2. Distinguish conceptual defects, implementation violations, incomplete execution connections, and errors in the audit's own interpretation.
3. Trace dependencies to establish the affected scope. Discuss unclear conceptual points with the owner before resolving them.

The owner has withdrawn parity as the objective and scope criterion. The overriding concerns are **clarity, consistency, language-design quality, and long-term implications**. The diagnosis covers the full participant-control audit and affected dependencies. Clarifications about optional participants and injects informed that review; they did not narrow it. Diagnosis is complete for this scope; architecture and implementation decisions remain open.

Existing settled semantics must be read before asking questions. When owner feedback is needed, ask and end the turn; do not continue research or move to another topic while awaiting an answer.

The earlier [requirements-scoping note](requirements-scope.md) and [PRD draft](prd.md) are retained as historical discussion records. Their process framing is superseded by the working diagnosis. Existing architecture and prior research remain inputs to understanding rather than substitutes for the author's intended semantics.

**Purpose and scope clarified by the owner**

RAE is for creating and controlling digital worlds for any purpose. This includes creating or recreating environments and governing behaviour within them. CTFs, scientific experiments, DevOps automation, workflow automation, in-world event injection and reaction, and disaster recovery are use cases discussed so far. They do not exhaust or define the product's purposes.

SDL expresses and implements author intent without arbitrary authoring obligations. An environment may declare access arrangements and entry points without declaring participants or specifying its future users. Participant-related information is needed only where the authored semantics require it. The owner identifies APTL/TechVault as an example and views a researcher reaching into the world as a possible source of an inject. The [focused evidence](environment-inject-diagnosis.md) records these clarifications and checks the existing general and participant-specific paths separately.

RAE's runtime is the shared product runtime that drives LilRAE, BigRAE, and other backends through execution. This role contributes to backend agnosticism. It is a product component alongside SDL and the processor, and may be the only runtime implementation built. It is not merely a reference implementation. The discussion does not establish a separate scenario runtime for each backend.

[OpenRAE/hub#3](https://github.com/OpenRAE/hub/issues/3) provides ecosystem context, including LilRAE's local realization responsibilities and BigRAE's organizational responsibilities. The owner's explicit shared-runtime clarification corrects the earlier audit interpretation that those product boundaries required independent scenario orchestration in each backend.

The owner previously requested a sound, modular, durable, safe, and secure foundation. The latest clarification establishes clarity, consistency, language-design quality, and long-term implications as the overriding concerns. Detailed requirements and acceptance criteria remain to be developed.

Substantial design work precedes implementation changes. This issue starts that exploration; it does not authorize execution of the audit's proposed repair sequence.

**Failure, durability, and author choice**

Durability does not imply that an interrupted execution is resumable. The owner identified an experiment whose failure requires a new trial rather than continuation. Authors need the option to express the required behaviour. The discussion has not defined the corresponding language constructs, failure categories, defaults, or execution lifecycle.

The record therefore does not impose automatic resumption, automatic retries, or automatic creation of a new trial. The authoring and execution semantics remain to be developed.

**OT scope and timing**

The owner identified all three forms of operational technology (OT) use: simulation/emulation, hardware-in-the-loop, and operational systems. The later clarification establishes sequencing: reaching physical OT in a lab or operational system, including disaster-recovery use, is a future direction.

A CTF does not require the overhead of operational-OT protections merely because the platform may eventually support physical OT. An OT simulation does not inherit the care required by an operational system. No common OT protection level, safety certification target, hard timing guarantee, or implementation profile has been agreed.

**Backend purpose and requirements: understanding reached so far**

Only the following boundary positions have been established. They are not a complete backend requirements model.

| Topic | Owner clarification |
| --- | --- |
| Authored requirements | An author may express what they require. RAE must accept it as the requirement when it is valid and expressible within RAE, plannable, and runnable by the runtime. |
| Backend suitability | The runtime must reject a backend that cannot or will not fulfil those requirements. |
| Concrete responsibility | Determining concrete ability, willingness, and the applicable execution constraints is largely the backend's responsibility. RAE cannot know or assume all of that accountability upstream. |
| Contextual refusal | A backend may refuse an operation as the scenario develops, even when the operation initially appeared to fall within its manifest and the scenario's requirements. |
| Required execution seam | The runtime/backend interaction needs to accommodate that refusal. Its representation and consequences have not been designed. |

The discussion has not specified manifest fields, a negotiation protocol, refusal reason codes, operation states, evidence obligations, or the runtime's response to each kind of refusal. It has not decided whether or when refusal permits retry, replanning, substitution, or a different backend. Earlier illustrative response tables are not an accepted protocol.

The allocation of concrete responsibility to backends does not change the agreed role of the shared runtime in driving their execution. The detailed division still requires investigation.

**Questions still open**

- What do clarity, consistency, language-design quality, and long-term implications require of RAE?
- What distinctions and lifecycle semantics are needed for authored failure handling, resumption, and a new trial?
- What must a backend declare, what can be established before execution, and what can only be decided in context?
- How is a contextual backend refusal communicated, and what does it mean for the ongoing execution?
- Which existing patterns or implementations fit these requirements, once the requirements are sufficiently understood?
- Which safety, security, timing, and durability obligations belong at each boundary for the current scope?

These questions identify gaps in the discussion. They are not a proposed feature list or acceptance criteria.

**Audit provenance**

The audit examined development revision `6bfdb7efdabbf5efe22fa023a16316830cf25380`. Its original runtime-ownership objection, F01, was withdrawn following the owner's clarification. The remaining findings are preserved as findings about that audited revision, not as a fresh assessment of this branch's base.

This exploration branch starts from development revision `f92f3a297408f54a409e0220136a2d1790786c23`. The audit has not been rerun against that revision.

The retained audit artifacts are:

- [Audit report](../participant-control-audit/audit-2026-09-21.md).
- [Issue-by-issue scope](../participant-control-audit/scope-2026-09-21.md).
- [Evidence inventory and captured counterexamples](../participant-control-audit/evidence-2026-09-21.json).
- [Existing reproduction script](../participant-control-audit/reproduce-2026-09-21.py).

The exploration adds discussion and research records. It does not change implementation code, published contracts, or accepted ADRs.
