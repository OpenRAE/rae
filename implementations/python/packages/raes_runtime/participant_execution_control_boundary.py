"""Validation boundary for backend-owned participant execution control."""

from __future__ import annotations

from collections.abc import Callable

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_calls import _BackendCallContext, _call_backend_apply
from .participant_effect_authority import participant_effect_authority


def _failure(
    snapshot: RuntimeSnapshot,
    request: ParticipantExecutionControlRequestModel,
    code: str,
    message: str,
) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[
            Diagnostic(
                code=code,
                domain="participant",
                address=request.execution_scope_ref,
                message=message,
            )
        ],
    )


def _precondition(
    request: ParticipantExecutionControlRequestModel,
    snapshot: RuntimeSnapshot,
) -> ApplyResult | None:
    payload = snapshot.participant_execution_services.get(request.execution_scope_ref)
    if payload is None:
        return _failure(
            snapshot,
            request,
            "runtime.participant-execution-not-found",
            "Participant execution scope is not configured.",
        )
    state = ParticipantExecutionServiceStateModel.model_validate(payload)
    if state.generation != request.expected_generation:
        return _failure(
            snapshot,
            request,
            "runtime.participant-execution-stale-generation",
            "Participant execution request generation does not match current state.",
        )
    return None


_EXPECTED_OBSERVATIONS = {
    "start": ("running", "ready", True),
    "resume": ("running", "ready", True),
    "reset": ("running", "ready", True),
    "pause": ("paused", "not_ready", False),
    "drain": ("quiescent", "not_ready", False),
    "teardown": ("terminated", "not_ready", False),
}


def _expected_observation(request: ParticipantExecutionControlRequestModel) -> tuple[str, str, bool]:
    return _EXPECTED_OBSERVATIONS[request.action]


def _common_readback_matches(
    request: ParticipantExecutionControlRequestModel,
    before: ParticipantExecutionServiceStateModel,
    observed: ParticipantExecutionServiceStateModel,
) -> bool:
    return _observed_state_matches(request, observed) and _has_new_transition_evidence(before, observed)


def _observed_state_matches(
    request: ParticipantExecutionControlRequestModel,
    observed: ParticipantExecutionServiceStateModel,
) -> bool:
    lifecycle, readiness, accepting = _expected_observation(request)
    expected_generation = request.expected_generation + (request.action == "reset")
    return (
        observed.observed_lifecycle == lifecycle
        and observed.desired_lifecycle == lifecycle
        and observed.readiness == readiness
        and observed.accepting_new_work is accepting
        and observed.generation == expected_generation
        and observed.observed_generation == expected_generation
    )


def _has_new_transition_evidence(
    before: ParticipantExecutionServiceStateModel,
    observed: ParticipantExecutionServiceStateModel,
) -> bool:
    return (
        bool(observed.last_transition_ref)
        and observed.last_transition_ref != before.last_transition_ref
        and bool(set(observed.evidence_refs).difference(before.evidence_refs))
    )


def _action_readback_matches(
    request: ParticipantExecutionControlRequestModel,
    observed: ParticipantExecutionServiceStateModel,
) -> bool:
    if request.action == "drain":
        return not (observed.reserved or observed.in_flight or observed.draining or not observed.quiescent)
    return request.action != "teardown" or observed.resources_released


def _successful_observed_result(
    request: ParticipantExecutionControlRequestModel,
    predecessor: RuntimeSnapshot,
    result: ApplyResult,
) -> ApplyResult:
    payload = result.snapshot.participant_execution_services.get(request.execution_scope_ref)
    if payload is None:
        return _failure(
            predecessor,
            request,
            "runtime.participant-execution-readback-missing",
            "Backend control succeeded without publishing execution-service readback.",
        )
    before = ParticipantExecutionServiceStateModel.model_validate(
        predecessor.participant_execution_services[request.execution_scope_ref]
    )
    observed = ParticipantExecutionServiceStateModel.model_validate(payload)
    if _common_readback_matches(request, before, observed) and _action_readback_matches(request, observed):
        return result
    return _failure(
        predecessor,
        request,
        "runtime.participant-execution-readback-invalid",
        "Backend control result did not prove the requested observed lifecycle transition.",
    )


def _validate_observed_result(
    request: ParticipantExecutionControlRequestModel,
    predecessor: RuntimeSnapshot,
    result: ApplyResult,
) -> ApplyResult:
    return result if not result.success else _successful_observed_result(request, predecessor, result)


def backend_execution_control_method(
    backend_method: Callable[..., object],
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> Callable[[ParticipantExecutionControlRequestModel, RuntimeSnapshot], ApplyResult]:
    """Wrap native control with generation preflight and observed-result checks."""

    def apply(
        request: ParticipantExecutionControlRequestModel,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        failure = _precondition(request, snapshot)
        if failure is not None:
            return failure
        result = _call_backend_apply(
            backend_method,
            request,
            snapshot,
            address=f"runtime.participant-execution.{request.execution_scope_ref}.{request.action}",
            snapshot=snapshot,
            realization=participant_effect_authority(request, snapshot),
            call=_BackendCallContext(
                information_state_context_resolver=information_state_context_resolver,
            ),
        )
        return _validate_observed_result(request, snapshot, result)

    return apply


__all__ = ["backend_execution_control_method"]
