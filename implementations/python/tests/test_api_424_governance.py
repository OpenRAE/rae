"""Contract publication cannot admit a runtime implementation under API-424."""

from paths import REPO_ROOT
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance


def test_contract_publication_rejects_runtime_ownership():
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["implementations/python/packages/raes_runtime/participant_flow_sink.py"],
        client=RepositoryRequirementClient(REPO_ROOT),
        requirement_uid="API-424",
    )
    assert any(f.rule_id == "requirement-ownership-mismatch" for f in failures)


def test_contract_publication_owns_its_selection():
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["implementations/python/packages/raes_contracts/contracts/participant_control_selection.py"],
        client=RepositoryRequirementClient(REPO_ROOT),
        requirement_uid="API-424",
    )
    assert not failures
