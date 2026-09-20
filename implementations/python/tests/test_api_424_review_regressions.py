"""Review regressions for MPC lifecycle compatibility, replay and conflict joins."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import effect_payload, evaluation_payload, ref
from pydantic import ValidationError
from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel, control_digest
from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel
from test_api_424_composition_boundaries import refresh
from test_api_424_control_effects import add_second_result, targets


@pytest.mark.parametrize(
    "scope,target",
    [
        ("participant", "participants.student"),
        ("episode", "episode-1"),
        ("run", "run-1"),
        ("execution", "execution-1"),
        ("workflow", "workflow-1"),
    ],
)
@pytest.mark.parametrize("operation", ["terminate", "pause", "cancel", "interrupt"])
def test_lifecycle_before_live_target_operation_conflicts(scope, target, operation):
    lifecycle = {
        "kind": "shutdown" if operation == "terminate" else "interrupt",
        "target_kind": scope,
        "target_ref": target,
        "operation": operation,
        "lifecycle_authority": ref("lifecycle", "authority"),
        "expected_revision": "rev1",
    }
    payload = add_second_result(evaluation_payload(), result_payload=effect_payload(lifecycle))
    payload["results"][1]["payload"]["predecessor_effect_ids"] = ["effect-2"]
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)
    payload["composition"].update(disposition="conflict", blockers=["effect-conflict"])
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "conflict"
    # Injection while live, followed by lifecycle shutdown, is a different order.
    payload["results"][1]["payload"]["predecessor_effect_ids"] = []
    payload["results"][-1]["payload"]["predecessor_effect_ids"] = ["effect-1"]
    payload["composition"].update(disposition="eligible", blockers=[])
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "eligible"


def exhausted_replay():
    payload = evaluation_payload()
    effect = ControlEffectRequestModel.model_validate(payload["results"][1]["payload"])
    payload["request"]["context"].update(
        effects_consumed=2,
        depth=2,
        attempt=2,
        prior_effect_claims=[
            {
                "effect_id": effect.effect_id,
                "key": effect.key.model_dump(mode="json"),
                "content_digest": control_digest(effect),
            }
        ],
        rule_firings=[
            {
                "rule_id": effect.key.rule_id,
                "rule_revision": effect.key.rule_revision,
                "firing_epochs": [effect.key.firing_epoch],
            }
        ],
    )
    payload["realizations"] = [
        {
            "effect_id": effect.effect_id,
            "disposition": "applied",
            "receipt": ref("receipt-1", "receipt"),
            "evidence": [ref("realization-evidence")],
        }
    ]
    refresh(payload)
    return payload


def test_unchanged_replay_at_exhausted_budget_is_not_charged_twice():
    record = ParticipantControlEvaluationModel.model_validate(exhausted_replay())
    assert record.request.context.effects_consumed == 2
    assert record.realizations[0].disposition == "applied"


def test_new_claim_at_exhausted_budget_is_rejected_even_in_existing_firing_epoch():
    payload = exhausted_replay()
    payload["results"][1]["payload"]["key"]["slot"] = "new-slot"
    payload["results"][1]["payload"]["effect_id"] = "new-effect"
    payload["realizations"] = []
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)


def test_changed_content_under_prior_key_remains_recordable_conflict():
    payload = exhausted_replay()
    payload["results"][1]["payload"]["target"]["result_item_ref"] = "different-result"
    payload["composition"].update(disposition="conflict", blockers=["effect-conflict"])
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "conflict"


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_effect_identity_retains_all_phase_blockers_under_permutation(reverse):
    payload = add_second_result(evaluation_payload())
    payload["results"][-1]["payload"] = deepcopy(payload["results"][1]["payload"])
    payload["results"][-1]["payload"]["phase"] = "required-predecessor"
    if reverse:
        payload["results"].reverse()
    payload["composition"].update(disposition="conflict", blockers=["effect-conflict", "predecessor:effect-1"])
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.blockers == (
        "effect-conflict",
        "predecessor:effect-1",
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_effect_identity_cannot_hide_missing_dependency_under_permutation(reverse):
    payload = add_second_result(evaluation_payload())
    payload["results"][-1]["payload"] = deepcopy(payload["results"][1]["payload"])
    payload["results"][-1]["payload"]["predecessor_effect_ids"] = ["missing-effect"]
    if reverse:
        payload["results"].reverse()
    payload["composition"].update(disposition="conflict", blockers=["effect-conflict"])
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)


@pytest.mark.parametrize(
    "target",
    [item for item in targets() if item["kind"] in {"permit", "transform", "mask", "route", "delay", "handoff"}],
    ids=lambda target: target["kind"],
)
def test_lifecycle_compatibility_covers_all_live_target_alternatives(target):
    payload = evaluation_payload()
    payload["results"][1]["payload"]["target"] = target
    shutdown = {
        "kind": "shutdown",
        "target_kind": "episode",
        "target_ref": "episode-1",
        "operation": "terminate",
        "lifecycle_authority": ref("lifecycle", "authority"),
        "expected_revision": "rev1",
    }
    add_second_result(payload, result_payload=effect_payload(shutdown))
    payload["results"][1]["payload"]["predecessor_effect_ids"] = ["effect-2"]
    with pytest.raises(ValidationError):
        ParticipantControlEvaluationModel.model_validate(payload)
    payload["composition"].update(disposition="conflict", blockers=["effect-conflict"])
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "conflict"


def test_shutdown_does_not_forbid_a_later_audit_record():
    payload = evaluation_payload()
    payload["results"][1]["payload"]["target"] = next(item for item in targets() if item["kind"] == "audit")
    shutdown = {
        "kind": "shutdown",
        "target_kind": "episode",
        "target_ref": "episode-1",
        "operation": "terminate",
        "lifecycle_authority": ref("lifecycle", "authority"),
        "expected_revision": "rev1",
    }
    add_second_result(payload, result_payload=effect_payload(shutdown))
    payload["results"][1]["payload"]["predecessor_effect_ids"] = ["effect-2"]
    assert ParticipantControlEvaluationModel.model_validate(payload).composition.disposition == "eligible"


def test_prior_claims_cannot_forge_consumption_root_or_firing_history():
    for change in ("consumption", "root", "epoch"):
        payload = exhausted_replay()
        context = payload["request"]["context"]
        if change == "consumption":
            context["effects_consumed"] = 0
        elif change == "root":
            context["prior_effect_claims"][0]["key"]["trigger_root"] = "different-root"
        else:
            context["rule_firings"] = []
        refresh(payload)
        with pytest.raises(ValidationError):
            ParticipantControlEvaluationModel.model_validate(payload)
