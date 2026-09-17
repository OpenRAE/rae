"""Scope denial and accepted effects retain the existing operation lifecycle."""

from dataclasses import replace

import pytest
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_processor.planner import plan
from raes_runtime.backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.registry import RuntimeTarget
from test_issue_1112_capture_admission import _capture_scenario, _manifest_with_offers, _offer
from test_issue_1242_scope_admission import scoped_plan
from test_issue_1242_scope_runtime import ScopeReportingProvisioner


@pytest.mark.parametrize("permission", ["closed", "open"])
def test_durable_retry_never_replays_a_denied_or_completed_augmentation(tmp_path, permission):
    execution = scoped_plan({"default": permission})
    backend = ScopeReportingProvisioner(execution.manifest, addition=True)
    target = RuntimeTarget(name="scoped", manifest=execution.manifest, provisioner=backend)
    archive = RunMaterializationArchive(tmp_path / "archive")
    control = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "state"), materialization_archive=archive
    )
    try:
        control.register_planner_produced_plan(execution)
        receipt = control.submit_provisioning(execution.provisioning, idempotency_key="scope-once")
        assert receipt.accepted, receipt.diagnostics
        operation = control.get_operation(receipt.operation_id)
        assert operation.state is (OperationState.FAILED if permission == "closed" else OperationState.SUCCEEDED)
        assert backend.calls == (0 if permission == "closed" else 1)
        assert bool(control.snapshot.materialization_attestations) is (permission == "open")
        if permission == "closed":
            assert any(item.code == "augmentation.scope-closed" for item in operation.diagnostics)
    finally:
        control.close()
    recovered = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "state"), materialization_archive=archive
    )
    try:
        assert recovered.submit_provisioning(execution.provisioning, idempotency_key="scope-once") == receipt
        assert backend.calls == (0 if permission == "closed" else 1)
    finally:
        recovered.close()


@pytest.mark.parametrize("shared", [False, True])
def test_closed_scope_names_the_specific_required_evidence_not_just_a_category(tmp_path, shared):
    requirements = {
        name: value.model_dump(mode="json") for name, value in _capture_scenario().evidence_requirements.items()
    }
    original = scoped_plan({"default": "closed"}, content={"evidence_requirements": requirements})
    manifest = replace(
        original.manifest,
        supported_contract_versions=original.manifest.supported_contract_versions
        | {"participant-behavior-history-event-stream-v1"},
        capabilities=replace(original.manifest.capabilities, observation=_manifest_with_offers(_offer()).observation),
    )
    execution = plan(original.model, manifest, scope=PlanScope(run_id="run-1"))
    assert execution.is_valid, execution.diagnostics

    class EvidenceCollector(ScopeReportingProvisioner):
        def prepare_augmentation(self, request, previous):
            report = super().prepare_augmentation(request, previous)
            return report.model_copy(
                update={
                    "effects": (
                        report.effects[0].model_copy(
                            update={
                                "requirement_refs": (("backend-operational",) if shared else ())
                                + ("/evidence_requirements/attacker-action-log",)
                            }
                        ),
                    )
                }
            )

    backend = EvidenceCollector(manifest, addition=True)
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.capture",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path)),
    )
    assert not result.success
    assert backend.calls == 0
    assert any(
        item.code == "augmentation.scope-closed"
        and "attacker-action-log" in item.message
        and "/nodes/host/services/0" in item.message
        for item in result.diagnostics
    )
