"""Bounded external ingress for sealed admitted trial plans."""

from __future__ import annotations

from pydantic import ValidationError

from .contracts.admitted_trial_plan import AdmittedTrialPlanModel
from .errors import InvalidInputError
from .json_ingress import StrictJsonIngressError, parse_bounded_json_object

MAX_ADMITTED_TRIAL_PLAN_BYTES = 32 * 1024 * 1024


class AdmittedTrialPlanIngressError(InvalidInputError):
    """An admitted-plan document failed safe ingress or contract validation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def parse_admitted_trial_plan_json(
    source: str | bytes | bytearray,
) -> AdmittedTrialPlanModel:
    """Parse and fully reconstruct one sealed admitted plan before use."""

    try:
        payload = parse_bounded_json_object(
            source,
            max_bytes=MAX_ADMITTED_TRIAL_PLAN_BYTES,
        )
    except StrictJsonIngressError as exc:
        raise AdmittedTrialPlanIngressError(exc.code, str(exc)) from exc
    try:
        return AdmittedTrialPlanModel.model_validate(payload)
    except ValidationError as exc:
        raise AdmittedTrialPlanIngressError(
            "contract-invalid",
            "Admitted trial plan contract validation failed",
        ) from exc


def revalidate_admitted_trial_plan(
    plan: AdmittedTrialPlanModel,
) -> AdmittedTrialPlanModel:
    """Reconstruct a caller-held model so private object state cannot bypass validation."""

    try:
        return AdmittedTrialPlanModel.model_validate(plan.model_dump(mode="python"))
    except ValidationError as exc:
        raise AdmittedTrialPlanIngressError(
            "contract-invalid",
            "Admitted trial plan contract validation failed",
        ) from exc


__all__ = [
    "MAX_ADMITTED_TRIAL_PLAN_BYTES",
    "AdmittedTrialPlanIngressError",
    "parse_admitted_trial_plan_json",
    "revalidate_admitted_trial_plan",
]
