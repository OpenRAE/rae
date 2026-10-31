"""Strict invocation facts retained by the incumbent operation ledger."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model

from typing import TYPE_CHECKING, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, model_validator
from raes_contracts.contracts import (
    BackendOperationControlModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    MixedBackendExecutionBindingModel,
    MixedBackendStageReportModel,
    validate_backend_operation_history,
)
from raes_contracts.contracts.backend_operation import OperationDigest, OperationIdentifier
from raes_contracts.contracts.base import ContractModel
from raes_contracts.contracts.mixed_runtime import MixedCompositionRuntimeStateModel
from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_contracts.runtime_state import OperationState

from .operation_temporal import EngineDeliveryBinding
from .operation_transcript_policy import AUTOMATIC_CONTROL_LIMIT, require_transcript_capacity
from .participant_invocation_tool_claims import invocation_tool_child_of
from .record_immutability import immutable_value_error

if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneOperationRecord


class InvocationLedger(ContractModel):
    """These facts survive restart; they never become another dispatch grant."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    schema_version: Literal["raes-invocation-ledger/v1"] = "raes-invocation-ledger/v1"
    request: BackendOperationRequestModel
    delivery: EngineDeliveryBinding | None = None
    native: StrictBool = False
    consumed: StrictBool = False
    reserved: StrictBool = True
    release_commitment: OperationDigest | None = None
    responses: tuple[BackendOperationResponseModel, ...] = Field(default=(), max_length=1024)
    controls: tuple[BackendOperationControlModel, ...] = Field(default=(), max_length=256)
    delivered_controls: tuple[OperationIdentifier, ...] = Field(default=(), max_length=256)
    automatic_controls: tuple[OperationIdentifier, ...] = Field(default=(), max_length=AUTOMATIC_CONTROL_LIMIT)
    mixed_binding: MixedBackendExecutionBindingModel | None = None
    mixed_time_state: TimeRuntimeStateModel | None = None
    mixed_post_time_state: TimeRuntimeStateModel | None = None
    mixed_composition_state: MixedCompositionRuntimeStateModel | None = None
    mixed_reports: tuple[MixedBackendStageReportModel, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def _valid_history(self) -> Self:
        require_transcript_capacity(self)
        validate_backend_operation_history(self.request, self.responses, controls=self.controls)
        self._require_mixed_history()
        if self.delivery is not None:
            self.delivery.reference.require_request(self.request)
            if self.native:
                raise ValueError("native invocation cannot carry an engine delivery")
        self._require_control_history()
        if not self.reserved and self.consumed and self.release_commitment is None:
            raise ValueError("a consumed invocation requires a validated release commitment")
        return self

    def _require_mixed_history(self) -> None:
        if self.mixed_binding is not None:
            from raes_contracts.contracts import backend_operation_request_digest, require_mixed_backend_request

            require_mixed_backend_request(self.mixed_binding, self.request)
            if self.mixed_time_state is None or self.mixed_composition_state is None:
                raise ValueError("mixed invocation requires its committed time and composition cut")
            digest = backend_operation_request_digest(self.request)
            seen = {}
            for report in self.mixed_reports:
                if report.binding != self.request.binding or report.request_digest != digest:
                    raise ValueError("mixed evidence belongs to another invocation")
                if seen.setdefault(report.sequence, report) != report:
                    raise ValueError("duplicate mixed stage changed content")
        elif any(
            (
                self.mixed_reports,
                self.mixed_time_state is not None,
                self.mixed_composition_state is not None,
                self.mixed_post_time_state is not None,
            )
        ):
            raise ValueError("mixed evidence requires its original binding")

    def _require_control_history(self) -> None:
        control_ids = [control.control_id for control in self.controls]
        if len(control_ids) != len(set(control_ids)):
            raise ValueError("control identities must be unique")
        if len(self.delivered_controls) != len(set(self.delivered_controls)):
            raise ValueError("control delivery claims must be unique")
        if not set(self.delivered_controls) <= set(control_ids):
            raise ValueError("control delivery requires retained intent")


def require_record_invocation(record: ControlPlaneOperationRecord) -> None:
    value = record.invocation
    if value is None:
        return
    if not isinstance(value, InvocationLedger):
        raise TypeError("operation invocation requires a strict ledger")
    InvocationLedger.model_validate(value.model_dump(mode="json"))
    binding = value.request.binding
    if binding.operation_id != record.receipt.operation_id or binding.context != record.receipt.context:
        raise immutable_value_error("invocation does not match immutable operation authority")
    if record.status.state is OperationState.ACCEPTED and value.consumed:
        raise ValueError("accepted operation cannot carry a consumed grant")
    if record.status.state is OperationState.RUNNING and not value.consumed:
        raise ValueError("running supervised operation requires a consumed grant")


def require_invocation_transition(prior: InvocationLedger | None, replacement: InvocationLedger | None) -> None:
    if prior is None:
        if replacement is not None:
            raise ValueError("a historical operation cannot acquire fabricated invocation authority")
        return
    if replacement is None:
        raise ValueError("retained invocation authority cannot be dropped")
    _require_immutable_invocation_binding(prior, replacement)
    _require_monotonic_invocation_authority(prior, replacement)
    _require_append_only_invocation_history(prior, replacement)


def _require_immutable_invocation_binding(prior: InvocationLedger, replacement: InvocationLedger) -> None:
    if prior.request != replacement.request or prior.native != replacement.native:
        raise immutable_value_error("invocation binding and command commitment are immutable")
    for name in ("mixed_binding", "mixed_time_state", "mixed_composition_state"):
        if getattr(prior, name) != getattr(replacement, name):
            raise immutable_value_error("mixed invocation cut is immutable")
    if prior.mixed_post_time_state is not None and replacement.mixed_post_time_state != prior.mixed_post_time_state:
        raise immutable_value_error("mixed post-effect readback is immutable")
    _require_immutable_delivery_binding(prior, replacement)


def _require_immutable_delivery_binding(prior: InvocationLedger, replacement: InvocationLedger) -> None:
    if prior.delivery is not None and prior.delivery != replacement.delivery:
        raise immutable_value_error("engine delivery binding is immutable")
    if prior.consumed and prior.delivery != replacement.delivery:
        raise ValueError("consumed invocation cannot acquire another delivery binding")


def _require_monotonic_invocation_authority(prior: InvocationLedger, replacement: InvocationLedger) -> None:
    if prior.consumed and not replacement.consumed:
        raise ValueError("consumed invocation cannot be granted again")
    if not prior.reserved and replacement.reserved:
        raise ValueError("released invocation cannot acquire another effect reservation")
    if prior.release_commitment is not None and prior.release_commitment != replacement.release_commitment:
        raise immutable_value_error("release evidence is immutable")


def _require_append_only_invocation_history(prior: InvocationLedger, replacement: InvocationLedger) -> None:
    for name in ("responses", "controls", "delivered_controls", "automatic_controls", "mixed_reports"):
        before, after = getattr(prior, name), getattr(replacement, name)
        if after[: len(before)] != before:
            raise ValueError("invocation history is append-only")
    new_controls = {control.control_id for control in replacement.controls[len(prior.controls) :]}
    if not set(replacement.automatic_controls[len(prior.automatic_controls) :]) <= new_controls:
        raise ValueError("retained controls cannot be reclassified as automatic")


def supervised_claim_conflicts(new: ControlPlaneOperationRecord, records: object) -> bool:
    from .operation_reconciliation_ledger import valid_reconciliation_child

    records = tuple(records)
    context = new.status.context
    if context.operation_kind.value == "indeterminate-resolution" or control_record_is_supervisory(new):
        return False
    return any(
        record.invocation is not None
        and record.invocation.reserved
        and record.receipt.operation_id != new.receipt.operation_id
        and not any(valid_reconciliation_child(record, child) for child in records)
        and not invocation_tool_child_of(record, new)
        and (record.status.context.target_scope, record.status.context.run_scope)
        == (context.target_scope, context.run_scope)
        for record in records
    )


def control_record_is_supervisory(record: ControlPlaneOperationRecord) -> bool:
    """A cancellation fact can claim no new dispatch grant or external effect."""

    from .participant_control_effect_continuations import cancellation_continuation_claim

    if _cancellation_effect_claim(record) or cancellation_continuation_claim(record):
        return True
    return (
        record.receipt.context.operation_kind.value == "participant-control"
        and record.invocation is None
        and isinstance((record.result_payload or {}).get("participant_control_cancellation"), dict)
    )


def _cancellation_effect_claim(record: ControlPlaneOperationRecord) -> bool:
    """Only a typed cancel claim may enter the supervisory claim lane."""
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model

    payload = record.result_payload or {}
    if not record.idempotency_key.startswith("control-effect:") or payload.get("kind") != "effect-request":
        return False
    effect = ControlEffectRequestV2Model.model_validate(payload)
    return (
        record.invocation is None
        and record.receipt.context.operation_kind.value == "participant-control"
        and record.receipt.context.parent_operation_id is not None
        and record.receipt.context.actor_id == effect.originating_principal_ref
        and record.receipt.context.request_commitment
        == canonical_json_digest({"domain": "participant-control-effect/v1", "effect": payload})
        and record.idempotency_key == "control-effect:" + canonical_json_digest(effect.key.model_dump(mode="json"))
        and _is_execution_cancellation(effect)
    )


def _is_execution_cancellation(effect: ControlEffectRequestV2Model) -> bool:
    return (
        effect.target.kind == "interrupt"
        and effect.target.operation == "cancel"
        and effect.target.target_kind == "execution"
    )


__all__ = (
    "InvocationLedger",
    "require_invocation_transition",
    "require_record_invocation",
    "supervised_claim_conflicts",
)
