"""Behavioral API-424 contract witnesses, not runtime realization tests."""

import json

import pytest
from participant_control_contract_fixtures import evaluation_payload, selection_payload
from pydantic import ValidationError


def model(payload):
    from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel

    return ParticipantControlEvaluationModel.model_validate(payload)


def test_teaching_fact_requests_inject_without_claiming_execution():
    record = model(evaluation_payload())
    assert record.results[0].payload.tokens == ("coached-hint",)
    assert record.results[1].payload.target.kind == "inject"
    assert record.composition.disposition == "eligible"
    assert record.realizations == ()


@pytest.mark.parametrize("field", ["taint", "labels", "policy", "effects", "plugin", "context", "metadata"])
def test_open_authority_maps_are_rejected(field):
    payload = evaluation_payload()
    payload["request"]["selection"]["bindings"][0][field] = {"arbitrary": "value"}
    with pytest.raises(ValidationError):
        model(payload)


@pytest.mark.parametrize("bad", [True, "2", -1])
def test_resource_bounds_use_strict_nonnegative_integers(bad):
    payload = evaluation_payload()
    payload["request"]["selection"]["bounds"]["max_depth"] = bad
    with pytest.raises(ValidationError):
        model(payload)


def test_protocol_values_are_deeply_immutable_and_detached():
    payload = evaluation_payload()
    record = model(payload)
    payload["request"]["context"]["state_cut"]["predecessor_event_refs"].append("later")
    assert record.request.context.state_cut.predecessor_event_refs == ("event-0",)
    with pytest.raises(ValidationError):
        record.request.context.subject.subject_ref = "forged"
    with pytest.raises(ValidationError):
        record.results[0].payload.tokens = ()


@pytest.mark.parametrize("status", ["missing", "unknown", "unsupported", "stale", "failed", "weakened"])
def test_mandatory_unresolved_slots_cannot_claim_eligibility(status):
    payload = evaluation_payload()
    payload["results"][0].update(status=status, payload=None)
    with pytest.raises(ValidationError):
        model(payload)


def test_exact_cut_and_binding_digest_are_required():
    payload = evaluation_payload()
    payload["request"]["context"]["expected_history_heads"][0]["revision"] = "later"
    with pytest.raises(ValidationError):
        model(payload)


def test_selection_rejects_cycles_and_missing_required_profiles():
    from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel

    payload = selection_payload()
    payload["slots"][0]["dependencies"] = [{"slot_id": "rule", "kind": "effect-request"}]
    with pytest.raises(ValidationError):
        ParticipantControlSelectionModel.model_validate(payload)
    payload = selection_payload()
    payload["required_profiles"].append("absent")
    with pytest.raises(ValidationError):
        ParticipantControlSelectionModel.model_validate(payload)


def test_request_parser_hides_rejected_values_and_rejects_duplicate_keys():
    from raes_contracts.contracts.participant_control_composition import parse_participant_control_evaluation

    with pytest.raises(ValueError) as caught:
        parse_participant_control_evaluation('{"private-secret":"never-echo","private-secret":1}')
    assert "never-echo" not in str(caught.value)
    assert "private-secret" not in str(caught.value)
    assert parse_participant_control_evaluation(json.dumps(evaluation_payload())).evaluation_id == "evaluation-1"
