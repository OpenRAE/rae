"""Closed process-boundary composition of existing trial contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator

from .canonical import canonical_json_digest
from .contracts import AdmittedTrialPlanModel, RuntimeSnapshotEnvelopeModel, TrialProcessorPlanReferenceModel
from .contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from .contracts.base import Rfc3339DateTimeString
from .contracts.operation_carriers import OperationReceiptModel, OperationStatusModel
from .errors import InvalidInputError
from .json_ingress import parse_bounded_json_object
from .realization_structure import validate_realization_value
from .runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS
from .trial_observations import TrialObservation
from .trial_parallelism import MAX_TRIAL_PARALLELISM

Identity = Annotated[str, Field(strict=True, min_length=1, max_length=256)]
Digest = Annotated[str, Field(strict=True, pattern=r"^sha256:[a-f0-9]{64}$")]
PhaseState = Literal["unobserved", "succeeded", "failed", "cancelled", "indeterminate"]


def trial_attempt_id(experiment_id: str, entry_id: str, ordinal: int) -> str:
    return "attempt:" + str(uuid5(NAMESPACE_URL, experiment_id + ":" + entry_id + ":" + str(ordinal)))


class TrialHandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always", hide_input_in_errors=True)

    @model_validator(mode="before")
    @classmethod
    def bounded(cls, value: object) -> object:
        if not validate_realization_value(value, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True).conformant:
            raise ValueError("trial handoff exceeds portable value limits")
        return value

    @classmethod
    def from_json(cls, source: str | bytes) -> Self:
        payload = parse_bounded_json_object(source, max_bytes=16_777_216, max_depth=64)
        try:
            return cls.model_validate(payload)
        except ValidationError:
            raise InvalidInputError("trial handoff contract validation failed") from None

    @classmethod
    def reconstruct(cls, value: Self) -> Self:
        """Bound mutable caller-held children before serialization or copying."""
        if not isinstance(value, cls):
            raise ValueError("trial handoff requires its typed carrier")
        cls.bounded(value)
        return cls.model_validate(value.model_dump(mode="json"))

    @property
    def content_digest(self) -> str:
        type(self).bounded(self)
        return canonical_json_digest(self.model_dump(mode="json"))


class TrialAssignmentModel(TrialHandoffModel):
    """Data binding only; trusted composition supplies authentication."""

    schema_version: Literal["assigned-trial/v1"] = "assigned-trial/v1"
    plan: AdmittedTrialPlanModel = Field(repr=False)
    plan_entry_id: Identity
    execution_attempt_id: Identity
    attempt: Annotated[int, Field(strict=True, ge=1, le=1000)]
    started_at: Rfc3339DateTimeString
    deadline: Rfc3339DateTimeString
    target_scope: Identity
    owner_id: Identity
    owner_generation: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    instantiated_sdl_digest: Digest
    processor_plan_refs: tuple[TrialProcessorPlanReferenceModel, ...] = Field(min_length=3, max_length=3, repr=False)
    effective_parallelism: Annotated[int, Field(strict=True, ge=1, le=MAX_TRIAL_PARALLELISM)] = 1

    @model_validator(mode="after")
    def binding(self) -> TrialAssignmentModel:
        admitted = revalidate_admitted_trial_plan(self.plan)
        # Returned handoffs must not retain mutable children of the admission.
        object.__setattr__(self, "plan", admitted)
        object.__setattr__(
            self,
            "processor_plan_refs",
            tuple(
                TrialProcessorPlanReferenceModel.model_validate(item.model_dump(mode="json"))
                for item in self.processor_plan_refs
            ),
        )
        entry = admitted.entries.get(self.plan_entry_id)
        if entry is None:
            raise ValueError("assigned entry is absent from the original plan")
        if self.execution_attempt_id != trial_attempt_id(self.experiment_id, self.plan_entry_id, self.attempt):
            raise ValueError("assigned attempt differs from the original allocation")
        start, end = datetime.fromisoformat(self.started_at), datetime.fromisoformat(self.deadline)
        if (end - start).total_seconds() != entry.execution_controls.attempt_timeout_seconds:
            raise ValueError("assigned deadline differs from admitted controls")
        if {ref.plan_kind for ref in self.processor_plan_refs} != {"provisioning", "orchestration", "evaluation"}:
            raise ValueError("assignment requires each processor commitment")
        if not self.target_scope.startswith("target:"):
            raise ValueError("assignment requires a logical target scope")
        lower, upper = admitted.parallelism_bounds()
        if not lower <= self.effective_parallelism <= upper:
            raise ValueError("assignment parallelism is outside the admitted bounds")
        return self

    @property
    def experiment_id(self) -> str:
        origin = self.plan.replacement_origin
        return self.plan.plan_id if origin is None else origin.root_plan_id

    @property
    def root_plan_digest(self) -> str:
        origin = self.plan.replacement_origin
        return self.plan.plan_digest if origin is None else origin.root_plan_digest


class TrialFactModel(TrialHandoffModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "observation": {"properties": {"kind": {"const": "execution"}}, "required": ["kind"]}
                        }
                    },
                    "then": {
                        "properties": {
                            "observation": {
                                "properties": {
                                    "ceased": {"const": True},
                                    "state": {"not": {"const": "running"}},
                                }
                            }
                        }
                    },
                }
            ]
        }
    )
    observation: Annotated[TrialObservation, Field(discriminator="kind")] = Field(repr=False)
    observed_at: Rfc3339DateTimeString
    execution_snapshot: RuntimeSnapshotEnvelopeModel | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def snapshot_kind(self) -> TrialFactModel:
        if (self.observation.kind == "execution") != (self.execution_snapshot is not None):
            raise ValueError("only execution facts require an execution snapshot")
        if self.observation.kind == "execution" and (
            not self.observation.ceased or self.observation.state == "running"
        ):
            raise ValueError("execution facts require an observed terminal cut")
        return self


class TrialOperationModel(TrialHandoffModel):
    receipt: OperationReceiptModel = Field(repr=False)
    status: OperationStatusModel = Field(repr=False)

    @model_validator(mode="after")
    def operation_join(self) -> TrialOperationModel:
        if self.receipt.operation_id != self.status.operation_id or self.receipt.context != self.status.context:
            raise ValueError("trial operation status differs from its receipt")
        return self


class TrialOutcomeModel(TrialHandoffModel):
    """Original observations, without fabricated terminal facts for lost work."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"progress": {"const": "completed"}}, "required": ["progress"]},
                    "then": {
                        "required": ["facts"],
                        "properties": {
                            "facts": {
                                "allOf": [
                                    {
                                        "contains": {
                                            "properties": {
                                                "observation": {
                                                    "properties": {"kind": {"const": kind}},
                                                    "required": ["kind"],
                                                }
                                            },
                                            "required": ["observation"],
                                        }
                                    }
                                    for kind in ("execution", "cleanup")
                                ]
                            }
                        },
                    },
                }
            ]
        }
    )
    schema_version: Literal["trial-outcome/v1"] = "trial-outcome/v1"
    assignment_digest: Digest
    facts: tuple[TrialFactModel, ...] = Field(default=(), max_length=5, repr=False)
    operations: tuple[TrialOperationModel, ...] = Field(default=(), max_length=4096, repr=False)
    configuration_state: PhaseState = "unobserved"
    capture_state: PhaseState = "unobserved"
    retry_state: PhaseState = "unobserved"
    progress: Literal["progress", "pending", "indeterminate", "cleanup-failed", "completed"]

    @model_validator(mode="after")
    def unique_facts(self) -> TrialOutcomeModel:
        kinds = [fact.observation.kind for fact in self.facts]
        if len(kinds) != len(set(kinds)):
            raise ValueError("trial outcome contains duplicate observation kinds")
        ids = [item.receipt.operation_id for item in self.operations]
        if len(ids) != len(set(ids)):
            raise ValueError("trial outcome contains duplicate operations")
        if self.progress == "completed" and not {"execution", "cleanup"} <= set(kinds):
            raise ValueError("completed trial requires execution and cleanup observations")
        return self


class TrialAssignmentControlModel(TrialHandoffModel):
    schema_version: Literal["assigned-trial-control/v1"] = "assigned-trial-control/v1"
    assignment_digest: Digest
    cancelled: StrictBool
    prepare_retry: StrictBool = False


__all__ = ["TrialAssignmentModel", "TrialAssignmentControlModel", "TrialOutcomeModel", "trial_attempt_id"]
