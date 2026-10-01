"""Exercise actual ownership and scope validation for the design publication."""

from paths import REPO_ROOT
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance
from tools.policy.requirement_scope import evaluate_requirement_scope, load_requirement_scope


def test_applicability_publication_has_narrow_semantic_ownership():
    client = RepositoryRequirementClient(REPO_ROOT)
    owned = [
        "specs/formal/participant-semantics/control-applicability-and-evaluation.md",
        "implementations/python/tests/control_applicability_model.py",
        "implementations/python/tests/test_issue_1352_control_applicability.py",
        "implementations/python/tests/test_issue_1352_governance.py",
    ]
    assert evaluate_requirement_governance(REPO_ROOT, owned, client=client, requirement_uid="SEM-235") == []
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["implementations/python/packages/raes_runtime/participant_control_orchestration.py"],
        client=client,
        requirement_uid="SEM-235",
    )
    assert any(f.rule_id == "requirement-ownership-mismatch" for f in failures)


def test_contract_migration_has_contract_ownership():
    assert (
        evaluate_requirement_governance(
            REPO_ROOT,
            ["docs/migration/control-applicability-and-evaluation.md"],
            client=RepositoryRequirementClient(REPO_ROOT),
            requirement_uid="API-424",
        )
        == []
    )


def test_issue_scope_runs_every_owner_and_rejects_unassigned_runtime():
    scope = load_requirement_scope(REPO_ROOT, "1352-control-applicability-decisions")
    client = RepositoryRequirementClient(REPO_ROOT)
    assert scope is not None
    assert evaluate_requirement_scope(REPO_ROOT, list(scope.bindings), client=client, scope=scope) == []
    failures = evaluate_requirement_scope(
        REPO_ROOT,
        ["implementations/python/packages/raes_runtime/participant_control_orchestration.py"],
        client=client,
        scope=scope,
    )
    assert any(f.rule_id == "requirement-scope-unassigned" for f in failures)
