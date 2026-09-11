---
id: DSL-108
title: "Feature, Condition, And Vulnerability Modeling"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:55:57.908015Z
updated_at: 2026-04-05T01:04:22.622618Z
---

# DSL-108 — Feature, Condition, And Vulnerability Modeling

## Statement

The language shall model deployed features, health and assertion conditions, and classified vulnerabilities with explicit dependency and reference semantics.

## Rationale

Requirement inventory phase. Status audit deferred until the full canonical graph is complete.

## Traceability

- IMPLEMENTS → PULL_REQUEST `369` (PR #369 feat(sdl): add runtime inventory surfaces)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Native feature and condition sections with externally authored classifications)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md` (Native dependency validation and explicit classification migration)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/testing.md` (SDL testing matrix covering condition and vulnerability validation)
- CONSTRAINS → ADR `docs/decisions/adrs/adr-001-scenario-description-language.md` (Issue-989 amendment: native features and conditions remain operational; vulnerability classifications use external concept bindings)
- CONSTRAINS → ADR `docs/decisions/adrs/adr-004-sdl-runtime-layer.md` (ADR-004: node-scoped condition bindings and fail-closed condition references)
- CONSTRAINS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Native SDL feature and condition configuration)
- CONSTRAINS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated native feature and condition configuration)
- CONSTRAINS → SPEC `contracts/schemas/concept-authority/external-concept-bindings-v1.json` (Classified weaknesses as exact-subject authored assertions, distinct from native configuration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/classification_migration.py` (Explicit conversion of historical weakness declarations and associations)
- TESTS → TEST `implementations/python/tests/test_classification_migration.py` (Weakness classification migration, provenance and native configuration independence)
- TESTS → TEST `implementations/python/tests/test_sdl_models.py` (Native feature and condition rules, with historical CWE model compatibility)
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py` (Condition/dependency validation and rejection of retired vulnerability references)
- TESTS → TEST `implementations/python/tests/test_runtime_models.py` (Runtime model tests for feature dependency and condition binding semantics)
- TESTS → TEST `implementations/python/tests/test_sdl_stress.py` (Native feature, condition and dependency stress scenarios)
- TESTS → TEST `implementations/python/tests/test_sdl_realworld.py` (Real-world native configuration and condition-backed objective scenarios)
- DOCUMENTS → GITHUB_ISSUE `368` (Issue #368 container health observations and runtime condition facts)
- TESTS → TEST `implementations/python/tests/test_sdl_parser.py` (Parser tests for runtime health and container observation fields)
- VERIFIES → SPEC `examples/scenarios/techvault.sdl.yaml` (TechVault scenario example exercising runtime health observation facts)
