"""The native proposal commitment is distinct from runtime-owned accepted state."""

from dataclasses import replace

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import OperationArtifactReferenceModel
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_runtime.backend_calls import _BackendCallContext, _RealizationApplyContext
from raes_runtime.backend_observation_calls import _ObservationApplyRequest
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from raes_runtime.operation_result_finalization import finalize_protocol_result
from runtime_descendant_fixtures import descendant_runtime


def test_supervised_inventory_keeps_the_native_proposal_commitment(tmp_path):
    manager, backend, plan, _target, archive = descendant_runtime(tmp_path)
    previous = RuntimeSnapshot()
    request = replace(plan.provisioning, operation_id="operation-1", inventory_attempt_id="attempt-1")
    proposal = backend.apply(request, previous)
    digest = canonical_json_digest(_snapshot_payload(proposal.snapshot))
    reference = OperationArtifactReferenceModel(contract_id="runtime-snapshot-v1", artifact_id="native", digest=digest)
    accepted, _ = finalize_protocol_result(
        proposal,
        reference,
        OperationState.SUCCEEDED,
        observation_request=_ObservationApplyRequest(
            address="runtime.provisioning",
            snapshot=previous,
            plan=request,
            manifest=plan.manifest,
            materialization_archive=archive,
            runtime=None,
        ),
        realization=_RealizationApplyContext(plan=request, operation_plan=request, manifest=plan.manifest),
        call=_BackendCallContext(materialization_archive=archive),
    )
    assert accepted.success, accepted.diagnostics
    assert "provision.node.leaf" in accepted.snapshot.entries
    assert canonical_json_digest(_snapshot_payload(proposal.snapshot)) == digest
    assert canonical_json_digest(_snapshot_payload(accepted.snapshot)) != digest
    manager.close()
