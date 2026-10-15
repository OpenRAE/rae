# Issue 797 — DSL-142 Participant-Directed Inject Binding And Delivery Preflight

Date: 2026-07-25

Issue: #797. Requirement: DSL-142.

This note fixes the repository-wide boundary for authored and compiled
participant-directed inject delivery. It does not implement SDL syntax,
schemas, validation, compilation, runtime delivery, migration, or tests, and
it is not an implementation plan.

No new ADR is needed. Accepted ADR-085 already decides that an
environment-directed inject remains an orchestration event, while a
participant-directed inject preserves its DSL-111 orchestration identity and
is separately governed as disclosure/observation at delivery. SEM-230 owns the
revisioned information-flow coordinates and distinct-operation semantics;
SEM-226 owns deny-first participant exposure and realized-delivery agreement.
DSL-142 adds the missing authored and compiled relation without reopening those
decisions.

## Binding Architecture Decisions

### Keep the inject and participant delivery as two related identities

`Inject`, `Event`, `Script`, `Story`, `Node.injects`, `InjectRuntime`, and the
existing orchestration `InjectBinding` remain DSL-111 orchestration authority.
Their canonical addresses and plan behavior do not change meaning.

Participant delivery is an explicit keyed relation under the existing
`ParticipantBehaviorSpecification` aggregate, following the incumbent
participant-local `tool_affordances` pattern. It is not:

- a field that changes `Inject` into a participant message;
- another top-level inject/template family;
- a new variant of `Node.injects` or orchestration `InjectBinding`;
- a generic participant I/O, message, gateway, transport, or receipt object; or
- an orchestration plan operation that implies runtime delivery.

Each relation binds exactly one original inject identity to exactly one
participant addressee. Delivering one inject to multiple participants requires
distinct binding identities so audience, policy, order, evidence, and
intervention joins cannot be merged or inferred from list position. The
binding may name a typed source/result item ref, but it must not copy the
inject body, environment effects, hidden content, policy body, or backend
payload into the participant declaration.

The compiled form follows the existing tool-affordance precedent: it receives
a stable `participant.behavior-specification.<spec>...` address and retains the
original `orchestration.inject.<inject>` address as a dependency. It belongs
in typed participant compiler metadata in `RuntimeModel`; it does not enter
`planner.resources`, `OrchestrationPlan`, or backend operation payloads in this
issue. Compiled presence proves declared intent only, never delivery,
observation, action, or backend support.

### Make delivery policy closed, reference-led, and deny-first

The authored binding owns a closed delivery-policy record, not a free-form
policy bag and not an embedded SEM-230 policy language. Its coordinates must be
explicit and compile to stable refs/addresses:

- participant addressee and owning behavior specification;
- original inject ref and an explicit orchestration occurrence anchor;
- source/result item identity by typed ref, never an inline arbitrary payload;
- observation-boundary ref owned by the behavior specification and participant;
- projection/disclosure policy identity and revision/basis refs;
- order basis and shared-time/temporal-constraint refs where time applies;
- closed failure/disposition meaning, with no silent fallback;
- required delivery-evidence requirement refs; and
- an optional mixed-control transition ref only when the inject directs action
  or changes control.

Policy identity, policy revision, exposure-policy identity, visibility basis,
and observation boundary are different coordinates. A non-empty policy string
is not authorization. The binding must be internally closed and semantically
consistent at SDL admission; later trusted SEM-226 resolvers still own the
effective policy, item authorization, apparatus selection, and realized
occurrence checks at an actual delivery order.

Required evidence reuses `evidence_requirements`. A non-empty set of delivery
evidence requirement refs states what a conforming delivery must produce; it
is not a receipt or proof that delivery occurred. Do not add a DSL-142 receipt
schema. SEM-226's `ParticipantExposureOccurrenceRecord` and
`ParticipantDecisionSurfaceExposureRealizationModel` remain the adjacent
realized-delivery incumbents, while API-423/RUN-319 own any future common
crossing record and append-only runtime workflow.

### Preserve narrative order and shared time rather than inventing delivery time

The DSL-111 narrative chain remains authoritative:

```text
inject -> event -> script -> story
```

A participant binding must name an orchestration occurrence anchor that
actually contains the referenced inject. If reuse makes an event insufficient
to identify the intended occurrence, the anchor must carry the existing
script/story context rather than selecting the first map/list match. Compiler
dependencies preserve both the original inject and the selected orchestration
anchor. Declaration order, map iteration order, wall-clock receipt time, and
backend callback order are never semantic ordering.

Delivery constraints reuse `temporal_constraints`, compiled shared-time
addresses, and the SEM-230 order coordinate. Do not add `deliver_at`, another
duration parser, a second clock, or timestamp-only ordering. A deadline/window
constrains delivery relative to its declared clock and occurrence; it does not
rewrite the event's schedule or prove that delivery happened. Scheduling does
not imply delivery, delivery does not imply observation, and observation does
not imply action.

### Bind direction and intervention without collapsing them

Most participant-directed injects are disclosure/observation only. An inject
that directs an action or changes control must additionally name one existing
compiled ACT-617 mixed-control transition in the same behavior specification.
Only compatible `external-direction` or `intervention` meaning is admissible.
The participant, controller/authority scope, policy revision, validity/order
interval, and evidence basis must agree across the delivery binding and the
mixed-control declaration.

The binding does not create, mutate, or realize a control occurrence. It must
not treat direction as SEM-211 admission, intervention as execution, or
delivery as an action attempt. API-409 remains the portable occurrence
authority, and runtime control remains out of scope.

### Preserve absence as environment-only behavior

An inject with no participant-delivery binding remains environment-only and
must compile exactly through the existing orchestration path. No participant
binding, observation entry, evidence claim, or control transition may be
inferred from:

- `Inject.from_entity` or `to_entities`;
- `Inject.environment`, description, or source;
- an event, script, story, or node inject reference;
- matching entity/participant names or roles;
- an observation boundary that happens to name the inject;
- an implementation manifest capability; or
- legacy document shape.

An explicitly bound inject may retain independent environment effects. Only
the named, governed participant item may cross the participant boundary; the
rest of the orchestration inject stays hidden unless ordinary SEM-210/SEM-226
projection independently authorizes it.

## Canonical Incumbents To Reuse

- **SDL ingress and phases:** `load_sdl_yaml()`, source-profile budgets,
  duplicate/canonical-key-safe YAML loading, `parse_sdl()`/`parse_sdl_file()`,
  `SDLModel(extra="forbid")`, `ScenarioContent`, `Scenario`,
  `ExpandedScenario`, `InstantiatedScenario`, `instantiate_scenario()`, and
  `admit_instantiated_scenario()`.
- **Participant authoring:** `ParticipantBehaviorSpecification`, its
  participant/role, authority-scope, observation-boundary, evidence-contract,
  tool-affordance, and mixed-control members; `Agent`; `ParticipantObservationBoundary`;
  and the existing participant behavior semantic analysis. Do not add a second
  participant aggregate or reference resolver.
- **Orchestration identity:** `Inject`, `Event`, `Script`, `Story`,
  `Node.injects`, `_inject_address()`, `InjectRuntime`, orchestration
  `InjectBinding`, `_compile_events()`, and the existing plan dependency graph.
  Participant delivery references these identities and never replaces them.
- **Policy and exposure:** ADR-085; SEM-230 `Effective(rho,o)`/`MayCross`;
  `participant_observation_effective_relation()`;
  `ParticipantExposurePolicyRevision`;
  `ParticipantExposureAuthorizationRecord`;
  `ParticipantExposureOccurrenceRecord`;
  `project_participant_exposure_bindings()`; and
  `ParticipantDecisionSurfaceExposureBindingModel`. Do not copy their
  operation, policy, marking, or realization semantics into SDL-142.
- **Time and order:** `TemporalConstraint`, the `time_domains`/`clocks`/
  `time_progression_policies` catalogs, `compile_time_model()`, and
  `CompiledTimeModel`. The new binding is another ordinary temporal subject;
  it does not own a time model.
- **Intervention:** `MixedControlParticipantOperation`, compiled controller
  states/transitions, ACT-617 validation, API-409
  `ParticipantControlDeclarationModel`, and contextual occurrence validation.
  Compose by stable declaration address.
- **Evidence:** SDL `EvidenceRequirement`, existing evidence-reference
  validation, participant observation/history envelopes, experiment evidence
  records, provenance refs, and SEM-226 realized-exposure agreement. Required
  evidence and produced evidence remain different facts.
- **Composition and catalogs:** `_mapping_scopes`, `_module_symbols`,
  `_language_metadata`, `composition._namespace_payload()`,
  `build_declaration_index()`, the compiler alias/address helpers,
  `specs/sdl/sections.md`, `specs/sdl/references.md`, and
  `tools/check_sdl_catalog_parity.py`. Every nested binding ref must be
  namespace-rewritten explicitly; there is no DSL-142-only registry.
- **Compiler:** participant behavior compilation, canonical participant and
  orchestration addresses, `ResolvedResource` dependency conventions,
  `RuntimeModel` cross-map address uniqueness, and value-safe `Diagnostic`.
  Do not add a participant plan domain or serialize the original inject spec
  into a participant binding.
- **Schemas and compatibility:** the four scenario-containing published
  contracts (`sdl-authoring-input-v1`, `instantiated-scenario-v1`,
  `instantiated-scenario-snapshot-v1`, and
  `scenario-satisfiability-evidence-v1`), `schema_bundle()`,
  `contracts/schema-publication-manifest.json`, per-contract publication
  entries, `tools/check_generated_schemas.py`, and ADR-009/061.
- **Errors and observability:** source-anchored `SDLParseDiagnostic`/
  `SDLParseError`, collect-all `SDLValidationError`, bounded
  `SDLInstantiationError`, compiler `Diagnostic`/`Severity`, and existing
  operation/API error envelopes. Add no exception hierarchy or logger.
- **Workflow:** `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`,
  `tools/check_semantic_coverage.py`, schema/publication/catalog checks, and
  `tools/verify_all.py`.

## Cross-Cutting Layers And Security Posture

1. **Source/parser gate.** The addition remains inert `sdl-yaml/v1` data under
   the existing UTF-8, input-byte, scalar, alias, expanded-node, depth,
   duplicate-key, non-string-key, tag, directive, and JSON-domain checks.
   Parsing performs no policy lookup, delivery, filesystem access, network
   request, process launch, or backend call.
2. **Closed shape gate.** Focused `SDLModel` records reject unknown members,
   empty/duplicate refs, illegal combinations, and open payload/config maps.
   Closed operation, order, and failure/disposition terms use the existing
   enum/variable normalization pattern. The model carries refs and safe
   metadata only, never policy bodies, raw hidden content, credentials, or
   backend-native delivery objects.
3. **Reference and semantic gate.** Existing participant semantic analysis and
   `SemanticValidator` resolve addressee, inject, orchestration anchor,
   observation boundary, evidence requirement, temporal constraint, and
   optional mixed-control transition. They reject widening beyond the parent
   behavior specification/participant, anchor-inject disagreement, stale
   policy/control revisions, incompatible transition kinds, missing required
   evidence, and ambiguous refs. Model validators own local shape only; graph
   agreement is not duplicated there or deferred to the compiler.
4. **Composition gate.** Module expansion rewrites every ref through canonical
   section maps, including nested binding ids and refs. Export/private-symbol,
   collision, budget, digest, lock, and trust rules stay unchanged. No raw
   string concatenation or delimiter parsing substitutes for the existing
   qualified-name machinery.
5. **Instantiation gate.** Variables may occupy explicitly permitted scalar/ref
   fields but never binding keys. Substitution leaves no `${...}` token, then
   closed structural and complete semantic admission run again. Invalid values
   that were deferred while unresolved fail before compilation, and portable
   provenance contains no secret policy or payload value.
6. **Published-schema/artifact gate.** All four scenario-containing schemas
   remain closed and move together with generated-bundle parity, publication
   hashes/`last_change`, compatibility classification, and independent JSON
   Schema fixtures. Relational invariants that JSON Schema cannot express stay
   in semantic admission and the existing `x-aces-invariants` mechanism where
   a portable contract requires disclosure.
7. **Compiler gate.** The compiler consumes only an admitted
   `InstantiatedScenario`, emits typed participant metadata with canonical
   addresses, and verifies every resolved dependency again with bounded,
   value-safe diagnostics. The participant record retains the orchestration
   inject address and selected anchor addresses but not the inject's hidden
   spec. A compiler error must not echo rejected content or policy data.
8. **Planner/backend gate.** DSL-142 adds no planned participant delivery
   resource, orchestration capability boolean, backend method, or automatic
   downgrade. Existing environment inject planning is unchanged. Later runtime
   work must advertise governed feature support through the existing
   API-407/capability-conformance seam and reject unsupported required
   semantics rather than interpreting compiler presence as support.
9. **Authentication and policy gate.** This issue adds no HTTP or MCP delivery
   route. A later route must enter through `create_control_plane_app()`,
   `ControlPlaneSecurityConfig.strict_defaults()`, verified bearer/proxy
   identity, target-bound roles, request-size and idempotency/fingerprint
   guards, and `AuditEvent`, then separately bind caller, controller,
   participant, audience, and effective policy. Operator/orchestrator authority
   is not participant visibility or declassification authority.
10. **Secret, OS, and process gate.** No DSL-142 value belongs in an environment
    variable, secret loader, command line, process argv, filename, stdout,
    stderr, shell string, socket, listener, or session. Reuse existing
    `redacted`/`operator_secret` omission rules on any referenced SDL source.
    The binding itself carries only safe refs/digests/classifications. A later
    adapter must use injected providers, fixed invocation shapes, bounded
    timeouts, controlled working directories, and no `shell=True`.
11. **Error-envelope and leakage gate.** Expected failures use collected SDL
    errors or bounded `Diagnostic` codes/field paths without rejected values.
    Future public 4xx errors must not reveal whether a hidden inject/item or
    another participant's binding exists. Unexpected API failures retain
    `{"detail":"internal server error"}`; Pydantic exception text, tracebacks,
    inject bodies, policies, evidence payloads, and authorization records stay
    out of responses, logs, and audit details.
12. **Persistence and observability gate.** DSL-142 adds no store, history,
    receipt, cache, audit channel, or runtime snapshot field. Future decisions
    and delivery occurrences are append-only and use `RuntimeSnapshot`,
    participant observation/behavior/control histories, `ControlPlaneStore`,
    and evidence/provenance incumbents. Snapshot `metadata`, history `details`,
    logs, and audit details are not policy or delivery-evidence stores.

## Extensibility Seam

The stable seam is one keyed participant-delivery relation parameterized by:

- original inject and explicit orchestration occurrence anchor;
- participant, behavior specification, episode/selection basis, and audience;
- source/result item ref, observation boundary, and visibility basis;
- projection/disclosure policy identity, immutable revision/version/digest
  refs, and operation basis;
- order model/order point plus optional shared-time constraint addresses;
- required evidence, provenance/marking/loss refs, and failure disposition;
  and
- optional mixed-control transition address.

The compiled relation keeps these as typed fields and stable addresses, with
trusted resolver dependencies supplying effective policy and realized
occurrence facts later. This seam admits the next reasonable variants—multiple
occurrences of one inject, role/episode selection, per-phase policy revision,
streaming or transformed content, another participant audience, explicit
weakening, and API-423/RUN-319 realization—without changing `Inject`, adding a
second event family, or re-editing an environment-only artifact.

## Gotchas And Anti-Patterns

Avoid:

- adding participant fields to `Inject`, changing `Node.injects`, or renaming
  the existing orchestration `InjectBinding`;
- compiling a duplicate participant inject/payload instead of retaining the
  original `orchestration.inject.*` address;
- placing participant delivery into `OrchestrationPlan` and thereby implying
  runtime realization;
- inferring delivery from entity addressees, node roles, event/script
  membership, observation-boundary membership, or manifest support;
- copying an inject's environment list, source, description, raw content,
  hidden answer, secret fixture, policy body, or backend object into the
  participant binding, diagnostic, log, fixture, or error;
- using a generic `message`, `ParticipantIOEvent`, gateway DTO, policy bag,
  optional-field union, or duplicate delivery/observation history;
- treating scheduling as delivery, delivery as observation, observation as
  action, direction as admission, admission as execution, or audit retention
  as disclosure;
- using list/map position, wall time, transport receipt order, or
  last-writer-wins as semantic order;
- applying current/future authorization to a past delivery order, mutating a
  prior occurrence after revocation, or treating revocation as erasure;
- treating `ParticipantExposurePolicyModel.constraints`, a policy ref, schema
  validity, compiler output, capability declaration, HTTP success, log line,
  or audit event as delivery authorization/evidence;
- adding a second schema registry, validator stack, exception hierarchy,
  evidence model, persistence store, logger, workflow script, or capability
  boolean;
- hand-editing generated schemas, updating only one scenario-containing
  schema, omitting publication accounting, or adding logic under the
  compatibility-only `implementations/python/src/aces/`; and
- updating the lineage ledger/source audit merely because delivery status
  changes. Those change only for a new normative derivation or compatibility
  claim.

## Non-Goals And Implementation Boundary

- No runtime delivery, participant UI, prompt format, email/chat gateway,
  transport, external-agent API, policy engine, credential broker, or backend
  adapter.
- No API-423 common crossing contract, RUN-319 enforcement/persistence,
  API-407 capability implementation, operation receipt, or new portable
  participant message schema.
- No conversion of environment injects, implicit participant visibility, or
  automatic migration that strengthens legacy meaning. Legacy scenarios
  without explicit bindings remain environment-only and behaviorally
  unchanged.
- No replacement of DSL-111 orchestration identity/order, SEM-210 visibility,
  SEM-226 exposure, ACT-617/API-409 control, shared-time semantics, or existing
  evidence/provenance contracts.
- No claim that authored/compiled presence proves delivery, observation,
  action, backend realization, noninterference, trace equivalence, refinement,
  simulation, or bisimulation.
- No lineage-ledger/source-audit update during preflight. The implementation
  must update the participant lineage prose with actual delivery evidence and
  explicit nonclaims; it changes normative lineage records only if its adopted
  derivation or compatibility claims actually change.
