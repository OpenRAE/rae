"""API-424 owns deriving a composition; RUN-320 must not reproduce its rules."""

import pytest
from participant_control_contract_fixtures import evaluation_payload, ref


def _request_results_support(payload):
    from raes_contracts.contracts.participant_control_composition import ParticipantControlRequestModel
    from raes_contracts.contracts.participant_control_results import (
        ControlEffectiveSupportModel,
        ControlMechanismResultModel,
    )

    request = ParticipantControlRequestModel.model_validate(payload["request"])
    results = tuple(ControlMechanismResultModel.model_validate(item) for item in payload["results"])
    support = tuple(ControlEffectiveSupportModel.model_validate(item) for item in payload["support"])
    return request, results, support


def _derive(payload):
    from raes_contracts.contracts.participant_control_composition import derive_control_composition

    request, results, support = _request_results_support(payload)
    return derive_control_composition(
        request,
        results,
        support,
        incumbent_gate_disposition=payload["composition"]["incumbent_gate_disposition"],
        incumbent_gate_evidence=ref("gate-evidence"),
    )


def _revalidated(payload, composition):
    from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel

    return ParticipantControlEvaluationModel.model_validate(
        {**payload, "composition": composition.model_dump(mode="json")}
    )


def test_derivation_reproduces_the_published_eligible_composition():
    payload = evaluation_payload()
    composition = _derive(payload)
    assert composition.disposition == "eligible"
    assert composition.blockers == ()
    assert composition.contributing_result_ids == ("result-fact", "result-rule")
    _revalidated(payload, composition)


def test_derived_composition_always_satisfies_the_published_validator():
    payload = evaluation_payload()
    payload["results"][0]["status"] = "missing"
    payload["results"][0]["payload"] = None
    composition = _derive(payload)
    assert "slot:fact" in composition.blockers
    assert composition.disposition != "eligible"
    _revalidated(payload, composition)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("stale", "stale"),
        ("unsupported", "unsupported"),
        ("weakened", "weakened"),
        ("failed", "failed"),
        ("missing", "failed"),
        ("unknown", "failed"),
    ],
)
def test_unsatisfied_mandatory_status_selects_its_exact_disposition(status, expected):
    payload = evaluation_payload()
    payload["results"][0]["status"] = status
    payload["results"][0]["payload"] = None
    composition = _derive(payload)
    assert composition.disposition == expected
    _revalidated(payload, composition)


@pytest.mark.parametrize("disposition", ["deny", "withhold", "abstain"])
def test_mandatory_decision_disposition_is_retained(disposition):
    payload = evaluation_payload()
    payload["request"]["selection"]["slots"][1]["kind"] = "decision"
    payload["results"][1]["payload"] = {
        "kind": "decision",
        "disposition": disposition,
        "rule": ref("hint-followup", "rule"),
    }
    composition = _derive(payload)
    assert composition.disposition == ("failed" if disposition == "abstain" else disposition)
    assert "slot:rule" in composition.blockers
    _revalidated(payload, composition)


def test_downgraded_support_is_weakened_not_eligible():
    payload = evaluation_payload()
    payload["support"][0]["effective_level"] = "bounded"
    payload["support"][0]["constraints"] = [ref("bounded-explicit-flows", "constraint")]
    composition = _derive(payload)
    assert composition.disposition == "weakened"
    assert composition.blockers == ("support:influence",)
    _revalidated(payload, composition)


def test_non_permit_incumbent_gate_blocks_without_any_provider_blocker():
    payload = evaluation_payload()
    payload["composition"]["incumbent_gate_disposition"] = "deny"
    composition = _derive(payload)
    assert composition.blockers == ("incumbent-gates",)
    assert composition.disposition == "deny"
    _revalidated(payload, composition)


def test_incompatible_effect_requests_derive_conflict():
    from raes_contracts.contracts.participant_control_composition import control_digest
    from raes_contracts.contracts.participant_control_selection import ControlMechanismBindingModel

    payload = evaluation_payload()
    payload["request"]["selection"]["slots"].append(
        {
            "slot_id": "rival",
            "instance_id": "influence",
            "kind": "effect-request",
            "role": "mandatory",
            "dependencies": [],
        }
    )
    rival = dict(payload["results"][1])
    rival_payload = {
        **rival["payload"],
        "effect_id": "effect-2",
        "key": {**rival["payload"]["key"], "slot": "rival"},
        "target": {
            **rival["payload"]["target"],
            "result_item_ref": "reflection-result-2",
        },
    }
    payload["results"].append(
        {
            **rival,
            "result_id": "result-rival",
            "slot_id": "rival",
            "payload": rival_payload,
            "binding_digest": control_digest(
                ControlMechanismBindingModel.model_validate(payload["request"]["selection"]["bindings"][0])
            ),
        }
    )
    composition = _derive(payload)
    assert "effect-conflict" in composition.blockers
    assert composition.disposition == "conflict"
    _revalidated(payload, composition)


@pytest.mark.parametrize("misstated", ["deny", "withhold", "unsupported", "failed", "conflict"])
def test_a_persisted_record_cannot_misstate_why_composition_failed(misstated):
    """Validation requires the canonical disposition, not just non-eligibility."""

    payload = evaluation_payload()
    payload["results"][0]["status"] = "stale"
    payload["results"][0]["payload"] = None
    composition = _derive(payload)
    assert composition.disposition == "stale"

    forged = {**composition.model_dump(mode="json"), "disposition": misstated}
    with pytest.raises(ValueError):
        _revalidated(payload, type(composition).model_validate(forged))
