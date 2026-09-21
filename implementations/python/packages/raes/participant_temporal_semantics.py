"""Typed participant temporal semantics (SEM-213)."""

from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ._base import SDLModel


class ParticipantTimeDomain(str, Enum):
    """Distinct SEM-213 time domains."""

    EPISODE_STEP = "episode_step"
    SCENARIO_TIME = "scenario_time"
    SIMULATION_TIME = "simulation_time"
    BACKEND_TIME = "backend_time"
    WALL_CLOCK_TIME = "wall_clock_time"


class ParticipantTemporalEventPoint(str, Enum):
    """Named participant event points used by temporal contracts."""

    SUBMIT = "submit"
    START = "start"
    END = "end"
    OBSERVED = "observed"
    EFFECTIVE = "effective"
    DEADLINE = "deadline"
    WINDOW_OPEN = "window_open"
    WINDOW_CLOSE = "window_close"
    RESET = "reset"
    REPLAY = "replay"


class ParticipantTemporalContractKind(str, Enum):
    """SEM-213 temporal contract kinds."""

    SCHEDULE = "schedule"
    CADENCE = "cadence"
    DEADLINE = "deadline"
    DWELL = "dwell"
    LATENCY = "latency"
    TIME_WINDOW = "time_window"
    TIMEOUT = "timeout"
    COOLDOWN = "cooldown"


class ParticipantBackendTimingDisclosureKind(str, Enum):
    """Backend timing realization disclosures."""

    PACING = "pacing"
    DILATION = "dilation"
    SYNCHRONIZATION = "synchronization"
    SERIALIZATION = "serialization"
    UNSUPPORTED_GUARANTEE = "unsupported_guarantee"


class ParticipantTemporalSupportMode(str, Enum):
    """How a backend supports a temporal guarantee."""

    EXACT = "exact"
    BOUNDED = "bounded"
    DISCLOSED_LIMITATION = "disclosed_limitation"
    UNSUPPORTED = "unsupported"


class ParticipantTemporalState(str, Enum):
    """Abstract SEM-213 temporal state-machine states."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    CADENCE_READY = "cadence_ready"
    CADENCE_WAITING = "cadence_waiting"
    DWELL_ACTIVE = "dwell_active"
    DWELL_SATISFIED = "dwell_satisfied"
    DEADLINE_OPEN = "deadline_open"
    DEADLINE_MET = "deadline_met"
    DEADLINE_MISSED = "deadline_missed"
    TIMEOUT = "timeout"
    RESET = "reset"
    REPLAY_BOUNDARY = "replay_boundary"


_DURATION_KINDS = frozenset(
    {
        ParticipantTemporalContractKind.CADENCE,
        ParticipantTemporalContractKind.DEADLINE,
        ParticipantTemporalContractKind.DWELL,
        ParticipantTemporalContractKind.LATENCY,
        ParticipantTemporalContractKind.TIMEOUT,
        ParticipantTemporalContractKind.COOLDOWN,
    }
)

_WINDOW_KINDS = frozenset(
    {
        ParticipantTemporalContractKind.SCHEDULE,
        ParticipantTemporalContractKind.TIME_WINDOW,
        ParticipantTemporalContractKind.DWELL,
    }
)

_BOUNDARY_KINDS = frozenset(
    {
        ParticipantTemporalContractKind.CADENCE,
        ParticipantTemporalContractKind.DEADLINE,
        ParticipantTemporalContractKind.DWELL,
        ParticipantTemporalContractKind.LATENCY,
        ParticipantTemporalContractKind.TIMEOUT,
        ParticipantTemporalContractKind.COOLDOWN,
        ParticipantTemporalContractKind.TIME_WINDOW,
    }
)

_REPEATED_OR_STUDY_LEVEL_KINDS = frozenset(
    {
        ParticipantTemporalContractKind.CADENCE,
        ParticipantTemporalContractKind.TIME_WINDOW,
    }
)

_SCHEDULE_ELIGIBILITY_POINTS = frozenset(
    {
        ParticipantTemporalEventPoint.SUBMIT,
        ParticipantTemporalEventPoint.START,
    }
)

_TIME_WINDOW_POINTS = frozenset(
    {
        ParticipantTemporalEventPoint.WINDOW_OPEN,
        ParticipantTemporalEventPoint.WINDOW_CLOSE,
    }
)

_DEADLINE_OUTCOME_POINTS = frozenset(
    {
        ParticipantTemporalEventPoint.END,
        ParticipantTemporalEventPoint.OBSERVED,
        ParticipantTemporalEventPoint.EFFECTIVE,
    }
)

_DWELL_START_POINTS = frozenset(
    {
        ParticipantTemporalEventPoint.START,
        ParticipantTemporalEventPoint.WINDOW_OPEN,
    }
)

_DWELL_END_POINTS = frozenset(
    {
        ParticipantTemporalEventPoint.END,
        ParticipantTemporalEventPoint.WINDOW_CLOSE,
    }
)

_CADENCE_CONSTRAINED_POINTS = frozenset(
    {
        ParticipantTemporalEventPoint.SUBMIT,
        ParticipantTemporalEventPoint.START,
        ParticipantTemporalEventPoint.OBSERVED,
        ParticipantTemporalEventPoint.EFFECTIVE,
    }
)


class ParticipantSharedTimeBinding(SDLModel):
    """Explicit shared-time binding; legacy descriptive references stay opaque."""

    profile: Literal["participant-shared-time/v1"]
    clock_ref: str = Field(min_length=1)
    constraint_ref: str = Field(min_length=1)
    event_point: Literal["start", "end", "observed", "effective"]
    evidence_mode: Literal["event", "continuous"]
    condition_precondition_id: str | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)
    observation_boundary_ref: str | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def _validate_evidence_requirements(self):
        if self.evidence_mode == "continuous":
            if self.condition_precondition_id is None or self.observation_boundary_ref is None:
                raise ValueError("continuous dwell requires a condition_precondition_id and observation_boundary_ref")
        elif self.condition_precondition_id is not None or self.observation_boundary_ref is not None:
            raise ValueError("event evidence does not use condition coverage fields")
        return self


class ParticipantTemporalContract(SDLModel):
    """Typed SEM-213 temporal contract for a participant action."""

    temporal_id: str
    temporal_kind: ParticipantTemporalContractKind
    time_domain: ParticipantTimeDomain
    clock_authority: str
    event_points: list[ParticipantTemporalEventPoint] = Field(min_length=1)
    description: str
    window_ref: str | None = None
    duration_ref: str | None = None
    reset_boundary: str | None = None
    replay_boundary: str | None = None
    randomization_basis: str | None = None
    ordering_basis: str
    backend_disclosure_refs: list[str] = Field(default_factory=list)
    shared_time_binding: ParticipantSharedTimeBinding | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @field_validator(
        "temporal_id",
        "clock_authority",
        "description",
        "ordering_basis",
    )
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant temporal contract fields must be non-empty")
        return value

    @field_validator(
        "window_ref",
        "duration_ref",
        "reset_boundary",
        "replay_boundary",
        "randomization_basis",
    )
    @classmethod
    def _require_optional_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("participant temporal contract optional fields must be non-empty when provided")
        return value

    @field_validator("event_points")
    @classmethod
    def _require_unique_event_points(
        cls,
        values: list[ParticipantTemporalEventPoint],
    ) -> list[ParticipantTemporalEventPoint]:
        if len(set(values)) != len(values):
            raise ValueError("participant temporal contract event_points must be unique")
        return values

    @field_validator("backend_disclosure_refs")
    @classmethod
    def _require_non_empty_disclosure_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant temporal contract backend_disclosure_refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("participant temporal contract backend_disclosure_refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_sem213_contract_shape(self) -> "ParticipantTemporalContract":
        event_points = set(self.event_points)
        if self.temporal_kind in _WINDOW_KINDS and self.window_ref is None:
            raise ValueError(f"{self.temporal_kind.value} temporal contracts require window_ref")
        if self.temporal_kind in _DURATION_KINDS and self.duration_ref is None:
            raise ValueError(f"{self.temporal_kind.value} temporal contracts require duration_ref")
        if self.temporal_kind in _BOUNDARY_KINDS:
            if self.reset_boundary is None:
                raise ValueError(f"{self.temporal_kind.value} temporal contracts require reset_boundary")
            if self.replay_boundary is None:
                raise ValueError(f"{self.temporal_kind.value} temporal contracts require replay_boundary")
        if not self.backend_disclosure_refs:
            raise ValueError(f"{self.temporal_kind.value} temporal contracts require backend_disclosure_refs")
        if self.temporal_kind in _REPEATED_OR_STUDY_LEVEL_KINDS and self.randomization_basis is None:
            raise ValueError(f"{self.temporal_kind.value} temporal contracts require randomization_basis")
        if self.temporal_kind == ParticipantTemporalContractKind.SCHEDULE and not (
            event_points & _SCHEDULE_ELIGIBILITY_POINTS
        ):
            raise ValueError("schedule temporal contracts require submit or start event_points")
        if self.temporal_kind == ParticipantTemporalContractKind.TIME_WINDOW and not (
            event_points >= _TIME_WINDOW_POINTS
        ):
            raise ValueError("time_window temporal contracts require window_open and window_close event_points")
        if self.temporal_kind == ParticipantTemporalContractKind.DEADLINE:
            if len(self.event_points) < 2:
                raise ValueError("deadline temporal contracts require at least two event_points")
            if ParticipantTemporalEventPoint.DEADLINE not in event_points:
                raise ValueError("deadline temporal contracts require a deadline event_point")
            allowed_outcomes = _DEADLINE_OUTCOME_POINTS
            if self.shared_time_binding is not None:
                allowed_outcomes = allowed_outcomes | {ParticipantTemporalEventPoint.START}
            if not (event_points & allowed_outcomes):
                raise ValueError("deadline temporal contracts require end, observed, or effective event_points")
        if self.temporal_kind == ParticipantTemporalContractKind.DWELL:
            if len(self.event_points) < 2:
                raise ValueError("dwell temporal contracts require at least two event_points")
            if not (event_points & _DWELL_START_POINTS) or not (event_points & _DWELL_END_POINTS):
                raise ValueError("dwell temporal contracts require start/window_open and end/window_close event_points")
        if self.temporal_kind == ParticipantTemporalContractKind.CADENCE and not (
            event_points & _CADENCE_CONSTRAINED_POINTS
        ):
            raise ValueError("cadence temporal contracts require submit, start, observed, or effective event_points")
        if self.temporal_kind == ParticipantTemporalContractKind.LATENCY and len(self.event_points) < 2:
            raise ValueError("latency temporal contracts require at least two event_points")
        if self.shared_time_binding is not None:
            binding = self.shared_time_binding
            if self.temporal_kind == ParticipantTemporalContractKind.DEADLINE:
                if binding.evidence_mode != "event" or binding.event_point not in {
                    point.value for point in event_points
                }:
                    raise ValueError("bound deadline requires event evidence for a declared event_point")
            elif self.temporal_kind == ParticipantTemporalContractKind.DWELL:
                if binding.evidence_mode == "event" or binding.event_point != "start":
                    raise ValueError("bound dwell requires condition coverage before action start")
                if binding.event_point not in {point.value for point in event_points}:
                    raise ValueError("bound dwell requires a declared event_point")
            else:
                raise ValueError("participant-shared-time/v1 binds deadline or dwell contracts")
        return self


class ParticipantBackendTimingDisclosure(SDLModel):
    """Backend timing realization disclosure for SEM-213 contracts."""

    disclosure_id: str
    disclosure_kind: ParticipantBackendTimingDisclosureKind
    support_mode: ParticipantTemporalSupportMode
    description: str
    affected_temporal_ids: list[str] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("disclosure_id", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant backend timing disclosure fields must be non-empty")
        return value

    @field_validator("affected_temporal_ids", "limitations")
    @classmethod
    def _require_non_empty_items(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant backend timing disclosure list entries must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("participant backend timing disclosure list entries must be unique")
        return values

    @model_validator(mode="after")
    def _validate_limitations(self) -> "ParticipantBackendTimingDisclosure":
        if (
            self.support_mode
            in {
                ParticipantTemporalSupportMode.DISCLOSED_LIMITATION,
                ParticipantTemporalSupportMode.BOUNDED,
                ParticipantTemporalSupportMode.UNSUPPORTED,
            }
            and not self.limitations
        ):
            raise ValueError(f"{self.support_mode.value} timing disclosures require limitations")
        return self


def validate_action_contract_temporal_payload(
    *,
    preconditions: list[object],
    temporal_contracts: list[ParticipantTemporalContract],
    backend_timing_disclosures: list[ParticipantBackendTimingDisclosure],
) -> None:
    """Validate SEM-213 cross-field references on a participant action contract."""

    temporal_ids = [contract.temporal_id for contract in temporal_contracts]
    duplicate_temporal_ids = sorted(
        {temporal_id for temporal_id in temporal_ids if temporal_ids.count(temporal_id) > 1}
    )
    if duplicate_temporal_ids:
        joined = ", ".join(duplicate_temporal_ids)
        raise ValueError(f"participant temporal_contracts require unique temporal_id values: {joined}")

    disclosure_ids = [disclosure.disclosure_id for disclosure in backend_timing_disclosures]
    duplicate_disclosure_ids = sorted(
        {disclosure_id for disclosure_id in disclosure_ids if disclosure_ids.count(disclosure_id) > 1}
    )
    if duplicate_disclosure_ids:
        joined = ", ".join(duplicate_disclosure_ids)
        raise ValueError(f"participant backend_timing_disclosures require unique disclosure_id values: {joined}")

    if backend_timing_disclosures and not temporal_contracts:
        raise ValueError("backend_timing_disclosures require temporal_contracts")

    if any(str(getattr(precondition.precondition_class, "value", "")) == "temporal" for precondition in preconditions):
        if not temporal_contracts:
            raise ValueError("temporal preconditions require temporal_contracts")

    known_disclosures = set(disclosure_ids)
    for contract in temporal_contracts:
        unknown_disclosures = sorted(set(contract.backend_disclosure_refs) - known_disclosures)
        if unknown_disclosures:
            joined = ", ".join(unknown_disclosures)
            raise ValueError(
                f"temporal_contract {contract.temporal_id!r} references unknown backend_timing_disclosures: {joined}"
            )

    known_temporal_ids = set(temporal_ids)
    for disclosure in backend_timing_disclosures:
        unknown_temporal_ids = sorted(set(disclosure.affected_temporal_ids) - known_temporal_ids)
        if unknown_temporal_ids:
            joined = ", ".join(unknown_temporal_ids)
            raise ValueError(
                f"backend_timing_disclosure {disclosure.disclosure_id!r} references unknown "
                f"temporal_contracts: {joined}"
            )
