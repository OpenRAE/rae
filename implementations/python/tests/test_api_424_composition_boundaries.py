"""Negative witnesses for exact dependencies, bounds and owning domains."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import evaluation_payload
from pydantic import ValidationError
from raes_contracts._canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel


def refresh(payload):
    bindings = {b["instance_id"]: b for b in payload["request"]["selection"]["bindings"]}
    for result in payload["results"]:
        result["binding_digest"] = canonical_json_digest(bindings[result["instance_id"]])
        result["context_digest"] = canonical_json_digest(payload["request"]["context"])
    for support in payload["support"]:
        support["context_digest"] = canonical_json_digest(payload["request"]["context"])


def test_transitive_mandatory_dependency_cannot_hide_unresolved_advisory_fact():
    payload = evaluation_payload()
    slots = payload["request"]["selection"]["slots"]
    slots[0]["role"] = "advisory"
    middle = deepcopy(slots[0])
    middle.update(slot_id="middle", dependencies=[{"slot_id": "fact", "kind": "ifc-fact"}])
    slots.append(middle)
    slots[1]["dependencies"] = [{"slot_id": "middle", "kind": "ifc-fact"}]
    result = deepcopy(payload["results"][0])
    result.update(result_id="result-middle", slot_id="middle")
    payload["results"].append(result)
    payload["results"][0].update(status="unknown", payload=None)
    payload["composition"]["contributing_result_ids"] = ["result-fact", "result-middle", "result-rule"]
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)


@pytest.mark.parametrize("bound", ["max_firings_per_rule", "max_depth"])
def test_zero_remaining_trigger_bound_rejects_new_effect(bound):
    payload = evaluation_payload()
    payload["request"]["selection"]["bounds"][bound] = 0
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)


def test_ifc_result_requires_its_selected_domain():
    payload = evaluation_payload()
    profile = payload["request"]["selection"]["bindings"][0]["profiles"][0]
    from raes_contracts.participant_flow_policy_profiles import PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST

    profile.update(
        ref="participant-boundary-flow-policy-v1", digest=PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST
    )
    payload["request"]["selection"]["required_profiles"] = [profile["ref"]]
    refresh(payload)
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)


def test_knowledge_of_only_some_inputs_is_not_complete_propagation():
    payload = evaluation_payload()
    payload["results"][0]["payload"]["source_refs"][0]["ref"] = "different-source"
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)


def test_bounded_downgrade_remains_disclosed_not_eligible():
    payload = evaluation_payload()
    from participant_control_contract_fixtures import ref

    payload["support"][0].update(
        effective_level="bounded",
        constraints=[ref("bounded-source", "constraint")],
        downgrade_authority=ref("downgrade", "authority"),
    )
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)
    payload["composition"].update(disposition="weakened", blockers=["support:influence"])
    assert ParticipantControlEvaluationModel.model_validate(payload).support[0].effective_level == "bounded"


def test_profile_digest_must_resolve_the_published_revision():
    from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel

    payload = evaluation_payload()["request"]["selection"]
    payload["bindings"][0]["profiles"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError):
        ParticipantControlSelectionModel.model_validate(payload)


def test_prior_firings_survive_retry_and_new_cut():
    payload = evaluation_payload()
    payload["request"]["context"]["rule_firings"] = [
        {"rule_id": "hint-followup", "rule_revision": "rev1", "firing_epochs": ["epoch-0"]}
    ]
    refresh(payload)
    with pytest.raises(ValidationError, match="per-rule firing budget"):
        ParticipantControlEvaluationModel.model_validate(payload)
    payload["results"][1]["payload"]["key"]["firing_epoch"] = "epoch-0"
    assert ParticipantControlEvaluationModel.model_validate(payload).request.context.attempt == 1
