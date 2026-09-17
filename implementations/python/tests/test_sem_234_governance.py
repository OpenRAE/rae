"""SEM-234 publication ownership uses the real repository policy evaluator."""

from paths import REPO_ROOT
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance


def test_semantic_publication_has_exact_document_ownership():
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["docs/decisions/issue-1013-sem-234-mixed-participant-control-preflight.md"],
        client=RepositoryRequirementClient(REPO_ROOT),
        requirement_uid="SEM-234",
    )
    assert failures == []


def test_semantic_publication_does_not_authorize_runtime_implementation():
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["implementations/python/packages/raes_runtime/participant_control_mediation.py"],
        client=RepositoryRequirementClient(REPO_ROOT),
        requirement_uid="SEM-234",
    )
    assert any(failure.rule_id == "requirement-ownership-mismatch" for failure in failures)
