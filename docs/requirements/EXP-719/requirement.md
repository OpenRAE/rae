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

- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-binding-descriptors-v1.json` (experiment-binding-descriptors-v1 published schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_allocation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_factorial.py`
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
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/random_stream_engine.py`
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
