"""IFC profile obligations and the admitted promise at the API-424/v2 gate."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import evaluation_payload, ref
from raes_contracts.contracts.participant_control_applicability import (
    ParticipantControlRequestV2Model,
    ParticipantControlSelectionV2Model,
    control_digest,
)
from raes_contracts.contracts.participant_control_composition_v2 import (
    control_slot_support_failure_v2,
    validate_control_support_v2,
)
from raes_contracts.contracts.participant_control_support_v2 import ControlSupportAssessmentV2Model
from test_issue_1365_applicable_contracts import _request_v2


def promised_request(*, owner=False, floor="exact"):
    request = _request_v2()
    selection = request["selection"]
    promise = deepcopy(evaluation_payload()["support"][0])
    promise["constraints"] = [ref("explicit-boundary-only", "constraint")]
    for obligation in selection["obligations"]:
        obligation.update(required_strength=floor, constraints=promise["constraints"], admitted_support=[promise])
    if owner:
        from raes_contracts.contracts.participant_flow_policy_profiles import (
            load_participant_boundary_flow_policy_profile,
        )

        profile = load_participant_boundary_flow_policy_profile("participant-owner-flow-policy-v1")
        pin = {**ref(profile.profile_id, "profile"), "digest": profile.canonical_digest}
        selection["bindings"] = selection["bindings"][:1]
        selection["bindings"][0]["profiles"] = [pin]
        selection["required_profiles"] = [profile.profile_id]
        selection["slots"] = selection["slots"][:1]
        for obligation, identity in zip(selection["obligations"], ("ifc-owner-a", "ifc-owner-b"), strict=True):
            obligation.update(obligation_id=identity, profile=pin)
        for coverage, identity in zip(
            request["applicability"]["coverage"], ("ifc-owner-a", "ifc-owner-b"), strict=True
        ):
            coverage.update(obligation_id=identity, status="applies", slot_ids=["fact"])
    selected = ParticipantControlSelectionV2Model.model_validate(selection)
    request["applicability"]["selection_digest"] = control_digest(selected)
    return ParticipantControlRequestV2Model.model_validate(request), promise


def assessment(request, promise, *, level="exact", **updates):
    observed = {**promise, "context_digest": control_digest(request.context), "effective_level": level, **updates}
    obligation = request.selection.obligations[0]
    return ControlSupportAssessmentV2Model(
        obligation_id=obligation.obligation_id,
        instance_id="influence",
        required_strength=obligation.required_strength,
        required_constraints=obligation.constraints,
        effective_support=observed,
        relation="exact" if level == "exact" else "bounded-compatible",
        evidence=[ref("trusted-assessment")],
    )


def test_admitted_extra_promise_survives_a_floor_compatible_downgrade():
    request, promise = promised_request(floor="bounded")
    exact = assessment(request, promise)
    validate_control_support_v2(request, (exact,))
    assert control_slot_support_failure_v2(request, "fact", (exact,)) is None
    weaker = assessment(request, promise, level="bounded")
    assert weaker.satisfied  # The original floor still holds.
    assert control_slot_support_failure_v2(request, "fact", (weaker,)) == "weakened"


@pytest.mark.parametrize("change", ["evidence", "constraints", "installation"])
def test_losing_any_admitted_guarantee_blocks_the_required_invocation(change):
    request, promise = promised_request()
    updates = {
        "evidence": {"evidence": [ref("replacement-evidence")]},
        "constraints": {"constraints": []},
        "installation": {"installation": ref("replacement-installation", "installation")},
    }[change]
    observed = assessment(request, promise, **updates)
    assert observed.satisfied
    assert control_slot_support_failure_v2(request, "fact", (observed,)) == "weakened"


def test_owner_profile_requires_both_profile_owned_obligations_and_installed_promises():
    request, _ = promised_request(owner=True)
    assert {item.obligation_id for item in request.selection.obligations} == {"ifc-owner-a", "ifc-owner-b"}
    for change in ("missing-owner", "missing-promise", "wrong-kind"):
        payload = request.selection.model_dump(mode="json")
        if change == "missing-owner":
            payload["obligations"] = payload["obligations"][:1]
        elif change == "missing-promise":
            payload["obligations"][0]["admitted_support"] = []
        else:
            payload["obligations"][0]["required_kind"] = "advisory"
        with pytest.raises(ValueError, match="owner.*obligation|owner.*promise"):
            ParticipantControlSelectionV2Model.model_validate(payload)


def test_owner_profile_cannot_be_selected_through_the_legacy_provider_protocol():
    from raes_contracts.contracts.participant_control_selection import ControlMechanismBindingModel

    request, _ = promised_request(owner=True)
    payload = request.selection.bindings[0].model_dump(mode="json")
    payload.pop("state_scope")
    payload["protocol_revision"] = "participant-control-provider/v1"
    with pytest.raises(ValueError, match="owner.*v2"):
        ControlMechanismBindingModel.model_validate(payload)


def test_owner_fact_has_an_exact_profile_pin_and_requires_v2_reader():
    from raes_contracts.contracts.participant_control_composition import _validate_ifc_result
    from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model
    from raes_contracts.contracts.participant_control_results import ControlMechanismResultModel

    request, _ = promised_request(owner=True)
    payload = deepcopy(evaluation_payload()["results"][0])
    payload["payload"] = dict(
        kind="ifc-fact",
        domain="owner-ifc/rev1",
        profile=request.selection.bindings[0].profiles[0].model_dump(mode="json"),
        relation=ref("owning-relation", "flow-relation"),
        label_ref="owner-label",
        sink_decision_ref="owner-sink",
        sink_disposition="permit",
    )
    payload["invocation_digest"] = "sha256:" + "a" * 64
    result = ControlMechanismResultV2Model.model_validate(payload)
    _validate_ifc_result(result, request.selection.bindings[0], request.context)
    from raes_contracts.contracts.participant_control_composition_v2 import _required_result_cause
    from raes_contracts.contracts.participant_control_invocation import control_predecessors_satisfied_v2

    payload["payload"]["sink_disposition"] = "deny"
    denied = ControlMechanismResultV2Model.model_validate(payload)
    assert not control_predecessors_satisfied_v2((denied,))
    assert _required_result_cause(denied) == "deny"
    legacy = deepcopy(payload)
    legacy.pop("invocation_digest")
    with pytest.raises(ValueError):
        ControlMechanismResultModel.model_validate(legacy)
    payload["payload"]["profile"]["digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="digest"):
        ControlMechanismResultV2Model.model_validate(payload)


def test_empty_new_promise_field_preserves_old_v2_selection_digest():
    request = ParticipantControlRequestV2Model.model_validate(_request_v2())
    payload = request.selection.model_dump(mode="json")
    assert all("admitted_support" not in item for item in payload["obligations"])


def test_an_additionally_selected_teaching_profile_cannot_discharge_owner_coverage():
    from raes_contracts.contracts.participant_control_composition import _validate_ifc_result
    from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model
    from raes_contracts.contracts.participant_owner_flow_admission import validate_owner_flow_result_coverage

    request, _ = promised_request(owner=True)
    payload = request.model_dump(mode="json")
    teaching = evaluation_payload()["request"]["selection"]["bindings"][0]["profiles"][0]
    payload["selection"]["bindings"][0]["profiles"].append(teaching)
    selected = ParticipantControlSelectionV2Model.model_validate(payload["selection"])
    payload["applicability"]["selection_digest"] = control_digest(selected)
    request = ParticipantControlRequestV2Model.model_validate(payload)
    raw = deepcopy(evaluation_payload()["results"][0])
    raw["payload"]["source_refs"] = [item.model_dump(mode="json") for item in request.context.inputs]
    raw["invocation_digest"] = "sha256:" + "a" * 64
    result = ControlMechanismResultV2Model.model_validate(raw)
    _validate_ifc_result(result, selected.bindings[0], request.context)
    with pytest.raises(ValueError, match="owner flow obligation requires its exact profile fact"):
        validate_owner_flow_result_coverage(request, (result,))
