# Issue #215 participant identity and actor/target audit preflight

Date: 2026-09-21. Requirement: none; the supplied issue is the contract.
ACT-613 is the issue's tracking label, not a requirement assignment for this run.

This is architecture guidance, not the audit, a remediation plan, or a new
language decision. Issue #215 delivers evidence and an actionable backlog;
semantic and implementation changes belong to its follow-up issues.

## Boundaries the audit must preserve

A participant is an author-designated autonomous subject. The author chooses
the autonomy and identity boundary; the language must not test whether a human,
model, process, tool, or service is sufficiently autonomous. A harness, twenty
tools, one model, and four deterministic actions can be one participant.
Composition does not designate its components as additional participants.
Only designated participants use participant semantics. Participants must also
be expressible as targets; being a target does not confer participation.

Keep participant identity distinct from affiliation, ownership, assignment,
role, credentials, resource identity, selected implementation, runtime episode,
and authenticated caller. Two participants may share an entity or implementation
without becoming one participant. Changing an implementation does not by itself
change authored identity. A service modeled as a participant needs that authored
designation; its transport endpoint or execution service cannot supply it.

Reuse the boundaries in ADR-020/022/041/067/092 and the formal participant
behavior, semantics, runtime, and backend contracts. Their existing definitions
are audit inputs, not proof that every definition satisfies #215. In particular,
ADR-020's “identity or alignment” and ADR-092's role/evaluation restrictions must
not silently become the definition of participation.

The [language-extensibility design intent](../research/language-extensibility/design-intent.md),
its [consistency review](../research/language-extensibility/consistency-review.md),
and [ADR-105](adrs/adr-105-recursive-partial-description-semantics.md) require
completeness at the chosen abstraction. Do not make internal composition,
deployment topology, implementation selection, or evidence collection mandatory
just to express identity or an actor/target relationship. Realization support,
operational inputs, observation demand, retention, and export remain separate.

## Repository checkpoints, not final audit findings

Paths below are relative to `implementations/python/packages/` unless stated
otherwise. Use the current repository revision when gathering final evidence.

| Audit question | Incumbent evidence and required distinction |
| --- | --- |
| Identity and affiliation | `raes/agents.py` enforces nonempty `Agent.entity` with a model validator even though the field defaults to an empty string. `raes/entities.py` describes organizations, teams, and people. `raes/validator/_content_objectives.py` resolves the entity and derives role from it. Audit model, published schema, prose, role selection, and downstream consumers; do not infer identity equivalence or cardinality from this binding. |
| Objective actor or owner | `raes/objectives.py` calls `agent`/`entity` actor bindings and requires exactly one. `raes/semantics/objective_semantics/`, compiler objective projection, and `_participant_relationships.py` consume that choice. Establish whether each use means acting, ownership, or assignment; do not promote an entity to participant or infer an acting participant from affiliation. |
| Service meanings | `raes/nodes.py::ServicePort` is a node-local transport binding, with no traffic authorization or live-listener claim. `_runtime_service_families.py` indexes service resources separately. ADR-041 owns implementation selection; ADR-092's execution binding relates action, native target services, and selected implementation. That binding does not establish participant-to-resource identity. |
| Target eligibility | `_declarations.py` retains kind, canonical address, aliases, and eligibility. Generic sections must enter `_REFERENCEABLE_SECTIONS` before `_reference_targetability.py`'s exclusion policy makes them targetable; special/nested declarations also set eligibility directly. Audit both routes. Do not claim that every newly added section automatically becomes targetable. |
| Reference purposes | `_core.py` has both generic reference validation and a narrower operating-scope index. Authority anchors use referenceability; behavior authority scopes and action interaction targets use targetability. Objectives, relationship subtypes, observation subjects, shared state, and runtime authority need their own semantic assessment. One existing boolean is not evidence that their rules should be identical. |
| Names across layers | `raes_processor/compiler/addresses.py::_participant_behavior_address` and `participant_behaviors.py` project `agents.<name>` into `participant.behavior.<name>`. Contract fixtures also use `participants.*`. Portable runtime envelopes carry participant/episode identities separately. Determine whether each spelling is a mapping, opaque external identity, legacy example, or defect before proposing a rename or alias. |
| Definition drift | `Agent.reject_legacy_starting_conditions` deliberately rejects the old field. ADR-079 §5 requires this migration to precondition assertions; `specs/sdl/references.md` documents `starting_assertions`. ADR-020 still publishes the old spelling. Reconcile authority and reader guidance; do not restore the rejected field as a convenience alias. Check adjacent role, scope, reward, and authority definitions against later decisions, including ADR-073. |

Compare clarification of existing fields, optional affiliation/refinement, and
an explicit relation only where a distinct meaning needs one. Assess authoring
cost, unresolved semantics, compatibility, and cross-layer impact before
selecting definitions or syntax. Do not preselect a new `participants` root,
general actor ontology, or mandatory component graph.

The audit needs representative tasks and counterexamples: one composite
participant; two participants sharing an organization or implementation; a
service used only as a resource versus explicitly designated as a participant;
one participant acting on another; and an organization owning an objective
without acting. Include ambiguous names, module namespaces, and a new
referenceable declaration kind. Preserve every declared constraint while
allowing an abstract scenario without concrete apparatus detail. Parser success
and green tests establish neither conceptual correctness nor adoptability.

## Canonical mechanisms and cross-cutting gates

The audit itself touches repository documents, evidence, policy checks, and
eventual GitHub publication. The executable layers below are inspection and
follow-up compatibility obligations, not authorization to change them in #215.

| Layer | Canonical incumbent and guardrail |
| --- | --- |
| Authority and schemas | `specs/authority/authority-boundary.yaml`, `specs/sdl/sections.md`, `specs/sdl/references.md`, concept-authority catalogs, and `contracts/schemas/` own their respective contracts. Reuse `ContractModel`, `schema_bundle()`, publication-manifest entries, valid/invalid fixtures, and `check_generated_schemas.py`/`check_schema_publication.py`. Published schemas are normative under ADR-009/061; older ADR wording calling them merely generated output is not current authority. A Python default or validator alone does not settle wire compatibility. |
| Decoding and model shape | `raes/_yaml_loader.py`, `parser.py`, `_base.py::SDLModel`, and `_identifiers.py` own safe decoding, closed shapes, portable names, and variable rules. Examples must use these gates. No executable YAML, variable-generated declaration keys, duplicate SDL schema, or audit-specific parser. |
| Reference and semantic policy | `DeclarationIndex`, `QualifiedName`, `SemanticValidator`, pure objective/participant analyzers, and existing relationship-subtype checks retain declaration kind, collision evidence, and ambiguity failures. Extend these owners if remediation requires changed candidate sets. Do not build a second resolver or derive ownership by splitting rendered addresses. |
| Composition, instantiation, compilation, editors | Reuse `raes/composition/_references.py` and `_behavior.py`, existing instantiation revalidation, compiler address/alias indexes, and language-service `_language_metadata.py`/`_language_references.py`. Trace every reference through imports, substitution, serialized phase artifacts, compilation, completion, navigation, and diagnostics. Editor suggestions must agree with field-specific semantic acceptance. |
| Apparatus configuration and secrets | `raes_contracts/participant_configuration.py::realize_participant_configuration` validates the complete manifest registry and owner normalization; `validate_participant_configuration_selection` checks participant, implementation, manifest, and digest agreement. `contracts/experiment_bindings.py` and `secret_references.py` separate literals from logical secret refs. Identity remediation cannot bypass those joins or put raw configuration, prompts, credentials, or hidden context into provenance. |
| Environment and host exposure | If a future binding reaches a node environment, reuse `raes/runtime_environment.py::RuntimeEnvironmentVariable`, `runtime_generated_value.py`, and `_stateful_resource_references.py`: preserve literal/value-source exclusivity, sensitivity, generated-output ownership and consumability. Generated values cannot masquerade as operator secrets. Participant identity introduces no new env binding, listener, host publication, subprocess, or OS privilege. Port declaration and target eligibility grant none of these. |
| Runtime authentication and authorization | `raes_runtime/control_plane_security.py::ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, and existing participant control/audience bindings own caller authentication, roles, and target scope. Participant crossing/flow/effect-authority gates own participant-facing policy. A rename or mapping must preserve exact subject, audience, episode, and policy-cut binding; affiliation, implementation selection, and provenance never grant access. Keep request limits and fail-closed admission. |
| Runtime evidence and persistence | Existing participant envelopes, behavior/observation/control histories, implementation provenance, capability admission, `RuntimeSnapshot`, and `ControlPlaneStore` own durable runtime meaning. Preserve episode identity, ordering, revisions/CAS, idempotency, and append-only history. Address changes can affect configuration digests, policy subjects, replay, stored records, and evidence joins. Document version/migration implications rather than rewriting historical identities. No new identity database or participant audit store. |
| Errors and observability | Reuse `SDLParseError`, `SDLValidationError`, `SDLInstantiationError`, structured `Diagnostic`/`Severity`, and existing conformance results. Repository checks use `tools.policy.common.PolicyFailure` and nox `SessionReporter`. Runtime HTTP failures retain `_operation_routes.py`'s redacted validation/500 handlers, `_responses.py`, and existing audit records. Report bounded refs/rule ids; never echo request bodies, tokens, hidden evidence, backend dumps, or arbitrary exception text. No parallel exception or logging hierarchy. |
| Workflow and distribution | `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/nox_support/policy_lanes.py`, and `.pre-commit-config.yaml` own verification. Preserve contract corpus packaging and conformance registration if follow-ups change published artifacts. Use existing parser, identifier, objective, participant, relationship, language-service, and contract fixture tests for their boundaries; do not add a standalone audit test framework. This requirement-free run must not manufacture requirement scope or traceability. |

The targetability extensibility seam belongs at the existing declaration index
and field-specific reference-policy consumers: parameterize allowed declaration
kinds by reference purpose where the audit proves a distinction is needed.
Adding a kind must require an intentional eligibility decision without copying
section lists into parsers, editors, and compilers. Keep identity rendering and
layer mapping centralized in existing compiler helpers. This leaves room for
another service kind, composite implementation, or relationship without another
participant schema or a blanket targetability rule. It does not prescribe a
new framework or select a policy representation before the audit.

## Evidence authority and literature limits

Use the existing [participant lineage](../explain/sdl/lineage.md#participant-semantics)
and current [v2 ledger](../../contracts/provenance/sdl-lineage-ledger-v2.json),
including its `sdl-field:agents` source records. V1 remains historical; v2 still
uses the `sdl-lineage-ledger/v1` schema identifier. ADR-080 and
`tools/check_sdl_lineage.py` govern this distinction. The section-level CybORG
claim does not establish that each participant field came from CybORG.

The following are research boundaries for the audit, not adopted RAE syntax:

| Primary precedent | Relevant distinction and limit |
| --- | --- |
| [UML, ISO/IEC 19505-2:2012 §16.3.1](https://www.omg.org/spec/UML/ISO/19505-2/PDF) | Actor roles are relative to a subject. This does not define a scenario participant's autonomy or mandate one person/process per identity. |
| [ActivityStreams 2.0 §4.3](https://www.w3.org/TR/activitystreams-core/#actor) | Actors include services and groups and specialize objects. This supports comparison of actor/object roles, not automatic participation for every RAE service or direct equivalence of its target vocabulary. |
| [PROV-O](https://www.w3.org/TR/prov-o/#description-starting-point-terms) | Association, attribution, and delegation distinguish responsibility relations. PROV Agent/Entity terminology is not interchangeable with RAE Agent/Entity; provenance is not operational authorization. |
| [TOSCA 2.0 §§7–8](https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html) | Typed relationships, requirements, and target capabilities inform endpoint compatibility. Deployment topology is not an autonomy definition or a required participant component inventory. |
| [Cognitive Dimensions tutorial](https://www.cl.cam.ac.uk/~afb21/CognitiveDimensions/CDtutorial.pdf) | Evaluate consistency, role expressiveness, hidden dependencies, viscosity, and premature commitment using author tasks. A heuristic inspection is not measured usability or evidence of user adoption. |

Record exact editions/revisions and sections, claim relevance and limits, and
alternatives rejected with reasons. Follow existing `docs/research/lineage/`
source-audit practice; extend the governed ledger only when a derivation claim
changes. Do not invent another citation/lineage registry or fetch sources in CI.
Distinguish confirmed defects, unresolved design questions, and intentional
layer differences, each with repo coordinates and bounded evidence.

## Audit publication contract and operational guardrails

Follow the research/ownership precedent in
`docs/research/language-extensibility/`, without copying its implementation
program or introducing another workflow. Every final audit finding needs a
resolved disposition or an implementation owner. Reuse existing owners where
appropriate; new issues belong to milestone **60 — Runtime & Participant Model**.
Each owner must state the semantic problem, intended result, affected surfaces,
acceptance examples and counterexamples, and compatibility implications.

GitHub blocking links are separate from SDL relationships and from checklist
containment. For prerequisite A and dependent B, the
[issue-dependencies API](https://docs.github.com/en/rest/issues/issue-dependencies)
uses `POST .../issues/B/dependencies/blocked_by` with A's numeric **issue id**
in `issue_id`, not A's issue number or GraphQL node id. Read back B's blockers
and A's blocking list with pagination. Check the affected transitive graph,
including pre-existing links, for cycles before adding edges and verify it
afterward. Reconcile existing edges on retry rather than duplicating writes.
Record real issue URLs and dependency direction; links/checklists alone do not
satisfy #215. Do not make the audit depend on completion of its remediation.
Link the eventual audit, owners, and order from #215 without implying that
publishing the audit delivers the fixes.

Publication uses the existing authenticated GitHub tool or CLI, scoped to
`OpenRAE/rae`; dependency writes need issue-write authorization. Use structured
bodies or `--body-file`, fixed commands, and existing pagination/error handling.
Do not inspect secret files or environment dumps, place tokens in argv/URLs,
enable credential-bearing debug logs, or interpolate issue text into a shell.
Keep temporary output within approved workspace/temp paths; do not persist
authenticated responses as research evidence. Repository evidence paths must
stay repository-relative and pass the existing safe-path discipline. Failed
writes need a bounded status and honest incomplete-publication record, not a
claim that textual links enforce dependencies.

## Non-goals and decision hygiene

This preflight creates no audit result, remediation plan, implementation issue,
dependency edge, schema change, runtime change, migration, or formal requirement.
It does not choose a universal agent definition, new participant syntax, an
autonomy threshold, a concrete deployment model, or a service-participant alias.
Do not turn an audit into parser cleanup, broaden authority to make an example
pass, or infer evidence/collection obligations from mere declaration.

Accepted ADRs are pinned under ADR-059; reconcile drift through a dated companion
or the governed amendment/supersession process. Do not silently edit accepted
decisions or refresh their pins merely to satisfy a check. A new ADR is warranted
only when the audit selects a genuinely changed architectural decision. This
note leaves those decisions open while fixing the boundaries for their review.
