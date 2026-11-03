---
id: GOV-928
title: "Trusted Package Publishing"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-05-15T04:13:16.700063Z
updated_at: 2026-11-02T00:00:00Z
---

# GOV-928 — trusted package publishing

## Statement

Package and registry uploads shall use short-lived, identity-bound credentials.
The release workflow shall use the registry's trusted publishing flow where supported.
It shall avoid long-lived release tokens where the registry supports that flow.

## Rationale

A package upload grants trust in the released code.
Control who can publish, as well as which bytes can be built and released.
This rule came from the retired governance backlog.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/tooling/release-please/run.cjs` (Complete Git range for release PR versions and notes, #1841)
- TESTS → TEST `implementations/tooling/release-please/run.test.cjs` (Older-dated commits, version rules, and refusal of missing history)

- IMPLEMENTS → CODE_FILE `.github/workflows/release-please.yml` (Trusted PyPI uploads from the checked SHA)
- IMPLEMENTS → CODE_FILE `tools/release_evidence_publication.py` (Tag, file names, and trusted handoff to each registry)
- IMPLEMENTS → CODE_FILE `tools/release_evidence.py` (Emits wheel and sdist names only after checks pass)
- IMPLEMENTS → CODE_FILE `.github/workflows/canonical-verification.yml` (Shared read-only commit checks)
- TESTS → TEST `implementations/python/tests/test_release_workflows.py` (Version rules, pins, SHA checks, installed builds, and OIDC trust)
- TESTS → TEST `implementations/python/tests/test_issue_1227_release_publication.py` (Upload names, handoff order, and admitted files)
- TESTS → TEST `implementations/python/tests/test_corpus_packaging.py` (Installed wheel corpus, CLI checks, and SDL checks)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1125-gov-928-exact-sha-release-verification-preflight.md` (Exact-SHA release checks and trust design)
- DOCUMENTS → DOCUMENTATION `docs/explain/releasing.md` (Release steps and rules for manual repair)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-684-public-release-acceptance-preflight.md` (Proof of public uploads, release controls, and trust design)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1227-release-publication-preflight.md` (Tested builds, uploads, and repair of partial releases)
- IMPLEMENTS → GITHUB_ISSUE `684` (Automatic PyPI upload history)
- IMPLEMENTS → GITHUB_ISSUE `1227` (Tested builds, uploads, and repair of partial releases)
- IMPLEMENTS → GITHUB_ISSUE `1125` (Repo-owned checks of the exact release SHA)
- IMPLEMENTS → GITHUB_ISSUE `1110` (Exact-SHA checks in real containers)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1110-required-container-release-gate.md` (Required real-container gate and its proof)
