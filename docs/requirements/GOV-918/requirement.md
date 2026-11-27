---
id: GOV-918
title: "Cross-Artifact Concept Binding"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-05T15:37:12.079287Z
updated_at: 2026-04-06T03:48:56.348597Z
---

# GOV-918 — Cross-Artifact Concept Binding

## Statement

SDL, manifests, contracts, provenance records, evidence requirements, and reporting artifacts shall bind their declared meaning to canonical concepts rather than relying only on repeated labels or artifact-local definitions.

## Rationale

Portability breaks down when SDL, processor manifests, backend manifests, and reporting surfaces reuse the same strings without binding them to shared meaning.

## Traceability

- TESTS → TEST `implementations/python/tests/test_concept_authority.py` (Concept binding entry and cross-catalog validation tests)
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py` (Backend manifest concept binding validation tests)
- TESTS → TEST `implementations/python/tests/test_processor_manifest.py` (Processor manifest concept binding validation tests)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Concept binding schema shape and drift detection tests)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-concept-model.md` (Shared concept model design guidance with GOV-918 binding example)
- DOCUMENTS → DOCUMENTATION `contracts/schemas/README.md` (Schema README documenting cross-artifact concept binding section)
- TESTS → TEST `implementations/python/tests/test_requirement_governance.py` (Requirement governance branch UID detection regression test)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (Repository policy tooling tests)
- TESTS → TEST `implementations/python/tests/test_runtime_manager.py` (Runtime manager tests updated for concept bindings)
- TESTS → TEST `implementations/python/tests/test_runtime_planner.py` (Runtime planner tests updated for concept bindings)
- TESTS → TEST `implementations/python/tests/test_runtime_registry.py` (Runtime registry tests updated for concept bindings)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-033-scenario-delivery-boundary-for-runtime-node-state.md` (ADR-033: Scenario/Delivery Boundary for Runtime Node State)
- CONSTRAINS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL authoring schema redaction guards for runtime mount/control fields)
- CONSTRAINS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated scenario schema redaction guards for runtime mount/control fields)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/precedents.md` (SDL design precedents scenario/delivery omission boundary)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/limitations.md` (SDL limitations deployment authoring boundary documentation)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (SDL sections reference for runtime mount/control boundary fields)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md` (SDL validation rules for runtime redaction boundary guards)
- TESTS → TEST `implementations/python/tests/test_runtime_models.py` (Runtime model tests for mount/control redaction and duplicate validation)
- TESTS → TEST `implementations/python/tests/test_sdl_models.py` (SDL model tests for runtime mount/control redaction fields)
- TESTS → TEST `implementations/python/tests/test_sdl_parser.py` (SDL parser tests for runtime mount/control redaction fields)
- IMPLEMENTS → PULL_REQUEST `409` (docs: fix scenario delivery drift wording)
- IMPLEMENTS → DOCUMENTATION `docs/explain/sdl/scenario-delivery-drift-audit.md` (Scenario/Delivery Classification Drift Audit and Remediation)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/index.md` (SDL guide navigation for scenario/delivery drift audit and remediation)
- DOCUMENTS → DOCUMENTATION `docs/index.md` (Published documentation toctree for scenario/delivery drift audit and remediation)
- TESTS → TEST `implementations/python/tests/test_design_drift_audit.py` (Scenario/delivery drift audit remediation coverage test)
- IMPLEMENTS → SPEC `contracts/concept-authority/concept-families-v1.json` (runtime-inventory native concept family binding nodes.*.runtime to a canonical concept)
- IMPLEMENTS → SPEC `contracts/concept-authority/reference-models-v1.json` (scenario-node-runtime reference model anchoring nodes.*.runtime to runtime-inventory)
- IMPLEMENTS → SPEC `contracts/profiles/semantic/reference-stack-v1.json` (Reference-stack semantic profile authoring-phase runtime-inventory coverage)
- DOCUMENTS → DOCUMENTATION `specs/concept-authority/concept-authority.md` (Runtime-inventory extension-governance decision path (Extension Discipline))
- TESTS → TEST `implementations/python/tests/test_reference_models.py` (Node-runtime reference model + nullable-optional binding resolution tests)
- TESTS → TEST `implementations/python/tests/test_semantic_profiles.py` (Reference-stack authoring runtime-inventory coverage test)
- IMPLEMENTS → GITHUB_ISSUE `493` (Issue #493: runtime-inventory family + reference model for nodes.*.runtime)
- IMPLEMENTS → PULL_REQUEST `532` (PR #532: add runtime-inventory concept family and node runtime reference model)
- IMPLEMENTS → CODE_FILE `tools/check_concept_authority_governance.py` (Concept-authority catalog governance gate (ADR-linkage + reference resolution))
- TESTS → TEST `implementations/python/tests/test_concept_authority_governance.py` (Concept-authority governance gate tests (failure modes, boundaries, catalog error paths))
- DOCUMENTS → ADR `docs/decisions/adrs/adr-062-concept-authority-catalog-governance-gate.md` (ADR-062: Concept-Authority Catalog Governance Gate)
- IMPLEMENTS → GITHUB_ISSUE `496` (Issue #496: Concept authority governance gate — new family requires ADR linkage (review CA-6))
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/semantic-projection-report-v1.json` (semantic-projection-report-v1 published schema)
