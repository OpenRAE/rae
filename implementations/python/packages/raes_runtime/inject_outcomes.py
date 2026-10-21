"""Bounded typed artifact-outcome admission, without fabricating a native snapshot."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import TYPE_CHECKING

from raes_backend_protocols.inject_execution import InjectExecutionEvidence, ResolvedInjectOutcome
from raes_contracts.contracts import (
    BackendOperationResponseModel,
    InjectOccurrenceOutcomeModel,
    inject_occurrence_outcome_digest,
    validate_inject_occurrence_outcome,
)
from raes_contracts.runtime_state import OperationState

from .control_plane_store import ControlPlaneOperationRecord

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


def settle_inject_outcome(
    plane: RuntimeControlPlane,
    record: ControlPlaneOperationRecord,
    response: BackendOperationResponseModel,
    remaining: Callable[[], int],
    plan: object,
) -> None:
    from .control_plane_supervised_execution import OperationSettlement, commit_settlement

    resolver = plane._operation_evidence
    observation_deadline = monotonic() + plane._supervision.observation_ms / 1000
    execution_remaining = remaining

    def remaining() -> int:
        budget = min(execution_remaining(), int((observation_deadline - monotonic()) * 1000))
        if budget <= 0:
            raise TimeoutError("inject evidence observation budget exhausted")
        return budget

    message = response.message
    if message.effects.residual_state is not None or (
        message.result is not None and message.result.contract_id != "associated-artifact-manifest-v1"
    ):
        # This artifact-only adoption cannot bypass native snapshot admission.
        # A later native-result realization must use finalize_protocol_result.
        raise ValueError("inject native result contract is unsupported by artifact-only resolution")
    if resolver is None or plane._inject_execution is None:
        raise ValueError("inject evidence authority is unavailable")
    with plane._mutation_authority.external_call():
        if (
            plane._execution_adapter.call(
                "effect", resolver.validate_effects, record.invocation.request, response, timeout_ms=remaining()
            )
            is not True
        ):
            raise ValueError("inject world-effect evidence could not be established")
        resolved = plane._execution_adapter.call(
            "effect",
            plane._inject_execution.resolve_outcome,
            record.inject_occurrence,
            record.invocation.request,
            response,
            timeout_ms=remaining(),
        )
    if not isinstance(resolved, ResolvedInjectOutcome):
        raise ValueError("inject resolution requires its typed outcome")
    outcome = resolved.outcome
    evidence = InjectExecutionEvidence.model_validate(resolved.evidence.model_dump(mode="json"))
    outcome = InjectOccurrenceOutcomeModel.model_validate(outcome.model_dump(mode="json"))
    validate_inject_occurrence_outcome(record.inject_occurrence, record.invocation.request, outcome)
    if outcome.response != response:
        raise ValueError("inject readback changed the observed response")
    release = (
        None
        if response.message.proposed_state is OperationState.INDETERMINATE
        else inject_occurrence_outcome_digest(outcome)
    )
    from .inject_capture import capture_inject

    captured = capture_inject(plane, record, plan, remaining)
    commit_settlement(
        plane,
        record,
        OperationSettlement(
            state=response.message.proposed_state,
            release_commitment=release,
            inject_resolution=ResolvedInjectOutcome(outcome, evidence),
            result_payload=None if captured is None else captured.model_dump(mode="json"),
        ),
    )
