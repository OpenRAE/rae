---
id: ASR-516
title: "RAES Authoring Adapter Semantic Consistency"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-04-03T07:17:05.483661Z
updated_at: 2026-09-16T02:12:52Z
---

# ASR-516 — RAES Authoring Adapter Semantic Consistency

## Statement

RAES shall publish conformance vectors that let CLI, agent or MCP, graphical, and documentation-driven adapters prove that they produce equivalent canonical RAES artifacts, diagnostics, and semantic results for the same admitted inputs. Concrete user journeys, pack files, and runtime outcomes remain under their owning repositories.

## Rationale

Retains the RAES conformance responsibility while HUB-6 owns cross-product task and acceptance coordination.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `1005` (ASR-516 — RAES Authoring Adapter Semantic Consistency)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1005-asr-516-authoring-adapter-semantic-consistency-preflight.md` (ASR-516 authoring adapter semantic consistency architecture preflight)
- IMPLEMENTS → DOCUMENTATION `specs/conformance/authoring-adapters.md` (Bounded authoring observation and independent comparison-axis contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/authoring_adapters.py` (Closed vector, profile and comparison contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle.py` (Published authoring contract registration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/authoring_adapters.py` (Profile-bound corpus loading and authoring-path comparison)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/_authoring_observations.py` (Production output admission and incumbent evidence projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/validators.py` (Authoring conformance model registration)
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml` (Bounded conformance delivery ownership with retained prerequisites)
- IMPLEMENTS → DOCUMENTATION `contracts/schemas/authoring-adapters/authoring-adapter-vector-v1.json` (Portable vector contract)
- IMPLEMENTS → DOCUMENTATION `contracts/schemas/authoring-adapters/authoring-adapter-comparison-v1.json` (Portable independent-axis comparison contract)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/authoring-adapter-conformance.md` (Consumer API and finite-evidence boundaries)
- TESTS → TEST `implementations/python/tests/test_authoring_adapters.py` (Published positive and negative vectors, evidence mutation, bounds and admission regressions)
- TESTS → TEST `implementations/python/tests/test_corpus_packaging.py` (Authoring-vector execution from an installed wheel)
- TESTS → TEST `implementations/python/tests/test_authoring_adapter_governance.py` (Scoped ownership, prerequisites and traceability enforcement)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Source-bound evidence replay after authoring conformance changes)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Current formal replay with immutable historical captures)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Evidence release selection, historical isolation and source integrity)
