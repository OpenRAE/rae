---
id: GOV-903
title: "Migration And Upgrade Paths"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-03T07:16:00.908374Z
updated_at: 2026-07-11T01:46:42.049621Z
---

# GOV-903 — Migration And Upgrade Paths

## Statement

The ecosystem shall support migration and upgrade paths across language, processing, module, task, run, and study versions.

## Rationale

Requirement inventory expansion. Evolution requires explicit migration and upgrade paths across language, processing, module, task, run, and study artifacts.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/classification_migration.py` (Deterministic classification migration with atomic refusals and typed loss reports)
- TESTS → TEST `implementations/python/tests/test_classification_migration.py` (Legacy conversion, exact provenance, loss authorization and refusal tests)

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-075-ecosystem-versioning-deprecation-and-migration-governance.md` (ADR-075 Ecosystem Versioning, Deprecation, and Migration Governance)
- IMPLEMENTS → SPEC `specs/evolution/versioning-deprecation-and-migration.md` (Versioning, Deprecation, and Migration Specification)
- IMPLEMENTS → GITHUB_ISSUE `90` (Issue #90: Versioning, deprecation & migration governance)
