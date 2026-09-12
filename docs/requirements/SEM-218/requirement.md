---
id: SEM-218
title: "Explicitness And Realization Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-05T00:54:58.405111Z
updated_at: 2026-09-06T00:00:00Z
---

# SEM-218 — Explicitness And Realization Semantics

## Statement

The ecosystem shall define semantics distinguishing binding author declarations from concerns left open to processor or backend realization, including when realization is permitted, when explicit declarations must be honored, and when unsupported exact requirements must be rejected rather than silently approximated.

## Rationale

Current state: identified gap. Honest portability requires normative semantics for what is binding, what may be realized later, and when approximation is forbidden.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/__init__.py` (Public owner and compatibility facade for realization authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_models.py` (Versioned recursive authority, closure, collection, reference, provenance, and limit contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_evaluation.py` (Bounded recursive conformance evaluation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_evaluation_context.py` (Shared bounded evaluation context and effective-closure resolution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_evaluation_collections.py` (Keyed-collection and sequence conformance evaluation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_scopes.py` (Closure overlays across materialized, additional, delegated, keyed, and sequence paths)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_limits.py` (Shared structural and metadata work admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_normalization.py` (Concise literal and stable-identity normalization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_normalization_scopes.py` (Source-index to semantic-identity scope normalization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_composition.py` (Canonical composition and structural refinement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_compatibility.py` (Lossless legacy conversion boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_compatibility_upgrade_leaf.py` (Legacy leaf upgrade and compatibility-closure helpers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_compatibility_downgrade_helpers.py` (Lossless recursive-to-legacy projection helpers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/bounded_domains.py` (Nullable scalar-domain support for recursive realization constraints)
- IMPLEMENTS → SPEC `specs/sdl/recursive-realization-constraints.md` (Normative recursive authority, collection, reference, limit, and provenance semantics)
- IMPLEMENTS → SCHEMA `contracts/schemas/realization-constraints/recursive-realization-constraint-v1.json` (Published recursive realization constraint contract)
- TESTS → TEST `implementations/python/tests/test_issue_1203_recursive_normal_form.py` (Nested authority, presence, collections, references, limits, refinement, and abstract-model acceptance coverage)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_structure.py` (Authored leaf and scoped collection lowering for mixed runtime constraints)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_concern_explicitness.py` (Concern-owned leaf selection with non-authoritative aggregate support summaries)
- TESTS → TEST `implementations/python/tests/test_issue_1200_mixed_runtime_constraints.py` (Admitted apply, serialized authority, exact siblings, delegated packages, unknown observations and numeric DNS identity)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1200-mixed-runtime-constraints-preflight.md` (Mixed runtime constraint and portable authority guardrails)

- IMPLEMENTS → GITHUB_ISSUE `1043` (Issue #1043 forwarding-agent realization semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_forwarding_agent.py` (Forwarding-agent ownership-role model)
- TESTS → TEST `implementations/python/tests/test_issue_1043_forwarding_agent_posture.py` (Forwarding-agent ownership and evidence-binding tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_evidence_requirements.py` (Evidence-plane validation for forwarding-agent ownership roles)
- TESTS → TEST `implementations/python/tests/test_issue_1043_realization_corroboration.py` (Forwarding-agent realization corroboration tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_observation.py` (Value-free runtime realization observation disclosure)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/apparatus.py` (Typed realization observation capabilities)
- IMPLEMENTS → PULL_REQUEST `369` (PR #369 feat(sdl): add runtime inventory surfaces)
- DOCUMENTS → GITHUB_ISSUE `363` (Issue #363 exact runtime filesystem facts must be expressible, not approximated)
- IMPLEMENTS → GITHUB_ISSUE `72` (Explicitness & realization semantics: binding declarations vs processor/backend realization (SEM-218))
- IMPLEMENTS → SPEC `specs/formal/realization/explicitness-and-realization.md` (SEM-218 normative spec: Explicitness And Realization Semantics)
- IMPLEMENTS → SPEC `specs/formal/realization/README.md` (SEM-218 realization-spec domain README)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/explicitness-realization-semantics.md` (SEM-218 implementer-facing companion (non-normative))
- IMPLEMENTS → PULL_REQUEST `163` (docs: add SEM-218 explicitness and realization semantics spec)
- DOCUMENTS → GITHUB_ISSUE `368` (Issue #368 exact container host/security/mount facts must be expressible, not approximated)
- TESTS → TEST `implementations/python/tests/test_runtime_models.py` (Runtime compiler tests requiring exact declared runtime facts and clean diagnostics)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md` (SDL validation documentation for exact runtime declarations and typed runtime facts)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/limitations.md` (SDL limitations documentation clarifying runtime facts now expressible through typed fields)
- IMPLEMENTS → GITHUB_ISSUE `489` (Issue #489 SEM-218 realization enforcement 1/3: explicitness classifier + substitution-downgrade rule)
- IMPLEMENTS → PULL_REQUEST `529` (PR #529 feat: add explicitness classifier semantics)
- TESTS → TEST `implementations/python/tests/test_sem_218_explicitness.py` (SEM-218 explicitness classifier and substitution downgrade regression tests)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-semantic-integrity.md` (Shared semantic integrity explanation updated for SEM-218 explicitness classifier realization)
- TESTS → TEST `implementations/python/tests/test_sem_218_realization.py` (SEM-218 part-2 tests: compiler emission class preservation + planner realization gate)
- IMPLEMENTS → GITHUB_ISSUE `490` (Issue #490 SEM-218 realization enforcement 2/3: typed compiler emission + planner gate)
- TESTS → TEST `implementations/python/tests/test_sem_218_runtime_realization.py` (SEM-218 runtime gate + provenance tests (Execution/Observation rows))
- IMPLEMENTS → GITHUB_ISSUE `491` (SEM-218 realization enforcement 3/3 (issue #491))
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-760-sem-218-provenance-preservation-preflight.md` (Issue 760 SEM-218 provenance-preservation architecture preflight)
- TESTS → TEST `implementations/python/tests/test_sem_218_realization_designation.py` (SEM-218 scoped realization posture cascade, planner gate, and provenance regression tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-539-realization-posture-cascade-preflight.md` (Issue 539 SEM-218 realization-posture cascade architecture preflight)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-985-runtime-configuration-realization-concerns-preflight.md` (Issue 985 runtime-configuration realization-concern architecture preflight)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_stateful_resource_references.py` (Runtime mount and stateful-resource destination conflict enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_requirements.py` (RuntimeConfiguration lowering into typed SEM-218 realization requirements)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/__init__.py` (Public planner realization disclosure and snapshot sanitization surface)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/core.py` (Planner materialization and reconciliation of runtime realization requirements)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/operations.py` (Deterministic planner operations for realization concern reconciliation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/ordering.py` (Ordering rules for realization concern plan operations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization.py` (SEM-218 runtime realization disclosure and safe observation integration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_concern_observations.py` (Strict observed realization-concern contracts and commitment validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_concern_projections.py` (Canonical safe projections for runtime realization concerns)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_concerns.py` (Canonical runtime realization concern descriptor registry)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_runtime_evaluation.py` (Runtime realization comparison and mismatch evaluation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_snapshot_sanitization.py` (Safe backend realization snapshot sanitization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_calls.py` (Backend realization observation sanitization and disclosure enforcement)
- TESTS → TEST `implementations/python/tests/test_issue_985_realization_projection.py` (Issue 985 canonical realization projection and sanitization tests)
- TESTS → TEST `implementations/python/tests/test_issue_985_runtime_observation_contract.py` (Issue 985 strict runtime observation contract tests)
- TESTS → TEST `implementations/python/tests/test_issue_985_runtime_realization_concerns.py` (Issue 985 compiler, planner, and backend realization concern tests)
- IMPLEMENTS → GITHUB_ISSUE `985` (Issue #985 lower RuntimeConfiguration dimensions into realization concerns)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/__init__.py` (Semantic validation hook for SEM-218 explicitness classification diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_configuration.py` (Exact node-scoped runtime declaration aggregation and duplicate validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_filesystem.py` (Typed runtime filesystem facts with exact path, ownership, mode, digest, and sensitivity fields)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_container.py` (Typed runtime container host, security, and health declarations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/explicitness.py` (SEM-218 exact, constrained, and open explicitness classifier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/scenario.py` (Scenario explicitness metadata surface for downstream consumers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/instantiate.py` (Instantiation path preserving authored explicitness through variable substitution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_capability_constraints.py` (Finite-domain realization constraints retained during instantiation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/runtime_model.py` (RuntimeModel realization requirement metadata field)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_state.py` (SEM-218 realization provenance ledger on runtime snapshots)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/realization_designation.py` (SEM-218 scoped realization designation cascade and canonical scope resolution)
- IMPLEMENTS → GITHUB_ISSUE `1066` (Portable runtime process-resource-limit realization semantics)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1066-runtime-resource-limits-preflight.md` (Issue 1066 architecture and supported-target inventory)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Portable SDL process-resource-limit authoring guidance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/nodes.py` (Node-scoped runtime process-limit phase participation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/phase_contracts.py` (Process-limit constraint provenance across SDL phases)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_resource_limits.py` (Portable process-resource-limit authoring model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_core.py` (Process-limit semantic validation integration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_runtime_process_limits.py` (Process-limit selector and cross-reference validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/manifest.py` (Backend manifest process-limit capability publication)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/process_resource_limits.py` (Manifest adapter for typed process-limit capability domains)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py` (Public process-limit contract facade)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py` (Process-limit contract exports)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/capabilities.py` (Process-limit capability contract model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/vocabulary.py` (Governed process-limit resource and scope vocabulary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_envelope_carrier.py` (Selected-configuration binding for typed process-limit capability domains)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/provisioning.py` (Process-limit constraint provenance compilation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_process_limits.py` (Typed process-limit admission and constraint semantics)
- TESTS → TEST `implementations/python/tests/test_issue_1066_runtime_resource_limits.py` (Absent, exact, constrained, open, unsupported, substituted, excess, and evidence conformance)
- IMPLEMENTS → GITHUB_ISSUE `1078` (Complete SEM-218 boundary coverage across RuntimeConfiguration)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1078-runtime-configuration-boundary-coverage-preflight.md` (Complete runtime-field ownership and architecture inventory)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1078-runtime-configuration-boundary-remediation.md` (Issue 1078 implementation and backend-boundary decision)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_runtime_concern_profiles.py` (Executable RuntimeConfiguration ownership and enforcement inventory)
- TESTS → TEST `implementations/python/tests/test_issue_1078_runtime_boundary_coverage.py` (Complete runtime concern, posture, closure, observation, and secret conformance)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-847-runtime-package-repositories-preflight.md` (Typed package-repository profile and existing runtime-packages authority boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_packages.py` (Closed, pinned APT repository profile within the runtime-packages concern)
- TESTS → TEST `implementations/python/tests/test_issue_847_runtime_package_repositories.py` (Repository validation, compilation, projection, schema, and compatibility coverage)

- DOCUMENTS → GITHUB_ISSUE `1201` (Recursive partial-description design and finite reference model; production semantics unchanged)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-105-recursive-partial-description-semantics.md` (Recursive partial-description production adoption through issue 1204)
- DOCUMENTS → DOCUMENTATION `docs/research/partial-description/semantics.md` (Candidate contract and versioned adoption boundary)
- DOCUMENTS → DOCUMENTATION `docs/research/partial-description/verification.md` (Finite model acceptance matrix and limitations)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1201-recursive-description-semantics-preflight.md` (Architecture and canonical-owner assessment)
- IMPLEMENTS → CODE_FILE `implementations/python/research/partial_description.py` (Finite design oracle for explicit constraints, delegation and scoped closure; not production enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/research/description_lifecycle.py` (Finite lifecycle and abstract-execution design examples)
- TESTS → TEST `implementations/python/tests/test_issue_1201_partial_description.py` (Finite composition, delegation and quantifier counterexamples)
- TESTS → TEST `implementations/python/tests/test_issue_1201_description_lifecycle.py` (Version, knowledge, reporting and data-demand design checks)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_realization_envelope_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/realization_envelope.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/backend_manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/protocols.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_domain_profile_contracts.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_domain_profile_schema_identity.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/compute_substrate.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/schema_constraints.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/snapshot_entry.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/plan_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/planning.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_collections.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_binding.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_common.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_normalization_overlays.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/pipeline.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_compute_substrate.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_deferred_constraints.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_recursive_constraints.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_scalar_sets.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_value_domains.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/resources.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/operating_system_capability_domains.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/prepared_node_admission.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/prepared_node_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/prepared_node_semantics.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/prepared_node_support.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/realization_authority.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/realization_authority_materialization.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/realization_collections.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/realization_constraint_views.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/realization_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/realization_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_apparatus_defaults.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_requirement.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_runtime_common.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_specialized_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_support.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_typed_runtime_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/profile_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/provisioner.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/target.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_realization_authority.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_models.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_plan_authorization.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_snapshots.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/observation_admission.py`
- TESTS → TEST `implementations/python/tests/test_issue_1067_resolved_realization_authority.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_backend_preparation.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_collection_lifecycle.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_nested_domains.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_preparation_admission.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_preparation_contract.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_preparation_os.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_prepared_credentials.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_prepared_node_admission.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_prepared_node_semantics.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_prepared_sequence.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_profile_carrier.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_profile_offline.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_recursive_carriage.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_recursive_defaults.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_recursive_environment.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_reference_profiles.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_resource_collections.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_safe_presence.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_specialized_constraints.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_substrate_handoff.py`
- IMPLEMENTS → GITHUB_ISSUE `1204` (Recursive authority through admitted preparation and results)
- IMPLEMENTS → SPEC `specs/sdl/backend-realization-preparation.md`
- IMPLEMENTS → SPEC `specs/sdl/plan-realization-profiles.md`
