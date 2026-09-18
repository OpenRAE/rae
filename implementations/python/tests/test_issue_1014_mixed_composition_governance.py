"""Governance ownership for issue #1014's multi-requirement delivery."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCOPE_PATH = REPO_ROOT / "docs/governance/requirement-scopes/1014.json"
ORDER_PATH = REPO_ROOT / "tools/policy/requirement_order.yaml"
UIDS = ["SEM-234", "SCE-002", "API-407", "API-423"]

DELIVERY_PATHS = {
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/invalid/alternative-fallback-pool.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/invalid/duplicate-apparatus-identity.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/invalid/open-metadata.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/invalid/simultaneous-single-form.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/invalid/staged-unadmitted-member.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/invalid/unknown-revision.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/valid/alternative.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/valid/simultaneous-mixed.json",
    "contracts/fixtures/plans/mixed-participant-composition-profile-v1/valid/staged.json",
    "contracts/schema-publication/entries/mixed-participant-composition-profile-v1.json",
    "contracts/schemas/plans/mixed-participant-composition-profile-v1.json",
    "docs/decisions/issue-1014-mixed-composition-contracts-preflight.md",
    "docs/explain/reference/mixed-participant-composition.md",
    "docs/governance/requirement-scopes/1014.json",
    "docs/requirements/API-407/requirement.md",
    "docs/requirements/API-423/requirement.md",
    "docs/requirements/SCE-002/requirement.md",
    "docs/requirements/SEM-234/requirement.md",
    "docs/research/formal-semantic-validation/bundles/retest-v30.json",
    "docs/research/formal-semantic-validation/execution-snapshot-v30.json",
    "docs/research/specification-coverage/analysis-v30.json",
    "docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1179-v30.json",
    "docs/research/specification-coverage/execution-snapshot-v30.json",
    "implementations/python/packages/raes_conformance/conformance/validators.py",
    "implementations/python/packages/raes_contracts/contracts/__init__.py",
    "implementations/python/packages/raes_contracts/contracts/_exports.py",
    "implementations/python/packages/raes_contracts/contracts/bundle.py",
    "implementations/python/packages/raes_contracts/contracts/mixed_composition.py",
    "implementations/python/packages/raes_contracts/contracts/mixed_composition_resolution.py",
    "implementations/python/packages/raes_contracts/json_ingress.py",
    "implementations/python/packages/raes_contracts/versions.py",
    "implementations/python/tests/test_issue_1014_mixed_composition_contracts.py",
    "implementations/python/tests/test_issue_1014_mixed_composition_governance.py",
    "tools/generate_contract_schemas.py",
    "tools/policy/requirement_order.yaml",
}


def test_issue_scope_is_closed_complete_and_truthful() -> None:
    scope = json.loads(SCOPE_PATH.read_text(encoding="utf-8"))
    assert scope["schema_version"] == "requirement-scope/v1"
    assert scope["issue_number"] == 1014
    assert scope["primary_requirement_uid"] == "SEM-234"
    assert scope["requirement_uids"] == UIDS
    assert set(scope["bindings"]) == DELIVERY_PATHS
    assert all(set(owners) <= set(UIDS) and owners for owners in scope["bindings"].values())
    assert set(scope["bindings"]["implementations/python/tests/test_issue_1014_mixed_composition_contracts.py"]) == set(
        UIDS
    )


def test_all_scoped_requirements_and_delivery_paths_share_the_bounded_phase() -> None:
    policy = yaml.safe_load(ORDER_PATH.read_text(encoding="utf-8"))
    phases = {phase["id"]: phase for phase in policy["phases"]}
    mixed = phases["mixed-participant-composition"]
    assert mixed["requirements"] == UIDS
    assert "API-407" not in phases["api400-deferred"]["requirements"]
    assert mixed["blocked_until"] == ["reference-implementations"]

    ownership = set(policy["ownership"]["mixed-participant-composition"])
    assert ownership >= DELIVERY_PATHS
