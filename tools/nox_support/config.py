"""Shared configuration constants for the repository nox sessions."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "implementations" / "python"
PUBLIC_DOCS_ROOT = REPO_ROOT / "docs" / "public"
DOCS_BUILD_ROOT = REPO_ROOT / "docs" / "_build"
PUBLIC_DOCS_ENTRYPOINTS = (
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "GOVERNANCE.md",
    "MAINTAINERS.md",
    "SECURITY.md",
    "SUPPORT.md",
)
PUBLIC_DOCS_EXAMPLE_TESTS = (
    "implementations/python/tests/test_public_docs_policy.py::test_checked_in_quickstart_scenario_parses",
    "implementations/python/tests/test_public_docs_policy.py::test_readme_quickstart_matches_checked_in_scenario",
    "implementations/python/tests/test_public_docs_policy.py::test_participant_control_claim_example_is_bounded",
)
RUFF_CONFIG = PROJECT_ROOT / "pyproject.toml"
OSV_LOCKFILE_PATH = PROJECT_ROOT / "uv.lock"
OSV_REPORT_PATH = PROJECT_ROOT / "osv-scanner-report.json"
COVERAGE_XML_PATH = PROJECT_ROOT / "coverage.xml"
COVERAGE_JSON_PATH = PROJECT_ROOT / "coverage.json"
MINIMUM_LINE_COVERAGE_PERCENT = 90.0
REQUIREMENT_UID_RE = re.compile(r"(?:^|[^A-Z0-9])[A-Z]{3}-\d{3}(?:$|[^A-Z0-9])", re.ASCII)
TARGETED_POLICY_TESTS = [
    "implementations/python/tests/test_tooling_artifact_policy.py",
    "implementations/python/tests/test_repo_policy_tools.py",
    "implementations/python/tests/test_requirement_governance.py",
    "implementations/python/tests/test_semantic_coverage.py",
    "implementations/python/tests/test_assurance_policy.py",
    "implementations/python/tests/test_authority_boundary.py",
    "implementations/python/tests/test_concept_authority_governance.py",
    "implementations/python/tests/test_agent_guidance_policy.py",
    "implementations/python/tests/test_example_library_policy.py",
    "implementations/python/tests/test_public_docs_policy.py",
    "implementations/python/tests/test_public_project_readiness.py",
    "implementations/python/tests/test_vale_tool.py",
    "implementations/python/tests/test_verification_plan.py",
]
CONTRACT_TRIGGER_PREFIXES = (
    "contracts/",
    "implementations/python/packages/raes_contracts/",
    "implementations/python/packages/raes_backend_protocols/",
    "implementations/python/packages/raes_processor/",
    "tools/generate_contract_schemas.py",
    "tools/check_json_artifacts.py",
)
FULL_TEST_TRIGGER_PREFIXES = ("implementations/python/",)
TOOLING_TEST_TRIGGER_PREFIXES = (
    "tools/",
    "implementations/tooling/",
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
    "noxfile.py",
)
EXCLUDED_PREFIXES = ("research/",)
PRIVATE_KEY_EXCLUDE_PREFIXES = ("implementations/python/tests/",)
MAX_LARGE_FILE_KB = "500"
VERIFY_PROJECT_SYNCED_ENV = "RAES_VERIFY_PROJECT_SYNCED"
VERIFY_COVERAGE_FILE_ENV = "RAES_VERIFY_COVERAGE_FILE"
JSON_SCHEMA_WORKERS_ENV = "RAES_JSON_SCHEMA_WORKERS"
EXPECTED_PYTHON_ENV = "RAES_EXPECTED_PYTHON"
EXPECT_FREE_THREADED_ENV = "RAES_EXPECT_FREE_THREADED"
