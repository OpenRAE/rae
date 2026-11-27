"""Participant time domains and temporal event points (SEM-213)."""

from enum import Enum


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


__all__ = ["ParticipantTemporalEventPoint", "ParticipantTimeDomain"]
