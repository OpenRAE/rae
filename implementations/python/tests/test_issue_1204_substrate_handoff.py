"""Compute-substrate authority is recovered from the portable phase plan."""

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.plan_projection import provisioning_plan_model
from raes_contracts.runtime_state import OperationState
from raes_reference_backend import create_reference_backend_target
from raes_reference_backend.provisioner import ReferenceProvisioner
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _provisioning_plan
from raes_runtime.manager import RuntimeManager
from test_issue_158_runtime_result_integrity import _SCENARIO


@pytest.mark.parametrize("owner", ["manager", "control-plane"])
@pytest.mark.parametrize("deliver_binding", [True, False])
def test_portable_substrate_constraints_have_the_same_result_gate(owner, deliver_binding):
    class BindingReference(ReferenceProvisioner):
        def apply(self, request, snapshot):
            result = super().apply(request, snapshot)
            return (
                result
                if deliver_binding
                else replace(result, snapshot=replace(result.snapshot, realization_envelope=None))
            )

    target = create_reference_backend_target()
    backend = BindingReference(
        target.provisioner._driver, realization_envelope=target.provisioner._realization_envelope
    )
    target = replace(target, provisioner=backend)
    manager = RuntimeManager(target)
    execution = manager.plan(parse_sdl(_SCENARIO))
    portable = _provisioning_plan(
        ProvisioningPlanModel.model_validate_json(provisioning_plan_model(execution.provisioning).model_dump_json())
    )
    assert portable.realization_constraints
    if owner == "manager":
        predecessor = manager.snapshot
        result = manager.apply(replace(execution, provisioning=portable))
        assert result.success is deliver_binding
        if not deliver_binding:
            assert result.snapshot == predecessor
    else:
        control_plane = RuntimeControlPlane(target)
        predecessor = control_plane.snapshot
        control_plane.register_planner_produced_plan(execution)
        receipt = control_plane.submit_provisioning(portable)
        status = control_plane.get_operation(receipt.operation_id)
        assert status.state is (OperationState.SUCCEEDED if deliver_binding else OperationState.FAILED)
        if not deliver_binding:
            assert control_plane.snapshot == predecessor
            assert (
                status.diagnostics[0].message
                == "Backend returned no bound substrate selection for 'nodes.web.realization.compute-substrate'."
            )
        control_plane.close()


def test_portable_substrate_admission_rejects_known_unsupported_choice_before_apply():
    from raes_contracts.bounded_domains import ExactDomain
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    target = create_reference_backend_target()
    manager = RuntimeManager(target)
    execution = manager.plan(parse_sdl(_SCENARIO))
    request = replace(
        execution.provisioning,
        realization_constraints=tuple(
            replace(item, posture="exact", value_domain=ExactDomain(value="physical-device"))
            for item in execution.provisioning.realization_constraints
        ),
    )
    calls = []

    def backend(selected, snapshot):
        calls.append(True)
        return target.provisioner.apply(selected, snapshot)

    result = _call_backend_apply(
        backend,
        request,
        manager.snapshot,
        snapshot=manager.snapshot,
        address="runtime.substrate",
        realization=_RealizationApplyContext(plan=request, manifest=target.manifest),
    )
    assert not result.success
    assert calls == []
    assert result.diagnostics[0].code == "realization.compute-substrate-not-admitted"


def test_constraint_only_authority_requires_manifest_before_backend_call():
    from raes_contracts.planning import RealizationAuthorityMode
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    manager = RuntimeManager(create_reference_backend_target())
    execution = manager.plan(parse_sdl(_SCENARIO))
    request = replace(
        execution.provisioning,
        resources={},
        realization_authority=tuple(
            replace(
                item,
                mode=RealizationAuthorityMode.CLOSED,
                bounds=(),
                structure=None,
                constraint_document=None,
                constraint_binding=None,
            )
            for item in execution.provisioning.realization_authority
            if item.address == execution.provisioning.realization_constraints[0].address
        ),
        operations=[
            replace(item, payload={})
            for item in execution.provisioning.operations
            if item.address == execution.provisioning.realization_constraints[0].address
        ],
    )
    calls = []

    def backend(*_):
        calls.append(True)
        return ApplyResult(True, manager.snapshot)

    result = _call_backend_apply(
        backend,
        request,
        manager.snapshot,
        snapshot=manager.snapshot,
        address="runtime.substrate",
        realization=_RealizationApplyContext(plan=request),
    )
    assert not result.success
    assert calls == []
    assert result.snapshot == manager.snapshot
    assert result.diagnostics[0].message == "Resolved realization authority requires the selected backend manifest."


@pytest.mark.parametrize("target", ["absent", "delete", "non-node"])
@pytest.mark.parametrize("portable", [False, True])
def test_substrate_constraints_require_a_live_node_operation(target, portable):
    from raes_contracts.planning import ChangeAction

    manager = RuntimeManager(create_reference_backend_target())
    request = manager.plan(parse_sdl(_SCENARIO)).provisioning
    node_address = request.realization_constraints[0].address
    operations = [
        replace(op, action=ChangeAction.DELETE)
        if target == "delete" and op.address == node_address
        else replace(op, resource_type="network")
        if target == "non-node" and op.address == node_address
        else op
        for op in request.operations
        if target != "absent" or op.address != node_address
    ]
    if portable:
        value = provisioning_plan_model(request).model_dump(mode="json")
        value["realization_authority"] = []
        value["operations"] = [
            {**op.model_dump(mode="json"), "action": selected.action.value, "resource_type": selected.resource_type}
            for selected in operations
            for op in provisioning_plan_model(request).operations
            if op.address == selected.address
        ]
        with pytest.raises(ValueError, match="realization constraints must reference non-delete node operations"):
            ProvisioningPlanModel.model_validate(value)
    else:
        with pytest.raises(ValueError, match="realization constraints must reference non-delete node operations"):
            replace(request, operations=operations, realization_authority=())
