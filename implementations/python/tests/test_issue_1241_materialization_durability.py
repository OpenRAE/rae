"""Archive publication follows the existing durable operation/idempotency owner."""

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.registry import RuntimeTarget
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner


@pytest.mark.parametrize("configured", [False, True])
def test_control_plane_configuration_preserves_keywords_and_defaults(tmp_path, configured):
    target = create_stub_target()
    snapshot = RuntimeSnapshot()
    archive = RunMaterializationArchive(tmp_path)
    options = (
        {
            "initial_snapshot": snapshot,
            "store": None,
            "behavior_specifications": {},
            "crossing_policy_resolver": None,
            "information_state_context_resolver": None,
            "enforce_final_sink_flow_control": False,
            "materialization_archive": archive,
        }
        if configured
        else {}
    )
    control = RuntimeControlPlane(target, **options)
    try:
        assert control.snapshot == snapshot
        assert control._materialization_archive is (archive if configured else None)
        assert control._enforce_final_sink_flow_control is not configured
    finally:
        control.close()


def test_unknown_control_plane_options_fail_before_initialization(monkeypatch):
    def unexpected_initialization(self):
        pytest.fail("unknown options must fail before lifecycle initialization")

    monkeypatch.setattr(RuntimeControlPlane, "_initialize_runtime_lifecycle", unexpected_initialization)
    target = create_stub_target()
    with pytest.raises(TypeError, match="unexpected keyword"):
        RuntimeControlPlane(target, unknown_option=True)


@pytest.mark.parametrize("archive_fails", [False, True])
def test_durable_restart_retains_references_or_cleanup_without_reapplying(tmp_path, archive_fails):
    class FailingArchive:
        def publish(self, content):
            raise OSError("archive unavailable")

    execution, _model = attesting_plan()
    backend = ReportingProvisioner(execution.manifest)
    target = RuntimeTarget(name="attesting", manifest=execution.manifest, provisioner=backend)
    archive = FailingArchive() if archive_fails else RunMaterializationArchive(tmp_path / "archive")
    control = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "state"), materialization_archive=archive
    )
    try:
        control.register_planner_produced_plan(execution)
        receipt = control.submit_provisioning(execution.provisioning, idempotency_key="materialization-once")
        assert receipt.accepted, receipt.diagnostics
        expected = OperationState.FAILED if archive_fails else OperationState.SUCCEEDED
        assert control.get_operation(receipt.operation_id).state == expected
        assert "provision.node.host" in control.snapshot.entries
        assert bool(control.snapshot.materialization_attestations) is not archive_fails
        assert backend.calls == 1
    finally:
        control.close()

    recovered = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "state"), materialization_archive=archive
    )
    try:
        again = recovered.submit_provisioning(execution.provisioning, idempotency_key="materialization-once")
        assert again == receipt
        assert backend.calls == 1
        assert "provision.node.host" in recovered.snapshot.entries
        assert bool(recovered.snapshot.materialization_attestations) is not archive_fails
    finally:
        recovered.close()


def test_empty_plan_cannot_introduce_untrusted_source_lineage(tmp_path):
    from raes_contracts.planning import ProvisioningPlan

    execution, _model = attesting_plan()
    backend = ReportingProvisioner(execution.manifest)
    control = RuntimeControlPlane(
        RuntimeTarget(name="attesting", manifest=execution.manifest, provisioner=backend),
        materialization_archive=RunMaterializationArchive(tmp_path),
    )
    try:
        forged = ProvisioningPlan(materialization_source=execution.provisioning.materialization_source)
        receipt = control.submit_provisioning(forged)
        assert not receipt.accepted
        assert backend.calls == 0
    finally:
        control.close()
