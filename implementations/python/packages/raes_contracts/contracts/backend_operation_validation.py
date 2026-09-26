"""Pure cross-message checks shared by transports and contract conformance readers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

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
    BackendOperationMessage,
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


def _validate_control(
    request: BackendOperationRequestModel,
    response: BackendOperationResponseModel,
    control: BackendOperationControlModel | None,
) -> None:
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
    by_control = _index_controls(controls)
    history = _InvocationHistory()
    for response in responses:
        message = response.message
        control = by_control.get(message.control_id) if hasattr(message, "control_id") else None
        validate_backend_operation_response(request, response, control=control)
        history.accept(response)


def _index_controls(controls: Sequence[BackendOperationControlModel]) -> dict[str, BackendOperationControlModel]:
    by_control: dict[str, BackendOperationControlModel] = {}
    for control in controls:
        if control.control_id in by_control and by_control[control.control_id] != control:
            raise ValueError("duplicate control identity changed its commitment")
        by_control[control.control_id] = control
    return by_control


@dataclass
class _InvocationHistory:
    """Transient transcript validation state; never persisted runtime authority."""

    seen: dict[int, BackendOperationResponseModel] = field(default_factory=dict)
    previous: int = 0
    terminal: bool = False
    acknowledged: bool = False

    def accept(self, response: BackendOperationResponseModel) -> None:
        if response.sequence in self.seen:
            if self.seen[response.sequence] != response:
                raise ValueError("duplicate response sequence changed its content")
            return
        if response.sequence <= self.previous:
            raise ValueError("response sequence is stale or unordered")
        self._advance(response.message)
        self.seen[response.sequence] = response
        self.previous = response.sequence

    def _advance(self, message: BackendOperationMessage) -> None:
        if self.terminal and message.kind not in {"control", "reconciliation"}:
            raise ValueError("terminal evidence cannot be rewritten")
        if isinstance(message, BackendOperationAdmissionModel):
            if self.acknowledged:
                raise ValueError("admission must precede invocation acknowledgement")
            self.terminal = message.disposition == "refused"
        if isinstance(message, BackendOperationAcknowledgementModel):
            if self.acknowledged:
                raise ValueError("invocation cannot be acknowledged twice")
            self.acknowledged = message.disposition == "accepted"
            self.terminal = not self.acknowledged
        self._execution_evidence(message)

    def _execution_evidence(self, message: BackendOperationMessage) -> None:
        if message.kind in {"progress", "outcome"} and not self.acknowledged:
            raise ValueError("execution evidence requires acknowledgement")
        if isinstance(message, BackendOperationOutcomeModel):
            self.terminal = True
