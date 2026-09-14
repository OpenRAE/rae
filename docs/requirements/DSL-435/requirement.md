---
id: DSL-435
title: "Stateful Realization Resource Declarations"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-07-15T02:40:07.724312Z
updated_at: 2026-07-15T02:43:21.148745Z
---

# DSL-435 — Stateful Realization Resource Declarations

## Statement

The language and processor shall support first-class, backend-neutral declarations for generated artifacts and persistent volumes, compile them into stable-addressed provisioning resources with validated dependency ordering and exact realization provenance, and require provisioner manifests to declare honest support before dispatch.

## Rationale

Downstream scenarios need to declare generated certificate/configuration artifacts and persistent data volumes as desired state. Reusing observed runtime mounts, generic metadata, content placement, or provider-specific fragments loses lifecycle, access, sensitivity, provenance, dependency, and capability semantics and permits unsupported realization to proceed ambiguously.

## Traceability

- TESTS → TEST `implementations/python/tests/test_sdl_catalog_parity.py` (implementations/python/tests/test_sdl_catalog_parity.py)
- TESTS → TEST `implementations/python/tests/test_sdl_lineage.py` (implementations/python/tests/test_sdl_lineage.py)
- DOCUMENTS → SPEC `specs/sdl/stateful-resources.md` (Stateful realization resources)
- TESTS → TEST `implementations/python/tests/test_stateful_realization_resources.py` (implementations/python/tests/test_stateful_realization_resources.py)
- IMPLEMENTS → ADR `docs/decisions/issue-780-dsl-435-stateful-realization-resources-preflight.md` (DSL-435 stateful realization resources preflight decision)
- IMPLEMENTS → CONFIG `contracts/schema-publication-manifest.json` (Published SDL schema manifest)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json` (Instantiated scenario snapshot schema)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated scenario schema)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL authoring input schema)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (Runtime control-plane admission tests)
- TESTS → TEST `implementations/python/tests/test_runtime_planner.py` (Runtime planner capability tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/stateful_resources.py` (implementations/python/packages/raes/stateful_resources.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/manifest.py` (implementations/python/packages/raes_backend_protocols/manifest.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/provisioner_capabilities.py` (implementations/python/packages/raes_backend_protocols/provisioner_capabilities.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/provisioner_manifest.py` (implementations/python/packages/raes_backend_protocols/provisioner_manifest.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_stubs/manifest.py` (implementations/python/packages/raes_backend_stubs/manifest.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/capabilities.py` (implementations/python/packages/raes_contracts/contracts/capabilities.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/schema_invariants.py` (implementations/python/packages/raes_contracts/contracts/schema_invariants.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/vocabulary.py` (implementations/python/packages/raes_contracts/vocabulary.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/__init__.py` (implementations/python/packages/raes_processor/planner/__init__.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/manifest_validation.py` (implementations/python/packages/raes_processor/planner/manifest_validation.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/stateful_admission.py` (implementations/python/packages/raes_processor/planner/stateful_admission.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_submission.py` (implementations/python/packages/raes_runtime/control_plane_submission.py)
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py` (Backend manifest generated-artifact capability tests)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1010` (SSH generated-artifact output isolation)
- IMPLEMENTS → ADR `docs/decisions/issue-1010-ssh-generated-artifact-output-isolation-preflight.md` (SSH generated-artifact output isolation preflight)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/artifact_generation.py`
- TESTS → TEST `implementations/python/tests/test_issue_1208_profile_selections.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_profiles.py`
- TESTS → TEST `implementations/python/tests/test_issue_1208_profile_composition.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/random_value.py` (Configurable random-value recipe for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/random_value_generation.py` (Portable random-value alphabets and reference generation for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/content.py` (Content text_from deferred generated-value binding for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/propositions.py` (StringPredicate expected_from deferred verification for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_stateful_resource_references.py` (Content and proposition generated-artifact reference admission for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_sections.py` (Stateful-resource reference validation wiring for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/planning.py` (Value-free run/instantiation scope identity on plan DTOs for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/capabilities.py` (Evaluator deferred-expected-comparison capability for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/manifest.py` (Reference random-value generator and scope capability declarations for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/stateful_resources.py` (Content-consumer projection for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/placement.py` (Content text_from ordering dependency for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/core.py` (Regeneration-scope reconciliation binding for issue #1276)
- IMPLEMENTS → ADR `docs/decisions/issue-1276-per-run-random-values-preflight.md` (Configurable per-run random values preflight)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1276` (Configurable random value generation for per-run scenario values)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py` (Published plan model run/instantiation scope identity for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/plan_projection.py` (Plan projection and digest scope identity for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_capability_schema.py` (Provisioner capability schema conditionals for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_models.py` (Plan API round-trip scope identity for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/manager.py` (RuntimeManager run/instantiation scope threading for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_realization.py` (Trial realization run/instantiation identity forwarding for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/reference.py` (Reference processor run/instantiation identity forwarding for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_sections.py` (Module namespace rewrite of content/proposition generated-artifact references for issue #1276)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/provisioner.py` (Reference generated-value retention across reconciliation for issue #1276)
- TESTS → TEST `implementations/python/tests/test_issue_1276_random_value_generation.py` (Configurable per-run random value generation tests)
