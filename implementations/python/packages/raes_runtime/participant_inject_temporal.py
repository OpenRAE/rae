"""Delivery windows remain distinct from logical control order."""

from raes_contracts.contracts.time_model import validate_time_runtime_state
from raes_processor.compiler.time_model import time_model_contract_model


def require_delivery_time(model, delivery, snapshot):
    declaration = time_model_contract_model(model.time_model)
    if declaration is None or snapshot.time_model_state is None:
        raise ValueError("inject delivery shared time is unavailable")
    validate_time_runtime_state(declaration, snapshot.time_model_state)
    constraints = {item.address: item for item in model.time_model.constraints}
    for reference in delivery.temporal_constraint_addresses:
        constraint = constraints.get(reference)
        if (
            constraint is None
            or constraint.kind != "window"
            or constraint.start_tick is None
            or constraint.end_tick is None
        ):
            raise ValueError("inject delivery temporal constraint is unsupported")
        clock = snapshot.time_model_state.clocks[constraint.clock_address]
        coordinate = clock.coordinate
        if coordinate.segment != 0 or not (constraint.start_tick, constraint.start_microstep or 0) <= (
            coordinate.tick,
            coordinate.microstep,
        ) <= (constraint.end_tick, constraint.end_microstep or 0):
            raise ValueError("inject delivery window is expired or unmappable")
