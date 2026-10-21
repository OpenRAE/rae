"""Post-effect observation through the incumbent lifecycle, without rollback claims."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import model_validator
from raes_contracts.contracts.backend_operation import OperationContractModel
from raes_contracts.observation_demand import EffectiveObservationDemand
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from .observation_execution import execute_plan_observation_demand, observation_submission_diagnostic
from .observation_results import observation_execution_from_payload


@dataclass(frozen=True)
class InjectCapturePlan:
    """A readback command naming its predecessor; it grants no world mutation."""

    observation_demands: tuple[EffectiveObservationDemand, ...]
    world_operation_id: str


class InjectCaptureResult(OperationContractModel):
    schema_version: Literal["inject-capture-result/v1"] = "inject-capture-result/v1"
    status: Literal["succeeded", "failed"]
    observation: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _owning_lifecycle(self):
        if self.status == "succeeded":
            if self.observation is None or observation_execution_from_payload(self.observation) is None:
                raise ValueError("inject capture requires its owning observation result")
            if not validate_realization_value(self.observation, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant:
                raise ValueError("inject capture exceeds portable bounds")
        elif self.observation is not None:
            raise ValueError("failed inject capture cannot claim observation")
        return self


def capture_plan(plan, operation_id):
    # Preserve the authored distinction between mandatory and optional selectors.
    return InjectCapturePlan(tuple(plan.observation_demands), operation_id)


def require_capture_admission(plane, plan) -> None:
    diagnostic = observation_submission_diagnostic(
        capture_plan(plan, "admission"),
        plane._target.manifest,
        plane._target.observation_runtime,
        durable_lifecycle_available=True,
    )
    if diagnostic is not None:
        raise ValueError("inject capture capability is unavailable")


def capture_inject(plane, record, plan, remaining) -> InjectCaptureResult | None:
    if not plan.observation_demands:
        return None
    try:
        with plane._mutation_authority.external_call():
            execution, diagnostic = plane._execution_adapter.call(
                "effect",
                execute_plan_observation_demand,
                capture_plan(plan, record.receipt.operation_id),
                deepcopy(plane._snapshot),
                plane._target.manifest,
                plane._target.observation_runtime,
                durable_lifecycle_available=True,
                operation_id=record.receipt.operation_id,
                timeout_ms=remaining(),
            )
        if diagnostic is not None or execution is None:
            return InjectCaptureResult(status="failed")
        return InjectCaptureResult(status="succeeded", observation=execution.result_payload)
    except Exception:
        return InjectCaptureResult(status="failed")
