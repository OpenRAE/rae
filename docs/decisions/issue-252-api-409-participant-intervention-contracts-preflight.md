# Issue #252 — API-409 Participant Intervention Contract Preflight

Date: 2026-07-24

Issue: #252.

Requirement: API-409.

This note records architecture boundaries and implementation guardrails for
portable external proposal and mixed-control occurrence contracts. It is
guidance only. It does not publish contract models or schemas, add runtime
mediation or persistence, change backend capabilities, or claim delivery,
execution, observation, or enforcement.

## Binding Authorities

- Accepted ADR-085 and
  `specs/formal/participant-semantics/information-flow-control.md` define the
  common participant, controller, authority, policy, order, disposition,
  marking, evidence, provenance, and limitation coordinates. They require
  proposal, approval or denial, direction, intervention, handoff, override,
  cancellation, admission, execution, delivery, and observation to remain
  distinct facts.
- ACT-617 is delivered at the authored and compiled layers through
  `ParticipantBehaviorSpecification.mixed_control`,
  `MixedControlParticipantOperation`, `MixedControlTransition`, and
  `ParticipantBehaviorSpecificationRuntime.control_transitions`. These objects
  declare permitted policy state and transitions. They are not occurrence,
  wire, admission, or execution records.
- ADR-054 and ADR-060 define the participant-runtime carrier discipline.
  `ParticipantRuntimeBaseEnvelopeModel` already owns event identity, schema
  identity, participant/episode scope, three timestamps, ordering,
  actor/producer/source identity, evidence/provenance, markings, redaction,
  and authorization scope.
- ADR-009, ADR-019, and ADR-061 make the published schemas under
  `contracts/schemas/` the hand-governed normative authority and the Python
  `schema_bundle()` output compatibility evidence. Every published change must
  have publication-ledger accounting and reference-generation parity.
- `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, and
  `tools/verify_all.py` own the workflow. No issue-local generator, registry,
  validation command, or test harness is needed.

These authorities already settle the architecture. API-409 does not need a new
ADR unless implementation discovers a conflict that cannot be resolved by
composition.

## Architecture Decisions And Boundaries

### Publish occurrence contracts, not another input envelope

API-409 belongs to the existing `participant-runtime` contract family. Every
top-level API-409 occurrence carrier must reuse
`ParticipantRuntimeBaseEnvelopeModel` exactly once. Do not add API-409 fields
to that base: doing so would change every existing API-406 participant-runtime
schema. Controller, authority, policy, target, and disposition coordinates
belong on the API-409 records or a shared component used only by this family.
The new carriers must narrow inherited optionality where API-409 requires a
fact: participant and episode scope, evidence/provenance, marking posture, and
the kind-specific identity and target cannot remain ambiguous. Each carrier
must also bind `schema_name`, `schema_version`, `event_type`, and
`extension_policy` to its own closed constants so a valid envelope cannot
claim the wrong contract or event kind.

The normative shape must preserve kind-specific requiredness. A proposal,
approval, denial, external direction, intervention, handoff, override, and
cancellation may share closed components, but they must remain distinct typed
facts. Do not publish a nullable `ParticipantExternalInput`, generic `message`,
or `details` bag whose meaning depends on a string. If one published schema
groups variants, it must use a closed discriminated union whose branches make
invalid cross-kind field combinations structurally unrepresentable.

The `MixedControlTransitionKind` terms are the existing authority for the
eight control-fact kinds. Reuse that enum or one centralized, tested mapping
from it. Do not copy equivalent enums into `aces_contracts`, `aces_runtime`,
backend protocols, and conformance. Occurrence dispositions need their own
closed vocabulary because a realized decision result is not the authored
`MixedControlDispositionRules` policy and is not
`ParticipantAdmissionDisposition`. Define that vocabulary once and keep
decision value, occurrence disposition, and later action admission separate.

### Bind declarations and occurrences without sharing identity

Each occurrence needs a fresh stable occurrence identity and a reference to the
applicable compiled ACT-617 declaration or policy coordinate. The authored
transition id/address says what is permitted; the occurrence id says what was
proposed or decided at one participant, episode, controller state, policy
revision, and order point. Never reuse a transition declaration id as an
occurrence id or infer an occurrence from the presence of a compiled
transition.

The common occurrence coordinates, in addition to the base envelope, are:

- controller subject, controller-state reference, authority-basis references,
  and controlled scope references;
- behavior-specification or mixed-control-policy reference and exact policy
  revision;
- declaration reference, expected controller-state revision, and applicable
  validity/effective-order coordinates;
- a closed occurrence disposition plus bounded reason-code/reference and
  limitation references, while reusing the base-envelope evidence, provenance,
  and marking fields rather than redefining them; and
- typed target references appropriate to the fact kind.

Use references, digests, controlled codes, and markings. Do not carry a policy
body, credential, prompt, raw rejected input, hidden payload, backend object,
free-form reason text, or unbounded `metadata`, `constraints`, `details`, or
`extensions` map.

### Preserve target and lifecycle distinctions

The kind-specific relations are:

- a proposal binds a proposal identity/revision, action-contract reference,
  decision-surface or proposal-binding reference where applicable, and a
  payload reference or digest; it is neither selected, admitted, nor executed;
- an approval or denial binds exactly one proposal identity and revision plus
  the controller state/revision at which the decision was made;
- an external direction binds a proposal or action/control reference and its
  authority scope, but does not bypass proposal validation or action admission;
- an intervention binds the affected control/action occurrence and the
  declared intervention transition;
- a handoff binds the prior and resulting controller-state references,
  expected/resulting revisions, and completion-evidence reference without
  changing participant identity;
- an override binds the occurrence or control revision it supersedes and
  records the resulting conflict or partial limitation without rewriting the
  target; and
- a cancellation binds the proposal, decision, admitted action, or attempt it
  addresses and records what was still cancellable. It never claims that
  already completed work did not occur.

Admission remains the existing SEM-211/
`ParticipantActionAdmissionRequest` boundary. Attempts and results remain
`ParticipantLifecycleEventModel`, `ParticipantBehaviorHistoryEventModel`, and
`ParticipantActionResultModel` facts. Delivery and observation remain the
participant observation/exposure carriers. API-409 records link to those facts
by stable reference when they exist; they do not embed or recreate their state
machines.

Transformed proposals always receive a new proposal identity and revision,
retain source/transformation/provenance/marking/loss references, and undergo
fresh shape, semantic, and admission validation. A transformation cannot carry
forward approval, denial, admission, execution, or idempotency state from the
source proposal.

### Validate at the owning layer

Closed shape, scalar constraints, branch-specific requiredness, uniqueness, and
single-record cross-field rules belong in `ContractModel` descendants and
schema-expressible `if`/`then`, `oneOf`, or discriminated-union constraints.

Relations across proposal, decision, compiled ACT-617 declaration, controller
state, participant/episode, and later lifecycle records belong in one
contract-level semantic validator following the existing
`validate_participant_decision_surface_context()` and runtime-fact
cross-reference patterns. Publish non-schema-expressible obligations through
the existing `x-aces-invariants` /
`aces-semantic-invariants-v1` mechanism. Do not duplicate the same reference
join in model validators, runtime route handlers, persistence adapters, and
conformance.

The relational validator must fail closed on at least unknown or mismatched
participant/episode refs, unknown declaration refs, controller or authority
confusion, policy/revision mismatch, stale proposal or state revision,
out-of-interval order, incompatible targets, identity reuse with a different
semantic fingerprint, and a transformed proposal that reuses source identity
or disposition.

### Keep API-423 and RUN-310 boundaries open

API-423 owns the later common crossing-policy decision, transformation,
disclosure, and realization relation. API-409 records carry the policy and
evidence coordinates necessary for that relation, but must not pre-implement a
universal crossing record or policy engine.

RUN-310 owns secure live mediation, append-only occurrence history, replay,
idempotency enforcement, conflict resolution, persistence, and controller
state changes. API-409 defines portable facts and semantic validation only. A
published schema is not evidence that the reference runtime or any backend
emits or enforces it.

## Canonical Incumbents To Reuse

| Concern | Canonical incumbent and required use |
| --- | --- |
| Contract closure and primitives | `ContractModel(extra="forbid")`, `NonEmptyString`, `PrefixedDigestString`, `Rfc3339DateTimeString`, and existing participant runtime literals. Extend these; do not create a DTO base or primitive package. |
| Event envelope | `ParticipantRuntimeBaseEnvelopeModel` and its event/source/raw-integrity submodels. Reuse it unchanged and exactly once per carrier. |
| Authored mixed-control authority | `MixedControlTransitionKind`, `MixedControlParticipantOperation`, controller states/transitions, ACT-617 semantic validation, and compiled state/transition addresses. Reference or centrally map these terms; do not serialize authored objects as occurrences. |
| Proposal and admission chain | `ParticipantDecisionSurfaceSelectionModel`, `bind_participant_decision_surface_selection()`, `ParticipantActionAdmissionRequest`, and `participant_action_admission_request_violations()`. Proposal/approval precedes and remains distinct from this admission path. |
| Lifecycle and observation | `ParticipantLifecycleEventModel`, `ParticipantBehaviorHistoryEventModel`, `ParticipantActionResultModel`, `ParticipantObservationEnvelopeModel`, and SEM-226 exposure bindings/realizations. Link by ref rather than copying fields. |
| Ordering | `ParticipantRuntimeOrderingBasis`, base-envelope logical/predecessor refs, and ACT-617 `total-effective-order`/revision rules. Do not invent timestamp ordering or infer order from array position. |
| Marking and safe value references | Base-envelope marking/redaction fields, `PrefixedDigestString`, and runtime-fact reference/secret-reference discipline. Payloads and policy material remain out of line. |
| Semantic invariants | Pydantic model validators, explicit cross-contract `validate_*` helpers, `_add_aces_invariant()`, and `aces-semantic-invariants-v1`. Use one join validator for cross-record rules. |
| Publication | `contracts/schemas/participant-runtime/`, `contracts/fixtures/participant-runtime/`, `contracts/schema-publication/entries/`, `schema_bundle()`, and explicit routing in `tools/generate_contract_schemas.py`. Published schemas are authority; generated parity is the compatibility proof. |
| Compatibility | ADR-061 and `tools/check_schema_publication.py --base-rev`. New contract ids are classified explicitly; existing base or carrier schemas are not tightened incidentally. |
| Capability declarations | `BACKEND_SUPPORTED_CONTRACT_IDS`, `PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS`, API-407 feature support, and capability evidence mappings. Register claimability only for the correct actor and evidence owner; schema publication alone must not create a support claim. |
| Diagnostics and errors | `Diagnostic`, `Severity`, `OperationReceipt`, `OperationStatus`, and the redacted control-plane 500 envelope. Validation messages remain value-safe; add no exception hierarchy. |
| Persistence and audit | `RuntimeSnapshot`, `ControlPlaneStore`, `InMemoryControlPlaneStore`, `LocalControlPlaneStore`, and `AuditEvent`. These are downstream RUN-310 incumbents; API-409 adds no store or logger. |
| Evidence tests | `test_act_617_mixed_control.py`, participant backend-contract schema/model fixture tests, decision-surface binding tests, schema publication/parity checks, and participant invariant tests. Extend these patterns rather than adding an API-409 runner. |
| Lineage | The participant section of `docs/explain/sdl/lineage.md` and ADR-080 ledger/source-audit rules. Record API-409 delivery and explicit nonclaims there; change the ledger/source audit only if normative derivation or compatibility claims change. |
| Workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, the `nox` verify graph, repo policy, requirement governance, JSON artifact, authority, schema publication, generated-schema parity, semantic coverage, and documentation checks. |

## Cross-Cutting Layers And Security Posture

The contract-only design passes these layers:

1. **Published shape and model validation.** Hand-governed closed schemas,
   matching `ContractModel` descendants, discriminated kind-specific shapes,
   and the shared semantic validator reject unknown keys, missing security
   coordinates, invalid references, stale revisions, and payload smuggling.
   Valid and invalid fixtures must pass both Draft 2020-12 schema validation
   and Python model validation.
2. **Secret and hidden-content boundary.** Portable records contain only typed
   ids, refs, digests, controlled dispositions/reasons, markings,
   provenance/evidence refs, and limitation refs. There is no inline action
   payload, policy body, credential/token/key, hidden state, prompt/answer,
   environment dump, backend representation, or raw rejected content.
3. **Diagnostic and serialization boundary.** Validators use value-independent
   messages and stable field paths/codes. Public code must not stringify a
   Pydantic `ValidationError` or rejected record into a response, audit detail,
   or log because framework errors can include rejected input. Expected
   failures map to bounded `Diagnostic`/disposition data; unexpected HTTP
   failures retain `{"detail":"internal server error"}`.
4. **Publication and compatibility boundary.** Each published schema has an
   explicit participant-runtime route, valid/invalid fixtures, a
   schema-publication entry with `last_change` and current content hash, and
   identical `schema_bundle()` output. The implementation must run the
   base-revision compatibility classifier and must not mutate existing
   participant carriers through the shared base.
5. **Concept and claim boundary.** Control kinds map to ACT-617 once;
   occurrence dispositions are governed once; admission, lifecycle,
   observation, capability, and relation terms keep their existing
   authorities. Schema validity is reported only as structural evidence, not
   runtime enforcement, backend support, or an information-flow proof.

API-409 itself adds no HTTP route, authentication mechanism, environment
binding, configuration object, secret loader, subprocess, daemon, socket,
filesystem store, or process-argument surface. Those layers are therefore not
implementation surfaces for this issue. A later adapter must enter through
`create_control_plane_app()`, `ControlPlaneSecurityConfig.strict_defaults()`,
verified bearer/proxy identity, role and target binding, request-size guards,
canonical request fingerprints, idempotency keys, and `AuditEvent`. It must
then separately bind the authenticated principal to the API-409 actor,
controller, participant, and authority basis. An operator role cannot
impersonate a controller.

Likewise, no API-409 value belongs in environment variables, process argv,
stdout, stderr, or a shell command. A future adapter must use injected
providers, fixed argv, controlled working directories, bounded timeouts, and
no `shell=True`. Future persistence belongs in first-class append-only
`RuntimeSnapshot` fields and `ControlPlaneStore`, not snapshot `metadata`,
generic history `details`, a gateway-local database, or raw audit bodies.

## Extensibility Seam

The stable seam is a kind-specific occurrence with a shared unchanged runtime
envelope and explicit declaration, participant/episode, controller/authority,
policy revision, order, target, disposition, evidence/provenance, marking, and
limitation references. The order parameter remains
`ParticipantRuntimeOrderingBasis` plus logical and predecessor references; the
first implementation may validate total effective order without closing the
partial-order seam.

The next reasonable changes must compose by reference: API-423 can attach a
crossing decision/transformation/realization record to an API-409 occurrence,
and RUN-310 can persist an append-only realization, without changing proposal
identity or adding execution fields to API-409. A future non-participant
controller is a closed subject-binding variant, not an arbitrary controller
string or metadata entry.

## Gotchas And Anti-Patterns

Avoid:

- one generic external-input/message envelope or an optional-field union that
  permits proposal, decision, handoff, cancellation, and execution fields to
  coexist;
- serializing authored ACT-617 transitions as runtime occurrences, sharing
  declaration and occurrence identity, or treating compiled presence as
  evidence that an event happened;
- copying control-kind, order, admission, lifecycle, capability, or
  disposition vocabularies into multiple packages;
- treating actor, controller, authenticated caller, operator role,
  participant implementation, backend process, and producer as one identity;
- treating approval or direction as admission, admission as execution,
  delivery as observation, or audit retention as participant disclosure;
- changing a proposal in place, carrying approval/admission across a
  transformation, or deduplicating distinct occurrences by payload value;
- last-writer-wins, wall-clock ordering, list order, silent conflict
  resolution, retroactive cancellation, or history mutation;
- raw payloads, policy bodies, credentials, hidden state, rejected input,
  backend objects, free-form reasons, or exception text in portable records,
  diagnostics, logs, errors, audit details, fixtures, or provenance;
- modifying `ParticipantRuntimeBaseEnvelopeModel` to make API-409 convenient;
- adding contract ids to backend or participant support declarations without
  the correct capability/evidence ownership, or interpreting schema presence
  as support;
- a second schema registry, publication ledger, validator stack, exception
  hierarchy, persistence store, audit channel, logger, or workflow script;
- adding implementation logic under `implementations/python/src/aces/`; and
- updating the lineage ledger/source audit merely because delivery status
  changes.

## Non-Goals And Implementation Boundaries

- No participant transport, HTTP endpoint, UI, gateway, authentication stack,
  provider integration, or human-control service.
- No runtime mediation, controller-state mutation, action admission,
  execution, delivery, observation, persistence, replay engine, backend
  realization, or capability claim.
- No generic participant crossing/policy record; API-423 owns that later
  relation.
- No raw action payload, policy body, secret, hidden state, rejected input, or
  backend-private detail in the portable contract or its error surface.
- No replacement of ACT-617 authored authority, SEM-211 admission, ADR-054
  lifecycle/observation carriers, SEM-226 exposure, existing evidence and
  provenance, or control-plane security.
- No claim that schema/model/fixture success proves runtime enforcement,
  backend conformance, noninterference, trace equivalence, simulation,
  refinement, or bisimulation.
