# Sources for the participant identity audit

Reviewed 2026-09-21 for [#215](https://github.com/OpenRAE/rae/issues/215).
This is a targeted architecture and authoring review. Sources were selected for
identity/role separation, service actors, responsibility, typed relationships,
participant interfaces, and notation usability. It is not a systematic review.
Repository behavior comes from [code inspection and probes](evidence.md).
The issue supplies the author-designated autonomy rule; no external source is
used to impose a threshold or a universal definition of an agent.

## Primary sources and bounded use

| Source and consulted location | Relevant precedent | Application and limit |
| --- | --- | --- |
| OMG, ISO/IEC 19505-2:2012, UML Superstructure, [§16.3.1 Actor](https://www.omg.org/spec/UML/ISO/19505-2/PDF), PDF pages 618–619 | An actor models a role relative to a subject, rather than necessarily one physical individual; one individual can play multiple roles. | Supports distinguishing role from physical identity. UML actors are external to the modeled subject; RAE participants are scenario subjects. Do not import UML multiplicities or externality as the participant definition. |
| W3C, Activity Streams 2.0, Recommendation 23 May 2017, [§4.3 Actor](https://www.w3.org/TR/activitystreams-core/#actor) and Activity Vocabulary [§3.2, Service](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-service) | Actors specialize objects; application, group, organization, person and service are actor types. Activity separates actor, object, target and instrument. | Supports services in acting roles and objects that can themselves be actors. Its social-activity `target` is not synonymous with all RAE targets. A Service type alone does not designate a RAE participant; its vocabulary is not an autonomy test. |
| W3C, PROV-O, Recommendation 30 April 2013, [§3.1 and starting-point terms](https://www.w3.org/TR/prov-o/#description-starting-point-terms), `wasAssociatedWith`, `wasAttributedTo`, `actedOnBehalfOf` | Responsibility for activity, attribution of an entity, and acting on another agent's behalf are separate relations. Qualified associations can retain roles and plans. | Supports separate objective ownership, assignment and realized attribution. PROV Agent denotes responsibility; PROV Entity is broader than RAE's organizational Entity. Neither provenance nor delegation in this ontology grants runtime authorization. |
| OASIS, [TOSCA 2.0](https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html), §§7.3–7.4 and 8.1–8.5, consulted 21 September 2026 | Relationship types can constrain source/target nodes and capabilities; requirements bind compatible capabilities. The document itself notes incomplete relationship-template grammar. | Supports relation-specific endpoint checks and separating nodes from capabilities. It does not imply default denial in TOSCA: undefined restrictions can admit all node types. RAE's explicit eligibility recommendation is our inference, not a TOSCA requirement. No deployment topology or TOSCA syntax is made compulsory. |
| Alan Blackwell and Thomas Green, [Cognitive Dimensions of Notations tutorial](https://www.cl.cam.ac.uk/~afb21/CognitiveDimensions/CDtutorial.pdf), 1998 version, “The full set,” “Hidden dependencies,” “Premature commitment,” and “The remaining dimensions” | Notations trade off visibility, consistency, abstraction, viscosity, role expressiveness, and closeness to users' tasks. | Supplies the heuristic rubric for the audit's task table. It does not measure RAE users or prove that a rename improves adoption. A user study would require participants, tasks, observations and analysis beyond this inspection. |
| Terry et al., [PettingZoo: A Standard API for Multi-Agent Reinforcement Learning](https://arxiv.org/html/2009.14471v7), arXiv:2009.14471v7, 26 October 2021, §§3–6 and appendix C | Explicit agent/environment interaction and ordering can prevent conceptual mistakes hidden by a convenient API; the paper demonstrates failures through case studies. | Supports examining actor/target meaning and cross-layer joins beyond parser acceptance. The AEC game/API is a learning-environment model, not a rule that every RAE service/tool must be an agent, nor an imported RAE scheduler. |
| Standen et al., [CybORG: A Gym for the Development of Autonomous Cyber Agents](https://arxiv.org/pdf/2108.09118), arXiv:2108.09118v1, 20 August 2021, §§2–4 | Simulation and emulation share an agent-facing interface while realization and action/observation detail differ. | Explains the repository's agent-interface lineage and why common syntax is not evidence of equivalent native behavior. It supplies neither composite-participant identity semantics nor an obligation to use one process/model per participant. |

URLs were opened directly during the review. The dated recommendations and
arXiv revisions identify consulted editions. The TOSCA URL is a maintained
publication: claims here are limited to the named sections observed on the
review date, rather than an assertion of immutable bytes. No source text or
external schema was copied into an executable RAE artifact.

## Repository lineage and authority

The [participant lineage](../../explain/sdl/lineage.md#participant-semantics)
connects agent interfaces, partial observation, local histories, interaction,
time, and attribution. The current
[v2 ledger](../../../contracts/provenance/sdl-lineage-ledger-v2.json) records
`sdl-field:agents` as adapted from CybORG scenario configuration with no
compatibility claim. Its separate interactive-access claim pins CyRIS 1.2 and
CybORG 3.0 boundaries. The autonomous-execution claim distinguishes participant
interfaces, shared time and operational resource precedents. Section-level
lineage is not evidence that every Agent field came from that source.

V1 is historical; v2's document still uses the `sdl-lineage-ledger/v1` schema.
This review changes no derivation or compatibility claim and therefore does not
rewrite either ledger. The new standards are audit precedents, not newly
adopted language authority.

ADR-020 is the framing baseline; ADR-022 separates action, observation,
attribution and outcome; ADR-041 separates implementation apparatus; proposed
ADR-067 composes the behavior model; ADR-092 separates autonomous policy,
execution service, targets and selected implementation. ADR-079 supersedes the
starting-condition field, and ADR-073 removes the reward label. These are
inputs to the audit, not proof that adjacent definitions are consistent.

The [language-extensibility review](../language-extensibility/design-review.md),
[clarified intent](../language-extensibility/design-intent.md), and
[consistency correction](../language-extensibility/consistency-review.md)
constrain the recommendations: abstract models can be complete; omitted
implementation detail is not automatically missing authoring; observation
demand is separate from representability and realization. Typed reference
eligibility must not become mandatory per-tool/component inventory.

## Synthesis boundary

The recommendation combines author-selected identity, typed semantic relations,
purpose-specific reference rules, explicit cross-layer mappings and task-based
guidance. No single source proves this combination correct for RAE. Each proposed
change has counterexamples and compatibility obligations in the
[implementation backlog](remediation-plan.md). Current accepted behavior,
design recommendations and evidence of execution remain separate claims.
