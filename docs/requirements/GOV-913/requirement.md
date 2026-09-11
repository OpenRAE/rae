---
id: GOV-913
title: "Trust And Integrity Of Reusable Assets"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-04-03T07:58:36.322037Z
updated_at: 2026-09-06T00:00:00.000000Z
---

# GOV-913 — Trust And Integrity Of Reusable Assets

## Statement

The ecosystem shall support trust, authenticity, and integrity policies for reusable scenarios, modules, tasks, studies, behavior vocabularies, and comparable reusable assets.

## Rationale

Requirement inventory expansion. Reusable ecosystem assets need explicit trust and integrity expectations so experiment meaning does not drift across reuse boundaries.

## Traceability

- IMPLEMENTS → SPEC `specs/supply-chain/reusable-asset-trust-integrity.md` (Reusable Asset Trust, Authenticity, and Integrity (normative spec))
- IMPLEMENTS → SPEC `contracts/schemas/asset-trust/reusable-asset-trust-policy-v1.json` (reusable-asset-trust-policy-v1 published schema)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-071-reusable-asset-trust-and-integrity-policy.md` (ADR-071: Reusable Asset Trust and Integrity Policy)
- TESTS → TEST `implementations/python/tests/test_reusable_asset_trust_policy.py` (Reusable-asset trust policy contract tests)
- IMPLEMENTS → GITHUB_ISSUE `115` (Trust & integrity of reusable assets (GOV-913))
- IMPLEMENTS → GITHUB_ISSUE `1098` (Upgrade vulnerable Click and cryptography locks and gate OSV findings)
- IMPLEMENTS → CONFIG `implementations/python/pyproject.toml` (Fixed Click and cryptography dependency floors)
- IMPLEMENTS → CONFIG `implementations/python/uv.lock` (Reviewed frozen dependency resolution)
- IMPLEMENTS → CONFIG `.github/workflows/ci.yml` (Required OSV dependency-vulnerability gate)
- IMPLEMENTS → CONFIG `noxfile.py` (Explicit OSV findings and scanner-error enforcement)
- IMPLEMENTS → CODE_FILE `tools/osv_scanner_tool.py` (OSV result classification)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-1098-gov-913-supply-chain-security-preflight.md` (Dependency vulnerability and gating preflight)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (Dependency-floor and OSV gate regression tests)
- DOCUMENTS → GITHUB_ISSUE `1106` (Cached OSV-Scanner integrity validation)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1106-gov-913-osv-cache-integrity.md` (Repository pin and atomic cache decision)
- IMPLEMENTS → CODE_FILE `tools/osv_scanner_tool.py` (Per-use cache type, mode, and digest validation)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (Tampered, symlinked, and atomic OSV cache regressions)
- DOCUMENTS → GITHUB_ISSUE `1096` (OCI module-registry reliability remediation)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1096-oci-module-registry-reliability-remediation.md` (OCI module-registry reliability decision)
- IMPLEMENTS → GITHUB_ISSUE `1107` (Bound OCI archive parsing and make cache/layout publication gapless)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1107-oci-archive-cache-publication-preflight.md` (Verified-bundle cache admission, bounded archive trees, and durable versioned publication preflight)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/_archive.py` (Bounded gzip admission and safe tar extraction)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/_verified_sources.py` (Descriptor-bound immutable OCI source graph)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/_cache.py` (Anchored cache locking, bounded archive admission, and concurrent first-use recovery)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/_filesystem.py` (Immutable version directories and atomic pointer repair)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/publishing.py` (Deterministic bundles and durable OCI layout publication)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/resolution.py` (Stable registry parsing and verified cache admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_expand.py` (Verified nested-source and admitted policy context propagation)
- TESTS → TEST `implementations/python/tests/test_sdl_module_registry.py` (Bundle-bound cache integrity, safe lock/depth handling, legacy-layout rejection, and atomic-pointer regressions)
- TESTS → TEST `implementations/python/tests/test_issue_1107_oci_source_snapshot.py` (Descriptor-bound source snapshot regressions)
- IMPLEMENTS → GITHUB_ISSUE `1216` (Reviewed development artifact locks and policy)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-106-developer-package-and-artifact-management.md` (Accepted development package and artifact architecture)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-107-artifact-promotion-and-release-admission.md` (Accepted artifact promotion and release admission architecture)
- IMPLEMENTS → CONFIG `implementations/tooling/artifacts.lock.json` (Reviewed raw and installed artifact identities)
- IMPLEMENTS → CONFIG `implementations/tooling/profiles/development-profiles.json` (Supported development platforms and locator classes)
- IMPLEMENTS → CONFIG `implementations/tooling/admission-policy.json` (Artifact, source snapshot, action and OCI admission policy)
- IMPLEMENTS → CONFIG `implementations/tooling/actions-policy.json` (Exact GitHub Action source commits)
- IMPLEMENTS → CONFIG `implementations/tooling/selector-bindings.json` (Literal selector authority bindings)
- IMPLEMENTS → CONFIG `implementations/tooling/inventory-coverage.json` (Complete package-artifact inventory ownership and disposition)
- IMPLEMENTS → CODE_FILE `tools/check_tooling_artifact_policy.py` (Deterministic offline artifact-policy gate)
- IMPLEMENTS → CODE_FILE `tools/tooling_policy_gate.py` (Dependency-free fail-before-acquisition launcher)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/package-artifacts/operations.md` (T22 and T23 policy-gate evidence)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-1216-development-artifact-lock-policy-preflight.md` (Artifact-lock implementation preflight)
- TESTS → TEST `implementations/python/tests/test_tooling_artifact_policy.py` (Artifact identity, drift, coverage and fail-before-acquisition regressions)
