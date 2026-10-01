---
id: GOV-928
title: "Trusted Package Publishing"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-05-15T04:13:16.700063Z
updated_at: 2026-08-12T05:22:38Z
---

# GOV-928 — Trusted Package Publishing

## Statement

The ecosystem shall use short-lived, identity-bound publishing mechanisms for package and registry publication and shall avoid long-lived release tokens where supported by the target registry.

## Rationale

Imported from the superseded governance backlog before deleting the old governance repo. Package publication is a supply-chain trust boundary and should be governed separately from implementation-level artifact integrity.

## Traceability

- IMPLEMENTS → CODE_FILE `.github/workflows/release-please.yml` (Exact-SHA-gated PyPI trusted publishing workflow)
- IMPLEMENTS → CODE_FILE `tools/release_evidence_publication.py` (Tag-derived subject-name correspondence and the validated publisher handoff)
- IMPLEMENTS → CODE_FILE `tools/release_evidence.py` (Emits the admitted wheel/sdist identity only after admission succeeds)
- IMPLEMENTS → CODE_FILE `.github/workflows/canonical-verification.yml` (Read-only reusable canonical commit verifier)
- TESTS → TEST `implementations/python/tests/test_release_workflows.py` (Release classification, dependency, exact-SHA, action pin, artifact smoke, and OIDC boundary policy tests)
- TESTS → TEST `implementations/python/tests/test_issue_1227_release_publication.py` (Publication-boundary subject-name, handoff ordering, and admitted-identity cases)
- TESTS → TEST `implementations/python/tests/test_corpus_packaging.py` (Installed-wheel corpus, CLI conformance, and semantic-validation acceptance tests)
- TESTS → TEST `implementations/python/tests/test_reference_backend_docker_gate.py` (Required-mode runtime/image failure and reviewed digest policy tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1125-gov-928-exact-sha-release-verification-preflight.md` (Exact-SHA release verification architecture and trust-boundary preflight)
- DOCUMENTS → DOCUMENTATION `docs/explain/releasing.md` (Release operator contract and manual recovery constraints)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-684-public-release-acceptance-preflight.md` (Public publisher evidence boundary, release controls, and acceptance preflight)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1227-release-publication-preflight.md` (Tested-artifact publication and partial-publication recovery architecture)
- IMPLEMENTS → GITHUB_ISSUE `684` (Automatic PyPI publishing delivery lineage)
- IMPLEMENTS → GITHUB_ISSUE `1227` (Tested-artifact publication and partial-publication recovery)
- IMPLEMENTS → GITHUB_ISSUE `1125` (Repository-owned exact-SHA release verification guarantee)
- IMPLEMENTS → GITHUB_ISSUE `1110` (Exact-SHA real-container release admission)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1110-required-container-release-gate.md` (Required real-container release-gate architecture and evidence boundary)
