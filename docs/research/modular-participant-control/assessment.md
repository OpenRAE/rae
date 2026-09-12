# Current state and literature assessment

Assessment cut: 2026-09-06, RAES `fb4cb4b7` on `dev`. Scope is the architecture
requested by [#1068](https://github.com/OpenRAE/rae/issues/1068). This is a
targeted primary-source assessment, not an exhaustive literature review or a
comparative experiment. Literature findings and RAES design decisions are
separated below. Sources were checked on the assessment date.

## Existing authority and executable boundary

| Existing surface | Evidence at the assessed cut | Disposition and gap |
| --- | --- | --- |
| #794, ADR-085, SEM-230 | [Information-flow semantics](../../../specs/formal/participant-semantics/information-flow-control.md) and [requirement](../../requirements/SEM-230/requirement.md) already own participant projection, policy, derivation, memory and claim scope. | Reuse. One semantic boundary permits multiple mechanisms; it does not require one engine. |
| SEM-220/226, ADR-095 | [Decision/delivery ADR](../../decisions/adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md) separates a decision, exact state cut, exposure, delivery and observation. | Reuse for every triggered effect and its visibility. A review receipt or the timing of withholding can itself be observable. |
| #812, ADR-101, SEM-233 | [Security algebra](../../../specs/formal/participant-semantics/adversarial-flow-control.md) and [contract semantics](../../../implementations/python/packages/raes_contracts/contracts/participant_flow_control_semantics.py) carry independent confidentiality/integrity obligation sets. | Preserve `sem-233/rev1` and historical records. It is a security profile, not the owner of every experimental label domain. |
| #1001 and #1002 | [Closed relation](../../../contracts/schemas/participant-runtime/participant-flow-control-relation-v1.json) and [portable contract](../../../implementations/python/packages/raes_contracts/contracts/participant_flow_control.py) validate derivation, release and final-sink bindings. | Reuse the carriers and lineage; closed validity is not actual source instrumentation or propagation. |
| #1003 | [Final-sink module](../../../implementations/python/packages/raes_runtime/participant_flow_sink.py) gets `resolve_flow_sink_decision` from the crossing resolver and checks exact context before committing. [Tests](../../../implementations/python/tests/test_issue_1003_final_sink_flow_enforcement.py) exercise boundary failures. | Retain final-sink enforcement. Replace implicit attribute discovery with a public provider protocol in #1069, after #1072 publishes it. Fixture-produced decisions do not constitute a production IFC provider. |
| #1004, API-407/420 | [Capability tests](../../../implementations/python/tests/test_issue_1004_apparatus_backend_capabilities.py) cover flow support, processing roles, apparatus and evidence declarations. | Reuse exact apparatus/manifest identities. Declaration, effective support, realization, bounded conformance and evaluation remain separate. |
| API-409/423, ACT-617, RUN-310/319 | [Control requirement](../../requirements/API-409/requirement.md), [crossing requirement](../../requirements/API-423/requirement.md), and [runtime requirement](../../requirements/RUN-319/requirement.md) preserve controller, authority, cut, evidence and effect distinctions. | Reuse operations. Add typed requests and deterministic composition, not another crossing, action, audit or persistence hierarchy. |
| DSL-111/142, API-421, RUN-308 | Existing inject identity/delivery and governed time/order own scheduling and participant disclosure. | An IFC fact can trigger a new inject request through these owners; a label alone cannot schedule or disclose it. |
| ADR-104 | [Operation-store architecture](../../decisions/adrs/adr-104-runtime-control-plane-architecture.md) owns mutation, durable claims, terminal commits and recovery. | Trigger claims and provider-state references join this authority. External uncertainty must not become a blind retry or an invented exactly-once guarantee. |
| SEM-234/ASR-537, ADR-102 | [Mixed-backend decision](../../decisions/adrs/adr-102-mixed-cross-backend-participant-control.md) governs composition across apparatus/backend edges. | Adjacent concern. Multiple mechanisms within one admitted apparatus do not imply a mixed-backend run or transfer relation. |
| ASR-535/536 and experiment authorities | Existing apparatus/run, evidence, measures and behavioral claims distinguish bounded evidence and adversarial protocols. | Reuse; amend ASR-536 to consume exact modular backend evidence. Add ASR-538 for modular conformance. |
| Hub #36/#37 and backend issues | All 14 [delivery nodes](delivery.md) are open at the assessment cut and already separate backend mechanism choice from RAES ownership. | Bind their requirements and exact dependency edges. Do not create duplicate issues or claim an engine has been selected. |

The older #812 research documents contain DRAFT and future-tense statements
from earlier delivery cuts. The checked-in SEM-233 record is now ACTIVE and
#1001–#1004 are closed; those later artifacts supersede the old status snapshot,
not the security profile's meaning. ASR-536 remains DRAFT. No backend mechanism
or adversarial-evaluation completion follows from those four issue closures.

## Primary-source lessons

| Source and inspected scope | Established lesson | Decision taken for RAES and its limit |
| --- | --- | --- |
| Myers and Liskov, [Complete, Safe Information Flow with Decentralized Labels](https://www.cs.cornell.edu/andru/papers/sp98/paper.html), IEEE S&P 1998; abstract and label model. | Principal-relative policies and explicit declassification support decentralized authority. | Use revisioned domains and explicit release relations. A single global trusted/untrusted scalar cannot stand in for independent authority and influence. This is an architectural application, not a transferred proof. |
| Krohn et al., [Information Flow Control for Standard OS Abstractions](https://pdos.csail.mit.edu/papers/flume-sosp07.pdf), SOSP 2007, abstract and introduction. | Flume realizes decentralized IFC over processes and communication endpoints with explicit privilege; its trusted-base and covert-channel assumptions bound its guarantees. | Backend instrumentation and isolation can realize IFC, while RAES owns the declared relation and sink. Host protection stays backend-owned. OS enforcement is not imposed on every backend. |
| Costa et al., [Securing AI Agents with Information-Flow Control](https://arxiv.org/abs/2505.23643), 2025, abstract; [FIDES implementation](https://github.com/microsoft/fides), repository description. | Tracks confidentiality and integrity and deterministically resolves action policies; evaluates security/utility tradeoffs. | Keep dynamic IFC recognizable, reuse SEM-233's independent coordinates, and pin implementation/evaluation scope. Its planner is a candidate implementation precedent, not a required RAES runtime dependency. |
| Debenedetti et al., [Defeating Prompt Injections by Design](https://arxiv.org/abs/2503.18813), 2025, abstract; [CaMeL implementation](https://github.com/google-research/camel-prompt-injection), repository description. | Separates trusted control from untrusted data and uses capability-based restrictions around agent execution. | Capability restriction and IFC can contribute different constraints. Quarantined processing and model placement remain backend apparatus choices, not endorsement or portable participant internals. |
| Ligatti, Bauer and Walker, [Edit Automata: Enforcement Mechanisms for Run-time Security Policies](https://cse.usf.edu/~ligatti/), IJIS 2005, authors' publication abstract. | Runtime enforcement can suppress, insert and terminate actions; expressive power depends on the enforcement model. | Adopt closed typed effect requests beyond permit/deny. RAES fresh identities and authority checks are additional design obligations; the paper does not establish them for RAES. |
| Carter, [A Principled Approach to Policy Composition for Runtime Enforcement Mechanisms](https://digitalcommons.usf.edu/etd/4006/), 2012, thesis abstract. | Composition of enforcement policies requires explicit reasoning about interactions at trust boundaries. | Use an admitted dependency graph, conjunction and explicit conflicts. We do not claim this particular RAES reducer inherits the thesis's formal results. |
| Bloem et al., [Shield Synthesis: Runtime Enforcement for Reactive Systems](https://arxiv.org/abs/1501.02573), 2015, abstract. | A synthesized shield corrects outputs relative to a selected property and timing model. | A deterministic shield is distinct from a heuristic monitor. Its requested replacement must be freshly admitted; composition can make a once-valid correction invalid. No general safety or liveness guarantee transfers. |
| Greenblatt et al., [AI Control: Improving Safety Despite Intentional Subversion](https://arxiv.org/abs/2312.06942v5), 2024, abstract. | Compares control protocols including trusted editing and untrusted monitoring under intentional subversion and limited trusted labor. | Keep monitor topology, audit budgets, adaptive knowledge, editing and separate safety/usefulness/cost measures in ASR-536. Trusted is a declared evaluation role, not intrinsic authority. |

These sources support explicit IFC, bounded enforcement and composition as
established mechanisms. Using a powerset domain to track experimental treatment
influence, and turning its resolved fact into a governed inject, are RAES design
choices motivated by that machinery. They are not claims that those papers
implemented a non-security RAES profile or proved its properties.

## Mechanisms, policies, and effects

| Mechanism or protocol | State/result contribution | Composition boundary |
| --- | --- | --- |
| Dynamic IFC | Source labels, conservative derivations, resolved sink predicates or observation facts. | Labels stay domain-specific; facts do not grant authority or execute effects. |
| Capability restriction | Available operation/target authority. | Conjoins with flow and action policy; designation alone does not permit release. |
| Deterministic action admission | Structural/domain applicability decision. | An admitted action can still fail final-sink policy. |
| Runtime shield | Property-state decision and a bounded replacement request. | New candidate must satisfy every applicable mechanism, including the shield at its new cut. |
| Heuristic monitor | Revisioned advisory assessment and safe evidence. | Only an admitted rule can consume it to request review, withhold or another effect. |
| Approval/trusted editing | A supervisory decision or fresh proposal. | Approval is neither execution nor declassification; editing retains input provenance. |
| Resource control | Budget/fairness state, constraints and expiry. | Declared allocation and shared-time policy; exhaustion cannot silently remove another mandatory mechanism. |
| Handoff/interruption/shutdown protocol | Requested controller/lifecycle transition under current authority. | Changes enabledness, not history or accumulated influence. A lifecycle effect needs a supported target and evidence. |

The resulting division is precise: RAES standardizes the semantic contract and
orchestration; each backend independently chooses executable machinery and
instrumentation. Hub provides discovery and explanations that link to exact
releases. Neither a literature implementation nor a backend manifest is a
reason to load arbitrary code from an experiment description.
