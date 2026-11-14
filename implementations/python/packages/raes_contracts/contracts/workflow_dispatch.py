"""Closed single-step commands; graph transitions remain runtime authority."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.base import ContractModel, NonEmptyString, Sha256DigestString
from raes_contracts.contracts.execution_state import WorkflowStepAttemptProvenanceModel
from raes_contracts.execution_policy import EffectiveExecutionPolicy

StepKind = Literal["objective", "retry", "decision", "switch", "parallel", "join", "call", "end"]
Attempt = Annotated[int, Field(strict=True, ge=1)]


class WorkflowStatePredicate(ContractModel):
    step_name: NonEmptyString
    outcomes: tuple[Literal["succeeded", "failed", "exhausted"], ...]
    min_attempts: Annotated[int, Field(strict=True, ge=1)] | None = None


class WorkflowPredicate(ContractModel):
    assertion_addresses: tuple[NonEmptyString, ...] = ()
    objective_addresses: tuple[NonEmptyString, ...] = ()
    step_state_predicates: tuple[WorkflowStatePredicate, ...] = ()


class WorkflowCase(ContractModel):
    case_index: Annotated[int, Field(strict=True, ge=0)]
    predicate: WorkflowPredicate
    next_step: NonEmptyString


class WorkflowExecutionInputs(ContractModel):
    execution_mode: Literal["scripted", "objective", "scaffolded"] = "scripted"
    objective_address: str = ""
    procedure_ref: str = ""
    scaffold_refs: tuple[NonEmptyString, ...] = ()
    allowed_action_families: tuple[NonEmptyString, ...] = ()
    tool_affordance_refs: tuple[NonEmptyString, ...] = ()
    capability_refs: tuple[NonEmptyString, ...] = ()
    fact_binding_refs: tuple[NonEmptyString, ...] = ()


class WorkflowProgramStep(WorkflowExecutionInputs):
    name: NonEmptyString
    step_type: StepKind
    predicate: WorkflowPredicate | None = None
    next_step: str = ""
    on_success: str = ""
    on_failure: str = ""
    on_exhausted: str = ""
    then_step: str = ""
    else_step: str = ""
    switch_cases: tuple[WorkflowCase, ...] = ()
    default_step: str = ""
    branches: tuple[NonEmptyString, ...] = ()
    join_step: str = ""
    owning_parallel_step: str = ""
    called_workflow_address: str = ""
    compensation_workflow_address: str = ""
    max_attempts: Annotated[int, Field(strict=True, ge=1)] | None = None
    state_contract: dict[str, object] = Field(default_factory=dict)


class WorkflowProgram(ContractModel):
    """Typed executable projection of an admitted compiled workflow."""

    workflow_address: NonEmptyString
    start_step: NonEmptyString
    steps: dict[NonEmptyString, WorkflowProgramStep]
    timeout_seconds: Annotated[int, Field(strict=True, ge=1)] | None = None
    compensation_mode: Literal["disabled", "automatic"] = "disabled"
    compensation_triggers: tuple[Literal["failed", "cancelled", "timed_out"], ...] = ()
    compensation_failure_policy: Literal["fail_workflow", "record_and_continue"] = "fail_workflow"
    execution_policies: tuple[EffectiveExecutionPolicy, ...] = ()

    @model_validator(mode="after")
    def valid_references(self) -> Self:
        if self.start_step not in self.steps:
            raise ValueError("workflow program start is not a declared step")
        for name, step in self.steps.items():
            if name != step.name:
                raise ValueError("workflow program step identity mismatch")
            targets = (
                step.next_step,
                step.on_success,
                step.on_failure,
                step.on_exhausted,
                step.then_step,
                step.else_step,
                step.default_step,
                step.join_step,
                *step.branches,
                *(case.next_step for case in step.switch_cases),
            )
            if any(target and target not in self.steps for target in targets):
                raise ValueError("workflow program references an undeclared step")
        return self


class WorkflowStepDispatch(WorkflowExecutionInputs):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["workflow-step-dispatch/v1"] = "workflow-step-dispatch/v1"
    dispatch_id: NonEmptyString
    program_digest: Sha256DigestString
    root_operation_id: NonEmptyString
    invocation_id: NonEmptyString
    workflow_address: NonEmptyString
    branch_id: NonEmptyString
    step_name: NonEmptyString
    step_type: StepKind
    attempt: Attempt
    predecessor_revision: Annotated[int, Field(strict=True, ge=0)]
    observation_addresses: tuple[NonEmptyString, ...] = ()
    observation_digests: dict[NonEmptyString, Sha256DigestString] = Field(default_factory=dict)
    execution_policy: EffectiveExecutionPolicy | None = None
    execution_policy_scopes: tuple[EffectiveExecutionPolicy, ...] = ()
    remaining_budget_ms: Annotated[int, Field(strict=True, ge=0)] | None = None

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class WorkflowStepResponse(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["workflow-step-response/v1"] = "workflow-step-response/v1"
    dispatch_id: NonEmptyString
    dispatch_digest: Sha256DigestString
    outcome: Literal["succeeded", "failed"] | None = None
    observations: dict[NonEmptyString, Sha256DigestString] = Field(default_factory=dict)
    attempt_provenance: WorkflowStepAttemptProvenanceModel | None = None

    def require_dispatch(self, dispatch: WorkflowStepDispatch) -> None:
        if self.dispatch_id != dispatch.dispatch_id or self.dispatch_digest != dispatch.digest:
            raise ValueError("workflow response belongs to another dispatch")
        executable = dispatch.step_type in {"objective", "retry"}
        if executable != (self.outcome is not None):
            raise ValueError("workflow response outcome does not match its step kind")
        if set(self.observations) != set(dispatch.observation_addresses):
            raise ValueError("workflow response does not cover its admitted observations")
        if self.observations != dispatch.observation_digests:
            raise ValueError("workflow response changed its admitted observation digests")
        if self.attempt_provenance is not None:
            provenance = self.attempt_provenance
            if (
                provenance.attempt_id != dispatch.dispatch_id
                or provenance.procedure_ref != dispatch.procedure_ref
                or tuple(provenance.exposed_scaffold_refs) != dispatch.scaffold_refs
                or tuple(provenance.allowed_action_families) != dispatch.allowed_action_families
                or (
                    dispatch.allowed_action_families
                    and (provenance.selected_action_family or self.outcome == "succeeded")
                    and provenance.selected_action_family not in dispatch.allowed_action_families
                )
                or (
                    dispatch.tool_affordance_refs
                    and (provenance.selected_affordance_ref or self.outcome == "succeeded")
                    and provenance.selected_affordance_ref not in dispatch.tool_affordance_refs
                )
            ):
                raise ValueError("workflow attempt realization exceeds its dispatch")
            if (provenance.step_name, provenance.execution_mode, provenance.objective_address, provenance.outcome) != (
                dispatch.step_name,
                dispatch.execution_mode,
                dispatch.objective_address,
                self.outcome,
            ):
                raise ValueError("workflow attempt provenance does not match its dispatch")
        elif executable and dispatch.execution_mode != "scripted":
            raise ValueError("governed workflow execution requires attempt provenance")
