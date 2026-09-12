"""Rejected backend candidates never become recoverable control-plane state."""

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.runtime_state import OperationState
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_reference_backend import create_reference_backend_target
from raes_reference_backend.provisioner import ReferenceProvisioner
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, _snapshot_payload
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from test_issue_158_runtime_result_integrity import _SCENARIO


class _PerturbedReference(ReferenceProvisioner):
    reject_next = False

    def apply(self, request, snapshot):
        result = super().apply(request, snapshot)
        if self.reject_next and result.success:
            entries = dict(result.snapshot.entries)
            address = "provision.node.web"
            entries[address] = replace(entries[address], resource_type="network")
            result = replace(
                result, snapshot=result.snapshot.with_entries(entries), details={"private-candidate": "not-accepted"}
            )
        return result


@pytest.mark.parametrize("durable", [False, True])
def test_rejected_success_preserves_the_immediate_predecessor_across_reload(tmp_path, durable):
    target = create_reference_backend_target()
    backend = _PerturbedReference(
        target.provisioner._driver, realization_envelope=target.provisioner._realization_envelope
    )
    target = replace(target, provisioner=backend)
    store = LocalControlPlaneStore(tmp_path / "state") if durable else InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    scenario = parse_sdl(_SCENARIO)
    first = plan(compile_runtime_model(scenario), target.manifest, control_plane.snapshot)
    control_plane.register_planner_produced_plan(first)
    receipt = control_plane.submit_provisioning(first.provisioning)
    assert control_plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    predecessor = _snapshot_payload(control_plane.snapshot)
    revision = store.load_snapshot_state().revision

    # A real authorized UPDATE follows an already accepted provisioning phase.
    updated = parse_sdl(_SCENARIO.replace("cpu: 1", "cpu: 2"))
    second = plan(compile_runtime_model(updated), target.manifest, control_plane.snapshot)
    control_plane.register_planner_produced_plan(second)
    backend.reject_next = True
    receipt = control_plane.submit_provisioning(second.provisioning)
    status = control_plane.get_operation(receipt.operation_id)
    assert status.state is OperationState.FAILED
    assert status.changed_addresses == []
    assert status.diagnostics[0].code == "runtime.backend-contract-invalid"
    assert status.diagnostics[0].message == "Backend changed a plan-owned resource type."
    assert _snapshot_payload(control_plane.snapshot) == predecessor
    assert store.load_snapshot_state().revision > revision
    control_plane.close()

    recovered_store = LocalControlPlaneStore(tmp_path / "state") if durable else store
    recovered = RuntimeControlPlane(target, store=recovered_store)
    assert _snapshot_payload(recovered.snapshot) == predecessor
    assert recovered.get_operation(receipt.operation_id).state is OperationState.FAILED
    assert "private-candidate" not in repr(recovered_store.load_records())
    assert "not-accepted" not in repr(recovered.get_snapshot())
    recovered.close()


@pytest.mark.parametrize("severity", [Severity.ERROR, Severity.WARNING])
def test_control_plane_respects_backend_validation_before_apply(severity):
    class ValidatingReference(ReferenceProvisioner):
        applies = 0

        def validate(self, request):
            return [Diagnostic("test.support", "runtime", "runtime.validate", "Backend support decision.", severity)]

        def apply(self, request, snapshot):
            self.applies += 1
            return super().apply(request, snapshot)

    target = create_reference_backend_target()
    backend = ValidatingReference(
        target.provisioner._driver, realization_envelope=target.provisioner._realization_envelope
    )
    target = replace(target, provisioner=backend)
    control_plane = RuntimeControlPlane(target)
    predecessor = _snapshot_payload(control_plane.snapshot)
    execution = plan(compile_runtime_model(parse_sdl(_SCENARIO)), target.manifest)
    control_plane.register_planner_produced_plan(execution)
    receipt = control_plane.submit_provisioning(execution.provisioning)
    status = control_plane.get_operation(receipt.operation_id)
    assert backend.applies == int(severity is not Severity.ERROR)
    assert receipt.accepted
    assert receipt.diagnostics == []
    assert status.state is (OperationState.FAILED if severity is Severity.ERROR else OperationState.SUCCEEDED)
    assert status.diagnostics[0].code == "test.support"
    if severity is Severity.ERROR:
        assert _snapshot_payload(control_plane.snapshot) == predecessor
    control_plane.close()
