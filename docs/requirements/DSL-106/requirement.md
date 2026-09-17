---
id: DSL-106
title: "Aggregated Authoring Diagnostics And Advisories"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:55:57.673618Z
updated_at: 2026-04-05T00:58:59.685304Z
---

# DSL-106 — Aggregated Authoring Diagnostics And Advisories

## Statement

The ecosystem shall provide aggregated structural and semantic diagnostics together with non-fatal advisories for authoring-visible issues.

## Rationale

Requirement inventory phase. Status audit deferred until the full canonical graph is complete.

## Traceability

- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md` (SDL validation docs for aggregated errors and advisories)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/parser.md` (Parser docs for author-visible advisories on successful parse)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/index.md` (SDL overview showing Scenario.advisories for authors)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/testing.md` (Testing strategy for clean parser and validation diagnostics)
- CONSTRAINS → ADR `docs/decisions/adrs/adr-001-scenario-description-language.md` (ADR-001: validator collects all errors rather than failing fast)
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py` (Validator tests for aggregated errors and advisory emission)
- TESTS → TEST `implementations/python/tests/test_sdl_parser.py` (Parser tests for author-visible advisories)
- TESTS → TEST `implementations/python/tests/test_sdl_fuzz.py` (Fuzz tests for clean diagnostic behavior under invalid inputs)
- TESTS → TEST `implementations/python/tests/test_example_schema_conformance.py` (Scenario loading and published-schema tests expecting advisory-clean curated examples)
- IMPLEMENTS → SPEC `specs/sdl/diagnostics.md` (specs/sdl/diagnostics.md §5: normative SDL error-vs-advisory classification criterion)
- TESTS → TEST `implementations/python/tests/test_sdl_diagnostic_boundary.py` (AST drift guard for validator advisory/error channel separation)
