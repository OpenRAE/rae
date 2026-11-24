---
id: GOV-941
title: "ADR Corpus Amendment Policy and Acceptance-Content Pin Gate"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-06-10T15:59:32.545921Z
updated_at: 2026-06-10T18:34:16.283005Z
---

# GOV-941 — ADR Corpus Amendment Policy and Acceptance-Content Pin Gate

## Statement

The ecosystem shall govern post-acceptance changes to accepted Architecture Decision Records through an explicit, documented amendment policy and a machine-checkable acceptance-content pin gate, so that the decision-record corpus remains honestly citable: every accepted ADR is pinned to its acceptance (or last recorded amendment) content, and any change to an accepted ADR's canonical content must be recorded as an amendment record (or land as a superseding ADR) in the same change. Because the filesystem-only gate cannot distinguish editorial from substantive edits, editorial-only changes also record a (one-line) amendment row rather than being exempt.

## Rationale

Review finding ADR-1 (issue #481): docs/decisions/adrs/README.md claims ADRs are "immutable once accepted", but git history shows accepted ADRs substantively edited post-acceptance (ADR-048, ADR-052, and ADR-025/029/032/038/041/050), so the corpus citability claim was unenforced and violated. A governed amendment policy (a new ADR) plus an enforced acceptance-content pin gate wired into the policy nox session makes the claim true and auditable, and reconciles the already-amended ADRs with honest amendment records.

## Traceability

- IMPLEMENTS → CODE_FILE `tools/check_adr_immutability.py` (ADR acceptance-content pin gate checker)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-059-adr-amendment-policy-and-pin-gate.md` (ADR-059 amendment policy)
- IMPLEMENTS → CONFIG `docs/decisions/adrs/adr-index.yaml` (Accepted-ADR manifest and amendment refs)
- IMPLEMENTS → CODE_FILE `tools/policy/adr.py` (Shared ADR parsers)
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml` (decision-record-governance phase mapping)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (ADR pin gate tests)
- IMPLEMENTS → CODE_FILE `tools/policy/common.py` (safe_repo_path shared helper (used by the pin gate))
- IMPLEMENTS → CODE_FILE `tools/policy/repo_policy.py` (repo_policy imports shared ADR parsers from the extraction)
- IMPLEMENTS → CODE_FILE `noxfile.py` (policy nox stage wiring for the pin gate)
- IMPLEMENTS → GITHUB_ISSUE `482` (Issue 482 ADR corpus hygiene)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/adrs/README.md` (ADR corpus policy and numbering convention)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/adrs/TEMPLATE.md` (Canonical ADR template with alternatives section)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-055-experiment-core-contract-boundary.md` (ADR-055 provenance amendment record)
