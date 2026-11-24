---
id: EXP-719
title: "Treatment And Controlled Variation Design"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-04-03T07:58:36.711782Z
updated_at: 2026-10-25T03:14:54.767864Z
---

# EXP-719 — Treatment And Controlled Variation Design

## Statement

The ecosystem shall support first-class treatment, factor, condition, and controlled-variation definitions for studies and repeated runs.

## Rationale

Requirement inventory expansion. Designed variation is a distinct experiment concern and should not be left implicit inside ad hoc run metadata.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `1666` (Compile and verify typed factorial treatments)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/__init__.py` (Expose source-aware trial readmission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/effects.py` (Compare resolved scenario and participant effects)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/sources.py` (Check complete authoring coordinates, bindings, and selections)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/readmission.py` (Readmit plans against trusted original inputs)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/replacement_inputs.py` (Share replacement coordinates with source-aware realization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/selected_scenario.py` (Admit typed targets through SDL authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/experiment_selection.py` (Check intended family without ordinary policies)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/apparatus.py` (Reuse pinned manifest checks during realization)
- TESTS → TEST `implementations/python/tests/test_issue_1666_factorial_compilation.py` (Cross independent model and prompt factors with structural effects)
- TESTS → TEST `implementations/python/tests/test_issue_1666_factorial_admission.py` (Reject invalid combinations and equal effects atomically)
- TESTS → TEST `implementations/python/tests/test_issue_1666_factorial_replay.py` (Verify source joins, allocation replay, realization, and archives)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/typed-factorial-example.md` (Explain supported forms and public lifecycle use)
- IMPLEMENTS → CODE_FILE `implementations/python/examples/factorial_treatments.py` (Demonstrate public loader, compiler, readmission, and one-entry APIs)

- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-binding-descriptors-v1.json` (experiment-binding-descriptors-v1 published schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_allocation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/random_stream.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_factorial.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_treatments.py` (Shared typed selection source, owner, and family joins)
- TESTS → TEST `implementations/python/tests/test_issue_1665_factorial_treatments.py` (Typed treatment contracts, exact archival criteria, and compatibility)
- TESTS → TEST `implementations/python/tests/test_issue_1665_treatment_type_agreement.py` (Boolean and numeric outcome agreement at all treatment boundaries)
- TESTS → TEST `implementations/python/tests/test_exp_719_factorial_allocation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan_components.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/batch_execution.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_bindings.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_conditions.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_spec.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_study.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_analysis.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_coordinate_order.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/experiment_spec.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/random_stream_engine.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/bindings.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/inputs.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/models.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/policies.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_scheduler.py`
- IMPLEMENTS → GITHUB_ISSUE `275`
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/batch-execution-receipt-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-authoring-input-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-study-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/plans/admitted-trial-plan-v1.json`
- TESTS → TEST `implementations/python/tests/test_exp_719_factorial_ingress.py`
- TESTS → TEST `implementations/python/tests/test_exp_719_factorial_realization.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_realization.py`
- TESTS → TEST `implementations/python/tests/test_exp_719_review_regressions.py`
- TESTS → TEST `implementations/python/tests/test_issue_1626_trial_participant_bindings.py` (Explicit participant-only conditions, exact owner admission, complete configuration and safe atomic rejection)
