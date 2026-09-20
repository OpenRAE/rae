---
id: ASR-501
title: "Normative Machine-Readable Schemas"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:40:05.256734Z
updated_at: 2026-05-11T00:48:09.850578Z
---

# ASR-501 — Normative Machine-Readable Schemas

## Statement

The ecosystem shall publish authoritative normative machine-readable schemas for its external contracts, independent of any single reference implementation or code-generation pipeline.

## Rationale

Current state: partially implemented. Checked-in normative schemas exist under contracts/schemas, but publication and verification tooling still target legacy paths and the external contract inventory is not yet complete across the intended ecosystem surface.

## Traceability

- DOCUMENTS → DOCUMENTATION `contracts/README.md` (Contracts Overview)
- DOCUMENTS → DOCUMENTATION `contracts/schemas/README.md` (Schemas Overview)
- CONSTRAINS → ADR `ADR-009` (Normative Artifact Authority and Repository Structure)
- CONSTRAINS → SPEC `contracts/schemas/sdl/scenario-instantiation-request-v1.json` (Scenario Instantiation Request Schema)
- CONSTRAINS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v1.json` (Backend Manifest Schema)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/workflow-result-envelope-v1.json` (Workflow Result Envelope Schema)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Runtime Contract Tests)
- DOCUMENTS → GITHUB_ISSUE `#5` (Fix normative schema publication and verification paths)
- IMPLEMENTS → PULL_REQUEST `369` (PR #369 feat(sdl): add runtime inventory surfaces)
- IMPLEMENTS → CONFIG `contracts/schema-publication-manifest.json` (Schema Publication Manifest)
- IMPLEMENTS → CODE_FILE `tools/check_schema_publication.py` (Schema Publication Checker)
- IMPLEMENTS → CONFIG `noxfile.py` (Nox Contracts Gate)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (Schema Publication Manifest Tests)
- IMPLEMENTS → PULL_REQUEST `134` (PR #134 Add schema publication manifest verification)
- IMPLEMENTS → GITHUB_ISSUE `65` (Issue #65 Normative machine-readable schemas)
- CONSTRAINS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL authoring schema with runtime inventory, filesystem, mount, container, and health fields)
- CONSTRAINS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated SDL schema with normalized runtime inventory, filesystem, mount, container, and health fields)
- DOCUMENTS → GITHUB_ISSUE `363` (Issue #363 requires normative SDL schema coverage for runtime filesystem inventory fields)
- DOCUMENTS → GITHUB_ISSUE `368` (Issue #368 requires normative SDL schema coverage for container host/security/mount fields)
- IMPLEMENTS → CODE_FILE `tools/check_schema_coverage.py` (Published-schema coverage gate: corpus, formal, or declared evidence per contract)
- IMPLEMENTS → CODE_FILE `tools/check_json_artifacts.py` (Canonical corpus routing and the covered_schema_paths join the coverage gate consumes)
- IMPLEMENTS → CONFIG `tools/nox_support/policy_lanes.py` (Full-inventory published schema coverage policy stage)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/published-schema-coverage.md` (The published-schema coverage rule, repair order, and coverage association shape)
- IMPLEMENTS → CONFIG `contracts/schema-publication/entries/raes-semantic-invariants-v1.json` (Declared alternate coverage for the embedded-annotation profile)
- TESTS → TEST `implementations/python/tests/test_issue_1330_schema_coverage.py` (Published-schema coverage gate and backfilled contract corpora tests)
- IMPLEMENTS → GITHUB_ISSUE `1330` (Issue #1330 detect missing fixture or formal coverage for published schemas)
