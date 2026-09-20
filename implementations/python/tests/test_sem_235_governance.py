"""Exercise the existing governance boundary for SEM-235 publication."""

from paths import REPO_ROOT
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance


def test_semantic_publication_rejects_runtime_implementation():
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["implementations/python/packages/raes_runtime/participant_flow_sink.py"],
        client=RepositoryRequirementClient(REPO_ROOT),
        requirement_uid="SEM-235",
    )
    assert any(f.rule_id == "requirement-ownership-mismatch" for f in failures)


def test_semantic_publication_allows_its_preflight():
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["docs/decisions/issue-1070-sem-235-architecture-preflight.md"],
        client=RepositoryRequirementClient(REPO_ROOT),
        requirement_uid="SEM-235",
    )
    assert failures == []
