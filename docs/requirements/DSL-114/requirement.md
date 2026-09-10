---
id: DSL-114
title: "External Knowledge Reference Surface"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-04-03T07:16:31.644847Z
updated_at: 2026-07-30T18:38:36.635787Z
---

# DSL-114 — External Knowledge Reference Surface

## Statement

The language shall provide author-facing constructs for declaring references and mappings between native constructs and external knowledge vocabularies, taxonomies, and enumerations.

## Rationale

Requirement inventory expansion. The author-facing language needs an explicit surface for external knowledge bindings when they matter.

## Traceability

- CONSTRAINS → ADR `docs/decisions/adrs/adr-001-scenario-description-language.md` (Issue-989 amendment authorizing externalized classification coverage)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/classification_migration.py` (Explicit atomic legacy classification conversion into generic bindings)
- IMPLEMENTS → SPEC `specs/concept-authority/classification-migration.md` (Classification inventory, canonical disposition and migration contract)
- TESTS → TEST `implementations/python/tests/test_classification_migration.py` (Exact-subject conversion, refusal, provenance and native noninterference)
- IMPLEMENTS → GITHUB_ISSUE `989` (Replace domain-shaped SDL classifications with generic concept bindings)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/external_concept_subjects.py` (Exact RAES subject adapter for external concept bindings)
- TESTS → TEST `implementations/python/tests/test_external_concept_bindings.py` (External concept binding structural and semantic tests)
- DOCUMENTS → DOCUMENTATION `specs/concept-authority/external-concept-bindings.md` (External concept binding normative specification)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#986` (Define portable external concept-scheme references and binding assertions)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/external_concept_bindings.py` (Portable external concept binding contract)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/external-concept-bindings-v1.json` (Published external concept bindings schema)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#104` (External knowledge reference surface (DSL-114))
