"""Descriptions retain their non-executable purpose across portable boundaries."""

from dataclasses import replace

import pytest
from raes_contracts.plan_projection import (
    evaluation_plan_model,
    orchestration_plan_model,
    provisioning_plan_model,
    runtime_plan_digest,
)
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply
from raes_runtime.control_plane_api_models import _evaluation_plan, _orchestration_plan, _provisioning_plan


@pytest.mark.parametrize(
    "plan_type,encode,decode",
    [
        (ProvisioningPlan, provisioning_plan_model, _provisioning_plan),
        (EvaluationPlan, evaluation_plan_model, _evaluation_plan),
        (OrchestrationPlan, orchestration_plan_model, _orchestration_plan),
    ],
)
def test_inspection_purpose_roundtrips_and_is_authenticated(plan_type, encode, decode):
    request = plan_type(purpose="inspection")
    restored = decode(type(encode(request)).model_validate_json(encode(request).model_dump_json()))
    assert restored.purpose == "inspection"
    assert runtime_plan_digest(restored) == runtime_plan_digest(request)
    assert runtime_plan_digest(request) != runtime_plan_digest(replace(request, purpose="execution"))


@pytest.mark.parametrize("plan_type", [ProvisioningPlan, EvaluationPlan, OrchestrationPlan])
def test_inspection_plan_is_refused_before_any_backend_effect(plan_type):
    calls = []
    previous = RuntimeSnapshot()

    def apply(request, snapshot):
        calls.append(request)
        return ApplyResult(True, snapshot)

    result = _call_backend_apply(
        apply,
        plan_type(purpose="inspection"),
        previous,
        address="runtime.inspection",
        snapshot=previous,
    )
    assert not result.success
    assert result.snapshot == previous
    assert not calls


@pytest.mark.parametrize(
    "plan_type,encode,decode",
    [
        (EvaluationPlan, evaluation_plan_model, _evaluation_plan),
        (OrchestrationPlan, orchestration_plan_model, _orchestration_plan),
    ],
)
def test_materializing_phase_operation_identity_is_bound_and_roundtrips(plan_type, encode, decode):
    received = []
    previous = RuntimeSnapshot()

    def apply(request, snapshot):
        received.append(getattr(request, "operation_id", None))
        return ApplyResult(False, snapshot)

    _call_backend_apply(apply, plan_type(), previous, address="runtime.phase", snapshot=previous)
    assert len(received) == 1
    assert isinstance(received[0], str)
    assert received[0]
    request = plan_type(operation_id=received[0])
    assert decode(encode(request)).operation_id == received[0]
    assert runtime_plan_digest(request) != runtime_plan_digest(plan_type())
