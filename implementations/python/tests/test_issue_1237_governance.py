"""Evidence ownership retains prerequisite and traceability enforcement."""

from pathlib import Path

import pytest
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = "implementations/python/packages/raes_contracts/evidence_output_validation.py"


@pytest.mark.parametrize("uid", ["EXP-708", "EXP-715"])
def test_evidence_requirements_own_registered_output_validation(uid):
    assert (
        evaluate_requirement_governance(
            ROOT, [EVIDENCE_PATH], client=RepositoryRequirementClient(ROOT), requirement_uid=uid
        )
        == []
    )


@pytest.mark.parametrize("uid", ["EXP-708", "EXP-715"])
def test_evidence_ownership_does_not_authorize_unrelated_runtime_code(uid):
    failures = evaluate_requirement_governance(
        ROOT,
        ["implementations/python/packages/raes_controlplane/security.py"],
        client=RepositoryRequirementClient(ROOT),
        requirement_uid=uid,
    )
    assert {failure.rule_id for failure in failures} == {
        "requirement-ownership-mismatch",
        "traceability-missing-implements",
    }


@pytest.mark.parametrize("uid", ["EXP-708", "EXP-715"])
def test_evidence_phase_requires_active_experiment_core_and_traceability(uid):
    class IncompleteClient(RepositoryRequirementClient):
        def get_requirement(self, project, requirement_uid):
            result = super().get_requirement(project, requirement_uid)
            return {**result, "status": "DRAFT"} if requirement_uid == "EXP-701" else result

        def get_traceability(self, requirement_id):
            return []

    failures = evaluate_requirement_governance(
        ROOT, [EVIDENCE_PATH], client=IncompleteClient(ROOT), requirement_uid=uid
    )
    assert {failure.rule_id for failure in failures} == {
        "requirement-order-blocked",
        "traceability-missing-implements",
    }
