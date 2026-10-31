---
id: ASR-526
title: "Conformance And Support Reporting"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-05T02:05:42.646645Z
updated_at: 2026-04-05T02:05:42.646645Z
---

# Conformance and support reporting

## Statement

The ecosystem shall provide machine-readable and human-readable conformance and support reports for processors and backends.
The reports shall expose the achieved conformance profile or level, passed and failed checks, and declared and observed unsupported or partially supported capabilities.
The reports shall expose the applicable validation basis and diagnostics sufficient to explain gaps or limitations.

## Rationale

People validating their own processors or backends need more than a binary pass/fail outcome. Honest portability requires reports that show what level was achieved, what was not supported, where support was partial or constrained, and what validation basis underlies the claim.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `222`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/report.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/report_text.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/processor.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/fixture_suite.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/validators.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_cli/conformance.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_cli/processor.py`
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/backend-conformance.md`
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml`
- TESTS → TEST `implementations/python/tests/test_issue_222_conformance_reporting.py`
- TESTS → TEST `implementations/python/tests/test_issue_222_conformance_cli.py`
- TESTS → TEST `implementations/python/tests/test_conformance_facade_parity.py`
