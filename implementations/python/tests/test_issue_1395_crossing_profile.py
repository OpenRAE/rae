"""Closed multi-operation profile admission; no equivalence assertion."""

from copy import deepcopy

import pytest
from crossing_model_fixtures import profile_payload
from raes_contracts.behavioral_relation_profiles import BehavioralRelationProfileModel


def multi_payload():
    from raes_contracts._participant_crossing_multi_profile import DOMAINS, HIDDEN, VISIBLE

    payload = profile_payload()
    payload.update(
        profile_id="participant-crossing-multi-operation-dpbb-finite-v1",
        profile_revision="rev1",
        left_carrier_ref="sem-230-participant-crossing-multi-abstract",
        observation_projection_ref="participant-crossing-multi-operation-projection",
    )
    payload["parameters"] = {
        "kind": "participant-crossing-multi-dpbb/v1",
        "domains": deepcopy(DOMAINS),
        "left": {
            "model_id": payload["left_carrier_ref"],
            "revision": "rev1",
            "source_path": "implementations/formal/participant_crossing/multi_abstract.py",
            "source_digest": "sha256:" + "1" * 64,
            "initial_state_ordinal": 0,
        },
        "right": {
            "model_id": "api-423-run-319-crossing-multi-kernel",
            "revision": "rev1",
            "source_path": "implementations/formal/participant_crossing/multi_concrete.py",
            "source_digest": "sha256:" + "2" * 64,
            "initial_state_ordinal": 0,
        },
        "visible_labels": list(VISIBLE),
        "hidden_labels": list(HIDDEN),
        "checker_tau": "internal",
        "complete_carrier": True,
        "depth_or_sample_bound": None,
        "fresh_operations": 2,
        "identity_reuse": "conflict-only-no-recycling",
        "order": "sequential-total-order",
        "time": "untimed",
        "probability": "excluded",
        "concurrency": "excluded",
        "controller_handoff": "excluded",
        "completion": "cached-result-observation",
        "failure_scope": "response-loss-after-durable-completion-and-clean-p1-restart",
        "history_scope": "crossing-batch-heads-other-histories-fixed",
        "context_scope": "synthetic-fixed-authority-with-exact-request-commitments",
    }
    return payload


def test_multi_profile_is_admitted_without_widening_legacy_profile():
    payload = multi_payload()
    assert BehavioralRelationProfileModel.model_validate(payload).model_dump(mode="json") == payload
    old = profile_payload()
    assert BehavioralRelationProfileModel.model_validate(old).model_dump(mode="json") == old
    old["parameters"]["fresh_operations"] = 2
    with pytest.raises(ValueError):
        BehavioralRelationProfileModel.model_validate(old)


@pytest.mark.parametrize("mutation", ["budget", "head", "label", "projection", "right", "bool", "shared"])
def test_multi_profile_rejects_incomplete_or_rebound_carriers(mutation):
    payload = multi_payload()
    params = payload["parameters"]
    if mutation == "budget":
        params["fresh_operations"] = 3
    elif mutation == "head":
        params["domains"]["history_head"].pop()
    elif mutation == "label":
        params["visible_labels"][0] = "tau"
    elif mutation == "projection":
        payload["observation_projection_ref"] = "participant-crossing-projection"
    elif mutation == "right":
        params["right"]["model_id"] = params["left"]["model_id"]
    elif mutation == "bool":
        params["right"]["initial_state_ordinal"] = False
    else:
        params["right"]["source_digest"] = params["left"]["source_digest"]
    with pytest.raises(ValueError):
        BehavioralRelationProfileModel.model_validate(payload)


def test_published_schema_admits_multi_variant():
    import json

    from crossing_model_fixtures import ROOT
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts/schemas/profiles/behavioral-relation-profile-v1.json").read_bytes())
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(multi_payload()))
    changed = multi_payload()
    changed["parameters"]["domains"]["history_head"].pop()
    assert list(validator.iter_errors(changed))


@pytest.mark.parametrize("payload_factory", [profile_payload, multi_payload], ids=["single", "multi"])
@pytest.mark.parametrize("value", [1, 1.0, 0, False, None, "true", "1"])
def test_complete_carrier_requires_json_boolean_true_in_python_and_schema(payload_factory, value):
    import json

    from crossing_model_fixtures import ROOT
    from jsonschema import Draft202012Validator

    payload = payload_factory()
    payload["parameters"]["complete_carrier"] = value
    schema = json.loads((ROOT / "contracts/schemas/profiles/behavioral-relation-profile-v1.json").read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValueError):
        BehavioralRelationProfileModel.model_validate(payload)


def test_multi_binding_checks_right_carrier_and_opacity_admission_rejects_it():
    from raes_contracts.behavioral_relations import (
        load_behavioral_relation_catalog_revision,
        validate_behavioral_claim_binding,
    )
    from test_issue_971_crossing_profile import crossing_binding

    profile = BehavioralRelationProfileModel.model_validate(multi_payload())
    binding = crossing_binding(profile)
    catalog = load_behavioral_relation_catalog_revision("rev8")
    validate_behavioral_claim_binding(binding, catalog=catalog, profile=profile)
    wrong_carrier = binding.model_copy(update={"right_carrier_ref": "wrong"})
    with pytest.raises(ValueError, match="right carrier"):
        validate_behavioral_claim_binding(wrong_carrier, catalog=catalog, profile=profile)
    from types import SimpleNamespace

    from raes_processor.participant_opacity import ParticipantOpacityOperationalError, _service

    request = SimpleNamespace(analysis_profile=_service.ANALYSIS_PROFILE)
    with pytest.raises(ParticipantOpacityOperationalError, match="opacity parameter profile"):
        _service._validate_profile_admission(request, profile)
