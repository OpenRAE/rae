"""Exact fixed-schedule admission using compiler identities and the shared clock."""

from fractions import Fraction

from raes_contracts.contracts.inject_occurrence import InjectSchedulePlacementModel, InjectTriggerRequestModel
from raes_contracts.contracts.time_model import validate_time_runtime_state
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler.time_model import time_model_contract_model
from raes_processor.models import RuntimeModel
from raes_processor.models.behavior_resources import EventRuntime, ScriptRuntime, StoryRuntime


def require_schedule(model: RuntimeModel, request: InjectTriggerRequestModel, snapshot: RuntimeSnapshot) -> None:
    if not isinstance(request.placement, InjectSchedulePlacementModel):
        return
    event, script, story = _schedule_membership(model, request)
    if event.assertion_addresses or len(model.time_model.clocks) != 1:
        raise ValueError("inject schedule requires an admitted unambiguous clock and assertion basis")
    seconds = _schedule_seconds(model, snapshot)
    _require_unit_speed(script, story)
    _require_event_cut(script, event, seconds)


def _schedule_membership(
    model: RuntimeModel,
    request: InjectTriggerRequestModel,
) -> tuple[EventRuntime, ScriptRuntime, StoryRuntime | None]:
    placement = request.placement
    event, script = model.events.get(placement.event), model.scripts.get(placement.script)
    story = model.stories.get(placement.story)
    if (
        event is None
        or script is None
        or request.inject not in event.inject_addresses
        or placement.event not in script.event_addresses
    ):
        raise ValueError("inject schedule membership differs")
    if placement.story is not None and (story is None or placement.script not in story.script_addresses):
        raise ValueError("inject story membership differs")
    return event, script, story


def _schedule_seconds(model: RuntimeModel, snapshot: RuntimeSnapshot) -> Fraction:
    declaration = time_model_contract_model(model.time_model)
    if snapshot.time_model_state is None:
        raise ValueError("inject schedule clock is unavailable")
    validate_time_runtime_state(declaration, snapshot.time_model_state)
    clock = model.time_model.clocks[0]
    reading = snapshot.time_model_state.clocks[clock.address]
    domain = next(item for item in model.time_model.domains if item.address == clock.time_domain_address)
    if domain.epoch != "scenario_start":
        raise ValueError("inject schedule requires an explicit scenario epoch mapping")
    if reading.coordinate.segment != 0 or reading.state != "running" or reading.coordinate.microstep != 0:
        raise ValueError("inject fixed schedule is not valid in this clock segment")
    return Fraction(reading.coordinate.tick * domain.tick_period_numerator, domain.tick_period_denominator)


def _require_unit_speed(script: ScriptRuntime, story: StoryRuntime | None) -> None:
    if script.spec.get("speed") != 1 or (story is not None and story.spec.get("speed") != 1):
        raise ValueError("inject schedule speed mapping is unsupported")


def _require_event_cut(script: ScriptRuntime, event: EventRuntime, seconds: Fraction) -> None:
    scheduled = script.spec.get("events", {}).get(event.name)
    start, end = script.spec.get("start_time"), script.spec.get("end_time")
    if any(type(value) not in (int, float) for value in (scheduled, start, end)):
        raise ValueError("inject schedule time mapping is unresolved")
    if not Fraction(str(start)) <= seconds <= Fraction(str(end)) or seconds != Fraction(str(scheduled)):
        raise ValueError("inject schedule is outside its authored event cut")
