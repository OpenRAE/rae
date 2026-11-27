"""Obligation-specific evidence for fail-closed runtime cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model, control_digest
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model

from .modular_control_types import ModularControlCase

if TYPE_CHECKING:
    from .modular_control_execution import _Measurement


def _parent_evaluations(measured: _Measurement) -> tuple[ParticipantControlEvaluationV2Model, ...]:
    parents = {
        item.commit.receipt.ref: item
        for item in measured.evaluations
        if item.commit.receipt is not None and item.commit.receipt.ref in measured.parent_operation_ids
    }
    return tuple(parents.values())


def _strict_denial(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(
        item.composition.disposition in {"deny", "withhold"}
        and any(
            result.payload is not None
            and result.payload.kind == "decision"
            and result.payload.disposition in {"deny", "withhold"}
            for result in item.results
        )
        for item in _parent_evaluations(measured)
    )


def _authority(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(
        not event.allowed
        and event.action == "dispatch_participant_control_effects"
        and event.target == case.participant_address
        for event in measured.audit
    )


def _stale_cut(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(
        event.reason == "control-stale-cut" and event.operation_id in measured.parent_operation_ids
        for event in measured.audit
    )


def _mandatory_coverage(case: ModularControlCase, measured: _Measurement) -> bool:
    for identity, resolution in measured.resolutions:
        if identity not in measured.parent_operation_ids:
            continue
        if resolution is None:
            return any(
                event.operation_id == identity and event.reason == "control-context-invalid" for event in measured.audit
            )
        if _coverage_missing(resolution.request):
            return True
    return False


def _coverage_missing(request: ParticipantControlRequestV2Model) -> bool:
    required = {item.obligation_id for item in request.selection.obligations}
    coverage = {item.obligation_id for item in request.applicability.coverage}
    return bool(required - coverage) or any(item.status == "unresolved" for item in request.applicability.coverage)


def _conflict(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(
        item.composition.disposition == "conflict"
        or {"permit", "deny"}
        <= {
            result.payload.disposition
            for result in item.results
            if result.payload is not None and result.payload.kind == "decision"
        }
        for item in _parent_evaluations(measured)
    )


def _required_integrity_failure(
    result: ControlMechanismResultV2Model,
    evaluation: ParticipantControlEvaluationV2Model,
    measured: _Measurement,
) -> bool:
    return (
        result.status == "failed"
        and result.slot_id in evaluation.request.applicability.required_slot_ids
        and (control_digest(evaluation.request.context), result.slot_id) in measured.integrity_slots
    )


def _integrity(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(
        item.composition.disposition == "failed"
        and any(_required_integrity_failure(result, item, measured) for result in item.results)
        for item in _parent_evaluations(measured)
    )


_CONDITIONS = {
    "strict-denial": _strict_denial,
    "authority": _authority,
    "stale-cut": _stale_cut,
    "mandatory-coverage": _mandatory_coverage,
    "conflict": _conflict,
    "integrity": _integrity,
}


def negative_condition(case: ModularControlCase, measured: _Measurement) -> bool:
    condition = _CONDITIONS.get(case.obligation)
    return condition is not None and condition(case, measured)
