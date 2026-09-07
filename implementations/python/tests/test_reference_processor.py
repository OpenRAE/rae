"""RUN-313: repository-owned reference processor.

The reference processor (``raes_processor.reference``) realizes the normative
processing model: it carries SDL authoring input through instantiation,
compilation, and planning to a portable :class:`ExecutionPlan`, and exposes the
published processor manifest. Per ADR-008 the processor's responsibility ends at
the execution plan; backend realization (apply) is the runtime's job. These
tests cover the processor in isolation and then drive its plan through the
reference runtime to prove every contract version the processor manifest
declares is exercised end to end.
"""

from __future__ import annotations

import json
from textwrap import dedent

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_contracts.contracts import (
    ProcessorManifestV2Model,
    WorkflowCancellationRequestModel,
)
from raes_processor.manifest import (
    REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2,
    reference_processor_manifest_payload,
)
from raes_processor.models import ExecutionPlan, RuntimeModel
from raes_processor.reference import (
    ReferenceProcessor,
    ReferenceProcessorResult,
    run_reference_processor,
)
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_api import _receipt_response
from raes_runtime.control_plane_api_models import _operation_status_model, _snapshot_model

WORKFLOW_ADDRESS = "orchestration.workflow.response"

_SCENARIO = dedent(
    """
    name: reference-processor
    nodes:
      vm1:
        type: compute
        resources: {ram: 1 gib, cpu: 1}
        conditions: {health: ops}
        roles: {ops: operator}
    conditions:
      health: {proposition: health-state, command: /bin/true, interval: 15}
    entities:
      blue: {role: blue}
    propositions:
      health-state:
        description: The admitted scenario declares the VM used by this test.
        subjects: [nodes.vm1]
        basis: declared_state
        predicate: {kind: presence, property: node, semantic_ref: "urn:raes:declared-property:node", operator: exists}
    assertions:
      health: {proposition: health-state, role: postcondition}
    objectives:
      validate:
        entity: blue
        success: {assertions: [health]}
    workflows:
      response:
        start: run
        steps:
          run: {type: objective, objective: validate, on_success: finish}
          finish: {type: end}
    """
)

_PARAM_SCENARIO = dedent(
    """
    name: parametrized-reference
    variables:
      cpu_count: {type: integer, default: 1}
    nodes:
      vm1:
        type: compute
        resources:
          ram: 1 gib
          cpu: ${cpu_count}
        conditions: {health: ops}
        roles: {ops: operator}
    conditions:
      health: {proposition: health-state, command: /bin/true, interval: 15}
    entities:
      blue: {role: blue}
    propositions:
      health-state:
        description: The admitted scenario declares the VM used by this test.
        subjects: [nodes.vm1]
        basis: declared_state
        predicate: {kind: presence, property: node, semantic_ref: "urn:raes:declared-property:node", operator: exists}
    assertions:
      health: {proposition: health-state, role: postcondition}
    objectives:
      validate:
        entity: blue
        success: {assertions: [health]}
    workflows:
      response:
        start: run
        steps:
          run: {type: objective, objective: validate, on_success: finish}
          finish: {type: end}
    """
)


def _stub_manifest():
    return create_stub_manifest()


def _plan_fingerprint(execution_plan: ExecutionPlan) -> str:
    """Stable, order-independent fingerprint of every planned operation."""

    operations = []
    for sub_plan in (
        execution_plan.provisioning,
        execution_plan.orchestration,
        execution_plan.evaluation,
    ):
        for op in sub_plan.operations:
            operations.append(
                {
                    "address": op.address,
                    "action": op.action.value,
                    "resource_type": op.resource_type,
                    "payload": op.payload,
                }
            )
    return json.dumps(operations, sort_keys=True, default=str)


class TestReferenceProcessorRealization:
    def test_realizes_valid_execution_plan_across_all_domains(self):
        result = run_reference_processor(_SCENARIO, _stub_manifest())

        assert isinstance(result, ReferenceProcessorResult)
        assert result.is_valid, result.diagnostics
        assert result.diagnostics == ()
        assert result.scenario_name == "reference-processor"
        assert isinstance(result.runtime_model, RuntimeModel)
        assert isinstance(result.execution_plan, ExecutionPlan)
        assert result.execution_plan.provisioning.operations
        assert result.execution_plan.orchestration.operations
        assert result.execution_plan.evaluation.operations

    def test_accepts_text_path_and_parsed_scenario_inputs(self, tmp_path):
        from_text = run_reference_processor(_SCENARIO, _stub_manifest())

        sdl_file = tmp_path / "scenario.yaml"
        sdl_file.write_text(_SCENARIO)
        from_path = run_reference_processor(sdl_file, _stub_manifest())

        from_parsed = run_reference_processor(parse_sdl(_SCENARIO), _stub_manifest())

        assert (
            _plan_fingerprint(from_text.execution_plan)
            == _plan_fingerprint(from_path.execution_plan)
            == _plan_fingerprint(from_parsed.execution_plan)
        )

    def test_invalid_input_type_raises_type_error(self):
        with pytest.raises(TypeError):
            run_reference_processor(123, _stub_manifest())  # type: ignore[arg-type]

    def test_parameters_change_realized_plan(self):
        one = run_reference_processor(_PARAM_SCENARIO, _stub_manifest(), parameters={"cpu_count": 1})
        two = run_reference_processor(_PARAM_SCENARIO, _stub_manifest(), parameters={"cpu_count": 2})

        assert one.is_valid, one.diagnostics
        assert two.is_valid, two.diagnostics
        assert _plan_fingerprint(one.execution_plan) != _plan_fingerprint(two.execution_plan)

    def test_realization_is_deterministic(self):
        first = run_reference_processor(_SCENARIO, _stub_manifest())
        second = run_reference_processor(_SCENARIO, _stub_manifest())

        assert _plan_fingerprint(first.execution_plan) == _plan_fingerprint(second.execution_plan)


class TestReferenceProcessorManifest:
    def test_manifest_payload_delegates_to_canonical_renderer(self):
        assert ReferenceProcessor.manifest_payload() == reference_processor_manifest_payload()

    def test_manifest_payload_validates_against_contract_model(self):
        model = ProcessorManifestV2Model.model_validate(ReferenceProcessor.manifest_payload())

        assert model.identity.name == "raes-reference-processor"
        assert set(model.supported_contract_versions) == set(REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2)


class TestReferenceProcessorEndToEndEvidence:
    def test_every_claimed_contract_is_exercised_end_to_end(self):
        target = create_stub_target()
        result = run_reference_processor(_SCENARIO, target.manifest)
        assert result.is_valid, result.diagnostics

        exercised: dict[str, object] = {}

        # processor-manifest-v2: the published declaration this processor renders.
        exercised["processor-manifest-v2"] = ProcessorManifestV2Model.model_validate(
            ReferenceProcessor.manifest_payload()
        )

        # The three plan contracts are produced directly by the processor.
        assert result.execution_plan.provisioning.operations
        exercised["provisioning-plan-v1"] = result.execution_plan.provisioning
        assert result.execution_plan.orchestration.operations
        exercised["orchestration-plan-v1"] = result.execution_plan.orchestration
        assert result.execution_plan.evaluation.operations
        exercised["evaluation-plan-v1"] = result.execution_plan.evaluation

        # Drive the plan through the reference runtime; the runtime emits the
        # operation receipt/status and snapshot contracts.
        control_plane = RuntimeControlPlane(target)
        control_plane.register_planner_produced_plan(result.execution_plan)
        for sub_plan, submit in (
            (result.execution_plan.provisioning, control_plane.submit_provisioning),
            (result.execution_plan.evaluation, control_plane.submit_evaluation),
            (result.execution_plan.orchestration, control_plane.submit_orchestration),
        ):
            receipt = submit(sub_plan)
            assert receipt.accepted, receipt.diagnostics
            exercised["operation-receipt-v1"] = _receipt_response(receipt)
            status = control_plane.get_operation(receipt.operation_id)
            assert status is not None
            exercised["operation-status-v1"] = _operation_status_model(status)

        exercised["runtime-snapshot-v1"] = _snapshot_model(control_plane.get_snapshot())

        # Workflow cancellation closes the loop on the cancellation request
        # contract: the runtime consumes a schema-valid request and returns a
        # contract-valid receipt.
        cancellation_request = WorkflowCancellationRequestModel(reason="reference cancel")
        cancel_receipt = control_plane.cancel_workflow(
            WORKFLOW_ADDRESS,
            reason=cancellation_request.reason,
        )
        assert cancel_receipt.accepted, cancel_receipt.diagnostics
        exercised["operation-receipt-v1"] = _receipt_response(cancel_receipt)
        exercised["workflow-cancellation-request-v1"] = cancellation_request

        assert set(exercised) == set(REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2), (
            "The reference processor manifest must claim exactly the contracts "
            "the end-to-end reference path exercises (no unbacked claims, no "
            "exercised-but-undeclared contracts)."
        )
