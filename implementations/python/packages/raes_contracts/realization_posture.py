"""Shared author and backend intent for realization choices."""

from enum import Enum


class Posture(str, Enum):
    """Author/backend intent for a bound value or child scope."""

    OPEN = "open"
    CONSTRAINED = "constrained"
    EXACT = "exact"


__all__ = ["Posture"]
