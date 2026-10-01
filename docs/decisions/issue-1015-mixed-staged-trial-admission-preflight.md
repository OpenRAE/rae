# Issue #1015 — Mixed and staged trial admission preflight

Date: 2026-09-18

Requirements: SEM-234, SCE-002, and API-407.

Scope: extend deterministic SCE-002 trial compilation and admission so a
sealed entry can bind the exact SEM-234 composition profile published by
#1014. This note is architecture guidance, not an implementation plan. It does
not implement compilation, publish a schema, coordinate a phase, dispatch a
backend operation, persist runtime state, or establish mixed-runtime support.

[ADR-102](adrs/adr-102-mixed-cross-backend-participant-control.md), the
[#1013 semantic preflight](issue-1013-sem-234-mixed-participant-control-preflight.md),
the
[#1014 contract preflight](issue-1014-mixed-composition-contracts-preflight.md),
and `sem-234/rev1` already decide the architecture. No new ADR is needed.

## Decisive architecture decisions

### Extend the admitted-trial seam; do not create another plan lifecycle

`AdmittedTrialPlanModel` and `AdmittedTrialEntryModel` remain the only
schedule-independent execution-intent root and entry. The entry's realization
carrier must be one closed choice:

- the incumbent single-realizer `AdmittedApparatusBindingModel`; or
- an exact reference to one contextually admitted
  `MixedParticipantCompositionProfileModel`.

Do not keep both as independently authoritative fields on one entry. The
single-realizer binding's one `realization_envelope` cannot truthfully
represent a graph whose components have distinct envelopes, while a random
"primary" envelope would create false authority. The mixed branch delegates
component manifests, per-component envelopes, allocation, topology and finite
phases to the #1014 profile and equality-checks every repeated manifest or
apparatus coordinate against that owner.

The admitted-plan schema is currently `draft` under ADR-061. A closed
entry-realization union may therefore be recorded as an in-line v1 draft
change, with the hand-governed schema, Python bundle, fixtures, publication
hash/change summary and all consumers changed together. Do not publish a
second `mixed-trial-plan` root, hide composition in an optional metadata map,
or let Python accept a shape that the normative JSON Schema does not.

The plan should pin profile inputs once and let entries refer to the exact
profile identity and digest. Reuse a narrowed, path-free
`ExperimentReferenceModel(ref_kind="profile")`; do not copy the profile's
components, allocations, edges or phases into admitted-plan child models. A
profile id cannot resolve to two digests in one compilation, and every
entry-level profile reference must resolve in the plan's exact input set. The
profile payload and all nested-profile payloads remain caller-supplied typed
artifacts, like the admitted expanded family; the compiler performs no fetch.

Absence of a mixed reference preserves the incumbent single-realizer path.
Presence of one is not a backend support claim. Until #1016 supplies the
runtime coordinator, `realize_admitted_trial_entry()` and other one-backend
consumers must reject the mixed branch explicitly before selecting a
`backend_key`; they must never choose one component, initial phase or fallback
and continue.

### Make realization assignment explicit, total and identity-bearing

The pure `TrialCompilationRequest` boundary must receive an immutable, exact
assignment from every canonical `TrialCoordinateModel` to one realization
binding. A legacy request may be adapted to the same single binding for every
coordinate, but mixed/alternative selection must not come from backend
availability, worker partition, scheduler placement, source-map order or a
default profile.

An already sealed mixed profile is an admitted compiler input, not SDL and not
a backend-discovered result. Its upstream producer must bind it to the exact
selected scenario for that coordinate. #1015 validates and seals that
assignment; it does not add a profile-selection language. An experiment that
compares alternative profiles uses distinct logical coordinates or distinct
compilations supplied by experiment authority. Each alternative is a complete
profile and becomes a distinct entry/run. It is never a list from which the
runtime may fall back.

The canonical coordinate-to-realization assignment, exact profile refs and any
immediate source-trial link are part of `plan_intent()`. Consequently
`plan_id`, `plan_entry_id`, `run_id`, entry digest and plan digest all change
when an admitted realization changes. The published `trial-compiler-v1`
identity profile fixes the exact plan projection and cannot silently acquire a
coordinate-to-profile assignment. Composition-bound plans therefore require
governed composition-aware compiler and identity profile values plus fixed
conformance vectors; legacy pure plans retain the existing v1 profiles and
bytes. Reuse the incumbent domain-separated `derive_identity()` machinery,
canonical coordinate projection, JCS bytes and acyclic sealing chain by
parameterizing it with the selected governed profile. Do not introduce UUIDs,
a second digest helper, a parallel compiler, a composition-local run id, or
post-seal mutation.

Traversal remains an execution detail. Canonical plan bytes and the canonical
failure diagnostic must be invariant under profile-map ordering, component
ordering, worker/thread count and `coordinate_partitions`. A failure in one
coordinate rejects the entire plan; no successful subset, dropped component,
clamped phase or reselection is emitted.

### Break the scenario-snapshot digest cycle deliberately

The #1014 profile requires a digest-pinned `scenario-snapshot` reference. The
final snapshot produced by `instantiate_admitted_trial_entry()` contains
`TrialInstantiationProvenance`, including `plan_digest` and `entry_digest`.
Binding that final digest inside a profile that is itself bound by the entry
would create this forbidden cycle:

```text
profile digest -> final snapshot digest -> plan/entry digest -> profile digest
```

For #1015, the profile's scenario authority is the admitted selection snapshot
returned by `select_scenario_family(..., trial_provenance=None)` for the exact
coordinate outcomes. The compiler recomputes that snapshot through the public
SDL owner and requires its canonical instantiated-snapshot identity to equal
`profile.scenario_snapshot_ref`. It does not trust a caller-provided digest or
compile addresses against a different object.

The later trial-provenance-bearing snapshot is a distinct archival artifact.
Its equality to the admitted selection is established by the existing pinned
family, selections, bindings and plan/entry provenance path, not by pretending
the two snapshot digests are equal. Do not exclude arbitrary provenance from
`canonical_instantiated_sdl_digest()`, weaken `TrialRunProvenanceModel`, put a
placeholder plan id in the profile, or reseal the profile after plan sealing.
If a future contract needs one identity spanning both artifacts, it requires a
separately versioned semantic-projection relation; it is not an implementation
shortcut for #1015.

### Reuse the three #1014 validation layers as one admission gate

Compilation must not reproduce the profile contract's structural, graph or
trusted-context rules. For every assigned profile it must:

1. reconstruct/revalidate the closed model and canonical profile digest;
2. apply `MixedCompositionValidationLimits` and root-local phase-graph checks;
3. build trusted context from the exact selected scenario, compiled address
   registry, concrete manifests/envelopes, API-407 capability resolution,
   crossing policy/subject indexes, time models, authorities, evidence
   satisfaction and nested profiles; and
4. call `validate_mixed_composition_context()` before entry sealing.

`MixedCompositionResolutionContext` is the dependency-inversion seam. Extend
that trusted context where #1015 exposes a missing relationship; do not add a
second compiler-only graph validator. In particular, its current
`compiled_targets: address -> kind` proves target existence and kind but not
cross-kind semantic overlap. The selected-scenario/compiler owner must supply
the canonical semantic-effect coverage of each allocation target, and the
contextual gate must reject two active providers covering the same effect even
when one target is `participant` and another is `action-family` or
`controlled-scope`. String-prefix comparison is not scope interpretation.

Graph and nested-profile resolution stays bounded and I/O-free. The existing
per-profile component/allocation/edge/phase/transition/depth/work limits are
reused. Trial compilation may add only aggregate ceilings such as profiles per
plan or total contextual work; it must not copy each composition limit into
`TrialCompilationLimitsModel`. Budget exhaustion rejects the whole admission
with the same canonical safe diagnostic regardless of traversal order.

### Validate apparatus per component and constraints jointly

Generalize the incumbent apparatus admission helpers rather than bypassing
them. Every profile component must resolve to the exact digest-qualified
processor or backend manifest identity allowed by the experiment's
`ExperimentApparatusConstraintModel`; participant implementation manifests
continue through the separate `AdmittedParticipantManifestReferenceModel`
join. Reuse manifest model validation, kind-specific allowlists,
processor/backend compatibility, supported-contract checks, participant-
manifest joins and `canonical_json_digest()`.
`apparatus_identity_ref` is a join key, not proof by itself.

Each component's `RealizationEnvelopeIdentityModel` must resolve to its exact
`BackendRealizationEnvelopeModel`. Use the incumbent `member()` relation for a
whole-scenario obligation and `member_projection()` only when the owning
compiled target supplies an exact admitted subtree/field path. Do not require
every partial provider to accept the whole scenario, union independent
envelopes, or infer joint support from non-empty individual intersections. The
selected realization must satisfy all active component projections plus edge,
mapping and policy constraints together. An unresolved projection or mutually
inconsistent set rejects admission.

API-407 requirements are resolved for the selected component/allocation/phase
through `resolve_participant_feature_support()` and exact authorized downgrade
records. Capability from another component cannot fill a gap. #1015 consumes
currently governed feature terms; it does not add mixed-runtime feature terms,
add the composition contract to backend support declarations, or claim a
service is realized. Those remain #1017 responsibilities.

Controller, action authority, provider responsibility, backend-native
ownership, routing and disclosure authority are equality-checked as separate
coordinates. A common string value does not merge their meanings. Profile
membership, manifest compatibility, selected controller identity or HLA-style
ownership never grants action or release permission.

### Keep finite phases inside the entry and outside the scheduler

The profile already owns possible membership, phase order, active allocations,
directed edges and transition declarations. Admission pins and validates that
finite schedule; it does not create mutable phase state or a second workflow.
`plan_batch_schedule()` continues to order whole trial entries only. It must
not schedule profile phases, evaluate triggers, activate providers, or treat a
phase index as a retry/attempt/dispatch ordinal.

Cleanup and isolation reuse their incumbent owners. The entry's
`TrialCleanupPlanModel` must cover the union of resources that any pre-admitted
component, edge/bridge or phase can own, including components inactive in the
initial phase. `entry_owned_resource_refs()` and
`isolation_resource_overlaps()` then remain the single definitions used by
plan validation and SCE-006. Deactivation is not cleanup, a phase boundary is
not clean-state evidence, and an isolation proof cannot ignore resources used
only by a later phase.

Attempt timeout, cancellation, retry and cleanup policy remain in
`AdmittedExecutionControlModel` and `TrialCleanupPlanModel`. Do not duplicate
them in the profile or derive them from its edge failure disposition. A
profile transition failure and whole-trial cleanup outcome are different
facts. #1016 owns trigger evaluation, quiescence, revision-fenced phase commit
and append-only transition evidence.

### Represent inter-trial change as an acyclic immediate-source join

A linked realization change is a new entry and new run. Its admitted entry may
carry one narrow immediate-source tuple containing the already sealed source
plan id/digest, entry id/digest and run id. The compiler must be given the
concrete source `AdmittedTrialPlanModel`, reconstruct it with
`revalidate_admitted_trial_plan()`, resolve the exact source entry/profile, and
compare the pinned task, authoring input, family and admitted selection
snapshot. Where participant/audience policy applies, its exact policy
coordinates must also remain fixed or the relation is not an alternative
realization of the same input.

Use the source tuple in the target identity projection. It may point only
backward to an already sealed external plan; no target/sibling forward
reference, source-plan mutation, run-id reuse or digest cycle is allowed. The
target profile describes the target realization; the source profile remains
available through the source plan. Later `ExperimentRunModel.derived_from_refs`
mirrors the relation and `TrialRunProvenanceModel` binds the target run to its
own entry. Neither existing archival carrier is pre-run authorization, and a
generic run ref alone is too weak to replace the exact admitted source tuple.

Validate only the immediate supplied source at compilation. Do not fetch or
recursively walk an unbounded lineage graph. Transitive history remains in
immutable plan/run artifacts and can be analyzed by a separately bounded
consumer.

## Canonical incumbents and required reuse

| Concern | Canonical owner and required fit |
| --- | --- |
| Semantic/profile authority | `specs/formal/participant-semantics/cross-backend-participant-control.md`, ADR-102 and `mixed-participant-composition-profile-v1`. Consume MCB-001–045 and the #1014 root; do not restate them in a compiler DTO. |
| Trial contracts and integrity | `AdmittedTrialPlanModel`, `AdmittedTrialEntryModel`, `AdmittedTrialPlanInputRefsModel`, the entry/plan seal helpers, `revalidate_admitted_trial_plan()`, JCS helpers and `x-raes-invariants`. Extend the existing entry realization seam, map-key/id joins and acyclic digest chain. |
| Deterministic compilation | `TrialCompilationRequest`, `TrialCompilationResult`, `CompilationFailure`, `compile_admitted_trial_plan()`, `plan_intent()`, `admitted_profiles()`, `coordinate_projection()`, `derive_identity()`, canonical coordinate order and the existing partition-permutation tests. Add governed composition-aware profile values/vectors to this subsystem; do not silently widen v1 or create a parallel compiler/identity implementation. |
| SDL selection and addresses | `select_scenario_family()`, `canonical_sdl_digest()`, `canonical_instantiated_sdl_digest()`, `CompiledAddress`, `require_compiled_address()`, `raes_processor/compiler/addresses.py` and the selected runtime-model address registry. Shape is not existence or semantic scope. |
| Composition validation | `parse_mixed_composition_profile()`, `MixedCompositionValidationLimits`, root-local validation, `MixedCompositionResolutionContext` and `validate_mixed_composition_context()`. Extend trusted relationship inputs, not portable graph fields or duplicate validation. |
| Apparatus and envelopes | `ExperimentApparatusConstraintModel`, digest-bound manifest references, `validate_selected_apparatus()` / `validate_admitted_apparatus()`, processor/backend compatibility, participant manifest validation, `BackendRealizationEnvelopeModel`, `member()` and `member_projection()`. Apply them per component and jointly. |
| Participant capability/policy/time | `resolve_participant_feature_support()`, `ParticipantCrossingSubjectReferenceModel`, `ParticipantCrossingPolicyReferenceModel`, incumbent crossing context/resolver patterns, `TimeModelDeclarationModel` and exact clock/mapping identities. Do not copy support, policy or time formulas. |
| Cleanup, isolation and scheduling | `TrialCleanupPlanModel`, `AdmittedExecutionControlModel`, `SchedulerIsolationProofModel`, `entry_owned_resource_refs()`, `isolation_resource_overlaps()`, `validate_scheduler_isolation_proof()` and `plan_batch_schedule()`. Cover all possible profile resources; keep the scheduler entry-level. |
| Lineage and archive | `TrialInstantiationProvenance`, `TrialRunProvenanceModel`, `ExperimentRunModel.derived_from_refs`, `validate_admitted_trial_run()` and `reconcile_admitted_trial_plan()`. Add only the pre-run immediate-source join the existing archival models cannot supply. |
| Diagnostics and errors | `StrictJsonIngressError`, `AdmittedTrialPlanIngressError`, processor `CompilationFailure`, `Diagnostic`/`DiagnosticModel`, canonical diagnostic ordering and `sanitized_failure_message()`. No composition exception hierarchy and no raw resolver/Pydantic/backend text. |
| Publication and conformance | ADR-061, hand-governed `contracts/schemas/`, `schema_bundle()`, explicit schema generation routing, publication records, fixtures and the existing conformance registry. Plan schema validity remains distinct from profile contextual validity and runtime realization. |
| Workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, `tools/check_generated_schemas.py`, `tools/check_schema_publication.py`, `tools/check_semantic_coverage.py` and `tools/verify_all.py`. Extend canonical sessions and exact issue scope; add no CI lane. |

## Cross-cutting security and host-layer path

1. **Composition file/parser gate.** External profile bytes pass
   `parse_mixed_composition_profile()` and therefore the shared bounded,
   duplicate-member/non-finite/depth-rejecting JSON ingress before model
   construction. Nested payloads are supplied as typed, digest-matched objects;
   no YAML, URL/path fetch, remote include or recursive loader is added.
2. **Plan ingress/shape gate.** External plans pass
   `parse_admitted_trial_plan_json()`; caller-held objects pass
   `revalidate_admitted_trial_plan()`. `ContractModel(extra="forbid")`, closed
   realization variants, keyed identities, profile refs and entry/plan digests
   reject unknown fields, coercion-dependent values, partial sealing and
   object-state bypass.
3. **SDL and compiled-scope gate.** The supplied `ExpandedScenario` has already
   passed bounded source/composition, import-lock/path/signature, closed-model
   and semantic admission. The compiler reruns public selected-scenario
   admission and resolves every allocation against the authoritative compiled
   address/effect index. No raw dict, alias, JSON pointer or backend handle is
   accepted as scope authority.
4. **Manifest/configuration gate.** Existing processor/backend/participant
   manifest models, supported-contract allowlists, configuration registries,
   apparatus allowlists, compatibility and exact envelope payloads validate
   each component. The profile adds no generic options/config/constraints map;
   a caller-supplied manifest ref or apparatus identity is not trusted without
   the concrete digest-matched payload.
5. **Authority/policy/time/evidence gate.** The contextual resolver checks
   controller, action authority, route, disclosure authority, crossing subject
   and policy cut, time model/mapping endpoints, API-407 support/downgrade and
   obligation-to-evidence relationships independently. These are trusted
   relationships supplied by the caller; the profile does not authenticate
   them, and a nonempty evidence ref is not proof of artifact content.
6. **Authentication/authorization gate.** #1015 adds no endpoint. Any future
   adapter must reuse `create_control_plane_app()`, `_ControlPlaneApiAuth`,
   `ControlPlaneSecurityConfig.strict_defaults()`, verified
   `ControlPlaneIdentity`/role, target binding, request-size guards, scoped
   idempotency/fingerprints and `AuditEvent`. Authentication, plan read,
   profile/artifact read, secret resolution and execution are separate
   permissions; provider membership grants none of them.
7. **Secret and environment gate.** Reuse `experiment_bindings.py`,
   `secret_references.py`, `participant_configuration.py`,
   `raes/runtime_environment.py` and runtime-fact binding policy. Portable
   plans/profiles may contain logical references and digests only. Resolved
   credentials, tokens, hidden participant state, secret hashes, environment
   variable locators, policy bodies and backend-native handles never enter
   profile/plan bytes, identity projections, diagnostics, fixtures, logs or
   telemetry. Ambient environment and backend defaults cannot select a
   profile, component or phase.
8. **Resource gate.** `TrialCompilationLimitsModel` bounds coordinates,
   products, per-entry material and plan bytes; `MixedCompositionValidationLimits`
   bounds each graph and traversal. An aggregate profile/work ceiling prevents
   many individually legal profiles from multiplying work without bound.
   Limits are explicit inputs; raising a non-binding limit cannot change plan
   bytes. Exhaustion is whole-plan rejection, never truncation.
9. **OS/process exposure gate.** Compilation remains pure and in-process over
   typed objects. Profile/plan JSON, selections, mappings, evidence refs,
   secret refs or credentials are not placed in process argv, shell strings,
   filenames, environment captures, stdout/stderr, subprocess input or
   backend commands. #1015 opens no socket, daemon, file-materialization or
   host-network surface.
10. **Error-envelope and observability gate.** Expected failures become the
    existing bounded, deterministically ordered `trial-compiler.*`
    diagnostics with fixed value-independent messages and canonical addresses.
    Never echo raw Pydantic input, selected/rejected values, profiles,
    manifests, policy/evidence bodies, host paths, resolver exceptions,
    environment dumps or tracebacks. A future HTTP adapter retains the generic
    `{"detail":"internal server error"}` unexpected-failure envelope. Logs and
    audit, if an adapter later adds them, contain safe ids/digests/versions,
    counts, stages and durations only; they are not scientific evidence.
11. **Persistence and execution gate.** Compilation writes nothing. Do not put
    profiles or plans in `RuntimeSnapshot.metadata`, operation details, audit
    blobs, scheduler memory, a mutable repository or a new composition store.
    `ControlPlaneStore.commit_participant_transition()` and its expected-head
    transaction remain #1016's runtime boundary. Admission success establishes
    no current permission, provider availability, delivery, cleanup or phase
    state.

## Extensibility seam

The required seam is the coordinate-to-realization binding carried through
the existing admitted-plan profile set and identity projection. Its mixed
branch references the exact revisioned composition root; its legacy branch
retains the single-realizer binding. A future backend, mapping kind or nested
composition changes trusted manifest/context inputs and governed profile
revisions, not SDL or every compiler stage.

The compiler/identity profile value is selected explicitly from the closed
admitted-plan profile set. A new output-affecting realization assignment or
identity projection mints another governed value and vector corpus; it never
retroactively changes bytes produced under an older profile.

`MixedCompositionResolutionContext` is parameterized by trusted indexes and
resource budgets. Add the next relationship there when validation needs a new
owner, such as canonical allocation-effect coverage. Do not introduce
backend-name branches or open callback/import/plugin fields.

A future failover/arbitration profile, lease, simultaneous scoped controllers,
joint/fused control, runtime membership discovery, or different phase engine
requires a new accepted authority/profile revision. It cannot be encoded as
another realization union member, an optional metadata field, a scheduler
choice or an interpretation of multiple components.

## Gotchas and anti-patterns

Avoid:

- treating multiple manifest refs in the incumbent apparatus binding as a
  composition graph, or choosing an arbitrary aggregate/primary envelope;
- copying profile components, allocations, edges, phases, time mappings,
  policies, capability declarations or evidence bodies into the plan;
- building a second graph/context validator in `raes_processor`, or checking
  cross-kind overlap by address prefix;
- binding the profile to the final provenance-bearing snapshot and creating a
  digest cycle, or silently excluding trial provenance from the canonical
  snapshot profile;
- profile selection by backend availability, scheduler, worker, host, retry,
  wall time, source order or environment; runtime fallback and resampling are
  forbidden;
- using phase order as causal order, phase activation as cleanup, an inactive
  pinned component as available, or a transition declaration as evidence that
  its trigger fired;
- unioning component capabilities/envelopes, letting one provider satisfy
  another's obligation, or treating contract publication as backend support;
- conflating participant identity, controller, action authority, provider,
  backend-native ownership, route and disclosure authority;
- letting `realize_admitted_trial_entry()` select one backend for a mixed
  entry before #1016 exists;
- carrying a run-only `ExperimentApparatusContextModel` as pre-run authority,
  or treating `ExperimentRunModel.derived_from_refs` as admission;
- reusing a source run id, mutating a source plan, linking to a sibling whose
  identity is not sealed, or recursively fetching an unbounded lineage;
- omitting later-phase resources from cleanup/isolation, or creating
  composition-specific retry, cleanup, scheduler, exception, logger,
  persistence, fixture-runner or CI abstractions;
- partial plans, partial profiles, silent component drops, limit truncation,
  fallback profiles, raw validation errors or post-seal mutation; and
- changing the draft admitted-plan schema without schema-bundle parity,
  publication hash/change summary, compatibility record, positive/negative
  fixtures, exports and all consumers moving together.

## Workflow and acceptance boundary

Issue #1015 declares SEM-234, SCE-002 and API-407. Its implementation must add
one exact issue-bound requirement scope and extend the existing
`mixed-participant-composition` ownership paths only for the actual delivery.
Use the canonical requirement-order phase and no broader fallback phase. The
branch name contains no requirement UID, so repository checks run with
`RAES_REQUIREMENT_UID=SEM-234`.

Acceptance evidence must cover pure legacy, pure alternative, simultaneous
mixed and staged entries; exact profile/source joins; component manifest and
per-component envelope drift; unsupported capability/downgrade; missing
scope, edge, clock/order, policy, authority or evidence; cross-kind overlap;
nested-cycle/work limits; cleanup/isolation coverage; final-snapshot cycle
avoidance; full atomic rejection; and byte/diagnostic stability under map,
worker and partition permutations. Extend the incumbent trial-plan/compiler
tests and canonical nox sessions; do not add a parallel harness or workflow.

## Non-goals and implementation boundary

#1015 admits and seals mixed realization intent. It does not:

- add backend choice to portable SDL or publish another authoring language;
- implement live mixed realization, a bridge/adapter protocol, phase state,
  trigger evaluation, provider handoff, backend dispatch or result admission;
- change scheduler authority, worker placement, queueing, leases, concurrency,
  attempt lifecycle, cleanup execution or runtime persistence;
- add API-407 mixed-runtime feature terms or backend conformance claims (#1017);
- add an HTTP/CLI/MCP endpoint, artifact store, secret manager, database,
  event stream, logger or subprocess;
- establish current controller/action/release permission, successful delivery,
  exact replay, interoperability, empirical transfer, trace inclusion,
  bisimulation, IFC/noninterference, backend equivalence or ASR-537
  demonstration; or
- replace #1016 runtime coordination, #1018 demonstration/evaluation or #1019
  claim reconciliation.

A sealed entry proves only deterministic, bounded admission of exact portable
intent against the supplied trusted context. Runtime availability, fresh
authority, realized support, transition commit, effects, evidence and cleanup
remain separate downstream facts.
