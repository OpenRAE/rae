# Shared Semantic Integrity

This note is the implementation-facing architecture preflight for `SEM-200`.
The guardrails below are guidance, not an implementation plan.

[ADR-016](../../decisions/adrs/adr-016-semantic-layer-scope-and-coverage-model.md)
fixes the *model* for `SEM-200` — the seven canonical lifecycle phases, the
construct-family concept, the status vocabulary, and `SEM-200`'s definition of
done — and is immutable once accepted. The *live* coverage table is the
[`## Coverage Model`](#coverage-model) section at the end of this note, which
ADR-016 governs; every `SEM-2xx` implementation PR moves its construct family's
row toward `active` there. The structural gate `tools/check_semantic_coverage.py`
validates that table on every `nox` policy run.

Per-change FM classifications for semantic and runtime-surface ADRs are
recorded in the sibling
[`fm-classification-ledger.yaml`](fm-classification-ledger.yaml) file. The
assurance-policy gate validates that ledger against
`specs/formal/assurance-policy.yaml`, including the ADR-023 through ADR-058
runtime-surface backfill.

`SEM-200` is broader than concept authority alone. It covers whether scenario
constructs keep the same meaning across authoring, validation, instantiation,
compilation, planning, execution, live observation, and post-run experiment
interpretation. The implementation should extend the existing semantic
authority stack rather than introduce another one.

## Lifecycle Boundary

The current canonical lifecycle is:

1. authored SDL YAML is parsed into closed SDL models
2. `SemanticValidator` enforces static SDL semantics and collects all authoring
   errors
3. `instantiate_scenario()` applies parameters/defaults, rejects unresolved
   placeholders, rebuilds the closed `InstantiatedScenario` with portable
   derivation evidence, and reruns semantic validation; direct/deserialized
   artifacts pass `admit_instantiated_scenario()` before compilation
4. `compile_runtime_model()` emits canonical runtime addresses, typed runtime
   resources, and compiled result/execution contracts
5. `plan()` validates backend capability semantics and derives typed
   provisioning, orchestration, and evaluation plans
6. `RuntimeManager` and `RuntimeControlPlane` accept only plan/result/snapshot
   data that passes the published contract and compiled semantic gates
7. live observation and interpretation consume runtime snapshot, result,
   history, participant-episode, evidence, provenance, and profile surfaces
   rather than backend-native objects

Each phase may add structure, but it must not reinterpret an upstream
construct by local convention.

## Canonical Incumbents

Use these existing surfaces before adding anything new:

- SDL shape and local parsing: `raes.SDLModel`, `sdl-yaml/v1` source-profile
  enforcement, explicit migration, variable-key rejection, and `SDLParseError`
- static SDL validation: `SemanticValidator` and `SDLValidationError`
- instantiation/admission: `instantiate_scenario()`,
  `admit_instantiated_scenario()`, `SDLInstantiationError`, and the published
  instantiated artifact/snapshot schemas
- shared SDL semantics: `raes.semantics.objectives` and
  `raes.semantics.workflow`
- runtime graph semantics: `raes_processor.semantics.planner`
- runtime diagnostics: `raes_processor.models.Diagnostic`
- contract boundaries: `raes_contracts.contracts.ContractModel`,
  `schema_bundle()`, generated `contracts/schemas/`, and fixture validation
- concept authority: `contracts/concept-authority/`,
  `specs/concept-authority/`, `raes_contracts.vocabulary`,
  `manifest_authority`, `controlled_vocabularies`, `reference_models`, and
  `semantic_profiles`
- backend and processor declarations: shared `v2` apparatus manifests with
  required `concept_bindings`, controlled vocabulary checks, supported contract
  authority checks, and realization-support disclosures
- live control plane: `control_plane_security`, `control_plane_api`,
  `RuntimeControlPlane`, and `ControlPlaneStore`
- formal-methods policy: ADR-007, the coding standards, and the existing
  `specs/formal/<domain>/` artifacts

## Cross-Cutting Gates

A SEM-200 implementation must pass every gate it touches:

- SDL parser gate: user-defined symbol keys stay concrete; `${var}` may only
  substitute values, not create or rename semantic identities.
- SDL model gate: Pydantic models remain closed where the repo already uses
  `extra="forbid"`; new construct shape belongs in owning SDL models, not
  untyped `dict` side channels.
- semantic validation gate: fail closed on missing, ambiguous, cyclic, or
  out-of-scope references; collect errors through the existing validation
  exception instead of adding a new hierarchy.
- instantiation gate: concrete scenarios must rerun semantic validation after
  parameter/default substitution; direct artifacts must have the closed phase
  shape, portable provenance, and the same semantic admission.
- contract gate: external payloads use `ContractModel`, published schema
  generation, fixtures, and `tools/check_json_artifacts.py`; do not edit
  `contracts/schemas/` directly.
- manifest/profile gate: supported contract versions, SDL versions, concept
  families, binding scopes, controlled vocabulary terms, and semantic profile
  phases must resolve through the existing authority helpers.
- compiler/planner gate: canonical addresses, objective-window semantics,
  workflow state contracts, and planner dependency semantics must come from the
  shared helpers, not copied local algorithms.
- backend boundary gate: backend exceptions and invalid payloads become
  structured `Diagnostic` values; live results are validated against compiled
  contracts before they enter snapshots.
- HTTP/control-plane gate: request bodies are size-limited, authenticated,
  authorized by role, audited, idempotency-fingerprinted, and returned through
  published response models; internal errors stay redacted.
- persistence gate: snapshots, operation records, and audit events are
  plain-data envelopes. Do not store bearer tokens, secrets, raw credentials,
  or backend-private objects in metadata, details, diagnostics, or evidence
  references.
- host/OS exposure gate: secrets and bearer tokens must not be passed in
  command-line arguments, tracebacks, logs, audit `details`, semantic profile
  artifacts, or scenario text. Runtime adapters should receive them through
  headers or process-local configuration that is not echoed into diagnostics.

## Extension Point

The primary extension point is the governed semantic surface, not a new
parallel model:

- add a pure shared helper when the same rule must be consumed by validation,
  compilation, planning, runtime validation, or tests
- add concept families only when meaning must be shared across artifacts
- add reference models only for recurrent shared structure
- add controlled vocabularies only when portable value comparison matters
- add semantic profile declarations when existing concept, contract, binding,
  and behavior assumptions must be composed for an interoperable stack
- add new profile phases or governed binding scopes only at the profile/schema
  authority layer, not as hard-coded one-off checks in a caller

Live observation and experiment interpretation should extend from runtime
snapshot/result/history, participant-episode, evidence, provenance, and
semantic-profile contracts. They should not overload evaluator `detail`,
backend manifest strings, or profile selectors as hidden authority surfaces.

## Guardrails

- Keep concept authority, reference structure, controlled vocabulary values,
  semantic profiles, SDL syntax, runtime contracts, and backend capability
  profiles separate.
- Treat `scenario-instantiation-request-v1.profile` as a selector until a
  governed semantic profile contract gives it stronger meaning.
- Preserve canonical identity semantics through composition/import expansion;
  downstream phases should see resolved identities, not source-file layout.
- Keep authoring, processing, execution, live observation, and interpretation
  meanings aligned through tests that compare the same construct across stages.
- Use the smallest adequate formal-methods artifact for the changed surface.
  FM2/FM3 changes need explicit invariants and typed IR/contract coverage.

## Anti-Patterns

Avoid:

- a second semantic registry beside concept authority and semantic profiles
- direct edits to generated schemas under `contracts/schemas/`
- duplicating SDL validation logic inside compiler, planner, conformance, or
  backend adapters
- raw string parsing where an existing structured model or helper exists
- treating backend-native payloads as the portable observation contract
- treating semantic profiles as backend capability profiles
- treating controlled vocabularies as concept definitions
- treating UCO or another ontology as the authoring syntax
- adding SEM-200-specific exception, logging, audit, persistence, or schema
  stacks
- writing raw secrets, tokens, credentials, or full backend tracebacks into
  diagnostics, audit records, snapshots, or JSON fixtures
- solving the requirement by creating one universal scenario super-model

## Non-Goals

The preflight guardrails above do not implement the missing `SEM-200` coverage,
add new schemas, add new construct-specific tests, or transition the requirement
status. They only fix the architectural guardrails for the implementation that
follows. The Coverage Model below is the inventory and tracker; closing each
`planned`/`partial` row is its own `/implement <child-UID>` run.

## Coverage Model

This is the live, ADR-016-governed coverage table for `SEM-200`. It is mutable
— each `SEM-2xx` implementation PR updates the affected row — and validated by
the structural gate `tools/check_semantic_coverage.py`.

Lifecycle phases (canonical, fixed, per ADR-016): `authoring`, `validation`,
`instantiation`, `compilation`, `planning`, `execution`, `observation`.

Status is one of:

- `active` — the owning requirement is `ACTIVE` in Ground Control; the
  construct's semantics are realized in a shared helper/spec; named tests cover
  it. The structural gate enforces that the row names at least one lifecycle
  phase, at least one *existing* non-test repository artifact, and at least one
  *existing* test under `implementations/python/tests/test_*.py`. It also
  enforces *integration, not just existence*: when the row names importable
  Python realizing modules, at least one named test must actually **import** one
  of them (resolving package re-exports — a bare
  `import` of a whole package does not count), and every `test_*` function in the
  row's named test files must contain at least one assertion (no zero-assertion
  stub tests). Whether the owning requirement is actually `ACTIVE`, and whether
  every claimed module is individually exercised, remain Ground Control /
  requirement-governance facts verified by review, not by the gate;
  `tools/check_semantic_coverage.py --report` surfaces per-row module-coverage
  counts so thin rows are visible.
- `partial` — some realization exists (a spec, a helper) but the owning
  requirement is still `DRAFT` or the coverage is incomplete. The gate enforces
  at least one phase and at least one existing non-test repository artifact.
- `planned` — no realization yet; owned by a `DRAFT` requirement.
  Phases and artifacts are left as `—`; the gate enforces that they stay empty.
  For a `planned` row, the construct family's lifecycle scope, artifact
  expectations, and wave are defined by the owning requirement's record in Ground
  Control (its statement and `wave` field) — this table tracks realization
  status, not the requirement database, and deliberately carries no wave column.

A construct family appears here only if its cross-stage *meaning* can drift, and
only if a `SEM-2xx` child of `SEM-200` (or, for a foundational/peer concern such
as the concept-authority meta-layer or the runtime/contract layers, an owning
peer requirement that is already `ACTIVE`) accounts for it. Pure SDL
data-modeling constructs (topology, features, content, exercise timeline, …) get
their cross-stage integrity from fail-closed validation (`SEM-201`), canonical
identities (`SEM-205`), and the compiled representation (`RUN-302`), so they have
no row of their own unless a construct-specific semantic gap is identified
and a `SEM-*` requirement opened for it. Higher-level capabilities that *consume*
the semantic layer (cross-run comparability, semantic diff, federation/standards
profiles, …) are downstream of `SEM-200` rather than construct families of it,
so they are tracked by their own requirements, not here.

| Construct family | Owning requirement(s) | Phases covered | Realizing artifacts | Status |
| --- | --- | --- | --- | --- |
| Fail-closed semantic validation (cross-cutting gate) | SEM-201 | validation, instantiation | `implementations/python/packages/raes/validator/__init__.py`, `implementations/python/packages/raes/instantiate.py`, `implementations/python/tests/test_sdl_validator.py` | active |
| Stable identifiers, parameterized values, and qualified references | DSL-101, DSL-102, SEM-205 | authoring, validation, instantiation, compilation, planning, execution, observation | `docs/decisions/adrs/adr-076-portable-sdl-identifiers-and-canonical-addresses.md`, `specs/sdl/document-model.md`, `specs/sdl/references.md`, `implementations/python/packages/raes/_identifiers.py`, `implementations/python/packages/raes/_declarations.py`, `implementations/python/packages/raes/parser.py`, `implementations/python/packages/raes/composition/__init__.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_runtime/backend_calls.py`, `implementations/python/packages/raes_runtime/control_plane.py`, `implementations/python/tests/test_sdl_identifiers.py` | active |
| Deterministic module composition and canonical-identity stability across expansion | DSL-103, SEM-205 | authoring, validation, compilation | `implementations/python/packages/raes/composition/__init__.py`, `implementations/python/packages/raes/module_registry/__init__.py`, `specs/formal/composition-readiness.md`, `implementations/python/tests/test_sdl_module_registry.py` | active |
| Instantiation, closed portable phase contracts, and revalidation of concrete scenarios | RUN-301 | instantiation, validation | `docs/decisions/adrs/adr-078-closed-sdl-phase-contracts-and-portable-derivation-evidence.md`, `specs/formal/sdl-phases/README.md`, `contracts/schemas/sdl/instantiated-scenario-v1.json`, `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json`, `implementations/python/packages/raes/phase_contracts.py`, `implementations/python/packages/raes/instantiate.py`, `implementations/python/tests/test_sdl_phase_contracts.py`, `implementations/python/tests/test_instantiated_scenario_schema.py`, `implementations/python/tests/test_sdl_validator.py`, `implementations/python/tests/test_run_300_lifecycle.py` | active |
| Objective windows, referenced scopes, reachability, and refresh | SEM-202 | validation, compilation, planning | `implementations/python/packages/raes/semantics/objectives.py`, `specs/formal/objectives/README.md`, `specs/formal/objectives/window-consistency.md`, `implementations/python/tests/test_semantics_objectives.py`, `implementations/python/tests/test_fm2_semantics.py` | active |
| Declarative objective actor binding, target resolution, success interpretation, and dependency ordering | DSL-112, SEM-207 | authoring, validation, instantiation, compilation, planning | `implementations/python/packages/raes/objectives.py`, `implementations/python/packages/raes/semantics/objective_semantics/__init__.py`, `implementations/python/packages/raes/validator/__init__.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_processor/models/`, `specs/formal/objectives/README.md`, `specs/formal/objectives/declarative-objective-semantics.md`, `implementations/python/tests/test_semantics_objectives.py`, `implementations/python/tests/test_fm2_semantics.py`, `implementations/python/tests/test_sdl_validator.py` | active |
| Workflow control semantics (branching, joins, calling, retry, completion, history) | DSL-113, SEM-203 | authoring, validation, compilation, planning, execution, observation | `implementations/python/packages/raes/orchestration/__init__.py`, `implementations/python/packages/raes/semantics/workflow.py`, `specs/formal/workflows/README.md`, `specs/formal/workflows/state-machine.md`, `implementations/python/tests/test_sdl_validator.py`, `implementations/python/tests/test_runtime_models.py`, `implementations/python/tests/test_sdl_models.py` | active |
| Workflow compensation semantics (registration, triggering, ordering, observation) | SEM-204 | validation, compilation, execution, observation | `implementations/python/packages/raes/semantics/workflow.py`, `specs/formal/workflows/compensation.md`, `implementations/python/tests/test_sdl_validator.py`, `implementations/python/tests/test_runtime_manager.py` | partial |
| Backend-neutral proposition truth and assertion-composed objective success (probe conditions remain separate implementation bindings; SDL scoring pipeline removed per ADR-073) | DSL-110, SEM-206 | authoring, validation, compilation, planning, execution, observation | `implementations/python/packages/raes/propositions.py`, `implementations/python/packages/raes/conditions.py`, `implementations/python/packages/raes/semantics/propositions.py`, `implementations/python/packages/raes/semantics/objective_semantics/__init__.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_processor/models/`, `specs/formal/objectives/proposition-and-assertion-semantics.md`, `implementations/python/tests/test_proposition_semantics.py`, `implementations/python/tests/test_truth_result_contracts.py`, `implementations/python/tests/test_fm2_semantics.py` | active |
| Runtime compiled representation and canonical addresses | RUN-302 | compilation | `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/tests/test_runtime_models.py`, `implementations/python/tests/test_fm2_semantics.py` | active |
| Planner dependency, ordering, refresh, and applicability semantics | RUN-303 | planning | `implementations/python/packages/raes_processor/semantics/planner.py`, `implementations/python/packages/raes_processor/planner/__init__.py`, `specs/formal/planner/README.md`, `specs/formal/planner/dependency-ordering.md`, `implementations/python/tests/test_semantics_planner.py`, `implementations/python/tests/test_runtime_planner.py` | active |
| Live execution state and lifecycle (snapshots, results, history) | RUN-304, API-402 | execution, observation | `implementations/python/packages/raes_runtime/manager.py`, `implementations/python/packages/raes_runtime/result_contracts.py`, `implementations/python/packages/raes_processor/models/`, `implementations/python/tests/test_runtime_manager.py`, `implementations/python/tests/test_runtime_models.py` | active |
| Runtime result and evaluator-result contracts | ASR-503, API-402 | execution, observation | `implementations/python/packages/raes_runtime/result_contracts.py`, `specs/formal/runtime-contracts/README.md`, `specs/formal/runtime-contracts/workflow-results.md`, `specs/formal/runtime-contracts/evaluator-results.md`, `implementations/python/tests/test_runtime_contracts.py`, `implementations/python/tests/test_run_311_participant_episode_lifecycle.py` | active |
| Control-plane semantics (auth, durable state, idempotency, audit) | API-403, API-404 | execution, observation | `implementations/python/packages/raes_contracts/operation_lifecycle.py`, `implementations/python/packages/raes_contracts/contracts/operation_carriers.py`, `implementations/python/packages/raes_runtime/control_plane_operation_context.py`, `implementations/python/packages/raes_runtime/control_plane_admission.py`, `implementations/python/packages/raes_runtime/control_plane_api/__init__.py`, `implementations/python/packages/raes_runtime/control_plane_security.py`, `implementations/python/packages/raes_runtime/control_plane_store.py`, `implementations/python/packages/raes_runtime/control_plane_store_local.py`, `implementations/python/packages/raes_runtime/control_plane_store_paths.py`, `specs/formal/runtime-control-plane/README.md`, `docs/decisions/issue-1092-local-control-plane-durability-preflight.md`, `implementations/python/tests/test_issue_1182_operation_lifecycle_contract.py`, `implementations/python/tests/test_runtime_control_plane.py`, `implementations/python/tests/test_runtime_control_plane_api.py`, `implementations/python/tests/test_issue_1092_control_plane_crash_consistency.py` | active |
| Backend and processor identity, capability, and compatibility manifests | API-401, API-412 | planning, execution | `implementations/python/packages/raes_processor/manifest.py`, `implementations/python/packages/raes_processor/capabilities.py`, `implementations/python/packages/raes_contracts/apparatus.py`, `implementations/python/packages/raes_contracts/manifest_authority.py`, `implementations/python/tests/test_backend_manifest.py`, `implementations/python/tests/test_processor_manifest.py` | active |
| Concept authority, controlled vocabularies, reference models, and semantic profiles (meta-layer) | GOV-920 | authoring, validation, compilation, planning, execution | `specs/concept-authority/concept-authority.md`, `specs/concept-authority/semantic-profiles.md`, `implementations/python/packages/raes_contracts/semantic_profiles.py`, `implementations/python/packages/raes_contracts/controlled_vocabularies.py`, `implementations/python/packages/raes_contracts/reference_models.py`, `docs/explain/reference/shared-concept-model.md`, `implementations/python/tests/test_concept_authority.py`, `implementations/python/tests/test_semantic_profiles.py` | active |
| Participant episode lifecycle boundaries and authored episode structure (initialization, reset, completion, timeout, truncation, interruption) | RUN-311, SEM-222, DSL-120, ACT-623 | authoring, validation, execution, observation | `docs/decisions/adrs/adr-013-participant-episode-lifecycle-boundaries.md`, `docs/decisions/adrs/adr-054-participant-runtime-observable-lifecycle.md`, `specs/formal/participant-episode-model/README.md`, `docs/decisions/issue-122-sem-222-episode-budget-model-preflight.md`, `implementations/python/packages/raes_contracts/participant_episode_closure.py`, `implementations/python/packages/raes_runtime/participant_result_contracts.py`, `implementations/python/tests/test_run_311_participant_episode_lifecycle.py`, `implementations/python/tests/test_sem_222_episode_termination_semantics.py`, `implementations/python/tests/test_sem_222_episode_termination_oracle.py` | partial |
| Declarative participant framing (identity, role, starting conditions, authority anchors, operating scope) | ACT-601 | authoring, validation | `implementations/python/packages/raes/agents.py`, `implementations/python/packages/raes/validator/__init__.py`, `docs/decisions/adrs/adr-020-declarative-participant-framing-boundaries.md`, `implementations/python/tests/test_sdl_models.py`, `implementations/python/tests/test_sdl_validator.py` | active |
| Participant behavior semantics (actions, observations, state transitions) | ACT-602, SEM-208 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/README.md`, `docs/decisions/adrs/adr-022-participant-behavior-and-interaction-semantics.md`, `implementations/python/packages/raes/participant_behavior/__init__.py`, `implementations/python/packages/raes/semantics/participant_behavior/__init__.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_processor/models/`, `implementations/python/tests/test_sem_208_participant_behavior.py`, `implementations/python/tests/test_participant_semantics_invariant_oracle.py` | partial |
| Multi-participant interaction and participant-local histories | SEM-209 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/README.md`, `docs/decisions/adrs/adr-022-participant-behavior-and-interaction-semantics.md`, `implementations/python/packages/raes/participant_behavior/__init__.py`, `implementations/python/packages/raes/semantics/participant_behavior/__init__.py`, `implementations/python/packages/raes/validator/__init__.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_processor/models/`, `implementations/python/packages/raes_conformance/conformance/snapshot_semantics.py`, `implementations/python/tests/test_sem_208_participant_behavior.py`, `implementations/python/tests/test_runtime_conformance.py`, `implementations/python/tests/test_participant_semantics_invariant_oracle.py` | partial |
| Visibility and information-boundary semantics | SEM-210 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/README.md`, `docs/decisions/adrs/adr-022-participant-behavior-and-interaction-semantics.md`, `implementations/python/packages/raes/participant_behavior/__init__.py`, `implementations/python/packages/raes/semantics/participant_behavior/__init__.py`, `implementations/python/packages/raes/validator/__init__.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_processor/models/`, `implementations/python/tests/test_sem_208_participant_behavior.py`, `implementations/python/tests/test_participant_semantics_invariant_oracle.py` | active |
| Participant information-flow policy, finite predicate-opacity runtime enforcement, and bounded reference-backend conformance | SEM-230, SEM-231, RUN-319, API-407, ASR-535 | validation, execution, observation | `specs/formal/participant-semantics/information-flow-control.md`, `specs/formal/participant-semantics/participant-predicate-opacity.md`, `docs/decisions/adrs/adr-085-participant-information-flow-and-control.md`, `docs/decisions/adrs/adr-099-participant-relative-predicate-opacity.md`, `contracts/profiles/behavioral-relation/participant-opacity-runtime-reference-v1.json`, `contracts/schemas/participant-runtime/participant-crossing-occurrence-v1.json`, `implementations/python/packages/raes_contracts/participant_opacity_runtime.py`, `implementations/python/packages/raes_runtime/participant_crossing_mediation.py`, `implementations/python/packages/raes_conformance/conformance/participant_opacity_probes.py`, `implementations/python/tests/test_issue_964_participant_opacity_runtime.py`, `implementations/python/tests/test_issue_965_participant_opacity_backend.py` | partial |
| Participant preconditions, effects, failure, causality, and attribution semantics | SEM-211, SEM-212 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/README.md`, `docs/decisions/adrs/adr-022-participant-behavior-and-interaction-semantics.md`, `implementations/python/packages/raes/participant_action_semantics.py`, `implementations/python/packages/raes/participant_attribution_semantics.py`, `implementations/python/packages/raes/participant_behavior/__init__.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_processor/models/`, `implementations/python/packages/raes_conformance/conformance/snapshot_semantics.py`, `implementations/python/packages/raes_contracts/contracts/__init__.py`, `implementations/python/tests/test_sem_211_participant_action_semantics.py`, `implementations/python/tests/test_sem_212_participant_attribution_semantics.py`, `implementations/python/tests/test_runtime_conformance.py`, `implementations/python/tests/test_participant_semantics_invariant_oracle.py` | partial |
| Participant temporal semantics | SEM-213 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/README.md`, `docs/decisions/adrs/adr-022-participant-behavior-and-interaction-semantics.md`, `implementations/python/tests/test_participant_semantics_invariant_oracle.py` | partial |
| Participant tool/affordance, decision-surface, exact-cut exposure, delivery, and visibility-boundary semantics | SEM-219, SEM-220, SEM-226 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/README.md`, `specs/formal/participant-semantics/information-flow-control.md`, `docs/decisions/adrs/adr-083-participant-tool-decision-surface-and-exposure-semantics.md`, `docs/decisions/adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md`, `docs/decisions/issue-119-sem-219-220-226-participant-decision-surface-preflight.md`, `docs/decisions/issue-294-sem-219-participant-tool-affordance-preflight.md`, `contracts/schemas/control-plane/participant-decision-surface-v1.json`, `contracts/schemas/control-plane/participant-decision-surface-v2.json`, `implementations/python/packages/raes/participant_behavior_specification.py`, `implementations/python/packages/raes/semantics/participant_behavior/__init__.py`, `implementations/python/packages/raes_contracts/contracts/participant_decision_surface.py`, `implementations/python/packages/raes_contracts/contracts/participant_decision_surface_v2.py`, `implementations/python/packages/raes_contracts/contracts/participant_decision_surface_exposure_v2.py`, `implementations/python/packages/raes_contracts/participant_decision_surface_delivery.py`, `implementations/python/packages/raes_processor/compiler/participant_behaviors.py`, `implementations/python/packages/raes_processor/models/behavior_resources.py`, `implementations/python/packages/raes_processor/models/decision_surface.py`, `implementations/python/packages/raes_processor/models/decision_surface_v2.py`, `implementations/python/packages/raes_processor/models/decision_surface_anchor_v2.py`, `implementations/python/packages/raes_processor/models/participant_exposure_v2.py`, `implementations/python/packages/raes_runtime/participant_control.py`, `implementations/python/tests/test_sem_208_participant_behavior.py`, `implementations/python/tests/test_sem_220_participant_decision_surface.py`, `implementations/python/tests/test_sem_220_participant_decision_surface_v2.py`, `implementations/python/tests/test_sem_220_participant_decision_surface_v2_runtime.py`, `implementations/python/tests/test_participant_semantics_invariant_oracle.py` | active |
| Participant reference trajectories and demonstrations | SEM-221 | — | — | planned |
| Participant budget, quota, consumption, and exhaustion semantics; authored interaction budgets | SEM-223, DSL-121, ACT-624 | authoring, validation, planning, execution, observation | `specs/formal/participant-episode-model/README.md`, `docs/decisions/adrs/adr-097-scoped-participant-resource-budgets-and-shared-service-fairness.md`, `specs/formal/participant-semantics/autonomous-execution.md`, `docs/decisions/issue-306-sem-223-participant-resource-budget-preflight.md` | partial |
| Participant outcome interpretation | SEM-215 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/README.md`, `docs/decisions/adrs/adr-022-participant-behavior-and-interaction-semantics.md`, `implementations/python/packages/raes/participant_outcome_semantics.py`, `implementations/python/packages/raes/semantics/participant_outcome.py`, `implementations/python/packages/raes_processor/models/`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_contracts/contracts/__init__.py`, `implementations/python/tests/test_sem_215_participant_outcome_interpretation.py`, `implementations/python/tests/test_participant_semantics_invariant_oracle.py` | active |
| Derived operational context views (portable meaning and comparability) | SEM-214 | execution, observation | `specs/formal/participant-semantics/README.md`, `specs/formal/runtime-contracts/participant-backend-contracts.md`, `implementations/python/packages/raes_contracts/contracts/__init__.py`, `implementations/python/packages/raes_runtime/participant_retrieval.py`, `implementations/python/packages/raes_runtime/control_plane_api_participant_retrieval.py`, `contracts/schemas/control-plane/participant-context-view-v1.json`, `implementations/python/tests/test_participant_backend_contracts.py`, `implementations/python/tests/test_runtime_control_plane.py`, `implementations/python/tests/test_runtime_control_plane_api.py` | active |
| Boundary semantics for runtime-observable state, captured evidence, derived evaluations, analysis outputs, and audience-specific views | SEM-216 | execution, observation | `specs/formal/participant-semantics/README.md`, `docs/decisions/issue-248-sem-216-boundary-semantics-preflight.md`, `implementations/python/packages/raes_contracts/contracts/__init__.py`, `contracts/schemas/control-plane/participant-context-view-v1.json`, `contracts/schemas/experiment-core/experiment-evidence-record-v1.json`, `implementations/python/tests/test_sem_216_boundary_semantics.py`, `implementations/python/tests/test_participant_backend_contracts.py`, `implementations/python/tests/test_runtime_contracts.py` | active |
| Evidence, evaluation, view-boundary, and observability-plane semantics | SEM-224, SEM-225, DSL-123, DSL-124 | authoring, validation, execution, observation | `docs/decisions/adrs/adr-066-observability-evidence-plane-separation.md`, `specs/formal/observability-evidence-plane.md`, `specs/sdl/observability-and-evidence.md`, `implementations/python/tests/test_issue_1043_forwarding_agent_posture.py` | partial |
| External knowledge bindings semantics | SEM-217 | validation, execution | `specs/formal/participant-semantics/README.md`, `docs/explain/reference/shared-concept-model.md`, `implementations/python/packages/raes_contracts/semantic_binding_effects.py`, `implementations/python/tests/test_sem_217_knowledge_bindings.py` | active |
| Explicitness and realization semantics (binding declarations vs processor/backend realization) | SEM-218 | authoring, validation, instantiation, compilation, planning, execution, observation | `specs/formal/realization/explicitness-and-realization.md`, `specs/formal/realization/README.md`, `docs/explain/reference/explicitness-realization-semantics.md`, `implementations/python/packages/raes/explicitness.py`, `implementations/python/packages/raes/realization_designation.py`, `implementations/python/packages/raes/phase_contracts.py`, `implementations/python/packages/raes/validator/__init__.py`, `implementations/python/packages/raes/instantiate.py`, `implementations/python/packages/raes_contracts/apparatus.py`, `implementations/python/packages/raes_contracts/vocabulary.py`, `implementations/python/packages/raes_contracts/contracts/__init__.py`, `implementations/python/packages/raes_contracts/runtime_state.py`, `implementations/python/packages/raes_backend_protocols/manifest.py`, `implementations/python/packages/raes_processor/compiler/__init__.py`, `implementations/python/packages/raes_processor/models/`, `implementations/python/packages/raes_processor/planner/__init__.py`, `implementations/python/packages/raes_processor/semantics/realization.py`, `implementations/python/packages/raes_runtime/backend_calls.py`, `implementations/python/packages/raes_runtime/manager.py`, `implementations/python/packages/raes_runtime/control_plane_store.py`, `implementations/python/packages/raes_runtime/control_plane_api_models.py`, `implementations/python/tests/test_sem_218_explicitness.py`, `implementations/python/tests/test_sem_218_realization.py`, `implementations/python/tests/test_sem_218_realization_designation.py`, `implementations/python/tests/test_sem_218_runtime_realization.py`, `implementations/python/tests/test_issue_1043_realization_corroboration.py`, `implementations/python/tests/test_runtime_planner.py`, `implementations/python/tests/test_backend_manifest.py`, `implementations/python/tests/test_processor_manifest.py`, `implementations/python/tests/test_runtime_contracts.py` | active |
| Clock, time-domain, advancement/pacing/synchronization, and temporal ordering/causality semantics | SEM-227, SEM-228, SEM-229, API-421, ASR-528, EXP-734 | authoring, validation, compilation, planning, execution, observation | `specs/formal/time-model/README.md`, `docs/decisions/adrs/adr-090-shared-time-domain-clock-and-progression-authority.md`, `docs/decisions/adrs/adr-091-portable-time-capability-control-and-provenance-contracts.md`, `implementations/python/packages/raes_contracts/contracts/time_model.py`, `implementations/python/packages/raes_backend_protocols/capability_admission.py`, `implementations/python/packages/raes_runtime/time_coordinator.py`, `implementations/python/packages/raes_conformance/time_semantics.py`, `implementations/python/tests/test_sem_227_shared_time_model.py`, `implementations/python/tests/test_api_421_time_contracts.py` | active |
| Deterministic benign participant execution under shared time | DSL-437 | authoring, validation, compilation, planning, execution, observation | `specs/formal/participant-semantics/autonomous-execution.md`, `docs/decisions/adrs/adr-092-autonomous-benign-participants-under-shared-time.md`, `contracts/schemas/participant-runtime/participant-execution-binding-v1.json`, `contracts/schemas/participant-runtime/participant-execution-control-v1.json`, `contracts/schemas/participant-runtime/participant-execution-service-state-v1.json`, `implementations/python/packages/raes/participant_execution.py`, `implementations/python/packages/raes/semantics/participant_behavior/__init__.py`, `implementations/python/packages/raes_backend_protocols/capability_admission.py`, `implementations/python/packages/raes_backend_protocols/participant_execution_service.py`, `implementations/python/packages/raes_runtime/participant_scheduler.py`, `implementations/python/packages/raes_runtime/participant_clock_driver.py`, `implementations/python/packages/raes_backend_protocols/participant_runtime_base.py`, `implementations/python/packages/raes_contracts/participant_autonomous_state.py`, `implementations/python/tests/test_dsl_437_benign_participant_execution.py`, `implementations/python/tests/test_issue_898_participant_execution_control.py`, `implementations/python/tests/test_dsl_437_evaluation_authority.py`, `implementations/python/tests/test_dsl_437_snapshot_durability_conformance.py` | active |
