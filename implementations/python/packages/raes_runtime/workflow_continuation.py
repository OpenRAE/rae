"""Closed workflow control facts retained by the incumbent operation store."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from raes_contracts.contracts.base import ContractModel, NonEmptyString, Sha256DigestString
from raes_contracts.contracts.execution_state import WorkflowHistoryEventModel, WorkflowStepStateModel
from raes_contracts.contracts.plan_operation import PlanOperationModel
from raes_contracts.contracts.workflow_dispatch import WorkflowProgram, WorkflowStepDispatch, WorkflowStepResponse


class WorkflowLocation(ContractModel):
    branch_id: NonEmptyString
    step_name: NonEmptyString
    barriers: tuple[NonEmptyString, ...] = ()
    waiting: bool = False


class WorkflowBarrier(ContractModel):
    step_name: NonEmptyString
    parent_branch: NonEmptyString
    branches: tuple[NonEmptyString, ...]
    arrived: tuple[NonEmptyString, ...] = ()


class WorkflowInvocation(ContractModel):
    invocation_id: NonEmptyString
    workflow_address: NonEmptyString
    parent_invocation: str = ""
    parent_step: str = ""
    compensation_for: str = ""
    status: Literal["running", "succeeded", "failed", "cancelled", "timed_out"] = "running"
    started_at: NonEmptyString
    updated_at: NonEmptyString
    terminal_reason: str | None = None
    steps: dict[NonEmptyString, WorkflowStepStateModel]
    locations: list[WorkflowLocation]
    barriers: dict[NonEmptyString, WorkflowBarrier] = Field(default_factory=dict)
    completion_order: list[NonEmptyString] = Field(default_factory=list)
    compensation_status: Literal["not_required", "pending", "running", "succeeded", "failed"] = "not_required"
    compensation_started_at: str | None = None
    compensation_updated_at: str | None = None
    compensation_failures: list[dict[str, str]] = Field(default_factory=list)
    compensation_queue: list[NonEmptyString] = Field(default_factory=list)
    compensation_child: str = ""


class WorkflowContinuation(ContractModel):
    """One immutable checkpoint; mutate only detached copies before commit."""

    schema_version: Literal["runtime-workflow-continuation/v1"] = "runtime-workflow-continuation/v1"
    root_operation_id: NonEmptyString
    program_digest: Sha256DigestString
    sequence: Annotated[int, Field(strict=True, ge=0)] = 0
    programs: dict[NonEmptyString, WorkflowProgram]
    invocations: dict[NonEmptyString, WorkflowInvocation]
    roots: tuple[NonEmptyString, ...]
    installation: tuple[PlanOperationModel, ...] = ()
    resources_required: bool = False
    events: dict[NonEmptyString, list[WorkflowHistoryEventModel]] = Field(default_factory=dict)
    outstanding: WorkflowStepDispatch | None = None
    observation_truths: dict[NonEmptyString, bool] = Field(default_factory=dict)


class WorkflowOperationState(ContractModel):
    """Typed optional extension of an existing operation record."""

    schema_version: Literal["runtime-workflow-operation/v1"] = "runtime-workflow-operation/v1"
    root_operation_id: NonEmptyString
    kind: Literal["root", "checkpoint", "response"]
    continuation: WorkflowContinuation | None = None
    response: WorkflowStepResponse | None = None
    baseline_revision: Annotated[int, Field(strict=True, ge=0)] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="after")
    def valid_kind(self) -> Self:
        if self.kind == "response":
            if self.response is None or self.continuation is not None or self.baseline_revision is not None:
                raise ValueError("response record requires only its response")
        elif self.continuation is None or self.response is not None:
            raise ValueError("workflow bookkeeping requires only its continuation")
        if (self.kind == "checkpoint") != (self.baseline_revision is not None):
            raise ValueError("only checkpoints require a predecessor revision")
        return self
