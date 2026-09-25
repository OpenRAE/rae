"""Pure cross-message checks shared by transports and contract conformance readers."""

from __future__ import annotations

from collections.abc import Sequence

from ..canonical import canonical_json_digest
from .backend_operation import (
    BackendOperationCapabilitiesModel,
    BackendOperationControlModel,
    BackendOperationRequestModel,
)
from .backend_operation_response import (
    BackendOperationAcknowledgementModel,
    BackendOperationAdmissionModel,
    BackendOperationControlDispositionModel,
    BackendOperationOutcomeModel,
    BackendOperationReconciliationModel,
    BackendOperationResponseModel,
)


def backend_operation_request_digest(request: BackendOperationRequestModel) -> str:
    return canonical_json_digest(request.model_dump(mode="json"))


def backend_operation_control_digest(control: BackendOperationControlModel) -> str:
    return canonical_json_digest(control.model_dump(mode="json"))


def canonical_backend_operation_capabilities_digest(capabilities: BackendOperationCapabilitiesModel) -> str:
    return canonical_json_digest(capabilities.model_dump(mode="json"))


def validate_backend_operation_response(
    request: BackendOperationRequestModel,
    response: BackendOperationResponseModel,
    *,
    control: BackendOperationControlModel | None = None,
) -> None:
    """Reject foreign or stale evidence; this does not authenticate its producer."""

    if response.binding != request.binding:
        raise ValueError("backend operation binding mismatch")
    if response.request_digest != backend_operation_request_digest(request):
        raise ValueError("backend operation request commitment mismatch")
    message = response.message
    if isinstance(message, (BackendOperationControlDispositionModel, BackendOperationReconciliationModel)):
        _validate_control(request, response, control)
    if isinstance(message, (BackendOperationOutcomeModel, BackendOperationReconciliationModel)):
        scope = request.binding.effect_scope
        if scope.kind == "resources" and not set(message.effects.residual_scope) <= set(scope.addresses):
            raise ValueError("residual effects exceed the admitted resource scope")


def _validate_control(request, response, control):
    message = response.message
    if control is None or control.binding != request.binding:
        raise ValueError("control binding missing or mismatched")
    if control.request_digest != response.request_digest:
        raise ValueError("control request commitment mismatch")
    if message.control_id != control.control_id or message.control_digest != backend_operation_control_digest(control):
        raise ValueError("control identity or commitment mismatch")
    if isinstance(message, BackendOperationReconciliationModel) and control.action not in {"observe", "reconcile"}:
        raise ValueError("control action cannot supply reconciliation evidence")


def require_backend_operation_admission(
    request: BackendOperationRequestModel,
    capabilities: BackendOperationCapabilitiesModel,
    response: BackendOperationResponseModel,
) -> None:
    """Check declarations and exact-context willingness, never grant invocation authority."""

    validate_backend_operation_response(request, response)
    message = response.message
    if not isinstance(message, BackendOperationAdmissionModel):
        raise ValueError("backend admission response required")
    if capabilities.backend_id != request.binding.backend_id:
        raise ValueError("backend capability identity mismatch")
    if request.binding.context.operation_kind not in capabilities.supported_operation_kinds:
        raise ValueError("backend operation kind is unsupported")
    if not set(request.required_guarantees) <= set(capabilities.guarantees):
        raise ValueError("required backend operation guarantee is unsupported")
    if message.capability_digest != canonical_backend_operation_capabilities_digest(capabilities):
        raise ValueError("backend capability commitment mismatch")
    if message.disposition != "willing":
        raise ValueError("backend context refused")


def validate_backend_operation_history(
    request: BackendOperationRequestModel,
    responses: Sequence[BackendOperationResponseModel],
    *,
    controls: Sequence[BackendOperationControlModel] = (),
) -> None:
    """Validate a bounded invocation transcript; no scheduling, effects or state mutation."""

    if len(responses) > 1024 or len(controls) > 256:
        raise ValueError("backend operation transcript exceeds its bound")
    by_control = {}
    for control in controls:
        if control.control_id in by_control and by_control[control.control_id] != control:
            raise ValueError("duplicate control identity changed its commitment")
        by_control[control.control_id] = control
    seen = {}
    previous = 0
    terminal = False
    acknowledged = False
    for response in responses:
        message = response.message
        control = by_control.get(message.control_id) if hasattr(message, "control_id") else None
        validate_backend_operation_response(request, response, control=control)
        if response.sequence in seen:
            if seen[response.sequence] != response:
                raise ValueError("duplicate response sequence changed its content")
            continue
        if response.sequence <= previous:
            raise ValueError("response sequence is stale or unordered")
        if terminal and message.kind not in {"control", "reconciliation"}:
            raise ValueError("terminal evidence cannot be rewritten")
        if isinstance(message, BackendOperationAdmissionModel):
            if acknowledged:
                raise ValueError("admission must precede invocation acknowledgement")
            terminal = message.disposition == "refused"
        if isinstance(message, BackendOperationAcknowledgementModel):
            if acknowledged:
                raise ValueError("invocation cannot be acknowledged twice")
            acknowledged = message.disposition == "accepted"
            terminal = not acknowledged
        if message.kind in {"progress", "outcome"} and not acknowledged:
            raise ValueError("execution evidence requires acknowledgement")
        if isinstance(message, BackendOperationOutcomeModel):
            terminal = True
        seen[response.sequence] = response
        previous = response.sequence
