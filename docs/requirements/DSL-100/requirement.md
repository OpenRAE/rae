---
id: DSL-100
title: "Author-Facing Scenario Language"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:39:07.329914Z
updated_at: 2026-04-05T00:32:48.479695Z
---

# DSL-100 — Author-Facing Scenario Language

## Statement

The ecosystem shall provide a stable author-facing language for describing cyber-range scenarios and experiments.

## Rationale

Current state: partially implemented. A usable ecosystem needs a clear language surface that authors can rely on without knowing backend-specific execution details.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/parameter_derivations.py` (Portable configurable parameter derivation contract)
- TESTS → TEST `implementations/python/tests/test_issue_1481_parameter_authority.py` (Composed module strings and serialized phase evidence)

- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/parser.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/testing.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/precedents.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/limitations.md`
- DOCUMENTS → DOCUMENTATION `implementations/python/README.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/index.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/complex-scenarios.md`
- DOCUMENTS → SPEC `examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml`
- DOCUMENTS → SPEC `examples/scenarios/port-authority-surge-response.sdl.yaml`
- DOCUMENTS → SPEC `examples/scenarios/satcom-release-poisoning.sdl.yaml`
- CONSTRAINS → ADR `docs/decisions/adrs/adr-001-scenario-description-language.md`
- CONSTRAINS → ADR `docs/decisions/adrs/adr-002-declarative-sdl-objectives.md`
- CONSTRAINS → ADR `docs/decisions/adrs/adr-003-workflows-targetable-subobjects-and-enum-variables.md`
- CONSTRAINS → ADR `docs/decisions/adrs/adr-006-workflow-control-language-redesign.md`
- CONSTRAINS → SPEC `specs/formal/objectives/README.md`
- CONSTRAINS → SPEC `specs/formal/objectives/window-consistency.md`
- CONSTRAINS → SPEC `specs/formal/workflows/README.md`
- CONSTRAINS → SPEC `specs/formal/workflows/state-machine.md`
- CONSTRAINS → SPEC `specs/formal/workflows/compensation.md`
- CONSTRAINS → SPEC `specs/formal/composition-readiness.md`
- CONSTRAINS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json`
- CONSTRAINS → SPEC `contracts/schemas/sdl/scenario-instantiation-request-v1.json`
- TESTS → TEST `implementations/python/tests/test_scenarios.py`
- TESTS → TEST `implementations/python/tests/test_sdl_models.py`
- TESTS → TEST `implementations/python/tests/test_sdl_parser.py`
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py`
- TESTS → TEST `implementations/python/tests/test_sdl_module_registry.py`
- TESTS → TEST `implementations/python/tests/test_sdl_realworld.py`
- TESTS → TEST `implementations/python/tests/test_sdl_stress.py`
- TESTS → TEST `implementations/python/tests/test_sdl_fuzz.py`
- TESTS → TEST `implementations/python/tests/test_semantics_objectives.py`
- TESTS → TEST `implementations/python/tests/test_fm2_semantics.py`
- IMPLEMENTS → GITHUB_ISSUE `541` (Issue #541: Second review of SDL prose specification)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-541-sdl-spec-second-review-preflight.md` (Issue 541 SDL specification second-review preflight)
- IMPLEMENTS → CODE_FILE `tools/check_sdl_catalog_parity.py` (SDL authority and implementation parity gate)
- IMPLEMENTS → POLICY `tools/policy/requirement_order.yaml` (SDL language-surface ownership policy)
- IMPLEMENTS → SPEC `specs/formal/sdl-phases/README.md` (Formal SDL phase membership and transfer contract)
- IMPLEMENTS → SPEC `specs/sdl/sections.md` (Normative SDL section catalog)
- IMPLEMENTS → SPEC `specs/sdl/diagnostics.md` (Normative SDL diagnostics contract)
- IMPLEMENTS → SPEC `specs/sdl/references.md` (Normative SDL reference semantics)
- IMPLEMENTS → SPEC `specs/sdl/document-model.md` (Normative SDL document model)
- IMPLEMENTS → SPEC `specs/sdl/variables-and-instantiation.md` (Normative SDL variable and instantiation contract)
- TESTS → TEST `implementations/python/tests/test_sdl_catalog_parity.py` (SDL catalog parity regression tests)
- TESTS → TEST `implementations/python/tests/test_sdl_phase_contracts.py` (SDL phase contract regression tests)
- TESTS → TEST `implementations/python/tests/test_instantiated_scenario_schema.py` (Instantiated SDL schema regression tests)
