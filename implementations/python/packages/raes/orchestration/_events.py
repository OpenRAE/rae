"""Authored narrative timing models: injects, events, scripts, and stories."""

from pydantic import Field, field_validator, model_validator

from .._base import SDLModel, parse_float_or_var
from .._source import Source
from ._durations import parse_duration


class Inject(SDLModel):
    """An action injected between entities during an exercise."""

    name: str = ""
    source: Source | None = None
    from_entity: str = ""
    to_entities: list[str] = Field(default_factory=list)
    description: str = ""
    environment: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entity_pairing(self) -> Inject:
        has_from = bool(self.from_entity)
        has_to = bool(self.to_entities)
        if has_from != has_to:
            raise ValueError("Inject must have both 'from_entity' and 'to_entities', or neither")
        return self


class Event(SDLModel):
    """A triggered action combining assertion preconditions and injects."""

    name: str = ""
    source: Source | None = None
    assertions: list[str] = Field(default_factory=list)
    injects: list[str] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_conditions(cls, value: object) -> object:
        if isinstance(value, dict) and "conditions" in value:
            raise ValueError("event conditions cannot state backend-neutral truth; reference precondition assertions")
        return value


class Script(SDLModel):
    """A timed sequence of human-readable durations parsed to seconds."""

    name: str = ""
    start_time: int | str
    end_time: int | str
    speed: float | str
    events: dict[str, int | str] = Field(min_length=1)
    description: str = ""

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time(cls, v: str | int | float) -> int | str:
        return parse_duration(v)

    @field_validator("speed", mode="before")
    @classmethod
    def parse_speed(cls, v: str | int | float) -> float | str:
        parsed = parse_float_or_var(v, minimum=0, field_name="speed")
        if isinstance(parsed, float) and parsed <= 0:
            raise ValueError("speed must be > 0")
        return parsed

    @field_validator("events", mode="before")
    @classmethod
    def parse_event_times(cls, v: dict[str, object]) -> dict[str, int | str]:
        if isinstance(v, dict):
            return {k: parse_duration(t) for k, t in v.items()}
        return v

    @model_validator(mode="after")
    def validate_time_bounds(self) -> Script:
        if isinstance(self.start_time, int) and isinstance(self.end_time, int) and self.end_time < self.start_time:
            raise ValueError(f"Script end_time ({self.end_time}s) must be >= start_time ({self.start_time}s)")
        for event_name, event_time in self.events.items():
            if not (
                isinstance(self.start_time, int) and isinstance(self.end_time, int) and isinstance(event_time, int)
            ):
                continue
            if event_time < self.start_time or event_time > self.end_time:
                raise ValueError(
                    f"Event '{event_name}' time ({event_time}s) is outside "
                    f"script bounds [{self.start_time}s, {self.end_time}s]"
                )
        return self


class Story(SDLModel):
    """Top-level exercise orchestration — a group of scripts."""

    name: str = ""
    speed: float | str = 1.0
    scripts: list[str] = Field(min_length=1)
    description: str = ""

    @field_validator("speed", mode="before")
    @classmethod
    def parse_speed(cls, v: str | int | float) -> float | str:
        return parse_float_or_var(v, minimum=1.0, field_name="speed")
