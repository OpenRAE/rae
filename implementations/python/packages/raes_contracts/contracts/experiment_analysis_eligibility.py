"""Shared run eligibility for study analysis and record accounting."""

from .experiment_run import ExperimentRunModel
from .trial_replacement import TrialReplacementPolicyModel

__all__ = ["experiment_run_is_analysis_eligible"]


def experiment_run_is_analysis_eligible(
    run: ExperimentRunModel | None, replacement_policy: TrialReplacementPolicyModel | None = None
) -> bool:
    """Check record status; callers must also establish evidence and replacement lineage."""
    return (
        run is not None
        and run.record_state == "archival"
        and run.run_status not in {"invalidated", "superseded"}
        and run.outcome_status != "not-evaluated"
        and not (
            replacement_policy
            and replacement_policy.max_replacements
            and run.run_status in replacement_policy.replace_on
        )
    )
