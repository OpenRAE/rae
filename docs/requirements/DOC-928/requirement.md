---
id: DOC-928
title: "Curated public documentation and enforced reader-first style"
status: ACTIVE
type: CONSTRAINT
priority: MUST
created_at: 2026-07-27T01:41:08.996409Z
updated_at: 2026-07-27T05:12:56.396922Z
---

# DOC-928 — Curated public documentation and enforced reader-first style

## Statement

RAES shall publish documentation only from an explicit curated public source root; public entry pages shall use task-first, example-led guidance with Stripe Documentation as the explicit editorial exemplar; repository gates shall enforce the RAES public-documentation style with Vale and verify that builds, search indexes, sitemaps, and previews exclude developer working records; developer documentation shall remain available through a separate repository index.

## Rationale

Issue #928 establishes a public documentation publication boundary and adds an executable Vale quality gate. A durable requirement is needed so the public source root, reader-first documentation standard, and enforcement artifacts have Ground Control traceability instead of existing as unowned CI policy.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `928` (Public project readiness: OpenSSF integrations and approachable documentation)
- IMPLEMENTS → DOCUMENTATION `docs/public/index.md` (RAES public documentation index)
- IMPLEMENTS → DOCUMENTATION `docs/public/quickstart.md` (Public quickstart guide)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/documentation-style-guide.md` (Documentation style guide with Stripe exemplar)
- IMPLEMENTS → CODE_FILE `tools/check_public_docs.py` (Public docs policy checker)
- IMPLEMENTS → CODE_FILE `tools/public_docs_guard.py` (Sphinx publication guard and cache invalidation)
- IMPLEMENTS → CODE_FILE `tools/public_docs_markup.py` (MyST publication-boundary source checks)
- IMPLEMENTS → CONFIG `docs/public/conf.py` (Public documentation build and guard registration)
- IMPLEMENTS → CONFIG `docs/governance/requirement-scopes/954.json` (Issue-bound documentation verification scope)
- IMPLEMENTS → GITHUB_ISSUE `954` (Publication-boundary enforcement and reporting contact)
- TESTS → TEST `implementations/python/tests/test_issue_954_docs_publication_boundary.py` (Static boundary checks and Sphinx build regressions)
- IMPLEMENTS → CODE_FILE `tools/vale_tool.py` (Pinned Vale tooling helper)
- TESTS → CODE_FILE `implementations/python/tests/test_public_docs_policy.py` (Public docs policy tests)
- IMPLEMENTS → CODE_FILE `.github/workflows/docs.yml` (Documentation build and policy workflow)
- IMPLEMENTS → CODE_FILE `.github/workflows/scorecard.yml` (OpenSSF Scorecard workflow)
- IMPLEMENTS → CONFIG `.vale.ini` (Vale style configuration)
- TESTS → CODE_FILE `implementations/python/tests/test_public_project_readiness.py` (Public project readiness tests)
