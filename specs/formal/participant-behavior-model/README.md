# Participant Behavior Model Formal Design

This document is the issue #77 formal design artifact for:

- `ACT-602` - Executable Participant Behavior Model
- `ACT-603` - Abstract Participant Interaction Model
- `ACT-606` - First-Class Participant Behavior Specifications
- `ACT-607` - Participant Authority And Scope Boundaries
- `ACT-608` - Participant Behavior Modes
- `ACT-609` - Offensive Behavior Vocabularies

It is governed by ADR-067. It composes the participant semantics from ADR-022
with SDL participant framing, participant runtime records, backend-facing
contracts, controlled vocabularies, and participant implementation provenance.
It is a design artifact, not an implementation artifact.

## Current Coverage And Gap

Existing coverage:

- ADR-020 pins authored participant framing on `agents.*`.
- ADR-022 and `specs/formal/participant-semantics/` define action,
  observation, visibility, interaction, attribution, temporal, and outcome
  semantics.
- ADR-041 defines participant implementation manifest and provenance records.
- ADR-054 and `specs/formal/participant-runtime/` define observable runtime
  lifecycle, behavior history, shared state, observation envelopes, and
  concurrency.
- ADR-060 and `specs/formal/runtime-contracts/participant-backend-contracts.md`
  define backend-facing carrier, retrieval, support, and outcome surfaces.
- `controlled-vocabularies-v1` already defines
  `participant-decision-surface-modes` and
  `participant-offensive-behavior-activities`.
- Issue #206 adds SDL `behavior_specifications` authoring, semantic
  validation, generated schema coverage, and compiled
  `participant.behavior-specification.*` runtime records for ACT-606.

Remaining child-issue boundaries:

- child issues must not publish local behavior semantics outside this model;
- authority/scope and mode work beyond ACT-606 must continue to bind through
  the governed refs and vocabularies defined here; and
- executable behavior-model gates for ACT-602, ACT-607, and ACT-608 remain
  owned by their child issues.

## Model Summary

The participant behavior model is:

```text
ParticipantBehaviorModel =
  ParticipantFraming
  + ActionContractSet
  + ObservationBoundarySet
  + OutcomeInterpretationRuleSet
  + AuthorityScopeBoundarySet
  + BehaviorSpecificationSet
  + BehaviorModeSelection
  + RealizationAndEvidenceBindings
  + RuntimeBehaviorEvidence
```

The model has three layers:

1. **Authored layer** - SDL `agents.*`, action contracts, observation
   boundaries, outcome interpretation rules, authority/scope refs, and
   behavior specification aggregates.
2. **Realization layer** - participant implementation manifests, selected
   decision-surface mode, backend capability and feature-support claims,
   realization profile, fidelity claims, and disclosure refs.
3. **Evidence layer** - participant behavior history, lifecycle events,
   observation envelopes, shared-state records, attribution edges, outcome
   reports, conformance diagnostics, and evidence refs.

These layers are linked by stable references. They are not interchangeable.

## ACT-603 - Abstract Participant Interaction Model

An abstract participant interaction is the tuple:

```text
Interaction =
  participant_address
  action_contract_ref
  attempt_ref
  observation_boundary_ref*
  precondition_result*
  effect_claim*
  failure_class?
  authority_scope_ref*
  state_ref*
  temporal_context
  ordering_relation
  joint_action_ref?
  attribution_ref*
  outcome_interpretation_ref*
  evidence_ref*
```

Rules:

- `participant_address` identifies the runtime participant and episode scope;
  authored identity and role remain SDL framing refs.
- `action_contract_ref` is required for portable action meaning. A raw action
  name, command, tool label, technique label, or benchmark milestone is not
  enough.
- `observation_boundary_ref` defines what the participant may see or infer.
  Hidden truth and archival evidence are outside the participant-visible view
  unless an explicit disclosure rule projects them.
- Preconditions and effects are evaluated against declared state, authority,
  scope, visibility, and temporal context. Unknown or unresolved references fail
  closed.
- Failure classes use the existing participant-semantics taxonomy. Backend
  errors must map to governed failure classes before becoming portable
  semantics.
- Interaction among participants is represented as joint action,
  coordination, contention, interference, or shared-state change, never as
  backend scheduler order alone.
- Outcome interpretation is participant-local until a named rule relates it to
  scenario, workflow, objective, evaluation, evidence, or reward surfaces.

### ACT-603 Implementation Preflight Guardrails

Executable ACT-603 work must be a binding over existing RAES surfaces, not a
new participant stack. The canonical incumbents are:

- SDL authored semantics: `agents.*`, `action_contracts`,
  `observation_boundaries`, and `outcome_interpretation_rules` in
  `implementations/python/packages/raes/`.
- SDL shape and reference validation: `SDLModel`, `parse_sdl`,
  `SemanticValidator`, `analyze_participant_behavior`, and
  `analyze_participant_outcome_interpretations`.
- Compiled runtime addresses: `participant.action-contract.*`,
  `participant.observation-boundary.*`,
  `participant.outcome-interpretation-rule.*`, and
  `participant.behavior.*` from `raes_processor.compiler`.
- Runtime interaction evidence: `ParticipantActionResult`,
  precondition/effect/result records, outcome interpretation records, and
  `iter_participant_behavior_history_violations` in
  `raes_processor.models`.
- Published contract authority: `ContractModel`, `schema_bundle()`,
  `contracts/schemas/`, `contracts/schema-publication-manifest.json`, and the
  `contracts/fixtures/` positive/negative fixture pattern.
- Governed terms: `controlled-vocabularies-v1`, especially participant
  decision-surface modes, runtime behavior features, runtime interaction
  features, and participant runtime feature support levels.
- Runtime/control-plane boundaries: `RuntimeSnapshot`, participant result
  contract diagnostics, participant retrieval views, `OperationReceipt`,
  `OperationStatus`, control-plane audit records, and conformance semantic
  diagnostics.

Security and boundary gates that any ACT-603 implementation touches must remain
in force:

- SDL authoring is closed by `SDLModel(extra="forbid")`; instantiated scenarios
  reject unresolved `${name}` tokens; `SemanticValidator` resolves participant
  refs and fails closed on unknown action contracts, observation boundaries,
  targetable refs, authority anchors, operating scope, and outcome-rule refs.
- Published exchange payloads are closed `ContractModel` payloads and must
  validate through JSON Schema plus semantic validators; a schema change must
  update the publication manifest ledger and fixtures, not only Python models.
- Runtime behavior history must pass participant episode/state/history,
  shared-state, concurrency, visibility, temporal, precondition/effect,
  failure-class, attribution, and outcome-grounding checks through the existing
  participant runtime validators.
- Control-plane exposure must use the existing FastAPI security model: strict
  auth defaults, read vs mutating role dependencies, request-size guard,
  idempotency fingerprinting, redacted internal-error envelopes, and audit
  records. Participant authority is not control-plane authorization.
- Credentials, bearer tokens, hidden prompts, answer keys, raw secret-bearing
  argv/env/config values, backend-private objects, and raw logs are not
  portable interaction data. They require refs, digests, markings, redaction
  policy, disclosure basis, or evidence records through the existing runtime
  value and evidence surfaces.

The extensibility seam is declaration plus disclosure, not a backend-specific
DTO. New or weaker realizations should be expressed through governed feature
support, support level, disclosure refs, mapping-loss labels, limitations, and
`x-<owner>:<term>` governed extensions where the vocabulary allows them. New
portable concepts must extend the existing typed precondition, effect, failure,
observation, attribution, temporal, outcome, interaction, or controlled
vocabulary surface before they appear in runtime evidence.

Anti-patterns for ACT-603 implementations:

- introducing a second action/precondition/effect/failure taxonomy;
- treating action names, tool labels, ATT&CK/CVE labels, backend commands,
  scheduler order, timestamps, rewards, or raw logs as portable semantics;
- adding participant-specific persistence, exceptions, audit, schema
  publication, or validation paths when the runtime snapshot, diagnostics,
  control-plane store, schemas, and validators already cover the boundary;
- weakening hidden-truth, evidence-only, disclosure, or redaction boundaries in
  order to make observations easier to emit; or
- making backend capability declarations prove that a specific participant
  implementation ran. Use provenance and runtime evidence for that claim.

## ACT-602 - Executable Participant Behavior Model

Executable behavior means the model is machine-checkable through RAES gates.
The executable chain is:

```text
SDL authoring
  -> parser normalization and closed models
  -> semantic validation
  -> compiled participant addresses and runtime refs
  -> runtime carrier emission
  -> contract/schema validation
  -> semantic conformance diagnostics
  -> traceable evidence refs
```

Required executable properties:

- authored symbol keys are stable and cannot be created by variables;
- action, observation, outcome, authority, scope, and behavior-spec refs
  resolve before compilation;
- compiled runtime addresses are canonical and stable enough for traceability;
- runtime records preserve participant address, episode, order, source,
  marking, evidence, and redaction context;
- backend support claims resolve through governed vocabularies and contract
  evidence;
- weaker guarantees are explicit through support level, mapping loss,
  disclosure refs, and diagnostics; and
- conformance cannot rely on schema acceptance alone.

Implementation issue #204 owns executable contract bindings, validators,
fixtures, and conformance evidence for this requirement.

## ACT-606 - First-Class Participant Behavior Specifications

A behavior specification is a named, versioned aggregate:

```text
BehaviorSpecification =
  spec_id
  semantic_version
  lifecycle_state
  participant_ref*
  participant_role_ref*
  action_contract_ref*
  observation_boundary_ref*
  outcome_interpretation_rule_ref*
  authority_scope_ref*
  behavior_mode?
  ai_offensive_behavior_ref*
  defensive_behavior_ref*
  offensive_behavior_ref*
  realization_profile_ref?
  backend_feature_support_ref*
  evidence_contract_ref*
  extension_policy
```

Rules:

- A behavior specification is first-class because it can be named, versioned,
  traced, reviewed, and validated as an artifact.
- It aggregates existing behavior surfaces. It does not replace action
  contracts, observation boundaries, outcome rules, manifests, backend
  capabilities, or runtime evidence.
- `behavior_mode` binds to the controlled vocabulary described in ACT-608.
- `offensive_behavior_ref` values bind to the ACT-609 offensive behavior
  vocabulary for attack-oriented participant tasks, goals, or activities.
- `defensive_behavior_ref` values bind to the ACT-610 defensive behavior
  vocabulary for detection, investigation, response, mitigation, and recovery
  classifications.
- `realization_profile_ref` records how the behavior can be realized without
  exposing private implementation configuration.
- `evidence_contract_ref` names the contracts needed to prove the behavior
  claim in a run or conformance report.
- Extension fields follow the governed `x-<owner>:<term>` discipline.

Implementation issue #206 adds the executable SDL authoring and validation
surface for this aggregate. The Python reference implementation parses
`behavior_specifications`, validates participant, role, action, observation,
outcome, authority, extension, and governed-mode refs, includes the surface in
generated SDL schemas, and compiles stable
`participant.behavior-specification.<name>` runtime records without creating a
parallel participant stack.

## ACT-607 - Authority And Scope Boundaries

Authority and scope are authored semantics. The model distinguishes:

| Facet | Portable meaning | Not equivalent to |
| --- | --- | --- |
| `starting_accounts` | Initial declared access anchors | proof of authority |
| `initial_knowledge` | Participant starting knowledge refs | hidden truth |
| `starting_assertions` | Precondition assertions over declared propositions | setup commands or proof that a probe passed |
| `authority_anchors` | Declared bases for allowed or expected action | bearer tokens, HTTP auth, OS user |
| `operating_scope` | Declared targetable action/observation boundary | backend sandbox, process boundary |
| action preconditions | Contract-level applicability checks | free-form policy prose |
| observation boundaries | Participant-visible information rules | backend logs or world truth |
| backend capability | Realization support claim | scenario permission |
| control-plane auth | API caller authorization | participant authority |

Rules:

- Authority and scope refs resolve through existing named-reference and
  targetable-element validation patterns.
- Action authority belongs in typed preconditions, evidence refs, and governed
  failure classes such as `authority_denied`.
- Observation access belongs in observation boundaries and visibility
  transitions.
- Credentials, tokens, prompts, answer keys, hidden truth, and backend private
  config are never inline authority evidence.
- Runtime denial, backend sandboxing, or control-plane authorization may enforce
  a boundary, but they do not define the authored boundary by themselves.

Implementation issue #207 owns executable authority/scope extensions beyond
the ACT-601 fields already shipped.

### ACT-607 Implementation Preflight Guardrails

Executable ACT-607 work must extend the existing participant-authoring and
behavior surfaces. The canonical incumbents are:

- SDL authored semantics: `agents.*.starting_accounts`,
  `initial_knowledge`, `starting_assertions`, `authority_anchors`,
  `operating_scope`, and behavior-specification `authority_scope_refs`.
- Action and observation semantics: typed participant action preconditions,
  governed failure classes such as `authority_denied`, observation boundaries,
  view rules, and view transitions.
- Parser and model gates: `parse_sdl`, `SDLModel(extra="forbid")`,
  variable-key rejection, `Scenario`, and `InstantiatedScenario`.
- Semantic validation: `SemanticValidator`, `_validate_named_ref`,
  `_validate_operating_scope_ref`, `_verify_agent`,
  `_verify_behavior_specification_authority_refs`, and
  `analyze_participant_behavior`.
- Runtime compilation: stable participant behavior, action-contract,
  observation-boundary, outcome-rule, and behavior-specification addresses from
  `raes_processor.compiler`.
- Published contract authority: closed `ContractModel` payloads,
  `schema_bundle()`, generated schemas, the schema-publication manifest, and
  valid/invalid fixtures.
- Runtime evidence and conformance: participant action precondition/result
  records, behavior history, observation envelopes, shared-state records,
  runtime snapshots, diagnostics, and existing participant-runtime validators.
- Control-plane and persistence boundaries: `ControlPlaneSecurityConfig`,
  read/mutating identity dependencies, request-size guards, idempotency
  fingerprints, audit records, redacted 500 envelopes, and
  `ControlPlaneStore`.

Security and boundary gates remain in force:

- SDL authoring must fail closed on unknown fields, variable-created keys,
  unresolved refs, ambiguous authority anchors, and invalid operating-scope
  targets. Instantiated scenarios must not carry unresolved `${name}` tokens.
- Participant authority is not control-plane authorization. Bearer tokens,
  proxy headers, control-plane identities, OS users, process boundaries, and
  backend sandbox settings may enforce or observe a boundary, but they do not
  define the authored authority/scope boundary.
- Secrets and private material stay out of portable authority evidence:
  credentials, tokens, hidden prompts, answer keys, backend-private
  configuration, raw command output, raw logs, argv/env values, and
  adjudication assets require refs, digests, markings, redaction policy, and
  evidence boundaries.
- Error surfaces must use existing collected `SDLValidationError`,
  `Diagnostic`, `HTTPException`, audit, and redacted internal-error patterns.
  New checks must not create a participant-specific exception hierarchy or
  leak raw secret/config values through diagnostics or fixtures.
- Published exchange shapes must remain closed contracts. A schema-facing
  change updates model source, generated schema bundle, publication-manifest
  ledger, and fixtures together.

The extensibility seam is a parameterized authority/scope reference resolver:
reuse the named-reference index for authority anchors, the spatial/resource
operating-scope index for scope, and add explicit allowed-target/facet
parameters when a future boundary type needs a narrower target set. If runtime
claims need normalized addresses, add that normalization at the compiler
addressing boundary rather than copying raw, possibly ambiguous authoring refs
into a second resolver.

Anti-patterns for ACT-607 implementations:

- introducing a new top-level `participants` or `authority` stack for the same
  authored participant concept;
- treating credential possession, account login, backend capability,
  participant implementation identity, or control-plane auth as authored
  authority;
- duplicating controlled vocabularies, schema publication, validation passes,
  persistence, audit, or exception machinery;
- placing trust anchors or access/control anchors in free-form `metadata`,
  diagnostics, raw logs, or backend-local DTOs; or
- proving conformance only through schema acceptance without semantic negative
  tests, runtime evidence, and redaction/leakage checks.

## ACT-608 - Participant Behavior Modes

Behavior mode declares how decisions are selected or controlled at the
participant decision-surface boundary.

| Requirement wording | Controlled vocabulary term |
| --- | --- |
| autonomous | `autonomous` |
| scripted | `scripted` |
| policy-directed | `policy-directed` |
| replayed | `replayed` |
| supervised | `human-supervised` |
| mixed-control | `mixed-control` |

Rules:

- Mode values resolve through `participant-decision-surface-modes`.
- The current `supervised` requirement wording maps to `human-supervised`.
  A broader supervised concept requires a governed vocabulary update.
- Behavior mode is distinct from participant role, implementation kind,
  backend feature support, control-plane authorization, and interaction class.
- `replayed` mode identifies decision-source replay. It does not by itself
  define trajectory corpus, evidence retention, dataset, or benchmark split
  semantics.
- `policy-directed` mode identifies policy-mediated decisions. It does not
  grant scenario authority or control-plane permission.
- `mixed-control` mode identifies combined control over one participant
  decision surface. It is not multi-participant interaction semantics.

Implementation issue #208 owns executable declaration, selection, validation,
and conformance for behavior modes.

## ACT-609 - Offensive Behavior Vocabularies

Offensive behavior refs declare attack-oriented participant tasks, goals, or
activities as governed vocabulary values on a behavior specification.

The base terms in `participant-offensive-behavior-activities` are a direct
adoption of MITRE ATT&CK Enterprise tactics v19.1. The pinned source artifact is
`contracts/concept-authority/attack-enterprise-tactics-source-v1.json`; it
records the upstream STIX bundle URL, ATT&CK version, retrieval date, SHA-256
digest, MITRE terms URL, and citation URLs. The source artifact was extracted
from the ATT&CK Enterprise matrix order, not hand-curated by RAES.

The base terms in `participant-ai-offensive-behavior-activities` are a separate
direct adoption of MITRE ATLAS tactics release v2026.06 (`collection.version`
`2026.06`, `format-version` `6.0.0`). The pinned source artifact is
`contracts/concept-authority/atlas-tactics-source-v1.json`; it records the
upstream YAML release asset URL, ATLAS content and format versions, retrieval
date, SHA-256 digest, MITRE ATLAS project and license citations, matrix id, and
term lineage fields. The source artifact was extracted from the ATLAS
`ATLAS-matrix` sequence order, not hand-curated by RAES.

Rules:

- External classifications use standalone generic concept binding documents,
  never behavior-specification fields (issue #989).
- Base vocabulary values preserve ATT&CK tactic shortnames, IDs, names, URLs,
  descriptions, and matrix order from the pinned v19.1 source artifact.
- ATLAS base vocabulary values preserve ATLAS tactic shortnames, IDs, names,
  URLs, descriptions, UUIDs, creation/modification dates, ATT&CK cross-reference
  metadata where present, and matrix order from the pinned v2026.06 source
  artifact.
- Optional source catalogs have no governed SDL scopes and closed adopted
  term sets; additional schemes require explicit source context.
- External behavior bindings classify authored behavior intent; they do not
  replace action contracts, observation boundaries, outcome rules, authority
  refs, SDL `goals`, experiment tasks, workflow steps, participant roles,
  behavior modes, backend feature support, or runtime history.
- ATT&CK and ATLAS are distinct adopted authorities. Do not merge ATLAS terms
  into the ATT&CK vocabulary, use one vocabulary to govern native fields, or treat
  overlapping labels as interchangeable without an explicit mapping surface.
- External technique, tool, CVE, or command identifiers require explicit
  mapping or loss metadata on the owning surface; they are not accepted as raw
  portable RAES semantics as native configuration.
- Future ATT&CK or ATLAS release updates must update the matching pinned source
  artifact, catalog terms, fixture, docs, schema metadata as needed, and
  checker validation evidence in one reviewable change.

Pinned ATT&CK v19.1 tactics:

| ATT&CK ID | Shortname | Name |
| --- | --- | --- |
| TA0043 | `reconnaissance` | Reconnaissance |
| TA0042 | `resource-development` | Resource Development |
| TA0001 | `initial-access` | Initial Access |
| TA0002 | `execution` | Execution |
| TA0003 | `persistence` | Persistence |
| TA0004 | `privilege-escalation` | Privilege Escalation |
| TA0005 | `stealth` | Stealth |
| TA0112 | `defense-impairment` | Defense Impairment |
| TA0006 | `credential-access` | Credential Access |
| TA0007 | `discovery` | Discovery |
| TA0008 | `lateral-movement` | Lateral Movement |
| TA0009 | `collection` | Collection |
| TA0011 | `command-and-control` | Command and Control |
| TA0010 | `exfiltration` | Exfiltration |
| TA0040 | `impact` | Impact |

Pinned ATLAS v2026.06 tactics:

| ATLAS ID | Shortname | Name |
| --- | --- | --- |
| AML.TA0002 | `reconnaissance` | Reconnaissance |
| AML.TA0003 | `resource-development` | Resource Development |
| AML.TA0004 | `initial-access` | Initial Access |
| AML.TA0000 | `ai-model-access` | AI Model Access |
| AML.TA0005 | `execution` | Execution |
| AML.TA0006 | `persistence` | Persistence |
| AML.TA0012 | `privilege-escalation` | Privilege Escalation |
| AML.TA0007 | `defense-evasion` | Defense Evasion |
| AML.TA0013 | `credential-access` | Credential Access |
| AML.TA0008 | `discovery` | Discovery |
| AML.TA0015 | `lateral-movement` | Lateral Movement |
| AML.TA0009 | `collection` | Collection |
| AML.TA0001 | `ai-attack-staging` | AI Attack Staging |
| AML.TA0014 | `command-and-control` | Command and Control |
| AML.TA0010 | `exfiltration` | Exfiltration |
| AML.TA0011 | `impact` | Impact |

Issue #209 originally implemented native behavior refs. Issue #989 retires
those fields and compiler carry-through in favor of
[generic concept bindings](../../concept-authority/external-concept-bindings.md).

## ACT-610 - Defensive Behavior Vocabularies

Defensive intent and outcome classifications use generic bindings against
the exact behavior-specification subject. The optional
`participant-defensive-behavior-activities` source catalog is independent of
ATT&CK and ATLAS and governs no SDL field.

The eight base terms are RAES adaptations of the active NIST CSF 2.0 Detect,
Respond, and Recover categories. The pinned source artifact is
`contracts/concept-authority/nist-csf-defensive-categories-source-v1.json`.
It preserves the official category identifiers, titles, function membership,
and category descriptions extracted from the NIST CSF 2.0 Core export. Its
digest covers the canonical category snapshot rather than generated XLSX bytes,
whose ZIP metadata changes between downloads.

| NIST CSF ID | RAES term | Function |
| --- | --- | --- |
| DE.CM | `continuous-monitoring` | Detect |
| DE.AE | `adverse-event-analysis` | Detect |
| RS.MA | `incident-management` | Respond |
| RS.AN | `incident-analysis` | Respond |
| RS.CO | `incident-response-reporting-and-communication` | Respond |
| RS.MI | `incident-mitigation` | Respond |
| RC.RP | `incident-recovery-plan-execution` | Recover |
| RC.CO | `incident-recovery-communication` | Recover |

These terms classify authored behavior; they do not prove that an incident
exists, a detection or investigation is correct, mitigation contains an event,
recovery completed, or an organization conforms to NIST CSF. Those claims use
the existing action, observation, outcome, evidence, runtime, and conformance
surfaces. D3FEND tactics and techniques remain distinct external mappings and
are not aliases for these categories. Governed local extensions use the shared
`x-<owner>:<term>` syntax.

Implementation issue #210 owns the executable SDL field, governed validation,
source-integrity checker, generated schemas, documentation, and compiler
carry-through for defensive behavior refs.

## ACT-611 - Autonomous Service And Agent Behavior Vocabularies

Autonomous-service and autonomous-agent vocabulary relationships are portable
external assertions about an exact behavior specification, not another field
inside that specification. ACT-611 uses
`external-concept-bindings/v1` to bind the canonical
`behavior_specifications.<name>` declaration and artifact digest to pinned
ActivityStreams Activity type IRIs or FIPA communicative-act identifiers.

Rules:

- the native behavior specification retains participant, action, observation,
  outcome, authority/scope, mode, realization, and evidence meaning;
- `behavior_mode: autonomous` remains the governed decision-surface mode and
  is not inferred from an external actor, agent, service, or behavior term;
- both schemes use the same neutral snapshot, exact subject adapter, resolver,
  conformance registration, and offline outcomes;
- relationship, effect, provenance, confidence, approximation/loss,
  limitations, review, and participant eligibility retain the portable
  binding contract semantics;
- external terms remain descriptive and never become executable actions,
  capabilities, authorization, runtime evidence, outcomes, or proof of
  autonomy.

The source and conformance contract is specified in
[`specs/concept-authority/autonomous-behavior-vocabularies.md`](../../concept-authority/autonomous-behavior-vocabularies.md).

## ACT-617 - Mixed-Control Participant Operation

A behavior specification in `mixed-control` mode carries one explicit
`mixed_control` policy for one of its `participant_refs`. The policy is a
closed authored state graph, not a runtime decision history:

```text
MixedControl =
  participant_ref
  policy_revision
  order_strategy
  initial_state_ref
  disposition_rules
  controller_state+
  control_transition+
```

Each controller state binds a controller agent (or `self`), that controller's
declared authority bases, a non-widening subset of the behavior
specification's authority scope, the policy revision, an order-bounded
validity interval, active/revoked authority state, and evidence refs. Each
transition has a portable local identity and preserves a distinct `proposal`,
`approval`, `denial`, `external-direction`, `intervention`, `handoff`,
`override`, or `cancellation` fact with from/to controller states, expected
and resulting state revisions, effective order and validity, evidence, and
proposal identity/revision where required.

Rules:

- `behavior_mode: mixed-control` and `mixed_control` require each other; a
  mode label never implies controller or authority state.
- A controller is `self` or a declared agent. Roles, credentials,
  control-plane identities, implementation identities, and backend processes
  cannot impersonate it.
- Authority bases must be declared by the controller. State scopes must be
  within both the behavior specification's `authority_scope_refs` and the
  controller's `operating_scope`.
- Policy, proposal, and state revisions fail closed. Transition order is an
  explicit unique total effective order; timestamps, mapping order, backend
  scheduling, and last-writer-wins are not semantic order.
- Duplicate identities are idempotent only when semantically equivalent.
  Stale, revoked, late, conflicting, or ambiguously concurrent decisions use
  explicit no-state-change dispositions; ordered concurrent decisions are
  revalidated against the resulting revision.
- Handoff requires a controller change and completion evidence. It never
  changes participant identity or rewrites prior provenance.
- Approval and direction target a proposal identity/revision. They are not
  action admission, execution, delivery, observation, or proof of success.
- Compilation emits typed child controller-state and control-transition
  records beneath `participant.behavior-specification.<name>`, with stable
  addresses, resolved dependencies, deterministic order, and authored
  provenance. It does not create top-level resources or live controller
  history.

Issue #251 provides the authored model, semantic validation, composition,
governed SDL schema publication, valid/invalid fixtures, typed compiler
projection, and negative/state-transition evidence. Issues #252 and #255 own
portable occurrence contracts and runtime mediation/persistence respectively.

## Cross-Clause Invariants

| ID | Invariant | Primary clauses |
| --- | --- | --- |
| PBM-01 | Action names are not portable behavior semantics without action contracts. | ACT-602, ACT-603 |
| PBM-02 | Observation is a participant-visible projection, not hidden truth or archival evidence. | ACT-603, ACT-606 |
| PBM-03 | Authority is authored scenario meaning, not credential possession or control-plane auth. | ACT-607 |
| PBM-04 | Behavior mode resolves through controlled vocabularies, not artifact-local strings. | ACT-608 |
| PBM-05 | Runtime behavior history is evidence of realized behavior, not the authored behavior specification. | ACT-602, ACT-606 |
| PBM-06 | Backend support claims require governed feature terms, support levels, disclosure refs, and evidence contracts. | ACT-602, ACT-608 |
| PBM-07 | Hidden prompts, credentials, answer keys, raw command output, backend-private objects, and adjudication assets stay out of portable behavior artifacts. | ACT-606, ACT-607 |
| PBM-08 | Unknown, opaque, unsupported, not applicable, bounded, lossy, and exact are distinct claims. | ACT-602, ACT-603, ACT-608 |
| PBM-09 | Offensive behavior refs are governed vocabulary classifications, not raw action names, roles, goals, tasks, commands, or external technique labels. | ACT-609 |
| PBM-10 | Defensive behavior refs classify intent or outcome domains and do not prove incident existence, effectiveness, recovery, or CSF conformance. | ACT-610 |
| PBM-11 | Mixed-control authority and ordered control facts are explicit, fail closed, and remain distinct from admission, execution, and observation. | ACT-617 |
| PBM-12 | Autonomous behavior vocabulary terms are external assertions about exact behavior specifications and do not create native or executable behavior meaning. | ACT-611 |

## Child-Issue Mapping

| Issue | UID | Executable ownership |
| --- | --- | --- |
| #204 | ACT-602 | Machine-checkable behavior model gates, fixtures, and conformance evidence. |
| #205 | ACT-603 | Abstract interaction implementation coverage over actions, observations, state, preconditions, effects, failure classes, and joint interactions. |
| #206 | ACT-606 | First-class behavior specification authoring, validation, versioning, traceability, and compiled runtime records. |
| #207 | ACT-607 | Authority/scope boundary authoring, validation, evidence, and failure mapping. |
| #208 | ACT-608 | Behavior-mode declaration, selection, controlled-vocabulary validation, and conformance. |
| #209 | ACT-609 | Offensive behavior vocabulary declaration, validation, and compiler carry-through. |
| #210 | ACT-610 | Defensive behavior vocabulary declaration, validation, source integrity, and compiler carry-through. |
| #211 | ACT-611 | Pinned autonomous behavior schemes, exact behavior-specification assertions, offline resolution, and conformance. |
| #251 | ACT-617 | Authored controller/authority state, ordered fail-closed control transitions, composition, and typed compiler projection. |

## Verification Expectations

Any executable issue that claims this model must provide:

- parser/model negative tests for unknown fields and variable-created keys;
- semantic validation tests for unresolved action, observation, outcome,
  authority, scope, and behavior-spec refs;
- generated schema and publication-manifest checks when a contract is added or
  changed;
- valid and invalid fixtures for every new portable contract;
- runtime or conformance tests that prove behavior-history, observation,
  authority, mode, evidence, and redaction invariants; and
- Ground Control IMPLEMENTS/TESTS or DOCUMENTS traceability links appropriate
  to the artifact.

Issue #77 satisfies the design requirement by publishing ADR-067 and this
formal spec. Child issues provide executable SDL syntax, schema, fixture,
runtime emission, and conformance implementation for #204 through #208.
