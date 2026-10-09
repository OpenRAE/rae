"""Editor completion, navigation and diagnostics share the reference purposes (#1339)."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from raes import SDLValidationError
from raes.language_service import language_completions, language_diagnostics, language_references
from test_issue_1339_reference_eligibility import (
    _PAIR,
    FIELDS,
    _parse,
    _payload,
    _refusal,
    _set,
    _with_condition_named_web,
)


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


def _occurrences(payload: dict, symbol: str) -> set[str]:
    return {item["path"] for item in language_references(yaml.safe_dump(payload), symbol)["occurrences"]}


def _pointer(payload: dict, path: tuple) -> str:
    """Return the JSON pointer of the reference value at *path*, the first item for a list field."""

    node = payload
    for key in path:
        node = node[key]
    return "/" + "/".join(str(key) for key in path) + ("/0" if isinstance(node, list) else "")


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


@pytest.mark.parametrize("complete", [True, False], ids=["valid-document", "incomplete-document"])
@pytest.mark.parametrize(
    "pointer",
    [
        "/objectives/goal/targets",
        "/action_contracts/probe/interactions/0/target",
        "/action_contracts/probe/interactions/0/shared_state_refs",
        "/action_contracts/probe/effects/0/target_refs",
        "/behavior_specifications/red-behavior/authority_scope_refs",
    ],
)
def test_a_bare_name_shared_with_an_ineligible_declaration_is_offered_only_in_qualified_form(
    pointer: str, complete: bool
) -> None:
    labels = {
        item["detail"]: item["label"]
        for item in _completions(_with_condition_named_web(_paired(complete=complete)), pointer)["items"]
    }

    assert labels["nodes.web"] == "nodes.web"
    assert "conditions.web" not in labels


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
        suggested = _set(_paired(), path, item["label"])
        _parse(suggested)
        assert _pointer(suggested, path) in _occurrences(suggested, item["detail"])
    assert result["context"] == f"reference:{context}"


@pytest.mark.parametrize(
    ("change", "labels"),
    [
        ({}, ["web"]),
        ({("agents", "blue", "operating_scope"): "${scope}"}, ["http", "web"]),
        ({("relationships", "pair", "target"): "${peer}"}, ["http", "web"]),
    ],
    ids=["both-endpoints", "parameterized-endpoint-scope", "parameterized-endpoint"],
)
def test_participant_relationship_scope_completion_offers_what_both_endpoints_hold(
    change: dict, labels: list[str]
) -> None:
    """Validation requires each scope ref within both endpoints' operating scope, unless one is unresolved."""

    payload = _paired()
    payload["variables"] = {
        "scope": {"type": "string", "default": "web"},
        "peer": {"type": "string", "default": "blue"},
    }
    payload["agents"]["red"]["operating_scope"] = ["web", "http"]
    payload["agents"]["blue"]["operating_scope"] = ["nodes.web"]
    for path, value in change.items():
        _set(payload, path, value)

    result = _completions(payload, "/relationships/pair/participant/scope_refs")

    assert sorted(item["label"] for item in result["items"]) == labels
    assert result["context"] == "reference:derived:operating_scope"
    for label in labels:
        payload["relationships"]["pair"]["participant"]["scope_refs"] = [label]
        _parse(payload)
    if not change:
        payload["relationships"]["pair"]["participant"]["scope_refs"] = ["http"]
        with pytest.raises(SDLValidationError, match="scope_refs must stay within participant 'blue' operating_scope"):
            _parse(payload)


def test_incomplete_documents_offer_infrastructure_only_in_qualified_form() -> None:
    payload = _paired(complete=False)
    payload["nodes"]["lan"] = {"type": "switch"}
    payload["infrastructure"] = {"lan": {"count": 1}}

    labels = {item["detail"]: item["label"] for item in _completions(payload, "/objectives/goal/targets")["items"]}

    assert labels["infrastructure.lan"] == "infrastructure.lan"
    assert labels["nodes.lan"] == "lan"
    assert "conditions.alive" not in labels


def test_participant_relationship_authority_completion_offers_only_the_source_anchors() -> None:
    payload = _paired()
    payload["agents"]["red"]["authority_anchors"] = ["entities.org"]
    refinement = payload["relationships"]["pair"]["participant"]

    result = _completions(payload, "/relationships/pair/participant/authority_basis_refs")

    assert [(item["label"], item["detail"]) for item in result["items"]] == [("org", "entities.org")]
    assert result["context"] == "reference:eligible:authority_anchor"
    refinement["authority_basis_refs"] = ["org"]
    _parse(payload)
    refinement["authority_basis_refs"] = ["nodes.web"]
    with pytest.raises(SDLValidationError, match="authority_basis_refs must not widen source authority"):
        _parse(payload)


@pytest.mark.parametrize("complete", [True, False], ids=["valid-document", "incomplete-document"])
def test_navigation_attributes_an_ambiguous_participant_endpoint_to_no_candidate(complete: bool) -> None:
    payload = _paired(complete=complete)
    payload["entities"]["blue"] = {"role": "blue"}
    endpoint = "/relationships/pair/target"

    assert endpoint not in _occurrences(payload, "agents.blue") | _occurrences(payload, "entities.blue")
    payload["relationships"]["pair"]["target"] = "agents.blue"
    assert endpoint in _occurrences(payload, "agents.blue")


@pytest.mark.parametrize("complete", [True, False], ids=["valid-document", "incomplete-document"])
@pytest.mark.parametrize("field", ["objective", "interaction", "shared-state", "effect", "authority-scope"])
def test_navigation_attributes_a_bare_name_shared_with_an_ineligible_declaration_to_no_declaration(
    field: str, complete: bool
) -> None:
    """Validation refuses the bare name as ambiguous, so navigation must not select the eligible declaration."""

    payload = _set(_with_condition_named_web(_paired(complete=complete)), FIELDS[field], "web")
    pointer = _pointer(payload, FIELDS[field])

    assert pointer not in _occurrences(payload, "nodes.web") | _occurrences(payload, "conditions.web")
    assert pointer in _occurrences(_set(payload, FIELDS[field], "nodes.web"), "nodes.web")


def test_navigation_resolves_operating_scope_through_its_own_aliases() -> None:
    payload = _paired()
    payload["nodes"]["lan"] = {"type": "switch"}
    payload["infrastructure"] = {"lan": {"count": 1}}
    payload["agents"]["red"]["operating_scope"] = ["lan", "http"]
    _parse(payload)

    assert "/agents/red/operating_scope/0" in _occurrences(payload, "infrastructure.lan")
    assert "/agents/red/operating_scope/0" not in _occurrences(payload, "nodes.lan")
    assert "/agents/red/operating_scope/1" in _occurrences(payload, "nodes.web.services.http")


@pytest.mark.parametrize("complete", [True, False], ids=["valid-document", "incomplete-document"])
def test_objective_target_candidates_complete_and_navigate_as_objective_subjects(complete: bool) -> None:
    """A candidate resolves where its slot does, so completion and navigation follow the slot's purpose."""

    payload = _paired(complete=complete)
    candidate = {"reference": "conditions.alive"}
    payload["variation_points"] = {
        "subjects": {
            "kind": "subset",
            "target": {"kind": "collection", "owner": "goal", "slot": "objectives.targets"},
            "members": {"candidate": candidate},
        }
    }
    pointer = "/variation_points/subjects/members/candidate/reference"

    result = _completions(payload, pointer)

    assert result["context"] == "reference:eligible:objective_subject"
    assert {"propositions.ready", "agents.blue"} <= {item["detail"] for item in result["items"]}
    assert "conditions.alive" not in {item["detail"] for item in result["items"]}
    assert pointer not in _occurrences(payload, "conditions.alive")
    candidate["reference"] = "propositions.ready"
    assert pointer in _occurrences(payload, "propositions.ready")


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
    assert any(_refusal("an action target", "propositions.ready") in message for message in messages)
    assert any("target participant endpoint must resolve unambiguously" in message for message in messages)
