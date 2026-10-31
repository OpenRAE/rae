"""Readmit a candidate against separately trusted original compilation inputs."""

from raes_contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.contracts import AdmittedTrialPlanModel
from raes_contracts.errors import EvidenceIntegrityError

from .compiler import compile_admitted_trial_plan
from .models import TrialCompilationRequest


def readmit_admitted_trial_plan(
    plan: AdmittedTrialPlanModel,
    *,
    request: TrialCompilationRequest,
) -> AdmittedTrialPlanModel:
    """Recompile original authority and require the complete sealed result to match.

    The caller must acquire the original inputs and expected pins independently.
    Self-consistent candidate seals alone cannot supply this authority.

    Raises:
        AdmittedTrialPlanIngressError: If the candidate plan fails closed reconstruction.
        EvidenceIntegrityError: If the candidate does not replay against the trusted inputs.
    """
    candidate = revalidate_admitted_trial_plan(plan)
    result = compile_admitted_trial_plan(request)
    if result.plan is None or canonical_json_bytes(candidate.model_dump(mode="json")) != canonical_json_bytes(
        result.plan.model_dump(mode="json")
    ):
        raise EvidenceIntegrityError("admitted plan does not match the trusted original compilation inputs")
    return candidate
