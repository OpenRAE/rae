"""One bounded native validation and observation boundary for protocol results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.runtime_state import OperationState

from .backend_calls import _validated_backend_result
from .backend_observation_calls import _apply_observation_result
from .control_plane_store_snapshots import _snapshot_payload

if TYPE_CHECKING:
    from raes_contracts.contracts import OperationArtifactReferenceModel
    from raes_contracts.runtime_state import ApplyResult

    from .backend_calls import _BackendCallContext, _RealizationApplyContext
    from .backend_observation_calls import _ObservationApplyRequest


def finalize_protocol_result(
    result: ApplyResult,
    reference: OperationArtifactReferenceModel,
    state: OperationState,
    *,
    observation_request: _ObservationApplyRequest,
    realization: _RealizationApplyContext,
    call: _BackendCallContext,
) -> tuple[ApplyResult, dict[str, object] | None]:
    if canonical_json_digest(_snapshot_payload(result.snapshot)) != reference.digest:
        raise ValueError("native result artifact commitment mismatch")
    accepted = _validated_backend_result(
        result,
        address=observation_request.address,
        baseline_snapshot=observation_request.snapshot,
        realization=realization,
        call=call,
    )
    if any(d.is_error and d not in result.diagnostics for d in accepted.diagnostics):
        raise ValueError("native operation result failed validation")
    if canonical_json_digest(_snapshot_payload(accepted.snapshot)) != reference.digest:
        raise ValueError("native validation did not preserve the committed result artifact")
    accepted, observation = _apply_observation_result(accepted, observation_request)
    if state is OperationState.SUCCEEDED and not accepted.success:
        raise ValueError("native operation release gates did not establish success")
    return accepted, None if observation is None else observation.result_payload
