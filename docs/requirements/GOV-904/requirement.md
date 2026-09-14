---
id: GOV-904
title: "RAES Semantic Diff and Impact Analysis"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-04-03T07:16:01.048495Z
updated_at: 2026-08-02T02:51:16.276043Z
---

# GOV-904 — RAES Semantic Diff and Impact Analysis

## Statement

RAES shall publish machine-readable semantic diff and impact-analysis contracts and APIs over admitted RAES scenarios, modules, tasks, runs, evidence specifications, and studies, preserving canonical identity, provenance, uncertainty, and explicit semantic loss. Presentation and pack-aware orchestration belong to consuming repositories.

## Rationale

Narrowed to the RAES semantic contract and analysis kernel consumed by Hub, env-packs, adapters, and backends.

## Traceability

- TESTS → TEST `implementations/python/tests/test_semantic_comparison.py` (GOV-904 semantic comparison contract and API tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-110-gov-904-semantic-diff-impact-analysis-preflight.md` (GOV-904 semantic comparison architecture preflight)
- IMPLEMENTS → CONFIG `contracts/profiles/semantic-comparison/reference-v1.json` (GOV-904 governed semantic comparison profile)
- IMPLEMENTS → SPEC `contracts/schemas/semantic-comparison/semantic-comparison-request-v1.json` (GOV-904 semantic comparison request contract)
- IMPLEMENTS → SPEC `contracts/schemas/semantic-comparison/semantic-comparison-result-v1.json` (GOV-904 semantic comparison result contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/semantic_comparison.py` (GOV-904 portable semantic comparison contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/semantic_comparison_results.py` (GOV-904 portable semantic comparison result contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison.py` (GOV-904 semantic comparison reference analyzer)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison_adapters.py` (GOV-904 admitted artifact adapters)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison_impact.py` (GOV-904 bounded impact traversal)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison_projections.py` (GOV-904 owner-specific semantic projections)
- IMPLEMENTS → GITHUB_ISSUE `110` (Issue 110: semantic diff and impact analysis)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#110` (Machine-readable RAES semantic diff and impact analysis (GOV-904))

- TESTS → TEST `implementations/python/tests/test_issue_1210_semantic_comparison.py` (Versioned presence, private data and observation comparisons)
