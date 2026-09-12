# Issue #1204 clause verification

This checklist maps the proposed delivery to the issue's acceptance criteria
and ASR-532, SEM-218, and SEM-219. Checked means implemented and covered by the
named local regressions, not merged or certified. CI, review, and merge remain
separate workflow gates. Python paths below are relative to
`implementations/python/`; line anchors identify the owning entry points.

## Issue acceptance

- [x] Compiler and authenticated handoff retain leaf domains, closure,
  defaults, and author provenance. Owners:
  `packages/raes_processor/compiler/realization_recursive_constraints.py:225`,
  `packages/raes_contracts/plan_projection.py`, and
  `packages/raes_runtime/control_plane_plan_authorization.py:16`.
  Tests: `tests/test_issue_1204_recursive_carriage.py:89`,
  `tests/test_issue_1204_recursive_defaults.py`, and
  `tests/test_issue_1204_profile_carrier.py` (authenticated plan tampering).
- [x] Unsupported semantics and capabilities fail before mutation when known.
  Owners: `packages/raes_processor/semantics/realization_support.py:25`,
  `packages/raes_runtime/backend_preparation.py:117`, and
  `packages/raes_processor/planner/prepared_node_support.py:16`.
  Tests: `tests/test_issue_1204_preparation_admission.py`,
  `tests/test_issue_1204_prepared_node_semantics.py`, and
  `tests/test_issue_1204_preparation_os.py:112`.
- [x] Runtime compares actual values and coverage under the admitted relation,
  retains selected observation strength, and validates the safe projection
  before replacement. Owners:
  `packages/raes_processor/semantics/realization_runtime_evaluation.py:176`,
  `packages/raes_runtime/backend_calls.py:165`.
  Tests: `tests/test_issue_1204_recursive_carriage.py:139`,
  `tests/test_issue_1204_recursive_carriage.py:209`, and
  `tests/test_issue_985_runtime_observation_contract.py`.
- [x] Core and attached extension-profile values use the same bounded relation;
  open siblings cannot erase exact siblings or grant participant authority.
  Owners: `packages/raes_contracts/realization_profiles.py:158`,
  `packages/raes_runtime/backend_profiles.py:73`,
  `packages/raes_processor/compiler/participant_behaviors.py:335`.
  Tests: `tests/test_issue_1204_reference_profiles.py`,
  `tests/test_issue_1204_profile_offline.py` (no external schema retrieval),
  `tests/test_issue_1200_mixed_runtime_constraints.py`, and
  `tests/test_sem_208_participant_behavior.py:931`.
- [x] Nested positive and negative cases cross parser, compiler, portable plan,
  authenticated handoff, observation projection, and accepted-state boundaries.
  Tests: `tests/test_issue_1204_nested_domains.py`,
  `tests/test_issue_1204_recursive_environment.py`,
  `tests/test_issue_1204_profile_carrier.py`, and
  `tests/test_issue_1204_recursive_carriage.py:106`.
- [x] An opt-in backend may provide one jointly supported completion without
  claiming universal Linux support. Legacy envelope coverage remains unchanged.
  Owners: `packages/raes_processor/planner/realization_preparation.py:133`,
  `packages/raes_runtime/backend_preparation.py:117`.
  Contract: `specs/sdl/backend-realization-preparation.md` (repository root).
  Tests: `tests/test_issue_1204_preparation_os.py:112`,
  `tests/test_issue_1204_prepared_sequence.py` (selected sequence delivery),
  `tests/test_issue_1204_preparation_os.py:131`, and
  `tests/test_issue_1204_preparation_contract.py`.
- [x] Backend-resolvable open choices are not mandatory author input; exact
  descendants and native execution prerequisites still constrain preparation.
  Owners: `packages/raes_processor/compiler/realization_recursive_constraints.py:225`,
  `packages/raes_processor/planner/prepared_node_admission.py:82`.
  Tests: `tests/test_issue_1204_specialized_constraints.py`,
  `tests/test_issue_1204_backend_preparation.py`, and
  `tests/test_issue_1204_prepared_node_semantics.py`.
- [x] #1212 demand policy and #1112 capture admission remain the observation
  authority; exact detail creates no experimental capture/retention/export floor.
  Owners: `packages/raes_runtime/observation_admission.py:34`,
  `packages/raes_processor/compiler/realization_compute_substrate.py`.
  Tests: `tests/test_issue_1204_substrate_handoff.py` and
  `tests/test_issue_1204_preparation_admission.py`.
- [x] Selections are reportable with their actual basis; selected corroboration
  and augmentation obligations retain honest strength labels. Owners:
  `packages/raes_runtime/backend_calls.py:393`,
  `packages/raes_processor/semantics/realization_runtime_evaluation.py:226`,
  `packages/raes_runtime/observation_admission.py:254`.
  Tests: `tests/test_issue_1204_substrate_handoff.py`,
  `tests/test_issue_1043_realization_corroboration.py`, and
  `tests/test_sem_218_runtime_realization.py`.
- [x] Additional portable nodes require prepared, plan-owned collection
  authority; exact membership remains binding. Owners:
  `packages/raes_processor/planner/realization_collections.py:27`,
  `packages/raes_processor/planner/realization_collections.py:114`,
  `packages/raes_processor/planner/prepared_node_admission.py:30`.
  Tests: `tests/test_issue_1204_resource_collections.py`,
  `tests/test_issue_1204_prepared_node_admission.py`, and
  `tests/test_issue_1204_collection_lifecycle.py`.
- [x] Successful results cannot rewrite resource identity or runtime-domain
  ownership. Owners: `packages/raes_runtime/backend_entry_transitions.py:47`,
  `packages/raes_runtime/backend_effect_transitions.py:50`.
  Tests: `tests/test_issue_1204_result_owners.py` and
  `tests/test_issue_1204_targeted_effects.py`.
- [x] CREATE, UPDATE, DELETE, and UNCHANGED accounting detects omitted and false
  change claims. Owners: `packages/raes_runtime/backend_entry_transitions.py:76`,
  `packages/raes_runtime/backend_calls.py:449`.
  Tests: `tests/test_issue_1204_result_transitions.py:45`,
  `tests/test_issue_1204_result_transitions.py:58`,
  `tests/test_issue_1204_result_transitions.py:65`, and
  `tests/test_issue_1204_result_transitions.py:71`.
- [x] All four admitted #158 perturbations assert the precise invariant
  diagnostic and predecessor preservation without expected-failure markers.
  Tests: `tests/test_issue_158_runtime_result_integrity.py:170`,
  `tests/test_issue_158_runtime_result_integrity.py:175`,
  `tests/test_issue_158_runtime_result_integrity.py:180`, and
  `tests/test_issue_158_runtime_result_integrity.py:185`.

## Requirement clauses

- [x] ASR-532: validate backend results at the execution boundary and reject or
  sanitize portable-contract violations. Owners:
  `packages/raes_runtime/backend_calls.py:165`,
  `packages/raes_runtime/backend_snapshot_contracts.py`,
  `packages/raes_runtime/backend_input_contracts.py:12`.
  Tests: `tests/test_issue_1204_result_shapes.py`,
  `tests/test_issue_1204_input_bounds.py`, and
  `tests/test_issue_1204_prepared_credentials.py`.
- [x] ASR-532: preserve plan authority and runtime-domain ownership. Owners:
  `packages/raes_runtime/backend_entry_transitions.py:76`,
  `packages/raes_runtime/backend_effect_transitions.py:50`.
  Tests: `tests/test_issue_1204_result_owners.py`,
  `tests/test_issue_1204_targeted_effects.py`, and
  `tests/test_issue_1204_resource_collections.py`.
- [x] ASR-532: enforce snapshot transitions and preserve the trusted predecessor
  with structured invariant diagnostics on rejection. Owners:
  `packages/raes_runtime/backend_calls.py:464`,
  `packages/raes_runtime/backend_entry_transitions.py:65`.
  Tests: `tests/test_issue_1204_result_transitions.py`,
  `tests/test_issue_1204_result_durability.py`, and
  `tests/test_issue_158_runtime_result_integrity.py:170`.
- [x] SEM-218: distinguish binding declarations from processor/backend choices
  and define when realization is permitted. Owner:
  `packages/raes_processor/compiler/realization_recursive_constraints.py:225`.
  Tests: `tests/test_issue_1204_recursive_defaults.py` and
  `tests/test_issue_1204_specialized_constraints.py`.
- [x] SEM-218: honor exact constraints and reject unsupported requirements
  without approximation. Owners:
  `packages/raes_processor/semantics/realization_support.py:124`,
  `packages/raes_processor/semantics/realization_runtime_evaluation.py:176`.
  Tests: `tests/test_issue_1204_recursive_carriage.py:139` and
  `tests/test_issue_1204_preparation_os.py:112`.
- [x] SEM-219: keep authored availability and visibility independent. Existing
  owners: `packages/raes_processor/compiler/participant_behaviors.py:335`,
  `specs/formal/participant-semantics/README.md:1364` (repository root).
  Tests: `tests/test_sem_208_participant_behavior.py:866`,
  `tests/test_sem_208_participant_behavior.py:909`, and
  `tests/test_sem_208_participant_behavior.py:931`.
- [x] SEM-219: invocation is independently admitted and referenced constraints
  remain binding. Existing owner:
  `packages/raes_runtime/participant_action_validation.py:23`; this delivery
  additionally restricts effects to the authenticated request's targets through
  `packages/raes_runtime/participant_effect_authority.py`.
  Tests: `tests/test_sem_208_participant_behavior.py:953`,
  `tests/test_issue_898_participant_execution_control.py`, and
  `tests/test_issue_1204_targeted_effects.py`.

## Approved design boundaries

- [x] Read-only, opt-in preparation with original-authority and selected-result
  validation; no complete joint-offer manifest requirement.
- [x] Additional portable nodes declared before apply, never inferred from a
  successful backend result or a backend-internal implementation choice.
- [x] Optional authenticated plan-level profiles with pinned local definitions,
  independently checked support, and installed backend semantic validation.
  No new SDL authoring syntax or dynamic semantic-handler loading.
- [x] ADR-105 production adoption amended in the delivery diff; acceptance
  becomes authoritative through review and merge, not this local checklist.
