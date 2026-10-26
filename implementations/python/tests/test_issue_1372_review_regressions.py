"""Recovery and optional-read regressions from the portable execution review."""

from threading import Event

import pytest
from mixed_execution_fixtures import portable_plane
from participant_crossing_fixtures import identity
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import backend_operation_control_digest
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from raes_runtime.mixed_runtime_phase import _mixed_runtime_is_quiescent
from raes_runtime.operation_reconciliation_ledger import valid_reconciliation_child
from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration
from test_issue_1362_provider_execution import Evidence, Provider, target
from test_issue_1362_runtime_supervision import supervisor
from test_issue_1372_mixed_execution import execute


def absence_response(provider, plane, control):
    return provider.report(
        provider.request,
        {
            "kind": "reconciliation",
            "control_id": control.control_id,
            "control_digest": backend_operation_control_digest(control),
            "effects": {
                "effect": "absent",
                "cessation_established": True,
                "evidence_refs": [
                    {
                        "contract_id": "runtime-snapshot-v1",
                        "artifact_id": "scoped-absence",
                        "digest": canonical_json_digest(_snapshot_payload(plane.snapshot)),
                    }
                ],
            },
        },
    )


def test_mixed_absence_uses_the_original_installation_and_permits_a_new_handoff():
    plane, state, roles, _, _ = portable_plane(handoff=True)
    bridge = roles["bridge"]
    original = bridge.start_operation

    def refused(request):
        bridge.request = request
        bridge.starts += 1
        return bridge.report(request, {"kind": "acknowledgement", "disposition": "refused", "reason": "unavailable"})

    bridge.start_operation = refused
    bridge.reconcile_operation = lambda control: absence_response(bridge, plane, control)
    try:
        parent = plane.advance_mixed_composition(
            transition_id="transition.sim-to-emu", identity=identity(), idempotency_key="refused-transfer"
        )
        original_status = plane.get_operation(parent.operation_id, identity=identity())
        assert original_status.state is OperationState.INDETERMINATE
        assert plane._operation_evidence is None
        plane.supervise_operation(parent.operation_id, action="reconcile", control_id="absence", identity=identity())
        child = plane.resolve_backend_absence(
            parent.operation_id, "absence", idempotency_key="verified-absence", identity=identity()
        )
        records = plane._store.load_records()
        assert valid_reconciliation_child(records[parent.operation_id], records[child.operation_id])
        assert plane.get_operation(parent.operation_id, identity=identity()) == original_status
        assert records[parent.operation_id].invocation.reserved
        bridge.start_operation = original
        installation = next(iter(plane._mixed_runtime.backend_installations.values()))
        installation.evidence.validate_effects = lambda request, response: (
            response.binding == request.binding and bridge.request == request
        )
        resumed = plane.advance_mixed_composition(
            transition_id="transition.sim-to-emu", identity=identity(), idempotency_key="after-absence"
        )
        assert plane.get_operation(resumed.operation_id, identity=identity()).state is OperationState.SUCCEEDED
        assert bridge.starts == 2
        assert plane.snapshot.mixed_composition_states[state.run_id]["phase_revision"] == 1
    finally:
        plane.close()


@pytest.mark.parametrize("durable", [False, True])
def test_phase_quiescence_recognizes_a_reconciled_nonmixed_parent(durable, tmp_path):
    provider = Provider()
    provider.bad_digest = True
    plane = RuntimeControlPlane(
        target(provider),
        operation_evidence=Evidence(),
        run_scope="run:quiescence",
        store=LocalControlPlaneStore(tmp_path / "scope") if durable else None,
    )
    try:
        parent = plane.submit_provisioning(ProvisioningPlan(), idempotency_key="parent")
        assert not _mixed_runtime_is_quiescent(plane, "quiescence", "mixed_composition_history:quiescence")
        provider.reconcile_operation = lambda control: absence_response(provider, plane, control)
        plane.supervise_operation(parent.operation_id, action="reconcile", control_id="absence", identity=supervisor())
        child = plane.resolve_backend_absence(
            parent.operation_id, "absence", idempotency_key="child", identity=supervisor()
        )
        records = plane._store.load_records()
        assert valid_reconciliation_child(records[parent.operation_id], records[child.operation_id])
        assert _mixed_runtime_is_quiescent(plane, "quiescence", "mixed_composition_history:quiescence")
    finally:
        plane.close()


def test_optional_observation_timeout_preserves_verified_success_and_no_observation():
    # The observation budget bounds every observation-lane call (time readback,
    # effect validation, stage reports and delivery reads). Keep enough headroom
    # for those healthy calls on a loaded runner; only the reader below overruns.
    plane, state, roles, _, _ = portable_plane(
        supervision=OperationSupervisionConfiguration(observation_ms=1000, execution_ms=10000)
    )
    release = Event()
    original = roles["observation"].read_stage

    def blocked(control):
        release.wait(4)
        return original(control)

    roles["observation"].read_stage = blocked
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.SUCCEEDED
        assert not record.invocation.reserved
        assert record.invocation.mixed_post_time_state is not None
        kinds = [event["event_kind"] for event in plane.snapshot.mixed_composition_history[state.run_id]]
        assert "delivery" in kinds
        assert "observation" not in kinds
    finally:
        release.set()
        plane.close()
