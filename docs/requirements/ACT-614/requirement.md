---
id: ACT-614
title: "Temporal Behavior Profiles"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:15:08.208790Z
updated_at: 2026-09-21T00:00:00Z
---

# ACT-614 — Temporal Behavior Profiles

## Statement

The ecosystem shall support participant behavior profiles with schedules, cadence, dwell, timing constraints, and other temporal characteristics.

## Rationale

Requirement inventory expansion. Participant behavior over time is a first-class scenario concern rather than a backend-local pacing detail.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `216`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_execution.py` (Versioned schedules and typed numeric parameters)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced profile references)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_temporal_semantics.py` (Explicit deadline and dwell bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_temporal_bindings.py` (Backend-independent binding validity)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_temporal.py` (Resolved temporal identity)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/capability_admission.py` (Exact manifest sufficiency)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_temporal.py` (Dispatch and outcome enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_temporal.py` (Evidence assessment and durable consistency)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_temporal_assessment.py` (Focused temporal assessment checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_temporal_probes.py` (Scenario-specific conformance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_declarations.py` (Typed temporal authoring values)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_sections.py` (Temporal import rewriting)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/observation_scope.py` (Dwell observation scope)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_autonomous.py` (Temporal behavior validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py` (Temporal objective validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_nodes_infra_network.py` (Temporal node validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_capabilities.py` (Optional backend controls)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_execution_manifest.py` (Manifest declarations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_execution_probes.py` (Claim-scoped conformance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle.py` (Temporal contract bundles)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/manifests.py` (Manifest schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_execution.py` (Execution binding contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_runtime.py` (Runtime temporal state)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_temporal.py` (Temporal contract models)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_views.py` (History projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py` (Realization-plan support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/schema_invariants.py` (Temporal schema invariants)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_autonomous_state.py` (Durable temporal state)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_binding.py` (Evidence binding validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_binding_events.py` (Evidence event projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_binding_history.py` (Evidence binding history projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_autonomous_execution.py` (Compiled temporal execution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Behavior compilation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/action_results.py` (Temporal action results)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_resources.py` (Temporal resource model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/history_event.py` (Temporal history events)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/history_event_serialization.py` (Temporal history event serialization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/temporal.py` (Resolved temporal model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/manager.py` (Shared-time driver lifecycle)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/manager_plan_admission.py` (Admission diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_action_validation.py` (Protected temporal state)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_episode_control.py` (Temporal episode control)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_execution_scheduler_state.py` (Temporal scheduler state)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_concurrency.py` (Temporal concurrent dispatch)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_concurrent_commit.py` (Temporal commit isolation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_concurrent_dispatch.py` (Temporal dispatch isolation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_concurrent_state.py` (Temporal concurrent state)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_operations.py` (Temporal scheduling operations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_binding.py` (Autonomous action-request binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_due.py` (Temporal scheduler due-action selection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_policy.py` (Temporal scheduling policy)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_submission_options.py` (Temporal submission options)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/registry.py` (Conformance runtime-manager interoperation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/time_control.py` (Authoritative time advancement)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/autonomous-execution.md` (Schedules, cadence, dwell, deadlines and lifecycle)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published authoring contract)
- IMPLEMENTS → SPEC `contracts/schemas/snapshots/runtime-snapshot-v1.json` (Published evidence and assessment carriers)
- DOCUMENTS → DOCUMENTATION `examples/scenarios/temporal-profiles/README.md` (User/automation mapping, capabilities and limits)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_profiles.py` (Imports, parameters, bindings and examples)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_admission.py` (Limited/rich manifests and conditional conformance)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_runtime.py` (Deadline, dwell, generation and retry enforcement)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_durability.py` (History, persistence and legacy identity)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_security.py` (Evidence authorization and backend mutation isolation)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_conformance.py` (Probe-owned clock driver shutdown on success and failure)
- TESTS → TEST `implementations/python/tests/test_dsl_437_benign_participant_execution.py` (Cadence, windows, intervals, dependencies, retries and cooldowns)
- TESTS → TEST `implementations/python/tests/_act_614_temporal_fixtures.py` (Temporal fixture support)
- TESTS → TEST `implementations/python/tests/test_issue_898_participant_execution_control.py` (Execution-control regression)
- TESTS → TEST `implementations/python/tests/test_issue_1181_unified_control_plane_mutations.py` (Control-plane mutation regression)
- TESTS → TEST `implementations/python/tests/test_participant_concurrent_batch_reservations.py` (Concurrent reservation regression)
