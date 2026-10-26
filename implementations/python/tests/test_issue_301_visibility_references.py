"""Compile authored visibility references once, without duplicate address rules."""

from copy import deepcopy

import pytest
import yaml
from test_issue_301_participant_tool_profiles import _blue_only_profile
from test_issue_301_projection_boundaries import _project
from tool_profile_support import (
    ACTIVE,
    BLUE_VIEW,
    PASSIVE,
    SCANNER_BLUE,
    SCANNER_WHITE,
    WHITE,
    WHITE_VIEW,
    Episode,
    compiled,
    toolkit_text,
)


def _authored_reference(ref):
    if ref.startswith("participant.action-contract."):
        return ref.removeprefix("participant.action-contract.")
    return ref.replace("participant.behavior-specification.", "behavior_specifications.").replace(
        ".tool-affordance.", ".tool_affordances."
    )


def _authored_document(text):
    document = yaml.safe_load(text)
    for boundary in document["observation_boundaries"].values():
        for field in ("observable_refs", "hidden_refs"):
            boundary[field] = list(dict.fromkeys(_authored_reference(ref) for ref in boundary.get(field, [])))
        rules = {}
        for rule in boundary["view_rules"]:
            ref = _authored_reference(rule["information_ref"])
            rules[ref] = dict(rule, information_ref=ref)
        boundary["view_rules"] = list(rules.values())
        for transition in boundary.get("view_transitions", []):
            transition["information_ref"] = _authored_reference(transition["information_ref"])
    return document


@pytest.mark.parametrize("version", ("v1", "v2"))
def test_authored_only_visibility_references_project_from_compiled_sdl(version):
    text = _blue_only_profile(scoped=False)
    for old, new in (
        ("toolkit", "red-surface"),
        ("analyst", "red-agent"),
        ("scan-active", "scan"),
        ("blue-view", "red-view"),
        ("scanner-blue", "scanner"),
    ):
        text = text.replace(old, new)
    model = compiled(yaml.safe_dump(_authored_document(text)))

    surface = _project(model, version)

    view = surface if version == "v1" else surface.participant_view
    assert view.action_entries[0].affordance_refs == [
        "participant.behavior-specification.red-surface.tool-affordance.scanner"
    ]


def test_authored_visibility_transitions_preserve_hidden_then_disclosed_binding():
    model = compiled(yaml.safe_dump(_authored_document(toolkit_text())))
    white = Episode.start(model, WHITE, WHITE_VIEW)
    with pytest.raises(ValueError, match="not participant-visible"):
        white.project((PASSIVE,), (SCANNER_WHITE,))

    white.reveal(ACTIVE)
    surface = white.project((PASSIVE,), (SCANNER_WHITE,))

    assert surface.participant_view.action_entries[0].visibility == "disclosed"
    boundary = model.observation_boundaries[WHITE_VIEW]
    assert boundary.view_transitions[1]["information_ref"] == SCANNER_WHITE
    assert SCANNER_WHITE in boundary.hidden_refs
    assert "behavior_specifications.toolkit.tool_affordances.scanner-white" in boundary.spec["hidden_refs"]


def test_ambiguous_visibility_reference_is_rejected():
    document = _authored_document(toolkit_text())
    document["content"]["scan-active"] = deepcopy(document["content"]["nmap"])

    with pytest.raises(ValueError, match="ambiguous.*visibility reference"):
        compiled(yaml.safe_dump(document))


def test_conflicting_visibility_aliases_are_rejected():
    document = _authored_document(toolkit_text())
    boundary = document["observation_boundaries"]["blue-view"]
    rule = next(rule for rule in boundary["view_rules"] if rule["information_ref"] == "scan-active")
    boundary["view_rules"].append(dict(rule, information_ref=ACTIVE, disposition="hidden"))
    boundary["hidden_refs"].append(ACTIVE)

    with pytest.raises(ValueError, match="conflicting.*visibility"):
        compiled(yaml.safe_dump(document))


def test_equal_aliases_keep_unknown_information_refs_and_canonical_addresses():
    document = yaml.safe_load(toolkit_text())
    boundary = document["observation_boundaries"]["blue-view"]
    rule = next(rule for rule in boundary["view_rules"] if ".tool_affordances." in rule["information_ref"])
    boundary["view_rules"].append(dict(rule, information_ref=SCANNER_BLUE))
    boundary["observable_refs"].append(SCANNER_BLUE)
    model = compiled(yaml.safe_dump(document))
    relation = model.observation_boundaries[BLUE_VIEW].view_relation_timeline[0]["view_relation"]
    assert relation["context.public"] == "observable"
    assert relation[ACTIVE] == "observable"
    assert "behavior_specifications.toolkit.tool_affordances.scanner-blue" not in relation


def test_alias_transitions_cannot_reuse_a_stale_initial_disposition():
    document = yaml.safe_load(toolkit_text())
    boundary = document["observation_boundaries"]["white-view"]
    rule = next(
        rule
        for rule in boundary["view_rules"]
        if rule["disposition"] == "hidden" and ".tool_affordances." in rule["information_ref"]
    )
    boundary["view_rules"].append(dict(rule, information_ref=SCANNER_WHITE))
    boundary["hidden_refs"].append(SCANNER_WHITE)
    transition = deepcopy(boundary["view_transitions"][-1])
    transition.update(
        transition_id="conflicting-alias-transition",
        information_ref=SCANNER_WHITE,
        effective_order=3,
    )
    boundary["view_transitions"].append(transition)

    with pytest.raises(ValueError, match="conflicting.*visibility transition"):
        compiled(yaml.safe_dump(document))
