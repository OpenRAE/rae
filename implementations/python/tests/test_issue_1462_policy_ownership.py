"""Issue #1462: SEM-204 owns the module that orders compensation, without widening other ^SEM- requirements."""

from pathlib import Path

import pytest
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import (
    _check_path_ownership,
    evaluate_requirement_governance,
    load_policy,
    match_phase,
)

ROOT = Path(__file__).resolve().parents[3]
_COMPENSATION_MODULE = "implementations/python/packages/raes_runtime/control_plane_workflows.py"


def test_sem_204_has_its_own_phase_and_keeps_the_shared_prerequisite():
    policy = load_policy(ROOT)
    phase = match_phase(policy, "SEM-204")
    assert phase.phase_id == "workflow-compensation-semantics"
    assert phase.phase["blocked_until"] == match_phase(policy, "SEM-223").phase["blocked_until"]


def test_sem_204_governance_passes_for_this_delivery():
    delivery = [
        _COMPENSATION_MODULE,
        "implementations/python/tests/test_issue_1462_compensation_order.py",
        "implementations/python/tests/test_issue_1462_policy_ownership.py",
        "docs/requirements/SEM-204/requirement.md",
        "docs/decisions/package-artifacts/operations.md",
    ]
    client = RepositoryRequirementClient(ROOT)
    assert evaluate_requirement_governance(ROOT, delivery, client=client, requirement_uid="SEM-204") == []


@pytest.mark.parametrize(
    "path",
    [
        _COMPENSATION_MODULE,
        "implementations/python/packages/raes/validator/_workflows_verify.py",
        "implementations/python/packages/raes_contracts/workflow/contracts.py",
        "implementations/python/packages/raes_processor/compiler/workflows.py",
        "specs/formal/workflows/compensation.md",
        "docs/research/specification-coverage/captures/capture-example/snapshot.json",
        "docs/research/formal-semantic-validation/capture-records/capture-example.json",
    ],
)
def test_sem_204_owns_the_compensation_module_and_its_shared_semantic_roots(path):
    policy = load_policy(ROOT)
    assert _check_path_ownership(policy, match_phase(policy, "SEM-204"), [path], requirement_uid="SEM-204") == []


@pytest.mark.parametrize(
    "path",
    [
        "implementations/python/packages/raes_runtime/control_plane_execution.py",
        "implementations/python/packages/raes_runtime/observation_results.py",
        "docs/requirements/SEM-233/requirement.md",
        "docs/decisions/issue-1209-clause-mapping.md",
    ],
)
def test_sem_204_does_not_own_other_runtime_modules_or_paths_named_for_other_requirements(path):
    policy = load_policy(ROOT)
    failures = _check_path_ownership(policy, match_phase(policy, "SEM-204"), [path], requirement_uid="SEM-204")
    assert [failure.rule_id for failure in failures] == ["requirement-ownership-mismatch"]


def test_other_semantics_requirements_still_use_the_shared_phase_roots():
    policy = load_policy(ROOT)
    phase = match_phase(policy, "SEM-223")
    assert phase.phase_id == "semantics-expansion"
    failures = _check_path_ownership(policy, phase, [_COMPENSATION_MODULE], requirement_uid="SEM-223")
    assert [failure.rule_id for failure in failures] == ["requirement-ownership-mismatch"]
