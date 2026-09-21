**Requirements scope: initial questions and source inspection**

Recorded: 2026-09-21. Tracking: [issue 1348](https://github.com/OpenRAE/rae/issues/1348).
Context: [owner clarifications and exploration status](README.md).

**Status**

The owner directed requirements scoping first, requirements work second, and consideration of language, processor, runtime, or other changes only afterward. The owner also identified recurring agent confusion and inadequate definition and maintenance of canonical requirements.

The owner selected **shared product requirements needed for current capability parity** as the scope of the first pass. An assessment of the entire RAE requirements catalogue is outside this first pass.

The specific capability baseline, requirement records to include, and acceptance criteria remain to be established. The selection does not approve the proposed areas below as a complete inventory, select a requirements hierarchy, replace a canonical source, or amend an existing requirement.

**Existing sources inspected**

Inspection was limited to selected foundational requirements, requirement-governance documentation, and architecture entry points at branch base `f92f3a297408f54a409e0220136a2d1790786c23`. It was not a requirements-quality audit of the full catalogue.

| Source | Observation relevant to scoping |
| --- | --- |
| [Requirement policy](../../../tools/policy/requirement_order.yaml) and [issue-bound scope documentation](../../governance/requirement-scopes/README.md) | Policy selects repository requirements. Statements and traceability reside under `docs/requirements/`; prerequisite and artifact-ownership rules reside in the policy file. Issue-bound scope manifests describe delivery scope, not the product requirements scope now being discussed. |
| [DSL-100](../../requirements/DSL-100/requirement.md) | Its statement describes a language for cyber-range scenarios and experiments. It does not state the broader digital-world purpose clarified by the owner. This identifies a reconciliation question, not an authorized replacement statement. |
| [RUN-300](../../requirements/RUN-300/requirement.md) and [API-404](../../requirements/API-404/requirement.md) | The former states a general obligation to preserve scenario meaning through processing and execution. The latter specifies particular control-plane profiles and their clauses. Existing records operate at different levels of detail. Their status as current records does not determine which details should constrain a refactor. |
| [Glossary](../../explain/reference/glossary.md) and [authority manifest](../../../specs/authority/authority-boundary.yaml) | The glossary's introduction includes source code among the locations of normative definitions. The manifest classifies implementations as non-normative and says Python models do not define ecosystem meaning. This is a concrete wording discrepancy to resolve when establishing the reading and authority model. |
| [Runtime architecture](../../explain/sdl/runtime-architecture.md) and [ADR index guidance](../../decisions/adrs/README.md) | The architecture document explicitly focuses on the currently implemented path. ADR guidance records decisions, rationale, alternatives, and consequences, with accepted content pinned. These are distinct inputs from statements of required product behaviour. |

These observations do not establish the cause of every agent misunderstanding or the maintenance state of every requirement. They support investigating how product intent, requirements, decisions, and implemented behaviour are distinguished and connected.

**Proposed scope questions**

The following areas are proposed for discussion, not accepted coverage decisions.

| Area | Question to settle before drafting requirements |
| --- | --- |
| Product purpose and parity | Which present capabilities and user outcomes must the refactor preserve? What baseline defines effective parity, and what is deferred? |
| Concepts and responsibilities | Which shared terms and responsibility boundaries must be understood consistently across RAE, authors, and backends? Which existing definitions need reconciliation? |
| Required behaviour and author choice | What requirements are needed for creating or recreating environments, governing behaviour, and expressing failure and continuation choices? Which decisions belong to the author? |
| Runtime/backend interaction | What requirements establish backend ability, willingness, and contextual refusal without assigning concrete backend accountability upstream? |
| Quality and compatibility | What does sound, modular, durable, safe, and secure mean for the present scope? Which compatibility obligations are part of parity, and which stronger guarantees are deferred? |
| Canonical requirements and maintenance | Where does each authoritative requirement live; who resolves ambiguity; how are its status, rationale, changes, and relationships to architecture kept current? |

These questions cross current component boundaries. They do not yet assign requirements to packages, prescribe language constructs or protocols, or select runtime mechanisms.

**Proposed result of the scoping work**

An agreed scope could identify:

- The requirement areas included now and those deferred, with the reason for each boundary.
- The existing records and other sources to examine for those areas.
- Known ambiguities, inconsistencies, missing statements, and questions requiring an owner decision.
- The canonical recording and maintenance approach for the resulting requirements.
- What must be resolved before the requirements work is considered sufficient to begin design.

This proposed result is a scope record, not the requirements themselves or a PRD. No canonical requirement or accepted ADR was changed in this inspection.
