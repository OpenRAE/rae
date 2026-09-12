---
id: ASR-532
title: "Runtime Backend Result Integrity"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-05-18T04:25:47.598518Z
updated_at: 2026-08-19T00:00:00Z
---

# ASR-532 — Runtime Backend Result Integrity

## Statement

The runtime shall validate backend results at the execution boundary and reject
or sanitize results that violate RAE-owned portable contracts, plan authority,
runtime-domain ownership, or snapshot-transition invariants. Rejections shall
preserve the trusted predecessor state and identify the violated invariant with
structured diagnostics.

## Rationale

ADR-004 and ADR-036 assign backend invocation and result validation to the RAE
runtime. Issue #158 characterizes that boundary with controlled result
perturbations. Certification of external backend implementations, verification
of backend manifest truthfulness, infrastructure observation, malicious-backend
containment, and comprehensive backend acceptance testing remain outside this
requirement.

## Traceability

- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Completion regression: replay compiled carriers and participant admission at the current source identity)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Completion regression: reject stale implementation and replay evidence after result-admission changes)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Completion regression: retain portable compiler coverage at the current source identity)
- TESTS → TEST `implementations/python/tests/test_act_604_dynamic_information_state.py`
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py`
- TESTS → TEST `implementations/python/tests/test_initial_service_state.py`
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_techvault_honesty.py`
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_techvault_native.py`
- TESTS → TEST `implementations/python/tests/test_realization_honesty_conformance.py`
- TESTS → TEST `implementations/python/tests/test_run_305_participant_runtime_state_history.py`
- TESTS → TEST `implementations/python/tests/test_run_307_shared_operational_state.py`
- TESTS → TEST `implementations/python/tests/test_runtime_conformance.py`
- IMPLEMENTS → GITHUB_ISSUE `1204` (Granular realization and backend-result admission)
- IMPLEMENTS → SPEC `specs/formal/runtime-contracts/backend-result-admission.md`
- IMPLEMENTS → SPEC `specs/sdl/backend-realization-preparation.md`
- IMPLEMENTS → SPEC `specs/sdl/plan-realization-profiles.md`
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-105-recursive-partial-description-semantics.md`
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1204-clause-mapping.md`
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1204-runtime-result-integrity-preflight.md`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_capability_constraints.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_realization_envelope_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/phase_contracts.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/realization_envelope.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_core.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/backend_manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/protocols.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_stubs/evaluation_support.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_stubs/manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_stubs/stubs.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_base.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_domain_profile_contracts.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_domain_profile_schema_identity.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_domain_profile_schema_registry.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_domain_profile_validation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_planning_validation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/compute_substrate.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/base.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_manifests.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/schema_constraints.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/snapshot_entry.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/plan_effects.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/plan_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/planning.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_collections.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_binding.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_common.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_limits.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_models.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_normalization.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_structure/_normalization_overlays.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_state.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_value_limits.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/pipeline.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_compute_substrate.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_deferred_constraints.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_recursive_constraints.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_requirements.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_scalar_sets.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_value_domains.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/resources.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/runtime_model.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/core.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/operating_system_capability_domains.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/operations.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/ordering.py`
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
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_apparatus_defaults.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_concern_observations.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_concern_projections.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_concerns.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_requirement.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_runtime_common.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_runtime_evaluation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_snapshot_sanitization.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_specialized_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_support.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_typed_runtime_projection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/evaluator.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/orchestrator.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/profile_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/provisioner.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/target.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/apply_failure.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_call_contracts.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_calls.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_effect_transitions.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_entry_transitions.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_input_contracts.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_preparation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_realization_authority.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_snapshot_contracts.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_models.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_execution.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_plan_authorization.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_snapshots.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/manager.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/observation_admission.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_effect_authority.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_execution_control_boundary.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/registry.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/time_control.py`
- TESTS → TEST `implementations/python/tests/test_issue_1067_resolved_realization_authority.py`
- TESTS → TEST `implementations/python/tests/test_issue_1200_mixed_runtime_constraints.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_backend_preparation.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_collection_lifecycle.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_input_bounds.py`
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
- TESTS → TEST `implementations/python/tests/test_issue_1204_result_durability.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_result_owners.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_result_shapes.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_result_transitions.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_safe_presence.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_service_dependencies.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_specialized_constraints.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_substrate_handoff.py`
- TESTS → TEST `implementations/python/tests/test_issue_1204_targeted_effects.py`
- TESTS → TEST `implementations/python/tests/test_issue_158_runtime_result_integrity.py`
- TESTS → TEST `implementations/python/tests/test_issue_898_participant_execution_control.py`
- TESTS → TEST `implementations/python/tests/test_issue_899_participant_resource_budgets.py`
- TESTS → TEST `implementations/python/tests/test_issue_985_runtime_observation_contract.py`
- TESTS → TEST `implementations/python/tests/test_run_308_concurrent_participant_execution.py`
- TESTS → TEST `implementations/python/tests/test_runtime_manager.py`
