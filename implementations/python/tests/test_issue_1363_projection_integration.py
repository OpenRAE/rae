"""Occurrence policies preserve canonical runtime and semantic-only authority identities."""

import pytest
from mixed_control_rev1_scenarios import parse, rev1_scenario
from raes_processor.compiler import compile_runtime_model
from raes_processor.compiler._mixed_control_policy import occurrence_policy_projection
from raes_processor.compiler.alias_index import _runtime_addressable_ref_index


@pytest.mark.parametrize("form", ["reusable-policy", "finite-script"])
@pytest.mark.parametrize("surface", ["mixed-authority", "semantic-authority", "behavior-scope"])
def test_occurrence_projection_keeps_every_canonical_anchor(form: str, surface: str) -> None:
    payload = rev1_scenario(form=form)
    owner = payload["behavior_specifications"]["controlled-red"]
    state = owner["mixed_control"]["controller_states"]["autonomous"]
    state["authority_basis_refs"] = ["red-team"]
    expected = {"entities.red-team"}
    if surface == "mixed-authority":
        payload["agents"]["red-agent"]["authority_anchors"].append("nodes.web")
        state["authority_basis_refs"].append("nodes.web")
        expected.add("provision.node.web")
    elif surface == "behavior-scope":
        owner["authority_scope_refs"].append("entities.red-team")
        expected.add("provision.node.web")
    scenario = parse(payload)
    compiled = compile_runtime_model(scenario)
    specification = compiled.behavior_specifications["participant.behavior-specification.controlled-red"]
    projection = occurrence_policy_projection(
        specification, episode_id="episode-1", addressable_ref_index=_runtime_addressable_ref_index(scenario)
    )
    actual = (
        projection.behavior_scope_refs
        if surface == "behavior-scope"
        else next(item for item in projection.states if item.state_ref.endswith(".autonomous")).authority_basis_refs
    )
    assert set(actual) == expected
