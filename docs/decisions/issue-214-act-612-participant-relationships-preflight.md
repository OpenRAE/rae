# Issue #214 — ACT-612 Multi-Participant Relationships Preflight

Date: 2026-09-16

Issue: #214.

Requirement: ACT-612.

This note records architecture boundaries and implementation guardrails for
explicit coordination, delegation, cooperation, competition, and supervision
relationships among participants. It is guidance only: it does not add SDL
fields, schemas, compiler resources, runtime contracts, API routes, persistence,
or backend behavior.

## Issue 1198 Correction Applied During Planning

The maintainer's #1198/#1201 clarification and accepted ADR-105 govern this
implementation. An abstract relationship is complete with a stable map key,
kind, and two participant endpoints. Action, objective, behavior, authority,
scope, observation, and control references are optional refinements. Validate
every supplied refinement, but do not require an author to supply a backend
mechanism, control policy, validity interval, or evidence merely to describe a
relationship. Declaration never grants operational rights or creates collection,
retention, or export demand. Existing control/evidence contracts remain binding
when explicitly selected or when a realized claim invokes them.

## Binding Authorities

- ADR-020 keeps authored participant identity, role, authority anchors, and
  operating scope on SDL `agents.*`, separate from credentials, OS identity,
  backend identity, and control-plane authorization.
- ADR-022 and `specs/formal/participant-semantics/` own action interactions,
  including coordination, contention, interference, shared-state change,
  joint-action ordering, attribution, observations, and outcomes.
- ADR-052 establishes the top-level SDL `relationships` map as the canonical
  directed graph between named scenario elements and the typed-subtype pattern
  for relationship facts that need structural and semantic validation.
- ADR-054 owns runtime lifecycle, behavior history, shared-state records,
  joint-action records, ordering, evidence, markings, and disclosure.
- ADR-067 and `specs/formal/participant-behavior-model/README.md` compose
  participant framing, behavior specifications, action contracts, authority,
  decision modes, implementation provenance, backend support, and runtime
  evidence. ACT-612 extends that model; it does not create another participant
  stack.
- The ACT-617 mixed-control design owns controller state, proposals, approvals,
  denials, intervention, handoff, override, cancellation, policy revision, and
  non-widening authority/scope checks. Delegation and supervision must reuse
  that machinery when they carry operational control meaning.
- ADR-081's `behavioral-relations` taxonomy classifies formal or empirical
  claims such as trace inclusion and noninterference. It is not the vocabulary
  for relationships between participants.
- `.ground-control.yaml`, `.gc/plan-rules.md`, and the canonical nox/policy
  sessions own verification workflow. ACT-612 does not need an issue-local
  validator runner, schema generator, or policy script.

These authorities settle the architecture sufficiently; another ADR is not
needed unless implementation discovers a conflict with them.

## Architecture Decisions And Boundaries

### Reuse one authored relationship graph

The existing SDL `relationships` map is the authored home for durable
participant-to-participant relationships. Extend its typed relationship pattern
rather than introducing `participant_relationships`, embedding a second graph
inside behavior specifications, or encoding the five relations in free-form
`properties`.

Both endpoints must resolve unambiguously to declared `agents.*` entries for a
participant relationship. A role, entity, account, credential, backend
service, implementation manifest, control-plane identity, or operating-system
principal cannot substitute for a participant endpoint. The endpoints must be
distinct; a reflexive edge does not establish a multi-participant relation.

Preserve the existing directed `source`/`target` contract. Direction is
semantic for delegation and supervision. Coordination, cooperation, and
competition must not be assumed reciprocal merely because their ordinary
language can be symmetric: mutuality must be explicit in the typed relation
contract or through an explicit reciprocal declaration, never inferred from a
single directed edge.

### Keep the five meanings distinct

One canonical relation-kind authority may expose the five required terms, but
each term has different meaning and optional grounding:

| Kind | Portable meaning | Existing semantic grounding | Must not imply |
| --- | --- | --- | --- |
| `coordination` | Participants intentionally synchronize actions or state. | `ParticipantInteractionClass.COORDINATION`, related action contracts, joint-action/order records. | Cooperation, shared goals, successful execution, or scheduler simultaneity. |
| `cooperation` | Participants pursue an explicitly aligned objective or outcome under declared scope. | Behavior-specification, action-contract, objective, and outcome-interpretation refs. | Synchronized execution, unrestricted data sharing, delegation, or trust. |
| `competition` | Participants pursue explicitly opposed objectives/outcomes or compete under a declared scope. | Objective/outcome refs; contention or interference only when the corresponding action/shared-resource facts exist. | Hostility, authorization to attack, resource contention, or zero-sum scoring. |
| `delegation` | A source assigns responsibility for work to a target; operational authority remains separately governed. | Optional authority/scope refs and, for operational controller transfer, ACT-617 proposal/approval/handoff state and occurrences. | Backend realization delegation, credential transfer, role inheritance, execution, or success. |
| `supervision` | A source declares oversight of a target; observation and control rights remain separately governed. | Optional behavior specification, observation boundary, authority/scope, and ACT-617 controller/approval/intervention/override semantics. | `human-supervised` mode, omniscient observation, administrator privilege, or automatic authority widening. |

Do not add cooperation or competition as aliases for the existing action-level
coordination/contention classes. Conversely, a relation-level coordination
edge does not make every action between the participants coordinated. When a
relationship and an action interaction describe the same fact, an agreement
guard must prevent contradictory endpoints, action refs, scope, or kind.

`human-supervised` remains a decision-surface mode of the supervised
participant; it is not a participant relationship and does not identify a
supervisor. `mixed-control` remains combined control over one participant's
decision surface; it is not general multi-participant cooperation. Realization
`delegation` in SEM-218 remains permission for a backend to fill an
underspecified apparatus choice; it is not responsibility or authority
delegation between participants.

### Relationships declare intent; existing records prove occurrences

The authored relationship carries stable identity and may select typed
references to existing behavior, action, objective, authority/scope, observation,
and control contracts. Validity and evidence remain within a selected owning
contract. Sparse relationships require no such refinements. The relationship
must not inline copies of those contracts or store executable policy in
arbitrary metadata.

An authored edge is not proof that participants coordinated, cooperated,
competed, delegated, or supervised during a run. Runtime claims remain grounded
in the existing carriers:

- participant behavior history and lifecycle events for attempts and results;
- participant joint-action records for membership, realized ordering,
  conflicts, isolation, and concurrency disclosure;
- shared-state records for versioned reads/writes and conflict policy;
- participant control occurrences/history for proposal, approval, handoff,
  intervention, override, denial, and cancellation facts;
- observations, outcome reports, attribution, evidence refs, provenance,
  markings, and redaction policy for what was visible and what supports the
  claim.

Backend capability terms such as `coordination`, `contention`,
`interference`, and `shared_state_change` remain support declarations. They do
not prove that a relationship was authored or realized.

### Preserve existing parser, semantic, composition, and compiler ownership

Participant relationship shape belongs under the existing closed
`Relationship` model and its generated SDL schemas. In-class validation owns
single-record invariants. Scenario-level checks belong in `SemanticValidator`,
alongside the current endpoint and typed-subtype checks, because endpoint type,
reference resolution, authority non-widening, action/objective agreement, and
cross-record consistency require the whole scenario.

Module composition must rewrite every participant and semantic reference using
the existing symbol maps. Stable relationship keys remain symbol-defining map
keys and cannot be created with `${...}` variables. Instantiation must rerun
semantic validation after substitution and reject unresolved, ambiguous,
reflexive, contradictory, or authority-widening relationships.

The compiler already preserves authored relationships in
`RuntimeModel.relationship_specs`. That metadata may retain a validated
declaration, but raw dictionaries must not become executable authority. Any
downstream operational use must compile stable typed addresses and resolved
dependencies through the existing compiler/address machinery, or reference the
existing action, behavior-specification, mixed-control, objective, and evidence
records. Do not create a second runtime relationship graph or infer operations
from `properties`.

## Canonical Incumbents To Reuse

| Concern | Canonical incumbent | Required use |
| --- | --- | --- |
| Authored graph | `raes.relationships.Relationship`, `RelationshipType`, `ScenarioContent.relationships` | Extend the one scenario relationship graph and typed-subtype pattern. |
| Participant identity | `ScenarioContent.agents`, ADR-020 `Agent`, `DeclarationIndex` | Require exact participant endpoints; do not accept roles, entities, or runtime identities as aliases. |
| Behavior aggregate | `ParticipantBehaviorSpecification` and stable participant behavior addresses | Bind relation scope to existing behavior refs rather than duplicating behavior fields. |
| Action interaction | `ParticipantInteractionDeclaration`, `ParticipantInteractionClass`, action preconditions/effects/failures | Ground coordination and actual contention/interference at action level. |
| Cooperation/competition meaning | objectives, outcome-interpretation rules, action contracts, behavior specifications | Express aligned/opposed intent with refs; do not infer it from roles or score values. |
| Delegation/supervision control | ACT-617 `mixed_control`, controller states/transitions, participant control occurrences/history | Reuse bounded authority, revision, validity, ordering, handoff, and conflict rules. |
| Authority and visibility | agent `authority_anchors`/`operating_scope`, behavior `authority_scope_refs`, observation boundaries | Enforce non-widening and keep authority separate from visibility and credentials. |
| Safe input and shape | safe YAML loading, parser normalization, `SDLModel(extra="forbid")`, portable identifier and variable-key rules | Keep one closed parser/shape path. |
| Semantic validation | `SemanticValidator`, `_validate_named_ref()`, `DeclarationIndex`, participant-behavior issue rendering | Resolve refs once and collect failures through the existing validation pass. |
| Composition | `raes.composition` relationship and behavior rewrite tables | Rewrite all external refs under namespaces; never parse rendered strings ad hoc. |
| Compiler | compiler address helpers, alias/dependency indexes, `RuntimeModel.relationship_specs`, typed participant behavior resources | Preserve declarations deterministically; require typed projection before operational use. |
| Runtime evidence | behavior history, joint-action, shared-state, control-occurrence, observation, attribution, and outcome contracts | Prove occurrences without inventing an ACT-612 event family. |
| Persistence | `RuntimeSnapshot`, `ControlPlaneStore`, snapshot revisions/CAS, append-only participant histories | Reuse only if live occurrences are later required; add no participant-relationship database. |
| Errors and diagnostics | `SDLParseError`, `SDLValidationError`, `SDLInstantiationError`, `Diagnostic`, `Severity`, conformance diagnostics | Add no ACT-612 exception hierarchy or renderer stack. |
| HTTP security, if exposed | `ControlPlaneSecurityConfig`, read/mutating identity dependencies, participant subject/audience bindings, request-size middleware, idempotency fingerprints, audit records, redacted handlers | Keep caller authorization separate from authored participant authority. |
| Schema authority | `ContractModel`, `schema_bundle()`, `contracts/schemas/sdl/`, schema-publication manifest entries, positive/negative fixtures | Change model source and governed schemas/ledger/fixtures together; do not hand-edit one side only. |
| Workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, repo policy and schema checks | Use canonical verification; add no issue-local workflow. |

## Cross-Cutting Layers And Security Posture

The intended authored design passes these layers:

1. **Safe decoding and closed shape.** YAML passes the existing safe loader,
   duplicate/canonical-key checks, normalized field rules, source limits, and
   closed Pydantic models. Relation IDs cannot be variable-generated mapping
   keys, and unknown fields fail before semantic validation.
2. **Whole-scenario semantic policy.** `SemanticValidator` requires two
   distinct agent endpoints, resolves every grounding ref through the canonical
   declaration indexes, enforces direction and selected refinements,
   rejects ambiguous refs, and prevents delegated/supervisory
   authority or scope from widening its declared sources.
3. **Composition and instantiation.** Existing namespace rewrite tables must
   cover endpoints and every added ref. Post-substitution validation must
   preserve the same endpoint, scope, and policy meaning; unresolved variables
   cannot reach compilation.
4. **Compiler and published shape.** Compiler output preserves stable identity,
   resolved dependencies, deterministic order, and authored provenance. SDL
   schema changes stay in parity with `schema_bundle()`, publication ledger
   entries, fixtures, reference catalogs, and installed package corpus.
5. **Runtime/conformance, only for realization claims.** Existing history,
   joint-action, shared-state, control, observation, outcome, and evidence
   validators check actual claims. Schema validity or an authored edge alone is
   never runtime proof.
6. **Errors and observability.** Parser/semantic failures remain on SDL errors;
   runtime/conformance failures remain structured diagnostics. Messages may
   identify bounded refs and rule names but must not echo credentials, policy
   bodies, hidden prompts, evidence contents, raw backend payloads, or scenario
   dumps.

ACT-612 authoring introduces no environment binding, secret loader, CLI flag,
subprocess, socket, file-permission rule, or process-argument surface. No token,
credential, prompt, private policy body, hidden answer key, raw command, or
backend object belongs in a relationship, fixture, diagnostic, log, snapshot,
or argv. Use stable refs, digests, provenance, markings, disclosure refs, and
redaction-policy refs.

No HTTP route or live persistence is required by this issue's authored
relationship boundary. If a later change exposes or mutates realized relation
state, it must pass strict control-plane authentication, target binding,
participant subject/audience authorization, request-size limits, canonical
fingerprinting/idempotency, snapshot revision/CAS, append-only history, audit,
and the redacted 4xx/500 envelopes. An authenticated operator is not thereby a
delegator or supervisor, and an authored supervisor is not thereby an API
principal.

## Extensibility Seam

Use one typed participant-relationship detail beneath the existing
`Relationship` edge, parameterized by relation kind, explicit direction or
reciprocity, stable grounding refs, authority/scope/validity where applicable,
and evidence/disclosure refs. Kind-specific semantic rules should dispatch from
that common seam. The next reasonable variations—coalition membership,
negotiation, mediation, or non-human supervision—must be addable as governed
relation kinds and validator rules without adding another top-level graph,
copying endpoint fields, or redesigning runtime evidence carriers.

Core terms must remain governed. Backend- or domain-specific extensions may use
the repository's existing `x-<owner>:<term>` concept-authority discipline only
when bound to an approved scope; arbitrary strings in `properties` are not the
extension seam.

## Gotchas And Anti-Patterns

- Do not create a parallel `participants`, `participant_relationships`,
  relation registry, reference resolver, exception tree, persistence store,
  schema generator, audit log, or workflow script.
- Do not use generic `Relationship.properties` for participant authority,
  scope, policy, behavior, objective, action, evidence, or validity facts.
- Do not conflate participant relations with ADR-081 behavioral claims, generic
  infrastructure relationships, workflow dependencies, backend capability
  terms, or SEM-218 apparatus delegation.
- Do not equate coordination with cooperation, competition with contention or
  hostility, delegation with handoff or execution, or supervision with
  `human-supervised`/`mixed-control` mode.
- Do not infer reciprocity, controller identity, authority, visibility, trust,
  scope, validity, execution, success, or evidence from roles, endpoint order,
  credentials, timestamps, scheduler order, or collection order.
- Do not duplicate action interactions, objective/outcome rules, mixed-control
  states/transitions, observation boundaries, or runtime occurrence fields
  inside a relationship. Reference them and enforce agreement.
- Do not treat `RuntimeModel.relationship_specs` raw dictionaries as an
  executable policy or backend request.
- Do not claim realized cooperation, competition, delegation, supervision, or
  coordination from schema acceptance, a backend support declaration, or a
  single terminal snapshot.
- Do not weaken hidden-truth, evidence-only, marking, disclosure, or redaction
  boundaries to make a relationship easier to inspect.

## Non-Goals

- Implementing ACT-612 models, parser behavior, validators, compiler output,
  schemas, fixtures, APIs, stores, runtime mediation, or backend realization in
  this preflight.
- Redesigning generic infrastructure relationships, participant identity,
  action interaction classes, objectives/outcomes, mixed-control operation,
  behavior modes, authority/scope, observations, or runtime evidence.
- Defining team membership, organizational charts, coalitions, negotiation
  protocols, reward games, trust inference, social reputation, or arbitrary
  graph analytics.
- Granting credentials, API roles, backend permissions, or operating-system
  privileges from an authored participant relationship.
- Claiming runtime enforcement, successful cooperation, fair competition,
  completed delegation, effective supervision, causal attribution, or formal
  behavioral equivalence from declarative coverage alone.
