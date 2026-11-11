"""Issue #307: DSL-120 owns its episode-policy delivery, without widening other ^DSL- requirements."""

from pathlib import Path

import pytest
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import _check_path_ownership, load_policy, match_phase
from tools.policy.requirement_scope import evaluate_requirement_scope, load_requirement_scope

ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = "contracts/fixtures/sdl/participant-episode-policy-v1/valid/analyst-shift-episode.yaml"
_GUIDE = "docs/public/participant-control.md"


def test_dsl_120_has_its_own_phase_and_keeps_the_shared_prerequisites():
    policy = load_policy(ROOT)
    phase = match_phase(policy, "DSL-120")
    assert phase.phase_id == "participant-episode-policy-language"
    assert phase.phase.get("blocked_until", []) == match_phase(policy, "DSL-121").phase.get("blocked_until", [])


def test_the_issue_scope_selects_dsl_120_and_every_bound_file_passes_its_governance():
    scope = load_requirement_scope(ROOT, "307-participant-episode-surface")
    assert scope is not None
    assert (scope.primary_requirement_uid, scope.requirement_uids) == ("DSL-120", ("DSL-120",))
    assert {owners for owners in scope.bindings.values()} == {("DSL-120",)}
    client = RepositoryRequirementClient(ROOT)
    assert evaluate_requirement_scope(ROOT, sorted(scope.bindings), client=client, scope=scope) == []


@pytest.mark.parametrize(
    "path",
    [
        _FIXTURE,
        _GUIDE,
        "specs/concept-authority/semantic-profiles.md",
        "specs/formal/assurance-fulfillment.yaml",
        "docs/governance/requirement-scopes/307.json",
        "docs/decisions/package-artifacts/operations.md",
        "implementations/python/packages/raes/participant_episode_policy.py",
        "contracts/schemas/sdl/materialized-scenario-v1.json",
        "docs/research/specification-coverage/captures/capture-example/snapshot.json",
        "docs/research/formal-semantic-validation/capture-records/capture-example.json",
    ],
)
def test_dsl_120_owns_its_delivery_and_the_shared_sdl_roots(path):
    policy = load_policy(ROOT)
    assert _check_path_ownership(policy, match_phase(policy, "DSL-120"), [path], requirement_uid="DSL-120") == []


@pytest.mark.parametrize(
    "path",
    [
        "docs/requirements/DSL-116/requirement.md",
        "docs/governance/requirement-scopes/298.json",
        "docs/decisions/issue-298-tool-authoring.md",
        "implementations/python/packages/raes_runtime/manager.py",
        "docs/requirements/DSL-435/requirement.md",
    ],
)
def test_dsl_120_does_not_own_paths_named_for_other_requirements(path):
    policy = load_policy(ROOT)
    failures = _check_path_ownership(policy, match_phase(policy, "DSL-120"), [path], requirement_uid="DSL-120")
    assert [failure.rule_id for failure in failures] == ["requirement-ownership-mismatch"]


def test_other_sdl_requirements_still_use_the_shared_phase_roots():
    policy = load_policy(ROOT)
    phase = match_phase(policy, "DSL-121")
    assert phase.phase_id == "sdl-language"
    failures = _check_path_ownership(policy, phase, [_FIXTURE, _GUIDE], requirement_uid="DSL-121")
    assert [failure.rule_id for failure in failures] == ["requirement-ownership-mismatch"] * 2
