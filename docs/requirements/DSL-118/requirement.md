---
id: DSL-118
title: "Participant Control Context And Instruction Surface"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:06.664729Z
updated_at: 2026-04-05T01:24:06.664729Z
---

# DSL-118 — Participant Control Context And Instruction Surface

## Statement

The language shall support participant control-context artifacts such as directives, policies, instructions, and similar execution-guiding context without binding the ecosystem to one participant implementation style.

## Rationale

Primary-source refresh shows that participant execution often depends on authored control context, but the ecosystem should model that context generically rather than around one prompting or policy framework.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `299`
- IMPLEMENTS → SPEC `specs/sdl/participant-control-context.md`
- IMPLEMENTS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v2.json`
- IMPLEMENTS → SPEC `contracts/schemas/participant-implementation-configuration/participant-configuration-result-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/participant-implementation-manifest/participant-implementation-manifest-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/plans/admitted-trial-plan-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/processor-manifest/processor-manifest-v2.json`
- IMPLEMENTS → SPEC `contracts/schemas/satisfiability/scenario-satisfiability-evidence-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/materialized-scenario-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_behavior_authoring.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_language_metadata.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_mapping_scopes.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_module_symbols.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_reference_targetability.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/agents.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_expand.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/instantiate.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_control_context.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/scenario.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/base.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_bindings.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_context.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_occurrence_v2.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_occurrence_v2_policy.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_occurrence_v2_state.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_occurrence_v2_validation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_flow_control.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_manifests.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_configuration.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_resources.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/runtime_model.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/bindings.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py`
- TESTS → TEST `implementations/python/tests/test_dsl_118_control_context.py`
- TESTS → TEST `implementations/python/tests/test_dsl_118_trial_control_context.py`
- IMPLEMENTS → DOCUMENTATION `docs/explain/sdl/control-context-migration.md`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_control_context.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_bundle_access.py`
- IMPLEMENTS → SPEC `contracts/provenance/sdl-lineage-ledger-v2.json`
- TESTS → TEST `implementations/python/tests/test_sdl_lineage.py`
- TESTS → TEST `implementations/python/tests/test_sdl_catalog_parity.py`
- TESTS → TEST `implementations/python/tests/test_contracts_facade_exports.py`
- TESTS → TEST `implementations/python/tests/test_issue_1339_relationship_endpoints.py`
- TESTS → TEST `implementations/python/tests/fixtures/issue-1339-declaration-kinds.sdl.yaml`
