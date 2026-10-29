"""An administrative snapshot choice cannot substitute for cessation evidence."""

import pytest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import backend_operation_control_digest
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_recovery import IndeterminateResolutionDisposition
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from test_issue_1362_provider_execution import Evidence, Provider, target
from test_issue_1362_runtime_supervision import supervisor


@pytest.mark.parametrize("durable", [False, True])
def test_only_verified_linked_absence_releases_exclusion_without_rewriting_parent(durable, tmp_path):
    provider = Provider()
    provider.bad_digest = True
    store = LocalControlPlaneStore(tmp_path / "ledger") if durable else None
    plane = RuntimeControlPlane(target(provider), store=store, operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan(), idempotency_key="parent")
        parent_status = plane.get_operation(receipt.operation_id)
        assert parent_status.state is OperationState.INDETERMINATE
        plane.resolve_indeterminate_operation(
            receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="snapshot-choice",
            identity=supervisor(),
        )
        assert not plane.submit_provisioning(ProvisioningPlan()).accepted
        # Unknown effect reports remain insufficient even with operator intent.
        plane.supervise_operation(receipt.operation_id, action="reconcile", control_id="unknown", identity=supervisor())
        rejected_identity = supervisor()
        with pytest.raises(ValueError):
            plane.resolve_backend_absence(
                receipt.operation_id, "unknown", idempotency_key="unknown-proof", identity=rejected_identity
            )

        def reconcile(control):
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
                                "artifact_id": "scoped-witness",
                                "digest": canonical_json_digest(_snapshot_payload(plane._snapshot)),
                            }
                        ],
                    },
                },
            )

        provider.reconcile_operation = reconcile
        plane.supervise_operation(receipt.operation_id, action="reconcile", control_id="absent", identity=supervisor())
        child = plane.resolve_backend_absence(
            receipt.operation_id, "absent", idempotency_key="verified-proof", identity=supervisor()
        )
        assert plane.get_operation(child.operation_id, identity=supervisor()).state is OperationState.SUCCEEDED
        assert plane.get_operation(receipt.operation_id) == parent_status
        provider.bad_digest = False
        assert plane.submit_provisioning(ProvisioningPlan()).accepted
        if durable:
            saved_target = plane._target
            plane.close()
            plane = RuntimeControlPlane(
                saved_target, store=LocalControlPlaneStore(tmp_path / "ledger"), operation_evidence=Evidence()
            )
            assert plane.get_operation(receipt.operation_id) == parent_status
            assert plane._store.load_records()[child.operation_id].reconciliation is not None
            assert plane.submit_provisioning(ProvisioningPlan()).accepted
    finally:
        plane.close()
