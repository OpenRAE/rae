"""#1363: the API-409 participant-control-occurrence-v2 carrier, its ranges and its reader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from mixed_control_v2_support import History
from pydantic import TypeAdapter, ValidationError
from raes.participant_mixed_control_policy import MixedControlCoordinate
from raes_contracts.contracts import (
    ParticipantControlOccurrenceModel,
    ParticipantControlOccurrenceV2Model,
    parse_participant_control_occurrence,
)
from raes_contracts.contracts.participant_control_coordinates import ControlCount, ControlPosition
from raes_contracts.participant_mixed_control_vocabulary import MIXED_CONTROL_COORDINATE_LIMIT
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "contracts/fixtures/participant-runtime/participant-control-occurrence-v2"
V1_FIXTURE = REPO_ROOT / "contracts/fixtures/participant-runtime/participant-control-occurrence-v1/valid/proposal.json"


def _accepted(**fields: Any) -> dict[str, Any]:
    return History().accepted_payload("take", **fields)


def _rejected(**attempt: Any) -> dict[str, Any]:
    return History().rejected_payload("take", "stale-state", **attempt)


@pytest.mark.parametrize("annotation", [ControlCount, ControlPosition, MixedControlCoordinate])
def test_the_authored_coordinate_limit_is_the_api_424_count_bound(annotation: object) -> None:
    adapter = TypeAdapter(annotation)
    assert adapter.validate_python(MIXED_CONTROL_COORDINATE_LIMIT) == MIXED_CONTROL_COORDINATE_LIMIT
    for value in (MIXED_CONTROL_COORDINATE_LIMIT + 1, True, "1"):
        with pytest.raises(ValidationError):
            adapter.validate_python(value)
    if annotation is ControlPosition:
        with pytest.raises(ValidationError):
            adapter.validate_python(0)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"resulting_state_revision": 2}, "advance state revision by exactly one"),
        ({"expected_history_head": 1}, "append at its expected history head"),
        ({"effective_order": 10, "valid_from_order": 11, "valid_until_order": 20}, "fall within"),
        ({"effective_order": 30, "valid_from_order": 11, "valid_until_order": 20}, "fall within"),
        ({"effective_order": 10, "valid_from_order": 12, "valid_until_order": 8}, "must not be inverted"),
    ],
)
def test_context_free_accepted_arithmetic_is_enforced_by_the_model(fields: dict, message: str) -> None:
    payload = _accepted(**fields)
    with pytest.raises(ValidationError, match=message):
        ParticipantControlOccurrenceV2Model.model_validate(payload)


def test_inclusive_bounds_equal_to_the_order_pass_and_each_rule_is_a_published_invariant() -> None:
    record = ParticipantControlOccurrenceV2Model.model_validate(
        _accepted(effective_order=10, valid_from_order=10, valid_until_order=10)
    )
    assert (record.occurrence.valid_from_order, record.occurrence.valid_until_order) == (10, 10)
    invariants = schema_bundle()["participant-control-occurrence-v2"]["x-raes-invariants"]
    by_validator = {item["id"]: item["validator"] for item in invariants}
    model = "raes_contracts.contracts.ParticipantControlOccurrenceV2Model"
    for rule in ("revision-advance", "history-head", "validity-bounds", "acting-controller"):
        assert by_validator[f"participant-control-occurrence-v2-{rule}"] == model


@pytest.mark.parametrize("value", [True, "5", 1_000_001, -1])
@pytest.mark.parametrize("field", ["expected_state_revision", "effective_order", "expected_history_head"])
def test_unrepresentable_attempted_coordinates_create_no_fact(field: str, value: object) -> None:
    for payload in (_rejected(**{field: value}), _accepted(**{field: value})):
        with pytest.raises(ValidationError):
            ParticipantControlOccurrenceV2Model.model_validate(payload)


@pytest.mark.parametrize("ref", ["x" * 257, "-leading", "has space", ""])
def test_unrepresentable_refs_create_no_fact(ref: str) -> None:
    for payload in (_rejected(permitted_transition_ref=ref), _accepted(permitted_transition_ref=ref)):
        with pytest.raises(ValidationError):
            ParticipantControlOccurrenceV2Model.model_validate(payload)


def test_an_overflowing_application_is_refused_but_its_rejection_is_recordable() -> None:
    limit = MIXED_CONTROL_COORDINATE_LIMIT
    overflowing = _accepted(expected_state_revision=limit, resulting_state_revision=limit + 1)
    with pytest.raises(ValidationError):
        ParticipantControlOccurrenceV2Model.model_validate(overflowing)
    history = History()
    payload = history.rejected_payload(
        "take", "coordinate-out-of-range", expected_state_revision=limit, observed={"state_revision": limit}
    )
    record = ParticipantControlOccurrenceV2Model.model_validate(payload)
    assert record.occurrence.reason_code.value == "coordinate-out-of-range"
    assert record.occurrence.attempted.expected_state_revision == limit


@pytest.mark.parametrize("disposition", ["accepted", "rejected"])
def test_a_full_history_cannot_be_extended_by_either_disposition(disposition: str) -> None:
    payload = _accepted() if disposition == "accepted" else _rejected()
    payload["occurrence"]["occurrence_revision"] = MIXED_CONTROL_COORDINATE_LIMIT + 1
    if disposition == "accepted":
        payload["occurrence"]["expected_history_head"] = MIXED_CONTROL_COORDINATE_LIMIT
    with pytest.raises(ValidationError):
        ParticipantControlOccurrenceV2Model.model_validate(payload)


@pytest.mark.parametrize("disposition", ["recorded", "limited", "superseded", "cancelled"])
def test_only_accepted_and_rejected_are_v2_dispositions(disposition: str) -> None:
    for payload in (_accepted(), _rejected()):
        payload["occurrence"]["disposition"] = disposition
        with pytest.raises(ValidationError):
            ParticipantControlOccurrenceV2Model.model_validate(payload)


def test_the_actor_is_the_acting_controller_on_both_dispositions() -> None:
    for payload in (_accepted(), _rejected()):
        payload["actor_ref"] = "participant.behavior.someone-else"
        with pytest.raises(ValidationError, match="acting controller"):
            ParticipantControlOccurrenceV2Model.model_validate(payload)


def test_cancellation_carries_no_outcome_and_rejections_carry_no_validity_bounds() -> None:
    payload = History().accepted_payload("cancel", target_kind="attempt", target_ref="attempt-1", target_revision=1)
    payload["occurrence"]["cancellation_effect"] = "prevented"
    with pytest.raises(ValidationError):
        ParticipantControlOccurrenceV2Model.model_validate(payload)
    rejected = _rejected()
    rejected["occurrence"]["valid_from_order"] = 0
    with pytest.raises(ValidationError):
        ParticipantControlOccurrenceV2Model.model_validate(rejected)


def test_the_reader_dispatches_on_lineage_and_never_upgrades_v1() -> None:
    v1 = json.loads(V1_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(parse_participant_control_occurrence(v1), ParticipantControlOccurrenceModel)
    assert isinstance(parse_participant_control_occurrence(_accepted()), ParticipantControlOccurrenceV2Model)
    relabelled = ({**v1, "schema_version": "2.0.0"}, {**_accepted(), "schema_version": "1.0.0"})
    for payload in relabelled:
        with pytest.raises(ValidationError):
            parse_participant_control_occurrence(payload)
    with pytest.raises(ValueError, match="lineage is unsupported"):
        parse_participant_control_occurrence({**v1, "schema_version": "3.0.0"})


def test_published_v2_fixtures_agree_with_the_model_and_schema() -> None:
    schema = json.loads(
        (REPO_ROOT / "contracts/schemas/participant-runtime/participant-control-occurrence-v2.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema == schema_bundle()["participant-control-occurrence-v2"]
    validator = Draft202012Validator(schema)
    valid = sorted((FIXTURES / "valid").glob("*.json"))
    invalid = sorted((FIXTURES / "invalid").glob("*.json"))
    assert valid
    assert invalid
    for path in valid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ParticipantControlOccurrenceV2Model.model_validate(payload)
        assert not list(validator.iter_errors(payload)), path.name
    for path in invalid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            ParticipantControlOccurrenceV2Model.model_validate(payload)
        assert list(validator.iter_errors(payload)), path.name
