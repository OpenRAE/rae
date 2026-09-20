"""Typed effect alternatives and multi-mechanism composition witnesses."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import context_payload, effect_payload, evaluation_payload, ref
from pydantic import ValidationError
from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel
from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel


def targets():
    subject = context_payload()["subject"]
    for kind in ("permit", "deny", "withhold"):
        yield {"kind": kind, "crossing_decision": ref("decision-1", "crossing"), "subject": subject}
    for kind in ("transform", "mask", "route"):
        yield {
            "kind": kind,
            "transformation": ref("transformation-1", "transformation"),
            "source": subject,
            "result": {**subject, "subject_ref": "fresh-subject"},
            "destination_ref": "destination-1",
            "admission_policy": ref("policy-1", "policy"),
        }
    yield {
        "kind": "delay",
        "subject": subject,
        "clock": ref("clock-1", "clock"),
        "earliest_order": 2,
        "latest_order": 3,
        "expiry_order": 4,
        "resumption_policy": ref("policy-1", "policy"),
    }
    yield {
        "kind": "handoff",
        "transition": ref("handoff-1", "control"),
        "participant_address": "participants.student",
        "episode_id": "episode-1",
        "prior_controller_ref": "teacher",
        "resulting_controller_ref": "supervisor",
        "expected_state_revision": 1,
        "completion_obligation": ref("handoff-evidence"),
    }
    yield {
        "kind": "request-review",
        "parent": subject,
        "obligation_ref": "review-1",
        "supervisor_authority": ref("supervisor", "authority"),
        "approval_ref": ref("approval", "control"),
        "denial_ref": ref("denial", "control"),
        "clock": ref("clock-1", "clock"),
        "expiry_order": 3,
        "resumption_policy": ref("policy-1", "policy"),
    }
    for kind, operation in (("interrupt", "pause"), ("shutdown", "terminate")):
        yield {
            "kind": kind,
            "target_kind": "episode",
            "target_ref": "episode-1",
            "operation": operation,
            "lifecycle_authority": ref("lifecycle-authority", "authority"),
            "expected_revision": "rev1",
        }
    yield {
        "kind": "audit",
        "subject": subject,
        "audit_record": ref("audit-1", "audit"),
        "audience_ref": "auditor",
        "retention_policy": ref("retention-policy", "policy"),
    }


@pytest.mark.parametrize("target", list(targets()), ids=lambda value: value["kind"])
def test_every_mpc09_effect_has_a_closed_request_shape(target):
    record = ControlEffectRequestModel.model_validate(effect_payload(target))
    assert record.target.kind == target["kind"]
    with pytest.raises(ValidationError):
        ControlEffectRequestModel.model_validate(effect_payload({**target, "callback": "execute"}))


def add_second_result(payload, *, kind="effect-request", role="mandatory", result_payload=None):
    binding = deepcopy(payload["request"]["selection"]["bindings"][0])
    binding["instance_id"] = "monitor"
    payload["request"]["selection"]["bindings"].append(binding)
    payload["request"]["selection"]["slots"].append(
        {"slot_id": "monitor-slot", "instance_id": "monitor", "kind": kind, "role": role, "dependencies": []}
    )
    payload["request"]["context"]["provider_states"].append(
        {"instance_id": "monitor", "state": ref("monitor-state", "provider-state")}
    )
    from raes_contracts._canonical import canonical_json_digest

    digest = canonical_json_digest(payload["request"]["context"])
    for result in payload["results"]:
        result["context_digest"] = digest
    for support in payload["support"]:
        support["context_digest"] = digest
    support = deepcopy(payload["support"][0])
    support["instance_id"] = "monitor"
    payload["support"].append(support)
    result = deepcopy(payload["results"][-1])
    result.update(
        result_id="result-monitor",
        slot_id="monitor-slot",
        instance_id="monitor",
        binding_digest=canonical_json_digest(binding),
        payload=result_payload or effect_payload(),
    )
    if result["payload"]["kind"] == "effect-request":
        result["payload"]["effect_id"] = "effect-2"
        result["payload"]["key"]["slot"] = "second-effect"
    payload["results"].append(result)
    payload["composition"]["contributing_result_ids"].append("result-monitor")
    return payload


@pytest.mark.parametrize("reverse", [False, True])
def test_unordered_effects_conflict_independently_of_arrival(reverse):
    payload = add_second_result(evaluation_payload())
    if reverse:
        payload["results"].reverse()
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)
    payload["composition"].update(disposition="conflict", blockers=["effect-conflict"])
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "conflict"


def test_advisory_deny_does_not_become_a_mandatory_veto():
    payload = add_second_result(
        evaluation_payload(),
        kind="advisory",
        role="advisory",
        result_payload={"kind": "advisory", "assessment": "negative", "score": 0.9, "sample": ref("sample")},
    )
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "eligible"


def test_empty_optional_selection_preserves_incumbent_denial():
    payload = evaluation_payload()
    payload["request"]["selection"].update(bindings=[], slots=[], required_profiles=[])
    payload["request"]["context"]["provider_states"] = []
    payload.update(results=[], support=[])
    payload["composition"].update(
        incumbent_gate_disposition="deny", disposition="deny", blockers=["incumbent-gates"], contributing_result_ids=[]
    )
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "deny"


@pytest.mark.parametrize("field,value", [("ref", "unpublished-profile"), ("revision", "rev99")])
def test_unknown_profile_authority_is_rejected(field, value):
    from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel

    payload = evaluation_payload()["request"]["selection"]
    payload["required_profiles"] = []
    payload["bindings"][0]["profiles"][0][field] = value
    with pytest.raises(ValidationError):
        ParticipantControlSelectionModel.model_validate(payload)


def test_effect_request_cannot_claim_applied():
    payload = effect_payload()
    payload["disposition"] = "applied"
    with pytest.raises(ValidationError):
        ControlEffectRequestModel.model_validate(payload)


def test_logical_key_conflict_is_recordable_without_dropping_contributors():
    payload = add_second_result(evaluation_payload())
    payload["results"][-1]["payload"]["key"] = deepcopy(payload["results"][1]["payload"]["key"])
    payload["composition"].update(disposition="conflict", blockers=["effect-conflict"])
    record = ParticipantControlEvaluationModel.model_validate(payload)
    assert len(record.results) == 3
