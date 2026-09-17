"""Versioned comparison preserves authored presence and private JSON meaning."""

import json
from pathlib import Path

import pytest
from raes import parse_sdl
from raes_contracts.semantic_comparison import (
    ArtifactKind,
    ImpactClosureStatus,
    SemanticComparisonProfileModel,
    SemanticComparisonRequestModel,
    canonical_semantic_comparison_profile_digest,
)
from raes_processor.semantic_comparison import analyze_semantic_comparison
from raes_processor.semantic_comparison_adapters import build_impact_scope, coordinate_for_artifact

ROOT = Path(__file__).resolve().parents[3]


def compare(before, after, version="2"):
    data = json.loads((ROOT / "contracts/profiles/semantic-comparison/reference-v1.json").read_text())
    data["owner_projection_versions"]["scenario"] = version
    if type(before).__name__ == "ExperimentTaskModel":
        data["owner_projection_versions"]["task"] = version
    profile = SemanticComparisonProfileModel.model_validate(data)
    left = coordinate_for_artifact(before, scenario_projection_version=version)
    right = coordinate_for_artifact(after, scenario_projection_version=version)
    scope = build_impact_scope(
        (before,),
        (after,),
        traversal_roots=(right.canonical_identity,),
        scenario_projection_version=version,
        closure_status=ImpactClosureStatus.COMPLETE,
    )
    request = SemanticComparisonRequestModel(
        comparison_profile=profile.profile_id,
        comparison_profile_digest=canonical_semantic_comparison_profile_digest(profile),
        analyzer_profile=profile.analyzer_profile,
        before=left,
        after=right,
        impact_scope=scope,
    )
    return analyze_semantic_comparison(profile, request, before, after)


def test_presence_preserving_projection_distinguishes_omitted_and_empty():
    before = parse_sdl("name: sample\nrealization: {default: open}\nnodes: {host: {type: compute, runtime: {}}}\n")
    after = parse_sdl(
        "name: sample\nrealization: {default: open}\nnodes: {host: {type: compute, runtime: {packages: []}}}\n"
    )
    result = compare(before, after)
    assert result.before.canonical_digest != result.after.canonical_digest
    by_id = {change.identity: change for change in result.changes}
    assert by_id["scenario:sample"].semantic_relation.value == "changed"
    assert by_id["scenario:sample/nodes:host"].semantic_relation.value == "changed"
    with pytest.raises(ValueError, match="projection"):
        compare(before, after, "1")


def test_private_description_key_is_not_editorial_text():
    from raes.scenario import Scenario
    from test_issue_1208_profile_selections import _account_profile

    def source(value):
        binding, _ = _account_profile(
            profile_context="service-materialization", address="provision.content.seed", value={"description": value}
        )
        return Scenario.model_validate(
            {
                "name": "private",
                "nodes": {"host": {"type": "compute"}},
                "content": {
                    "seed": {"type": "file", "target": "host", "path": "/seed", "service_materialization": binding}
                },
            }
        )

    result = compare(source("first"), source("second"))
    by_id = {change.identity: change for change in result.changes}
    assert by_id["scenario:private"].semantic_relation.value == "changed"
    assert by_id["scenario:private/content:seed"].semantic_relation.value == "changed"


def test_native_editorial_description_still_has_no_semantic_effect():
    before = parse_sdl("name: sample\ndescription: before\n")
    after = parse_sdl("name: sample\ndescription: after\n")
    assert compare(before, after).changes[0].semantic_relation.value == "unchanged"


def test_unsupported_owner_projection_cannot_claim_compatibility():
    data = json.loads((ROOT / "contracts/profiles/semantic-comparison/reference-v1.json").read_text())
    data["owner_projection_versions"][ArtifactKind.MODULE.value] = "2"
    with pytest.raises(ValueError):
        SemanticComparisonProfileModel.model_validate(data)


@pytest.mark.parametrize("revision", ["", "semantic_revision: raes-progressive-semantics/v1\n"])
def test_progressive_source_requires_current_owner_projection(revision):
    scenario = parse_sdl("name: current\n" + revision)
    with pytest.raises(ValueError, match="projection"):
        compare(scenario, scenario, "1")
    assert compare(scenario, scenario).changes[0].semantic_relation.value == "unchanged"


def test_task_comparison_preserves_independent_observation_demand():
    from raes_contracts.contracts import ExperimentTaskModel
    from raes_contracts.observation_demand import ObservationDemandRule
    from test_issue_1212_observation_demand import _document

    data = json.loads((ROOT / "contracts/fixtures/experiment-core/experiment-task-v1/valid/reference.json").read_text())
    before = ExperimentTaskModel.model_validate(data)
    data["observation_demands"] = _document(
        ObservationDemandRule(
            rule_id="silent", scope="", purpose="experimental", mode="none", collection="forbid", export="forbid"
        )
    ).model_dump(mode="json")
    after = ExperimentTaskModel.model_validate(data)
    assert compare(before, after).changes[0].semantic_relation.value == "changed"
    with pytest.raises(ValueError, match="projection"):
        compare(before, after, "1")


@pytest.mark.parametrize("field", ["observation_demands", "non_use", "validation_basis_disclosures"])
def test_task_default_presence_cannot_change_semantics_under_the_same_coordinate(field):
    from raes_contracts.contracts import ExperimentTaskModel

    data = json.loads((ROOT / "contracts/fixtures/experiment-core/experiment-task-v1/valid/reference.json").read_text())
    data.pop(field, None)
    omitted = ExperimentTaskModel.model_validate(data)
    data[field] = omitted.model_dump(mode="json")[field]
    explicit = ExperimentTaskModel.model_validate(data)
    assert coordinate_for_artifact(omitted) == coordinate_for_artifact(explicit)
    for before, after in ((omitted, explicit), (explicit, omitted)):
        assert all(change.semantic_relation.value == "unchanged" for change in compare(before, after).changes)
