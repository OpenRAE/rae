"""Pure deterministic trial-set compilation (SCE-002)."""

from .compiler import compile_admitted_trial_plan
from .models import TrialCompilationRequest, TrialCompilationResult
from .profiles import realization_assignment_key
from .readmission import readmit_admitted_trial_plan
from .replacement import TrialReplacementResult, compile_replacement_trial

__all__ = [
    "TrialCompilationRequest",
    "TrialCompilationResult",
    "compile_admitted_trial_plan",
    "compile_replacement_trial",
    "TrialReplacementResult",
    "realization_assignment_key",
    "readmit_admitted_trial_plan",
]
