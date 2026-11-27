"""Every relationship reference offered in a valid context survives the owning semantic checks."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from raes import parse_sdl
from raes.language_service import language_completions
from test_act_617_mixed_control import _scenario_yaml
from test_issue_1339_editor_eligibility import _paired
from test_issue_1339_reference_eligibility import _payload
from test_issue_1339_relationship_endpoints import _ENDPOINT_RELATIONSHIPS, matrix_payload


@pytest.mark.parametrize("complete", [False, True])
def test_participant_endpoint_completion_never_offers_the_selected_peer(complete: bool) -> None:
    payload = _paired(complete=complete)
    items = language_completions(yaml.safe_dump(payload), cursor_path="/relationships/pair/target")["items"]
    assert {item["detail"] for item in items} == {"agents.blue"}


@pytest.mark.parametrize(
    "kind", ["domain_controller_for", "joins_domain", "forest_trusts", "placed_on_carrier", "uses_shared_service"]
)
@pytest.mark.parametrize("side", ["source", "target"])
def test_each_typed_endpoint_candidate_validates_when_inserted_into_its_relationship(kind: str, side: str) -> None:
    payload = matrix_payload()
    if kind == "joins_domain":
        relationship = {
            "type": kind,
            "source": "nodes.workstation",
            "target": "corp",
            "domain_join": {"controller_refs": ["dc"]},
        }
    else:
        relationship = deepcopy(_ENDPOINT_RELATIONSHIPS[kind])
    payload["relationships"]["probe"] = relationship
    parse_sdl(yaml.safe_dump(payload))
    items = language_completions(yaml.safe_dump(payload), cursor_path=f"/relationships/probe/{side}")["items"]
    assert items
    for item in items:
        candidate = deepcopy(payload)
        candidate["relationships"]["probe"][side] = item["label"]
        parse_sdl(yaml.safe_dump(candidate))


def _controlled_relationship() -> dict:
    payload = yaml.safe_load(_scenario_yaml())
    for agent in payload["agents"].values():
        agent["operating_scope"] = ["nodes.web", "nodes.internal"]
    payload["relationships"] = {
        "supervises": {
            "type": "participant",
            "source": "supervisor-agent",
            "target": "red-agent",
            "participant": {
                "kind": "supervision",
                "scope_refs": ["nodes.web"],
                "control_specification_ref": "controlled-red",
            },
        }
    }
    return payload


@pytest.mark.parametrize("suffix", ["", "/0"])
def test_selected_control_specification_bounds_scope_completion(suffix: str) -> None:
    payload = _controlled_relationship()
    parse_sdl(yaml.safe_dump(payload))
    items = language_completions(
        yaml.safe_dump(payload), cursor_path=f"/relationships/supervises/participant/scope_refs{suffix}"
    )["items"]
    assert {item["detail"] for item in items} == {"nodes.web"}
    for item in items:
        payload["relationships"]["supervises"]["participant"]["scope_refs"] = [item["label"]]
        parse_sdl(yaml.safe_dump(payload))


@pytest.mark.parametrize("kind", ["domain_controller_for", "placed_on_carrier", "forest_trusts"])
def test_incomplete_typed_details_still_apply_known_endpoint_attribute_rules(kind: str) -> None:
    payload = matrix_payload()
    relationship = deepcopy(_ENDPOINT_RELATIONSHIPS[kind])
    payload["relationships"]["probe"] = relationship
    detail = {
        "domain_controller_for": "domain_controller",
        "placed_on_carrier": "carrier_placement",
        "forest_trusts": "forest_trust",
    }[kind]
    relationship.pop(detail)
    side = "source" if kind == "domain_controller_for" else "target"
    items = language_completions(yaml.safe_dump(payload), cursor_path=f"/relationships/probe/{side}")["items"]
    refused = (
        "nodes.lan"
        if side == "source"
        else ("nodes.dc" if kind == "placed_on_carrier" else "identity_forests.enterprise")
    )
    assert all(item["detail"] != refused for item in items)


@pytest.mark.parametrize("field", ["source_action_refs", "scope_refs", "authority_basis_refs"])
def test_a_reference_cursor_in_a_not_yet_authored_participant_block_remains_safe(field: str) -> None:
    result = language_completions(yaml.safe_dump(_payload()), cursor_path=f"/relationships/link/participant/{field}")
    assert result["status"] == "ok"
    assert result["items"]


def test_an_overlong_cursor_index_does_not_escape_the_completion_boundary() -> None:
    payload = _controlled_relationship()
    pointer = "/relationships/supervises/participant/scope_refs/" + "9" * 5000
    result = language_completions(yaml.safe_dump(payload), cursor_path=pointer)
    assert result["status"] == "ok"
