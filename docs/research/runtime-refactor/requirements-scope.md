**Requirements scope: affected language designs and their dependencies**

Recorded: 2026-09-21. Tracking: [issue 1348](https://github.com/OpenRAE/rae/issues/1348).
Context: [owner clarifications and exploration status](README.md).

**Status**

Historical scoping record. The owner subsequently replaced requirements/PRD development with diagnosis, assuming conceptual problems can be corrected while retaining the language. The [working diagnosis](diagnosis.md) supersedes the process framing below and records the current investigation. The source inspection and initial affected-area map remain inputs to that work.

The owner directed requirements scoping first, requirements work second, and consideration of language, processor, runtime, or other changes only afterward. The owner also identified recurring agent confusion and inadequate definition and maintenance of canonical requirements.

The owner has withdrawn the earlier parity-based scope. The overriding concerns are **clarity, consistency, language-design quality, and long-term implications**. The dialogue now develops a [working PRD](prd.md), focused on current concerns and expanded to other areas over time.

The current focus is the language design of areas affected by conceptual problems identified in the milestone-67 audit. The owner wants to determine whether the designs can be corrected, whether entire areas need replacement, or whether the problems extend into shared SDL foundations. The remedy's extent is a question to investigate. A defect list alone does not establish the appropriate design boundary.

The investigation below implements that scope clarification. Its preliminary assessments are review judgments, separate from the owner's requirements recorded in the PRD. No replacement design or amendment to a canonical requirement has been selected.

**Existing sources inspected**

Inspection covers selected requirements, governance documentation, architecture entry points, and the semantic sources cited below at branch base `f92f3a297408f54a409e0220136a2d1790786c23`. It is not a requirements-quality audit of the full catalogue. The original audit examined an earlier revision; its runtime counterexamples have not been rerun here.

| Source | Observation relevant to scoping |
| --- | --- |
| [Requirement policy](../../../tools/policy/requirement_order.yaml) and [issue-bound scope documentation](../../governance/requirement-scopes/README.md) | Policy selects repository requirements. Statements and traceability reside under `docs/requirements/`; prerequisite and artifact-ownership rules reside in the policy file. Issue-bound scope manifests describe delivery scope, not the product requirements scope now being discussed. |
| [DSL-100](../../requirements/DSL-100/requirement.md) | Its statement describes a language for cyber-range scenarios and experiments. It does not state the broader digital-world purpose clarified by the owner. This identifies a reconciliation question, not an authorized replacement statement. |
| [RUN-300](../../requirements/RUN-300/requirement.md) and [API-404](../../requirements/API-404/requirement.md) | The former states a general obligation to preserve scenario meaning through processing and execution. The latter specifies particular control-plane profiles and their clauses. Existing records operate at different levels of detail. Their status as current records does not determine which details should constrain a refactor. |
| [Glossary](../../explain/reference/glossary.md) and [authority manifest](../../../specs/authority/authority-boundary.yaml) | The glossary's introduction includes source code among the locations of normative definitions. The manifest classifies implementations as non-normative and says Python models do not define ecosystem meaning. This is a concrete wording discrepancy to resolve when establishing the reading and authority model. |
| [Runtime architecture](../../explain/sdl/runtime-architecture.md) and [ADR index guidance](../../decisions/adrs/README.md) | The architecture document explicitly focuses on the currently implemented path. ADR guidance records decisions, rationale, alternatives, and consequences, with accepted content pinned. These are distinct inputs from statements of required product behaviour. |

These observations do not establish the cause of every agent misunderstanding or the maintenance state of every requirement. They support investigating how product intent, requirements, decisions, and implemented behaviour are distinguished and connected.

**Affected areas: initial investigation map**

Finding identifiers refer to the [audit](../participant-control-audit/audit-2026-09-21.md). These areas may overlap; their boundaries remain subject to dependency tracing.

| Design area | Evidence and question for the review |
| --- | --- |
| Participant, controller, and supervisory authority | F02 challenges the requirement that a controller be an agent or `self`. [ACT-607 and ACT-617](../../../specs/formal/participant-behavior-model/README.md) explicitly distinguish participant authority from control-plane authorization. Determine whether mixed-control correctly models an in-world relationship but lacks a separate supervisory relationship, or whether its controller concept is itself inadequate. Treating every supervisor as a participant is not an assumed remedy. |
| Authored control policy and execution occurrences | F03 concerns the policy model itself. ACT-617 calls it an authored state graph, but transitions fix expected/resulting state revisions and effective order. Determine what reusable control behaviour must express and whether the existing policy/occurrence distinction can support it. Trace the consequences through compilation, API-409, and runtime history. |
| Modular decisions, dependencies, and effects | F07–F10 concern obligation coverage, advisory results, provider dataflow, and effect composition. [MPC-01, MPC-05, and MPC-06](../../../specs/formal/participant-semantics/modular-participant-control.md) already require distinctions violated by several audited paths. F08 additionally exposes a target/phase contradiction in accepted effect plans. Determine whether the composition model is coherent and sufficiently specified before classifying the failures as implementation repairs or reasons to replace it. |
| Information-flow domains and extension | F11 questions portable policy expressiveness and hardcoded profile support. MPC-04 defines a general domain contract while preserving a small security profile. Determine which limitations belong to that profile, which arise from its publication/extension mechanism, and whether they compromise the shared information-flow model. Broader profile requirements have not been established in this dialogue. |
| Authored effects, realization, and evidence | F04 and F12–F15 question what cancellation, injection, routing, delivery, observation, and success records actually establish. MPC-09–MPC-11 already distinguish several of these stages. Trace each affected concept across declaration, occurrence, shared-runtime execution, backend response, and evidence to locate missing or contradictory obligations. Include contextual backend refusal where it affects these meanings. |

F05, F06, and F16 supply additional API, authorization, and operational evidence. They may expose shared design dependencies, but do not by themselves establish that SDL concepts require replacement.

**Shared foundations and existing corrections**

The initial inspection does not establish that the problems pervade the SDL. ACT-607 explicitly separates starting access, authority, observation, backend capability, and API authorization. MPC-08–MPC-11 distinguish authorization, approval, execution, delivery, and observation. These are concrete distinctions to evaluate for consistency across consumers; their presence does not certify the surrounding designs or implementations.

[Participant identity, affiliation, and objective assignment](../../../specs/sdl/participant-identity.md), adopted by ADR-109, is already on this branch's base. It distinguishes authored participant identity from control-plane identity and separates affiliation, assignment, and authority. This correction must be accounted for when reassessing F02; the remaining agent-only controller restriction does not justify treating the whole identity model as unchanged since the audit.

[Augmentation scope](../../../specs/sdl/augmentation-scope.md) and [recursive realization constraints](../../../specs/sdl/recursive-realization-constraints.md) already define relevant open/closed, exact-value, presence, and delegation semantics. The earlier generic omission question is withdrawn. These semantics are dependencies to read and preserve or challenge with specific evidence, not unanswered basics to ask the owner again.

**Review method and required result**

For each affected area:

1. Recover its intended requirements and distinguish them from architectural choices, semantic rules, and implementation behaviour.
2. Identify conceptual contradictions, missing requirements, and implementation violations separately. Reassess the audit's interpretations as well as the code.
3. Trace shared concepts and dependent consumers until the evidence supports a boundary for the problem. Expand the scope when that tracing identifies a shared defect.
4. Ask the owner only about unresolved intent or requirements that affect the design judgment, then record the answer in the PRD.
5. Assess whether the area permits a coherent correction, requires replacement, or depends on broader foundational changes. Explain the evidence, affected surfaces, and remaining uncertainty.

The result should support a decision about the scale of design work. It must also identify which requirement records need reconciliation and how their authority and maintenance should be resolved before component changes begin. No whole-language viability judgment, replacement decision, or implementation estimate is established by this initial map.
