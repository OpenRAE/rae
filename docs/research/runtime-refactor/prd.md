**RAE product requirements — historical draft**

Started: 2026-09-21. Tracking: [issue 1348](https://github.com/OpenRAE/rae/issues/1348).

**Superseded process**

The owner subsequently rejected the PRD as the instrument for this work and directed diagnosis of the problems and their affected dependencies. The working premise is that conceptual problems can be corrected while retaining the language. The [working diagnosis](diagnosis.md) carries subsequent clarification and investigation. This document retains the earlier dialogue; it is not an active PRD or an adopted requirements baseline.

The statements below record the preceding discussion stage. They do not select an architecture, framework, language construct, or backend protocol. Implementation changes remain deferred until the problems and affected scope are better understood.

**Overriding concerns**

The owner identified four overriding concerns:

- Clarity.
- Consistency.
- Language-design quality.
- Long-term implications.

Current capability parity has been withdrawn as the objective and scope criterion. No parity baseline is being established. The specific requirements and evaluation criteria for the four concerns have yet to be articulated. Compatibility and migration obligations have not been decided.

The owner reports recurring agent misunderstanding despite existing ADRs, architectural documents, and diagrams. This is context for the requirements work; agent confusion is not a property of RAE. The definition and maintenance of canonical requirements are concerns to address.

**Current focus**

The current focus is the language design of areas affected by the conceptual problems identified in the milestone-67 audit. The owner wants to understand whether those designs can be corrected, whether entire areas require replacement, or whether the problems extend into shared SDL foundations. The extent of the required remedy is unresolved.

The review must therefore examine affected concepts and their relationships, including their expression in requirements, ADRs, semantics, contracts, and implementation. An individual defect is evidence about a design; fixing it does not establish that the design is sound. A ground-up rebuild has not been requested.

Existing settled SDL semantics must be read before asking the owner questions. Questions should address unresolved requirements in the affected areas. The scope can expand where the investigation establishes a relevant conceptual dependency or contradiction. Parity does not determine that boundary.

**Product purpose**

RAE is for creating and controlling digital worlds for any purpose. This includes creating or recreating environments and governing behaviour within them.

CTFs, experiments, DevOps automation, workflow automation, in-world event injection and reaction, and disaster recovery are use cases discussed so far. They do not exhaust the product's purposes.

**Author intent and the world boundary**

The researcher or author determines what constitutes the world for their use case and expresses that intent in SDL. This choice is exogenous to the language. The language exists to let them express intent, not restrict intent.

**Product and backend boundaries established so far**

| Topic | Recorded understanding |
| --- | --- |
| Shared runtime | RAE's product runtime drives LilRAE, BigRAE, and other backends through execution. This contributes to backend agnosticism. The runtime is a product component alongside SDL and the processor, and may be the only runtime implementation built. It is not merely a reference implementation. |
| Authored requirements | Authors may express what they require. RAE must accept it as the requirement when it is valid and expressible within RAE, plannable, and runnable by the runtime. |
| Backend suitability | The runtime must reject a backend that cannot or will not fulfil those requirements. |
| Concrete responsibility | Concrete ability, willingness, and applicable execution constraints are largely the backend's responsibility. RAE cannot know or assume all of that accountability upstream. |
| Contextual refusal | A backend may refuse an operation as the scenario develops, even when it initially appeared to fall within its manifest and the scenario. The runtime/backend interaction needs a seam for this refusal. Its protocol and consequences remain undefined. |

These statements do not constitute a complete responsibility model or backend requirements set.

**Conceptual distinctions under review**

The owner identified conflation of participants with researchers, authors, and auditors, and conflation of in-world and out-of-world concerns. These examples are not an exhaustive list. The author determines the world boundary through the intent expressed in SDL. Existing definitions must be examined for consistency and adequacy in the affected designs; their absence from this dialogue does not mean that the language lacks them.

**Durability and author choice**

Durability does not imply resumption. An experiment may require a new trial after failure. Authors need the option to express the required behaviour. The corresponding failure categories, defaults, authoring constructs, and execution lifecycle remain undefined.

The earlier request for a sound, modular, durable, safe, and secure foundation remains part of the dialogue. The latest clarification establishes the overriding concerns above; it does not supply detailed definitions or acceptance criteria for those qualities.

**OT scope**

The intended uses include simulated/emulated operational technology (OT), hardware-in-the-loop, and operational systems. Reaching physical OT in a lab or operational system, including disaster-recovery use, is a future direction.

A CTF does not require operational-OT protections merely because the platform may eventually support physical OT. An OT simulation does not inherit the care required by an operational system. No common OT protection level, safety certification target, or hard timing guarantee has been agreed.

**Dialogue record**

Question: what should count toward current capability parity: working capabilities, capabilities the implementation attempts to support, or documented but unimplemented capabilities?

Owner answer: parity is distorting the discussion and is to be dropped. The overriding concerns are clarity, consistency, language-design quality, and long-term implications. The dialogue may begin this PRD, focused on current concerns and expanded to other areas later.

Disposition: the parity question is withdrawn. Its earlier scope selection is superseded. The answer does not select a compatibility policy or authorize implementation changes.

Question: beyond the runtime/backend boundary already clarified, which recurring misunderstandings should the requirements eliminate, and what should the correct understanding be?

Owner answer: agents conflate participants with researchers, authors, and auditors, and conflate in-world and out-of-world concerns. These are examples, not an exhaustive list. Agent confusion is not a property of the system; the owner questioned the relevance of asking about it.

Disposition: record the named conceptual distinctions without treating agent behaviour as a system requirement or asking the owner to inventory misunderstandings. Continue with questions about RAE's concepts and required behaviour directly.

Question: what determines whether an entity or activity is part of an authored world?

Owner answer: the author wrote it in SDL. It is whatever the researcher or author wants it to be for their use case. That choice is exogenous to the language; the language exists to let them express intent, not restrict intent.

Question: when an author lists services without stating whether the list is exhaustive, does that require those services to exist, require that only those services exist, or require further specification?

Owner answer: existing open/closed and exact semantics cover this. Read the SDL and documentation rather than asking basic questions already settled there.

Disposition: the question is withdrawn. Relevant existing sources include [augmentation scope](../../../specs/sdl/augmentation-scope.md) and [recursive realization constraints](../../../specs/sdl/recursive-realization-constraints.md). Their distinct notions of augmentation, closure, exact values, and delegation must not be collapsed into a new generic omission question.

Owner scope correction: this is about language design in the areas affected by the audit's conceptual problems. Point fixes may be insufficient. The investigation must establish whether correction, replacement of affected areas, or broader foundational change is required. It must not presume that the whole SDL needs rebuilding or that individual fixes will suffice.

**Supporting records**

- [Exploration context](README.md).
- [Requirements-scoping questions and source inspection](requirements-scope.md).
- [Research notes](research.md).
- [Milestone-67 audit](../participant-control-audit/audit-2026-09-21.md).

The source inspection, external research, and audit recommendations are inputs to the dialogue. They have not been adopted as requirements by inclusion here.
