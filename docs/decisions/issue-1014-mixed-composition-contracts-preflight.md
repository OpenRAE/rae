# Issue #1014 — Portable mixed-composition contracts preflight

Date: 2026-09-18

Scope: publish the portable contract surface required by SEM-234 while
composing SCE-002, API-407, and API-423. This note is architecture guidance,
not an implementation plan. It does not publish a schema, add a model or
validator, compile or admit a trial, coordinate a runtime, change a backend
manifest, or establish realization.

[ADR-102](adrs/adr-102-mixed-cross-backend-participant-control.md), the
[#813 design preflight](issue-813-cross-backend-participant-control-preflight.md),
the [#1013 semantic preflight](issue-1013-sem-234-mixed-participant-control-preflight.md),
and `sem-234/rev1` already settle the architecture. No new ADR is needed.

## Decisive architecture decisions

### Publish one composition root

Publish one closed `mixed-participant-composition-profile-v1` root. Components,
allocation entries, directed edges, cross-clock/order bindings, loss
declarations, evidence bindings, and the finite phase schedule are nested
definitions of that root, not independently versioned top-level contracts.
Separate top-level schemas would permit incompatible revisions of what
SEM-234 admits as one sealed graph.

The wire-contract version, semantic authority (`sem-234/rev1`), and composition
profile (`mixed-cross-backend-participant-control-v1@rev1`) are distinct
coordinates. The root has one canonical RFC 8785/JCS digest through the
existing `canonical_json_digest()` authority; the digest field is excluded from
its own canonical projection, following the admitted-plan sealing pattern. It
has no `trial_id`, `run_id`, plan-entry id, runtime phase status, operation id,
or observed-apparatus state. #1015 binds the exact profile digest into the
incumbent admitted trial plan; `AdmittedTrialEntryModel.run_id` remains the only
preallocated run identity.

Use identifier-keyed maps with key/embedded-id equality for independently
referenced collections such as components, allocations, edges, phases, and
transitions. Inline closed single-owner mapping, loss, or evidence records
instead of normalizing them into another registry unless more than one owner
actually references them. A separate closed phase-order list may order phase
ids. Do not use open metadata maps or list position as identity. Two component
keys cannot alias the same apparatus identity and digest-pinned manifest
binding; genuine multiple instances need distinct governed component
identities rather than backend-local handles.

Composition mode, realization form, topology class, control-loop posture,
world assumption, and federation-membership posture are separate closed
coordinates. Each alternative-realization profile instance must be complete
and must become a distinct #1015 plan entry/run; alternative instances are not
an active fallback pool. A simultaneous-mixed profile must have at least one
phase with multiple active providers and evidence-backed distinct realization
forms. A staged profile seals all possible members before execution. Backend
names, adapter classes, or component count do not establish any of those
meanings.

Closed wire shapes and operational vocabularies do not make the profile an
exhaustive backend catalog. ADR-105 delegated materialization remains valid:
unspecified internal descendants can stay private while exact selected
constraints, externally visible allocation units, and composition-boundary
obligations remain binding.

### Keep declarations, requirements, and realized facts separate

The composition root carries requirements and sealed intent:

- an allocation names one SEM-234 allocation-unit kind, one canonical compiled
  target, one provider component, and its phase applicability;
- an edge names directed endpoints and references the incumbent authority,
  participant/audience policy, crossing scope, mapping, loss, failure, and
  evidence owners;
- a feature requirement names a governed API-407 feature and minimum support
  level, with an optional already-authorized downgrade policy/provenance
  binding; and
- a phase names active component/allocation/edge refs and finite transition
  rules, not mutable runtime state.

Backend `ParticipantFeatureSupportModel` entries remain declarations in
`backend-manifest-v2`. The profile must not embed or copy those declarations,
and general `realization_support`, `constraints`, or disclosure maps must not
stand in for an API-407 participant-feature result. Contextual validation uses
`resolve_participant_feature_support()` for the selected component, edge, and
phase. It never unions support across components, infers `exact` from list or
method presence, or authorizes a downgrade itself. New standard
mixed-composition feature terms and their conformance probes remain #1017
scope; #1014 may consume only governed current terms or governed extension
terms and cannot claim they are realized.

`ExperimentApparatusContextModel` remains observed run evidence. It cannot be
used as composition intent. Components instead bind stable component ids to
kind-appropriate exact authorities. Processor/backend components reuse
digest-pinned `ExperimentManifestReferenceModel` values and
`ApparatusIdentityModel`; participant implementations reuse
`AdmittedParticipantManifestReferenceModel` and its concrete manifest join.
`ExperimentManifestReferenceModel` deliberately rejects digest-qualified
participant or `other` subjects, so do not widen it or disguise an
adapter/bridge as a generic manifest. If no incumbent adapter-manifest owner
exists, use a narrow closed composition-owned identity/version/digest reference
resolved from trusted context, or bind the adapter through its already-pinned
backend component; do not publish adapter payloads or a generic manifest
carrier. `RealizationEnvelopeIdentityModel` remains an exact envelope
reference. The current `AdmittedApparatusBindingModel` owns one envelope and
cannot by itself prove a multi-envelope component graph; #1015 owns that
admission join. An observed context may later report whether intent was
realized, but cannot admit or repair it.

Inter-trial lineage stays outside the reusable composition profile. #1015
must create a new `AdmittedTrialEntryModel`/`run_id` and seal an exact source
reference at the admitted-trial boundary; the eventual archival
`ExperimentRunModel` mirrors that relation through `derived_from_refs` and
binds its new identity through `TrialRunProvenanceModel`. Neither the source
run nor a generic `derived_from_refs` value is pre-run authorization. Do not
put predecessor plan/run ids into the composition profile, reuse an old entry,
or create a profile-to-entry digest cycle.

### Compose incumbent owners rather than copying them

- The existing `plan-realization-profiles-v1`/`PlanProfileAuthority` contract
  owns recursive, plan-resource realization constraints and backend-selected
  values. `realization-envelope-v1` owns the set of SDL instances one realizer
  can accept, and `RealizationEnvelopeIdentityModel` identifies one such exact
  envelope. None is an allocation/topology/phase graph. Do not rename, widen,
  embed arbitrary composition data in, or substitute any of them for the new
  SEM-234 root; reference their exact identities only where their incumbent
  meaning is required.
- SCE-002 scenario/module/family composition, parameter binding, and seeded
  selection remain owned by `raes.composition`, `selected_scenario.py`,
  `experiment_selection.py`, and the trial compiler. SEM-234 provider
  composition is a separate admitted-realization graph. Do not reuse
  `compose_realization_constraints()` or its recursive constraint vocabulary
  as a provider graph, copy resolved parameters or runtime facts into the
  profile, or let provider/phase availability consume or reseed a random draw.
- Allocation targets use `CompiledAddress` and must resolve through the
  compiler/address owner. Address shape alone is not target existence, kind,
  or scope evidence. Cross-kind overlap is resolved by the owning semantic
  scope, never by string-prefix comparison.
- A topology edge is not an API-423 occurrence or a universal message. It
  references the exact crossing subject/scope and policy owners needed by the
  exchange. Component source/destination is not participant-relative
  ingress/egress. API-423 continues to own request, decision, transformation,
  disclosure, delivery-attempt, delivery, observation, audit, and their
  history joins. Its current transformation history permits one result
  identity per source; a profile requiring parallel audience-specific results
  must refuse that contract version rather than restamp sources or discard
  history.
- Cross-clock bindings reference the exact `time-model-v1` declarations and
  mapping addresses. Composition adds only the edge-relative preserved-order,
  applicability, loss, failure, and evidence binding that the incumbent
  affine/identity mapping does not express. It must not copy scale, offset,
  clock authority, or domain definitions into a competing time model.
- Prospective composition loss reuses the incumbent participant-runtime
  `ParticipantRuntimeMappingLoss` vocabulary in a composition-owned closed
  obligation record with exact basis/affected/limitation references. Runtime
  `ParticipantCrossingLossModel` entries remain API-423 facts. Do not turn the
  runtime fact into prospective intent, reuse API-423's hyphenated
  backend-posture values as API-407's underscored support-level enum, or create
  a third support or loss scale.
- Evidence fields are typed references and obligation bindings, not evidence
  bodies. Actual records remain `ExperimentEvidenceRecordModel`, associated
  artifacts retain checksum/size/URI/sensitivity validation, and realized
  run/study traceability remains in the experiment family. A nonempty evidence
  ref does not prove the referenced content or satisfy an obligation.
- Control authority, provider responsibility, optional backend-native
  ownership, routing, and disclosure authority remain separate references.
  No composition field grants another owner's authority by implication.

### Represent a sealed schedule, not a phase engine

The v1 schedule is finite, pre-admitted, and quiescent. It names one initial
phase, the complete possible-membership set, active refs per phase, and closed
transitions with trusted trigger/evaluator refs, progress bounds, failure
dispositions, and evidence obligations. Every ref must resolve inside the
sealed root or through an exact supplied external authority.

Phase transitions do not select a scenario, consume a random draw, discover a
provider, reset participant memory, establish cleanup, erase history, or
change trial/run identity. The contract carries no current phase, pending
effect, retry counter, lease, or completion result. #1016 owns runtime state
and revision-fenced commit. A topology feedback cycle is not a recursive
profile reference: nested profile resolution must be acyclic and bounded,
while an admitted feedback edge needs explicit progress/failure semantics.

## Validation ownership

Keep three gates distinct:

1. **Ingress and structural validation.** Reuse `parse_bounded_json_object()`,
   `StrictJsonIngressError`, `ContractModel(extra="forbid")`, strict scalar
   shapes, closed vocabularies, map-key equality, cardinality bounds, and
   canonical-digest verification. Reject duplicate JSON members, non-finite
   numbers, oversized input, unknown versions, extras, duplicate identities,
   and malformed refs before graph traversal.
2. **Root-local graph validation.** Check complete key/ref resolution,
   endpoint direction, possible/active membership, phase-order and transition
   closure, exactly one canonical value for each authority/order/loss binding,
   no orphan entries, and no implicit reverse edge. Reject the entire root on
   exhaustion; never truncate.
3. **Contextual validation.** Consume trusted, caller-supplied concrete
   scenario/address indexes, manifests and payload digests, realization
   envelopes, time models, policy/authority cuts, evidence/artifact indexes,
   and nested profiles. Check target kind/existence, manifest identity and
   digest, envelope membership, API-407 effective support, edge clock/mapping
   endpoints, policy/audience/crossing agreement, evidence-ref existence, and
   acyclic bounded nested-profile resolution. It does not fetch paths/URLs,
   choose providers, compile, mutate, repair, dispatch, or manufacture current
   permission.

The contextual validator follows the existing `validate_*_context()` pattern
and raises bounded, value-independent `ValueError` failures. A resolver wrapper
fails closed and suppresses unexpected resolver exceptions like
`validate_participant_flow_control_resolved_context()`. At the processor
boundary, expected failures are converted through the incumbent
`CompilationFailure` path to bounded `Diagnostic`/`DiagnosticModel` values;
contract code must not import the processor package. It must call incumbent
validators and the capability resolver rather than recreate their rules. A
Pydantic object proves only structural/root-local validity; callers holding a
deserialized object must still run contextual validation before #1015
admission.

Graph validation needs explicit caller limits for source bytes, components,
allocations, edges, phases, transitions, nested depth, visited nodes/work, and
diagnostics. Follow `TrialCompilationLimitsModel` and
`AssociatedArtifactValidationLimits`; current trial-product limits do not
implicitly bound composition traversal. Byte limits alone do not bound JSON
nesting, so reject excessive object/array depth and node count with an
iterative pre-model walk in a composition ingress wrapper over the shared
`parse_bounded_json_object()` path. Extend that shared parser only with
backward-compatible optional limits if enforcement must happen before
`json.loads`; do not add a competing loader or rely on a recursive validator
reaching Python's recursion limit.

## Canonical incumbents to reuse

| Concern | Canonical owner and required fit |
| --- | --- |
| Semantic authority | `specs/formal/participant-semantics/cross-backend-participant-control.md`, ADR-102, and stable MCB-001–045 identities. The contract expresses `sem-234/rev1`; it does not redefine it. |
| Closed contract and identity | `ContractModel`, `raes_contracts.versions`, `NonEmptyString`, `PrefixedDigestString`, `canonical_json_digest()`, keyed-map equality, and `x-raes-invariants`. No second base model or serializer. |
| Existing realization profiles | `plan-realization-profiles-v1`, `PlanProfileAuthority`, `realization-envelope-v1`, and `RealizationEnvelopeIdentityModel` retain recursive resource-constraint and single-realizer envelope meaning. Reference them; do not overload them as the SEM-234 graph. |
| SCE-002 variation | `raes.composition`, `selected_scenario.py`, `experiment_selection.py`, `trial_compiler/domains.py`, `policies.py`, `compiler.py`, the admitted trial-plan family, and runtime-fact bindings. Preserve selected-scenario, seed/random-stream, input, and plan-entry identities; composition scheduling cannot rerandomize or substitute values. |
| Scenario targets | `CompiledAddress`, `require_compiled_address()`, `raes_processor/compiler/addresses.py`, instantiated-scenario validation, and owning scope interpretation. No raw paths, callbacks, selectors, or backend commands. |
| Trial intent and lineage | `AdmittedTrialPlanModel`, `AdmittedTrialEntryModel`, `AdmittedApparatusBindingModel`, exact input refs/digests, cleanup/isolation owners, `revalidate_admitted_trial_plan()`, `TrialRunProvenanceModel`, and `ExperimentRunModel.derived_from_refs`. #1014 publishes the reusable profile; #1015 owns its exact acyclic plan-entry binding and source-lineage join. |
| Apparatus and manifests | `ApparatusIdentityModel`, digest-qualified processor/backend `ExperimentManifestReferenceModel`, `AdmittedParticipantManifestReferenceModel`, `RealizationEnvelopeIdentityModel`, backend/processor/participant manifest validators, compatibility checks, and realization-envelope membership. Preserve each reference's admitted subject kinds; observed apparatus context stays evidence-only. |
| API-407 capability | `ParticipantFeatureSupportLevel`, governed feature vocabularies, `ParticipantFeatureSupportModel`, `PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS`, and `resolve_participant_feature_support()`. Requirements and declarations remain different DTOs. |
| API-423 and policy | `ParticipantCrossingSubjectReferenceModel`, `ParticipantCrossingPolicyReferenceModel`, `validate_participant_crossing_occurrence_context()`, and the trusted resolver/context pattern in `participant_crossing_mediation.py`. Edges do not duplicate occurrence stages or grant policy. |
| Authentication and final policy | `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig`, `ControlPlaneIdentity`, participant subject/audience bindings, and the SEM-233 final-sink gate. #1014 adds no endpoint; any later endpoint must preserve caller, target, controller, audience, provider, and release as independent checks. |
| Time and order | `TimeModelDeclarationModel`, `ClockDeclarationModel`, `TimeDomainMappingDeclarationModel`, participant time-management contexts, time capabilities, realized-time evidence, and `ParticipantRuntimeOrderingBasis`. No timestamp-as-causality or second clock model. |
| Loss and evidence | `ParticipantRuntimeMappingLoss`, API-423 loss facts, experiment evidence/reference models, associated-artifact manifests and byte validation, run traceability, limitations, and behavioral claim bindings. Keep intent, fact, artifact, and claim distinct. |
| Configuration and secrets | `experiment_bindings.py`, `participant_configuration.py`, `secret_references.py`, `raes/runtime_environment.py`, runtime-fact binding policy, and `RuntimeFactDispatchCommand`. The profile may carry logical refs/digests, never resolved values or another interpolation/secret resolver. |
| Diagnostics and errors | `StrictJsonIngressError`, resolver-wrapper `ValueError`, processor `CompilationFailure`, `Diagnostic`, `DiagnosticModel`, `sanitized_failure_message()`, request guards, sanitized backend failures, and generic HTTP 500 envelopes. No composition exception hierarchy or logger. |
| Runtime persistence and host boundary | `participant_crossing_state_cut.py`, scoped idempotency, expected history heads, `ControlPlaneStore.commit_participant_transition()`, durability/store-revision helpers, the guarded one-writer local store, component-specific `RuntimeTarget`, `backend_call_contracts.py`, and `backend_result_diagnostics.py`. These are downstream consumers, not #1014 additions; #1016 must extend the governed cut rather than create a composition store or side event stream. |
| Conformance classification | `raes_conformance/conformance/validators.py` `_MODEL_VALIDATORS` and `_SEMANTIC_CONTEXT_REQUIRED_CONTRACTS`, plus `sanitized_failure_message()`. Register structural validation once and classify the root `structural-context-required`; do not report schema/model success as semantic conformance or add a parallel runner. |
| Publication | Hand-governed `contracts/schemas/`, `schema_bundle()`, explicit `tools/generate_contract_schemas.py` routing, per-contract publication records, valid/invalid fixtures, `check_generated_schemas.py`, `check_schema_publication.py`, and ADR-061 compatibility classification. |
| Workflow and layering | `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/policy/adr_policy.yaml`, requirement governance, and existing verification workflows. Contract code stays in `raes_contracts`; no import from processor/runtime. |

## Cross-cutting security and host-layer path

1. **File/parser gate.** The composition ingress path reuses
   `parse_bounded_json_object()`/`StrictJsonIngressError`, adds explicit
   composition byte/depth/node limits before model construction, and accepts an
   object only. No second JSON loader, YAML, generic dict loader, unbounded
   recursion, or remote include.
2. **Shape and semantic gate.** Published JSON Schema and Pydantic reject
   extras and malformed values; root-local and contextual validators perform
   graph and cross-artifact joins. Schema validity alone never admits a trial.
3. **Manifest/config gate.** Manifest payloads pass the existing backend,
   processor, and participant-implementation manifest validators, their
   supported-contract allowlists,
   `participant_configuration.py` target shapes, `experiment_bindings.py`, and
   realization-envelope checks. The profile contains no generic `config`,
   `constraints`, `metadata`, or backend-options map and cannot bypass
   configuration registries.
4. **Authentication/authorization gate.** #1014 adds no endpoint or caller
   authority. A future endpoint must use `create_control_plane_app()`,
   `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig`,
   `ControlPlaneIdentity`, strict security defaults, verified identity/role,
   exact target binding, size guards, mutation fingerprints/idempotency, and
   `AuditEvent`. Authentication never supplies participant authority, policy
   release, or downgrade.
5. **Secret-handling gate.** Portable values contain logical refs/digests only.
   No credential, token, resolved secret, policy body, hidden observation,
   participant private state, executable expression, host path, backend handle,
   or environment-variable secret locator belongs in the profile, fixture,
   diagnostic, log, or digest input. `secret_references.py`,
   `raes/runtime_environment.py`, `runtime_fact_binding_policy.py`, and
   `RuntimeFactDispatchCommand` remain the only late-binding path.
6. **OS/process exposure gate.** This publication creates no subprocess,
   daemon, socket, store, environment binding, or file materialization. Keep
   document content out of argv, environment dumps, filenames, stdout/stderr,
   and backend-native commands. A file path argument is never authority.
7. **Error-envelope and observability gate.** Expected failures expose bounded
   codes, JSON pointers, governed ids, counts, and profile versions only. Do
   not echo raw Pydantic input, full refs, policy/evidence bodies, manifests,
   host paths, environment values, backend exceptions, or tracebacks. Audit is
   a separately authorized audience; logs are not scientific evidence.
8. **Persistence gate.** #1014 adds only Git-tracked schemas, fixtures,
   publication records, reference models, validators, and documentation. Do
   not store a composition in snapshot metadata, operation details, an audit
   blob, a backend-local cache, or a new repository. #1015 owns sealed-plan
   binding; #1016 must reuse `ControlPlaneStore.commit_participant_transition()`
   and its revision/history compare-and-swap rather than add a side store.

## Extensibility seam

The seam is the root's explicit semantic/profile revision plus referenced
subprofiles for allocation interpretation, edge mapping, time/order,
authority/policy, observer projection, trigger/failure behavior, and evidence.
A new backend contributes digest-pinned manifests, governed API-407 feature
terms/strength, mapping profiles, losses, and evidence; it does not add a field
to SDL or a backend-name branch to every validator.

The contextual validator is parameterized by trusted resolver indexes and
resource limits. That permits a later mapping kind, backend, nested profile,
or evidence owner without making the portable root fetch resources or depend
on processor/runtime packages. A future lease, failover/arbitration, or
joint-controller design requires a new accepted authority/profile revision;
it cannot arrive through extra fields or an extension map.

## Gotchas and anti-patterns

Avoid:

- separate top-level allocation, edge, phase, mapping, loss, or evidence
  schemas that can be versioned independently of the sealed composition root;
- treating SCE-002 scenario/module composition, recursive realization
  constraints, experiment variation selection, or runtime-fact substitution as
  the SEM-234 provider graph, or allowing provider availability to perturb a
  seeded trial;
- extending portable SDL with backend choice, using observed apparatus as
  authorization, or adding another trial/run identity;
- copying API-407 declarations into the profile, merging them with
  realization support, using API-423 posture as feature strength, or unioning
  capabilities across providers;
- a generic bridge message, HLA/FOM/handle field, backend-local command,
  adapter callback/import path, open options map, or arbitrary metadata bag;
- treating an edge as a crossing occurrence, a route/filter as release, a
  provider as controller, native ownership as authority, or a nonempty
  evidence ref as proof;
- duplicating clocks/mapping formulas, policy bodies, occurrence stages,
  evidence bodies, exception families, logging, persistence, or workflow
  logic;
- accepting unresolved refs because the schema is valid, using string prefixes
  for scope overlap, inventing reverse/transitive edges, linearizing partial
  order by timestamps/phase/list order, or truncating validation on limits;
- mutable phase state, runtime fallback, late joins, schedule-dependent bytes,
  hidden retries, or a phase-local idempotency cache in the portable profile;
- adding the new contract id to backend/processor supported-contract claims
  before that implementation actually consumes or realizes it. Publication is
  not capability support; #1017 owns mixed-backend declaration/conformance.

## Repository publication guardrails

Issue #1014 declares SEM-234, SCE-002, API-407, and API-423. Reuse the canonical
issue-bound scope in `docs/governance/requirement-scopes/` to assign every
delivery file to its exact owner; do not collapse the delivery to one UID or
globally remap an incumbent requirement solely for this issue. At preflight
time, API-423 has no phase mapping and therefore fails with
`requirement-policy-missing`. API-407 currently matches the manually blocked
`api400-deferred` phase, so an issue-bound scope that truthfully includes all
four assigned UIDs fails even if no delivery file is assigned to API-407: the
scope checker evaluates every listed UID. The `mixed-participant-composition`
ownership map covers the semantic, documentation, and witness-test slice but
not the contract schema, fixture, publication-record, generator,
`raes_contracts`, conformance registry, or new test paths that #1014 will need.
Resolve those narrow phase, ownership, exact issue-scope, and traceability gaps
before implementation. Do not borrow the broader `semantics-expansion` phase,
omit one of the issue's requirements, assign a UID no files to evade its
prerequisites, or weaken the governance check.

The root belongs to the `contracts/schemas/plans/` and
`contracts/fixtures/plans/` family because it is sealed realization/admission
intent, not a participant-runtime occurrence. The schema is the normative
authority. The matching Python model is the reference implementation and must
generate identical JSON through `schema_bundle()`. Add an explicit generator
route rather than relying on its fallback, a per-contract publication entry
with hash and `last_change`, and positive/negative fixtures covering
alternative, simultaneous mixed, and staged profiles. A paired alternative
fixture may demonstrate that a realization change requires two distinct
profile digests, but it must not invent plan-entry/run lineage inside this
contract; #1015 owns that join. Negative fixtures prove structural rejection;
contextual tests separately cover unresolved manifests/scopes/mappings/policy
cuts, unknown revisions, duplicate apparatus identities, contradictory
canonical values, nested-profile cycles, and bounded traversal.

Do not hand-edit generated output as if the generator were authority, add a
parallel registry/checker/CI workflow, or update backend support allowlists to
make publication tests pass. Use the existing schema, JSON-artifact, concept,
lineage, requirement, ADR, and repository-policy gates. Update lineage or
claim records only for an actual normative derivation or compatibility claim.

## Non-goals and implementation boundary

#1014 publishes portable shape plus root-local and contextual validation. It
does not compile or modify an admitted trial plan (#1015), coordinate or persist
an active phase (#1016), add mixed-composition backend features or conformance
claims (#1017), execute ASR-537 (#1018), or reconcile transfer/equivalence
claims (#1019).

It adds no runtime endpoint, controller, scheduler, adapter, bridge, HLA/FMI/
HELICS carrier, policy engine, secret resolver, store, event stream, exception
hierarchy, logger, inter-trial lineage carrier, or workflow. Contract validity
establishes neither runtime or backend realization nor interoperability,
transfer, IFC/noninterference, trace inclusion, bisimulation, exactly-once
effects, or equivalence.
