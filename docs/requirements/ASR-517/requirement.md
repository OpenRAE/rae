---
id: ASR-517
title: "Normative Artifact Authority Boundary"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-04T22:58:17.268810Z
updated_at: 2026-05-17T22:14:30.798337Z
---

# ASR-517 — Normative Artifact Authority Boundary

## Statement

The ecosystem shall define an explicit authority boundary in which normative prose, schemas, fixtures, and conformance profiles are authoritative independent of any reference implementation or code-generation pipeline.

## Rationale

Normative authority must be explicit so ecosystem contracts and semantics are not effectively owned by a single reference implementation or schema-generation workflow.

## Traceability

- IMPLEMENTS → SPEC `specs/authority/authority-boundary.yaml` (Normative Artifact Authority Boundary (canonical manifest))
- IMPLEMENTS → CODE_FILE `tools/check_authority_boundary.py` (Structural gate enforcing the authority-boundary manifest)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md` (ADR-019: Canonical Manifest for the Normative Artifact Authority Boundary)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md` (ADR-009: Normative Artifact Authority and Repository Structure (pre-existing authority decision))
- TESTS → TEST `implementations/python/tests/test_authority_boundary.py` (Tests for the authority-boundary structural gate)
- IMPLEMENTS → GITHUB_ISSUE `69` (Normative artifact authority boundary (ASR-517))
- IMPLEMENTS → CODE_FILE `tools/check_generated_schemas.py` (Schema compatibility-proof checker (ADR-009 §7))
- IMPLEMENTS → POLICY `tools/policy/conftest/repo_policy.rego` (Legacy top-level root and concept-authority path policy rules)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (Compatibility-proof + schema-authority gate tests)
- TESTS → TEST `tools/policy/conftest/repo_policy_test.rego` (Legacy top-level root and concept-authority Rego rule tests)
