"""Issue #309: ACT-623 owns its episode-structure delivery; the stacked #307 files keep DSL-120's checks."""

import json
from pathlib import Path

import pytest
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import _check_path_ownership, load_policy, match_phase
from tools.policy.requirement_scope import evaluate_requirement_scope, load_requirement_scope, parse_requirement_scope

ROOT = Path(__file__).resolve().parents[3]
_BRANCH = "309-participant-episode-structure"
_SCOPE = "docs/governance/requirement-scopes/309.json"
_CONFORMANCE = "implementations/python/packages/raes_conformance/conformance/participant_episode_structure.py"


def test_act_623_has_its_own_phase_and_keeps_the_shared_prerequisites():
    policy = load_policy(ROOT)
    phase = match_phase(policy, "ACT-623")
    assert phase.phase_id == "participant-episode-structure"
    assert phase.phase.get("blocked_until", []) == match_phase(policy, "ACT-624").phase.get("blocked_until", [])


def test_the_issue_scope_selects_act_623_and_every_bound_file_passes_its_owners_governance():
    scope = load_requirement_scope(ROOT, _BRANCH)
    assert scope is not None
    assert (scope.primary_requirement_uid, scope.requirement_uids) == ("ACT-623", ("ACT-623", "DSL-120"))
    client = RepositoryRequirementClient(ROOT)
    assert evaluate_requirement_scope(ROOT, sorted(scope.bindings), client=client, scope=scope) == []


def test_the_stacked_issue_307_files_stay_bound_to_dsl_120():
    stacked = load_requirement_scope(ROOT, "307-participant-episode-surface")
    scope = load_requirement_scope(ROOT, _BRANCH)
    assert {path for path, owners in scope.bindings.items() if "DSL-120" in owners} == set(stacked.bindings)


def test_act_623_cannot_absorb_the_stacked_dsl_120_files():
    document = json.loads((ROOT / _SCOPE).read_text(encoding="utf-8"))
    document["bindings"] = {path: ["ACT-623"] for path in document["bindings"]}
    scope = parse_requirement_scope(document, issue_number=309)

    failures = evaluate_requirement_scope(ROOT, sorted(scope.bindings), client=RepositoryRequirementClient(ROOT), scope=scope)

    assert {(failure.rule_id, failure.path) for failure in failures} >= {
        ("requirement-ownership-mismatch", "docs/public/participant-control.md"),
        ("requirement-ownership-mismatch", "specs/concept-authority/semantic-profiles.md"),
        ("traceability-missing-implements", "implementations/python/packages/raes/composition/_episode_policy.py"),
    }


@pytest.mark.parametrize(
    "path",
    [
        _SCOPE,
        _CONFORMANCE,
        "implementations/python/packages/raes_processor/models/behavior_resources.py",
        "contracts/fixtures/sdl/participant-episode-policy-v1/valid/standalone-episode-structure.yaml",
        "specs/sdl/sections.md",
        "specs/formal/assurance-fulfillment.yaml",
        "docs/research/specification-coverage/captures/capture-example/snapshot.json",
        "docs/research/formal-semantic-validation/capture-records/capture-example.json",
    ],
)
def test_act_623_owns_its_delivery_and_the_shared_participant_model_roots(path):
    policy = load_policy(ROOT)
    assert _check_path_ownership(policy, match_phase(policy, "ACT-623"), [path], requirement_uid="ACT-623") == []


@pytest.mark.parametrize(
    "path",
    [
        "docs/governance/requirement-scopes/307.json",
        "docs/governance/requirement-scopes/298.json",
        "docs/public/participant-control.md",
        "specs/concept-authority/semantic-profiles.md",
    ],
)
def test_act_623_does_not_own_other_issue_scopes_or_dsl_120_only_paths(path):
    policy = load_policy(ROOT)
    failures = _check_path_ownership(policy, match_phase(policy, "ACT-623"), [path], requirement_uid="ACT-623")
    assert [failure.rule_id for failure in failures] == ["requirement-ownership-mismatch"]


@pytest.mark.parametrize("uid", ["ACT-624", "DSL-120"])
def test_other_requirements_do_not_own_the_act_623_scope(uid):
    policy = load_policy(ROOT)
    failures = _check_path_ownership(policy, match_phase(policy, uid), [_SCOPE], requirement_uid=uid)
    assert [failure.rule_id for failure in failures] == ["requirement-ownership-mismatch"]


def test_other_participant_model_requirements_still_use_the_shared_phase():
    assert match_phase(load_policy(ROOT), "ACT-624").phase_id == "participant-model"
