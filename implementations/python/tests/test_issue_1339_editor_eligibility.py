"""Editor completion, navigation and diagnostics share the reference purposes (#1339)."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from raes import SDLValidationError
from raes.language_service import language_completions, language_diagnostics, language_references
from test_issue_1339_reference_eligibility import FIELDS, _parse, _payload, _set

_PAIR = {"type": "participant", "source": "red", "target": "blue", "participant": {"kind": "cooperation"}}


def _paired(*, complete: bool = True) -> dict:
    payload = _payload()
    payload["relationships"]["pair"] = deepcopy(_PAIR)
    payload["agents"]["red"]["operating_scope"] = ["web"]
    if not complete:
        # An author mid-edit: the subtype is typed, its detail is not, so the model does not validate yet.
        del payload["relationships"]["pair"]["participant"]
    return payload


def _completions(payload: dict, pointer: str) -> dict:
    return language_completions(yaml.safe_dump(payload), cursor_path=pointer)


@pytest.mark.parametrize("complete", [True, False], ids=["valid-document", "incomplete-document"])
def test_participant_relationship_completion_offers_only_participants(complete: bool) -> None:
    result = _completions(_paired(complete=complete), "/relationships/pair/target")

    assert [(item["label"], item["detail"]) for item in result["items"]] == [
        ("blue", "agents.blue"),
        ("red", "agents.red"),
    ]
    assert result["context"] == "reference:eligible:participant_endpoint"


@pytest.mark.parametrize("complete", [True, False], ids=["valid-document", "incomplete-document"])
def test_an_ambiguous_bare_participant_is_offered_only_in_qualified_form(complete: bool) -> None:
    payload = _paired(complete=complete)
    payload["entities"]["blue"] = {"role": "blue"}

    labels = {item["detail"]: item["label"] for item in _completions(payload, "/relationships/pair/target")["items"]}

    assert labels == {"agents.blue": "agents.blue", "agents.red": "red"}
    valid = _paired()
    valid["entities"]["blue"] = {"role": "blue"}
    with pytest.raises(SDLValidationError, match="target participant endpoint must resolve unambiguously"):
        _parse(valid)
    valid["relationships"]["pair"]["target"] = labels["agents.blue"]
    _parse(valid)


@pytest.mark.parametrize(
    ("pointer", "path", "context", "refused_detail"),
    [
        ("/objectives/goal/targets", FIELDS["objective"], "eligible:objective_subject", "conditions.alive"),
        (
            "/action_contracts/probe/interactions/0/target",
            FIELDS["interaction"],
            "eligible:action_target",
            "propositions.ready",
        ),
        (
            "/action_contracts/probe/interactions/0/shared_state_refs",
            FIELDS["shared-state"],
            "eligible:shared_state",
            "agents.blue",
        ),
        (
            "/action_contracts/probe/effects/0/target_refs",
            FIELDS["effect"],
            "eligible:action_target",
            "assertions.done",
        ),
        (
            "/behavior_specifications/red-behavior/authority_scope_refs",
            FIELDS["authority-scope"],
            "eligible:authority_scope",
            "propositions.ready",
        ),
        (
            "/propositions/ready/subjects",
            ("propositions", "ready", "subjects"),
            "eligible:observation_subject",
            "objectives.goal",
        ),
        (
            "/relationships/link/target",
            ("relationships", "link", "target"),
            "eligible:relationship_endpoint",
            "objectives.goal",
        ),
        (
            "/agents/red/operating_scope",
            ("agents", "red", "operating_scope"),
            "derived:operating_scope",
            "relationships.link",
        ),
    ],
)
def test_every_suggested_reference_validates_and_refused_kinds_are_not_suggested(
    pointer: str, path: tuple, context: str, refused_detail: str
) -> None:
    result = _completions(_paired(), pointer)

    assert refused_detail not in {item["detail"] for item in result["items"]}
    assert result["items"]
    for item in result["items"]:
        _parse(_set(_paired(), path, item["label"]))
    assert result["context"] == f"reference:{context}"


def test_participant_relationship_scope_completion_uses_the_operating_scope() -> None:
    result = _completions(_paired(), "/relationships/pair/participant/scope_refs")

    assert {item["detail"] for item in result["items"]} == {"nodes.web", "nodes.web.services.http"}
    assert result["context"] == "reference:derived:operating_scope"


def test_incomplete_documents_offer_infrastructure_only_in_qualified_form() -> None:
    payload = _paired(complete=False)
    payload["nodes"]["lan"] = {"type": "switch"}
    payload["infrastructure"] = {"lan": {"count": 1}}

    labels = {item["detail"]: item["label"] for item in _completions(payload, "/objectives/goal/targets")["items"]}

    assert labels["infrastructure.lan"] == "infrastructure.lan"
    assert labels["nodes.lan"] == "lan"
    assert "conditions.alive" not in labels


def test_navigation_and_diagnostics_follow_the_purpose_of_each_field() -> None:
    payload = _set(
        _set(_paired(), FIELDS["objective"], "propositions.ready"), FIELDS["interaction"], "propositions.ready"
    )
    payload["relationships"]["pair"]["target"] = "entities.org"
    text = yaml.safe_dump(payload)

    proposition_paths = {item["path"] for item in language_references(text, "propositions.ready")["occurrences"]}
    organization_paths = {item["path"] for item in language_references(text, "entities.org")["occurrences"]}
    messages = [item["message"] for item in language_diagnostics(text)["diagnostics"]]

    assert "/objectives/goal/targets/0" in proposition_paths
    assert "/action_contracts/probe/interactions/0/target" not in proposition_paths
    assert "/objectives/goal/owner" in organization_paths
    assert "/relationships/pair/target" not in organization_paths
    assert any("propositions.ready is not eligible as an action target" in message for message in messages)
    assert any("target participant endpoint must resolve unambiguously" in message for message in messages)
