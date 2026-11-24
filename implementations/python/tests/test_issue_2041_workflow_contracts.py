"""Published step carriers and provider transport retain one dispatch boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from raes_conformance.conformance.validators import contract_validation_strength, validate_contract_payload
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendOperationRequestModel
from raes_contracts.contracts.workflow_dispatch import WorkflowStepResponse
from raes_contracts.runtime_state import OperationState
from raes_runtime.manager import RuntimeManager
from test_issue_1360_backend_operations import request_payload
from test_issue_1362_provider_execution import Provider, target
from test_issue_2041_runtime_step_dispatch import scenario


@pytest.mark.parametrize("contract", ["workflow-step-dispatch-v1", "workflow-step-response-v1"])
def test_contract_fixture_reader_checks_shape_without_claiming_dispatch_permission(contract):
    root = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "control-plane" / contract
    valid = json.loads((root / "valid" / "objective.json").read_text())
    invalid = json.loads((root / "invalid" / "backend-successor.json").read_text())
    assert validate_contract_payload(contract, valid) == ()
    assert contract_validation_strength(contract) == "structural"
    assert validate_contract_payload(contract, invalid)


def test_legacy_backend_operation_request_keeps_its_digest_input():
    payload = request_payload()
    request = BackendOperationRequestModel.model_validate(payload)
    assert "workflow_step" not in request.model_dump(mode="json")


def test_operation_provider_receives_only_the_current_step():
    class StepProvider(Provider):
        def __init__(self):
            super().__init__()
            self.commands = []

        def operation_capabilities(self):
            original = super().operation_capabilities()
            return type(original).model_validate(
                {**original.model_dump(), "supported_operation_kinds": ["orchestration"]}
            )

        def start_operation(self, request):
            assert request.workflow_step is not None
            assert request.command.contract_id == "workflow-step-dispatch-v1"
            self.commands.append(request.workflow_step)
            return super().start_operation(request)

        def observe_operation(self, control):
            dispatch = self.request.workflow_step
            response = WorkflowStepResponse(dispatch_id=dispatch.dispatch_id, dispatch_digest=dispatch.digest)
            reference = {
                "contract_id": "workflow-step-response-v1",
                "artifact_id": "step-result",
                "digest": canonical_json_digest(response.model_dump(mode="json")),
            }
            return self.report(
                self.request,
                {
                    "kind": "outcome",
                    "proposed_state": "succeeded",
                    "effects": {"effect": "absent", "cessation_established": True, "evidence_refs": [reference]},
                    "satisfaction": "satisfied",
                    "release_gates_satisfied": True,
                    "cancellation_established": False,
                    "result": reference,
                },
            )

    class StepEvidence:
        def validate_effects(self, request, response):
            return response.binding == request.binding and response.message.effects.cessation_established

        def resolve_result(self, request, response, predecessor):
            dispatch = request.workflow_step
            return WorkflowStepResponse(dispatch_id=dispatch.dispatch_id, dispatch_digest=dispatch.digest)

    provider = StepProvider()
    with RuntimeManager(target(provider), operation_evidence=StepEvidence()) as manager:
        execution = manager.plan(scenario("      run: {type: end}\n"))
        manager.register_planner_produced_plan(execution)
        receipt = manager.submit_orchestration(execution.orchestration, idempotency_key="provider-step")
        assert receipt.accepted
        assert manager.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert len(provider.commands) == 1
        assert provider.commands[0].step_name == "run"
        assert not hasattr(provider.commands[0], "control_steps")


def test_failed_governed_attempt_can_stop_before_selecting_an_action():
    from raes_backend_stubs.stubs import StubOrchestrator
    from raes_contracts.contracts.workflow_dispatch import WorkflowStepDispatch

    payload = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "contracts/fixtures/control-plane/workflow-step-dispatch-v1/valid/objective.json"
        ).read_text()
    )
    dispatch = WorkflowStepDispatch.model_validate(
        {
            **payload,
            "execution_mode": "scaffolded",
            "allowed_action_families": ["permitted"],
            "tool_affordance_refs": ["affordance:permitted"],
        }
    )
    response = WorkflowStepResponse.model_validate(StubOrchestrator().dispatch_step(dispatch))
    response.require_dispatch(dispatch)
    assert response.outcome == "failed"
    for field in ("selected_action_family", "selected_affordance_ref"):
        provenance = response.attempt_provenance.model_copy(update={field: "forbidden"})
        invalid = response.model_copy(update={"attempt_provenance": provenance})
        with pytest.raises(ValueError, match="exceeds"):
            invalid.require_dispatch(dispatch)
