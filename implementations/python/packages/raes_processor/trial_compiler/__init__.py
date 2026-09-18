"""Pure deterministic trial-set compilation (SCE-002)."""

from .compiler import compile_admitted_trial_plan
from .models import TrialCompilationRequest, TrialCompilationResult
from .profiles import realization_assignment_key

__all__ = [
    "TrialCompilationRequest",
    "TrialCompilationResult",
    "compile_admitted_trial_plan",
    "realization_assignment_key",
]
