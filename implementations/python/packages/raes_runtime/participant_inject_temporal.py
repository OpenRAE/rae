"""Delivery windows remain distinct from logical control order."""

from raes_contracts.contracts.time_model import TimeCoordinateModel, validate_time_runtime_state
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler.time_model import time_model_contract_model
from raes_processor.models import ParticipantInjectDeliveryRuntime, RuntimeModel
from raes_processor.models.time_model import CompiledTemporalConstraint

_SHARED_TIME_UNAVAILABLE = "inject delivery shared time is unavailable"


def require_delivery_time(
    model: RuntimeModel,
    delivery: ParticipantInjectDeliveryRuntime,
    snapshot: RuntimeSnapshot,
) -> None:
    declaration = time_model_contract_model(model.time_model)
    if declaration is None or snapshot.time_model_state is None:
        raise ConflictError(_SHARED_TIME_UNAVAILABLE)
    try:
        validate_time_runtime_state(declaration, snapshot.time_model_state)
    except ValueError as exc:
        raise ConflictError(_SHARED_TIME_UNAVAILABLE) from exc
    constraints = {item.address: item for item in model.time_model.constraints}
    for reference in delivery.temporal_constraint_addresses:
        constraint = _supported_window(constraints.get(reference))
        clock = snapshot.time_model_state.clocks[constraint.clock_address]
        _require_window_cut(constraint, clock.coordinate)


def _supported_window(constraint: CompiledTemporalConstraint | None) -> CompiledTemporalConstraint:
    if (
        constraint is None
        or constraint.kind != "window"
        or constraint.start_tick is None
        or constraint.end_tick is None
    ):
        raise ConflictError("inject delivery temporal constraint is unsupported")
    return constraint


def _require_window_cut(constraint: CompiledTemporalConstraint, coordinate: TimeCoordinateModel) -> None:
    start = constraint.start_tick, constraint.start_microstep or 0
    end = constraint.end_tick, constraint.end_microstep or 0
    if coordinate.segment != 0 or not start <= (coordinate.tick, coordinate.microstep) <= end:
        raise ConflictError("inject delivery window is expired or unmappable")
