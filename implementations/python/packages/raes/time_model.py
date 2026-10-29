"""Shared clock, time-domain, progression, and temporal constraint semantics."""

from enum import Enum
from math import gcd

from pydantic import Field, field_validator, model_validator

from ._base import SDLModel


class TimeDomainKind(str, Enum):
    """Meaning of values carried by a time domain."""

    WALL_CLOCK = "wall_clock"
    MONOTONIC = "monotonic"
    SIMULATED = "simulated"
    LOGICAL = "logical"
    EXTERNAL = "external"


class TimeDomainVisibility(str, Enum):
    """Who may observe a time domain."""

    RUNTIME_ONLY = "runtime_only"
    PARTICIPANT_VISIBLE = "participant_visible"
    EVIDENCE_ONLY = "evidence_only"


class TimeEpochKind(str, Enum):
    """Interpretation of tick zero."""

    UNIX = "unix"
    SCENARIO_START = "scenario_start"
    RUN_START = "run_start"
    UNANCHORED = "unanchored"
    EXTERNAL = "external"


class ClockAuthorityKind(str, Enum):
    """Plane that owns authoritative clock values."""

    RUNTIME = "runtime"
    BACKEND = "backend"
    SYSTEM = "system"
    EXTERNAL = "external"


class ClockMonotonicity(str, Enum):
    """Allowed direction of authoritative clock movement."""

    STRICT = "strict"
    NON_DECREASING = "non_decreasing"
    MAY_JUMP = "may_jump"


class TimeMappingKind(str, Enum):
    """Supported exact conversion families."""

    IDENTITY = "identity"
    AFFINE_RATIONAL = "affine_rational"


class TimeAdvancementMode(str, Enum):
    """How a clock may advance."""

    REAL_TIME = "real_time"
    DILATED = "dilated"
    STEPPED = "stepped"
    EVENT_DRIVEN = "event_driven"
    EXTERNALLY_PACED = "externally_paced"


class TimeSynchronizationMode(str, Enum):
    """How multiple time consumers coordinate progress."""

    NONE = "none"
    AUTHORITY = "authority"
    BARRIER = "barrier"
    CONSERVATIVE = "conservative"


class TimeResetBehavior(str, Enum):
    """Clock behavior at a reset boundary."""

    NEW_SEGMENT_ZERO = "new_segment_zero"
    NEW_SEGMENT_PRESERVE_VALUE = "new_segment_preserve_value"
    UNSUPPORTED = "unsupported"


class TimeReplayBehavior(str, Enum):
    """Clock behavior when a run is replayed."""

    RESTART_FROM_ANCHOR = "restart_from_anchor"
    RESTORE_RECORDED_ADVANCES = "restore_recorded_advances"
    UNSUPPORTED = "unsupported"


class TemporalConstraintKind(str, Enum):
    """Backend-independent temporal predicate families."""

    PRECEDENCE = "precedence"
    DURATION = "duration"
    WINDOW = "window"
    DEADLINE = "deadline"
    CADENCE = "cadence"


class ExactRatio(SDLModel):
    """Reduced positive rational value."""

    numerator: int = Field(gt=0)
    denominator: int = Field(gt=0)

    @model_validator(mode="after")
    def _require_reduced(self) -> ExactRatio:
        if gcd(self.numerator, self.denominator) != 1:
            raise ValueError("exact ratios must be reduced")
        return self


class TimeCoordinate(SDLModel):
    """One superdense point on a declared clock."""

    tick: int
    microstep: int = Field(default=0, ge=0)


class TimeDomain(SDLModel):
    """Authored meaning and resolution of one time domain."""

    kind: TimeDomainKind
    tick_period_seconds: ExactRatio
    epoch: TimeEpochKind
    visibility: TimeDomainVisibility = TimeDomainVisibility.RUNTIME_ONLY
    description: str

    @field_validator("description")
    @classmethod
    def _require_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("time domain description must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_epoch(self) -> TimeDomain:
        if self.kind == TimeDomainKind.WALL_CLOCK and self.epoch != TimeEpochKind.UNIX:
            raise ValueError("wall_clock time domains require the unix epoch")
        if self.kind == TimeDomainKind.MONOTONIC and self.epoch == TimeEpochKind.UNIX:
            raise ValueError("monotonic time domains cannot use the unix epoch")
        return self


class Clock(SDLModel):
    """Authored clock authority over one time domain."""

    time_domain_ref: str
    authority_kind: ClockAuthorityKind
    authority_ref: str
    monotonicity: ClockMonotonicity
    supports_pause: bool = False
    supports_reset: bool = False
    supports_jump: bool = False
    description: str

    @field_validator("time_domain_ref", "authority_ref", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("clock references and description must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_jump_policy(self) -> Clock:
        if self.monotonicity == ClockMonotonicity.MAY_JUMP and not self.supports_jump:
            raise ValueError("may_jump clocks must declare supports_jump")
        if self.monotonicity != ClockMonotonicity.MAY_JUMP and self.supports_jump:
            raise ValueError("supports_jump requires may_jump monotonicity")
        return self


class TimeDomainMapping(SDLModel):
    """Explicit exact conversion between otherwise incomparable domains."""

    source_domain_ref: str
    target_domain_ref: str
    mapping_kind: TimeMappingKind
    scale: ExactRatio = Field(default_factory=lambda: ExactRatio(numerator=1, denominator=1))
    offset_ticks: int = 0
    description: str

    @field_validator("source_domain_ref", "target_domain_ref", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("time-domain mapping references and description must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_mapping(self) -> TimeDomainMapping:
        if self.source_domain_ref == self.target_domain_ref:
            raise ValueError("time-domain mappings must connect distinct domains")
        if self.mapping_kind == TimeMappingKind.IDENTITY and (
            self.scale != ExactRatio(numerator=1, denominator=1) or self.offset_ticks != 0
        ):
            raise ValueError("identity mappings require scale 1/1 and zero offset")
        return self


class TimeProgressionPolicy(SDLModel):
    """Authored advancement, pacing, synchronization, and lifecycle policy."""

    clock_ref: str
    advancement_mode: TimeAdvancementMode
    pacing_ratio: ExactRatio = Field(default_factory=lambda: ExactRatio(numerator=1, denominator=1))
    synchronization_mode: TimeSynchronizationMode
    step_ticks: int | None = Field(default=None, gt=0)
    drift_bound_ticks: int | None = Field(default=None, ge=0)
    reset_behavior: TimeResetBehavior
    replay_behavior: TimeReplayBehavior
    description: str

    @field_validator("clock_ref", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("time progression policy references and description must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_progression(self) -> TimeProgressionPolicy:
        if self.advancement_mode == TimeAdvancementMode.STEPPED and self.step_ticks is None:
            raise ValueError("stepped time progression requires step_ticks")
        if self.advancement_mode != TimeAdvancementMode.STEPPED and self.step_ticks is not None:
            raise ValueError("step_ticks is only valid for stepped time progression")
        if self.advancement_mode not in {TimeAdvancementMode.REAL_TIME, TimeAdvancementMode.DILATED} and (
            self.pacing_ratio != ExactRatio(numerator=1, denominator=1)
        ):
            raise ValueError("pacing_ratio is only meaningful for real_time or dilated progression")
        return self


class TemporalConstraint(SDLModel):
    """One typed temporal predicate over ordinary RAES subjects."""

    constraint_kind: TemporalConstraintKind
    clock_ref: str
    subject_refs: list[str] = Field(min_length=1)
    start: TimeCoordinate | None = None
    end: TimeCoordinate | None = None
    duration_ticks: int | None = Field(default=None, gt=0)
    cadence_ticks: int | None = Field(default=None, gt=0)
    description: str

    @field_validator("clock_ref", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("temporal constraint references and description must be non-empty")
        return value

    @field_validator("subject_refs")
    @classmethod
    def _require_unique_subjects(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("temporal constraint subject_refs must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("temporal constraint subject_refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_constraint_shape(self) -> TemporalConstraint:
        self._validate_coordinate_order()
        self._validate_subject_cardinality()
        self._validate_required_coordinates()
        return self

    def _validate_coordinate_order(self) -> None:
        if self.start is not None and self.end is not None:
            if (self.end.tick, self.end.microstep) < (self.start.tick, self.start.microstep):
                raise ValueError("temporal constraint end must not precede start")

    def _validate_subject_cardinality(self) -> None:
        if self.constraint_kind == TemporalConstraintKind.PRECEDENCE and len(self.subject_refs) != 2:
            raise ValueError("precedence constraints require exactly two subject_refs")

    def _validate_required_coordinates(self) -> None:
        if self.constraint_kind == TemporalConstraintKind.DURATION and self.duration_ticks is None:
            raise ValueError("duration constraints require duration_ticks")
        if self.constraint_kind == TemporalConstraintKind.WINDOW and (self.start is None or self.end is None):
            raise ValueError("window constraints require start and end")
        if self.constraint_kind == TemporalConstraintKind.DEADLINE and self.end is None:
            raise ValueError("deadline constraints require end")
        if self.constraint_kind == TemporalConstraintKind.CADENCE and self.cadence_ticks is None:
            raise ValueError("cadence constraints require cadence_ticks")


__all__ = [
    "Clock",
    "ClockAuthorityKind",
    "ClockMonotonicity",
    "ExactRatio",
    "TemporalConstraint",
    "TemporalConstraintKind",
    "TimeAdvancementMode",
    "TimeCoordinate",
    "TimeDomain",
    "TimeDomainKind",
    "TimeDomainMapping",
    "TimeDomainVisibility",
    "TimeEpochKind",
    "TimeMappingKind",
    "TimeProgressionPolicy",
    "TimeReplayBehavior",
    "TimeResetBehavior",
    "TimeSynchronizationMode",
]
