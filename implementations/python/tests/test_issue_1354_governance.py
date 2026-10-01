"""Exercise the real governance consumer for the IFC semantic publication."""

from paths import REPO_ROOT
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance
from tools.policy.requirement_scope import evaluate_requirement_scope, load_requirement_scope


def test_ifc_publication_has_exact_semantic_ownership():
    client = RepositoryRequirementClient(REPO_ROOT)
    paths = [
        "docs/decisions/issue-1354-ifc-profile-variability-preflight.md",
        "specs/formal/participant-semantics/ifc-profile-variability.md",
        "implementations/python/tests/ifc_profile_variability_model.py",
        "implementations/python/tests/test_issue_1354_ifc_profile_variability.py",
    ]
    assert evaluate_requirement_governance(REPO_ROOT, paths, client=client, requirement_uid="SEM-235") == []
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        ["implementations/python/packages/raes_runtime/participant_control_orchestration.py"],
        client=client,
        requirement_uid="SEM-235",
    )
    assert any(f.rule_id == "requirement-ownership-mismatch" for f in failures)


def test_issue_scope_validates_both_owners_without_runtime_authority():
    scope = load_requirement_scope(REPO_ROOT, "1354-ifc-profile-variability")
    assert scope is not None
    client = RepositoryRequirementClient(REPO_ROOT)
    assert evaluate_requirement_scope(REPO_ROOT, list(scope.bindings), client=client, scope=scope) == []
    failures = evaluate_requirement_scope(
        REPO_ROOT,
        ["implementations/python/packages/raes_runtime/participant_control_orchestration.py"],
        client=client,
        scope=scope,
    )
    assert any(f.rule_id == "requirement-scope-unassigned" for f in failures)
