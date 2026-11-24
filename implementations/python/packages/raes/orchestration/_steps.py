"""Workflow control-flow models: step types, predicates, policies, and steps."""

from enum import Enum

from pydantic import Field, field_validator, model_validator
from raes_contracts.sdl_model import SDLModel
from raes_contracts.variable_references import normalize_enum_value, parse_int_or_var

from ._durations import parse_duration


class WorkflowStepType(str, Enum):
    """Control-flow node types for declarative experiment workflows."""

    OBJECTIVE = "objective"
    DECISION = "decision"
    SWITCH = "switch"
    PARALLEL = "parallel"
    JOIN = "join"
    RETRY = "retry"
    CALL = "call"
    END = "end"


class WorkflowStepExecutionMode(str, Enum):
    """Authored realization boundary for an executable workflow step."""

    SCRIPTED = "scripted"
    OBJECTIVE = "objective"
    SCAFFOLDED = "scaffolded"


class WorkflowStepOutcome(str, Enum):
    """Portable workflow-visible outcomes emitted by executable steps."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXHAUSTED = "exhausted"


class WorkflowStepStateRef(SDLModel):
    """Predicate reference to previously observed workflow step state."""

    step: str
    outcomes: list[WorkflowStepOutcome] = Field(min_length=1)
    min_attempts: int | str | None = None

    @field_validator("min_attempts", mode="before")
    @classmethod
    def parse_min_attempts(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return None
        return parse_int_or_var(v, minimum=1, field_name="min_attempts")

    @model_validator(mode="after")
    def validate_unique_outcomes(self) -> WorkflowStepStateRef:
        if len(self.outcomes) != len(set(self.outcomes)):
            raise ValueError("Workflow step-state outcomes must be unique")
        return self


class WorkflowPredicate(SDLModel):
    """Typed branch predicate over assertions, objectives, and prior step state."""

    assertions: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    steps: list[WorkflowStepStateRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_conditions(cls, value: object) -> object:
        if isinstance(value, dict) and "conditions" in value:
            raise ValueError(
                "workflow predicate conditions cannot state backend-neutral truth; reference precondition assertions"
            )
        return value

    @model_validator(mode="after")
    def validate_non_empty(self) -> WorkflowPredicate:
        if any(
            (
                self.assertions,
                self.objectives,
                self.steps,
            )
        ):
            return self
        raise ValueError("Workflow predicate must reference at least one assertion, objective, or step state")


class WorkflowSwitchCase(SDLModel):
    """One ordered branch case within a ``switch`` workflow step."""

    when: WorkflowPredicate
    next_step: str = Field(alias="next")
    description: str = ""


class WorkflowTimeoutPolicy(SDLModel):
    """Workflow-level timeout policy."""

    seconds: int | str

    @field_validator("seconds", mode="before")
    @classmethod
    def parse_seconds(cls, v: str | int | float) -> int | str:
        parsed = parse_duration(v)
        if isinstance(parsed, int) and parsed <= 0:
            raise ValueError("timeout seconds must be > 0")
        return parsed


class WorkflowCompensationMode(str, Enum):
    """Workflow-level compensation behavior."""

    AUTOMATIC = "automatic"
    DISABLED = "disabled"


class WorkflowCompensationTrigger(str, Enum):
    """Terminal workflow reasons that may trigger compensation."""

    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class WorkflowCompensationFailurePolicy(str, Enum):
    """How primary workflow status should treat compensation failures."""

    FAIL_WORKFLOW = "fail_workflow"
    RECORD_AND_CONTINUE = "record_and_continue"


class WorkflowCompensationPolicy(SDLModel):
    """Workflow-level compensation policy."""

    mode: WorkflowCompensationMode = WorkflowCompensationMode.DISABLED
    on: list[WorkflowCompensationTrigger] = Field(default_factory=list)
    failure_policy: WorkflowCompensationFailurePolicy = Field(
        default=WorkflowCompensationFailurePolicy.FAIL_WORKFLOW,
    )
    order: str = "reverse_completion"

    @field_validator("order", mode="before")
    @classmethod
    def normalize_order(cls, v: object) -> str:
        if v is None:
            return "reverse_completion"
        return str(v)

    @model_validator(mode="after")
    def validate_policy(self) -> WorkflowCompensationPolicy:
        if self.mode == WorkflowCompensationMode.AUTOMATIC and not self.on:
            raise ValueError("Automatic workflow compensation requires at least one trigger in 'on'")
        if self.order != "reverse_completion":
            raise ValueError("Workflow compensation currently only supports order 'reverse_completion'")
        if len(self.on) != len(set(self.on)):
            raise ValueError("Workflow compensation triggers must be unique")
        return self


class WorkflowStep(SDLModel):
    """A named workflow step with explicit portable control semantics."""

    type: WorkflowStepType = Field(alias="type")
    execution_mode: WorkflowStepExecutionMode = WorkflowStepExecutionMode.SCRIPTED
    objective: str = ""
    procedure_ref: str = ""
    scaffold_refs: list[str] = Field(default_factory=list)
    allowed_action_families: list[str] = Field(default_factory=list)
    tool_affordance_refs: list[str] = Field(default_factory=list)
    capability_refs: list[str] = Field(default_factory=list)
    fact_binding_refs: list[str] = Field(default_factory=list)
    next: str = ""
    on_success: str = ""
    on_failure: str = ""
    on_exhausted: str = ""
    when: WorkflowPredicate | None = None
    then_step: str = Field(default="", alias="then")
    else_step: str = Field(default="", alias="else")
    cases: list[WorkflowSwitchCase] = Field(default_factory=list)
    default_step: str = Field(default="", alias="default")
    branches: list[str] = Field(default_factory=list)
    join: str = ""
    workflow: str = ""
    compensate_with: str = ""
    max_attempts: int | str | None = None
    description: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        normalized = normalize_enum_value(v)
        # Tuple membership compares by equality, so an unhashable authored value reaches type validation.
        if normalized in ("if", "while"):
            raise ValueError(
                f"workflow step type '{normalized}' is no longer supported; "
                "use 'decision' or 'retry' with explicit success/failure "
                "transitions instead"
            )
        return normalized

    @field_validator("max_attempts", mode="before")
    @classmethod
    def parse_max_attempts(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return None
        return parse_int_or_var(v, minimum=1, field_name="max_attempts")

    @field_validator(
        "scaffold_refs",
        "allowed_action_families",
        "tool_affordance_refs",
        "capability_refs",
        "fact_binding_refs",
    )
    @classmethod
    def validate_goal_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("workflow step governed references must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("workflow step governed references must be unique within each field")
        return values

    @model_validator(mode="after")
    def validate_execution_mode(self) -> WorkflowStep:
        self._validate_goal_mode_compatibility()
        self._validate_scaffolded_mode()
        return self

    def _validate_goal_mode_compatibility(self) -> None:
        goal_modes = {WorkflowStepExecutionMode.OBJECTIVE, WorkflowStepExecutionMode.SCAFFOLDED}
        if self.execution_mode in goal_modes and self.type not in {
            WorkflowStepType.OBJECTIVE,
            WorkflowStepType.RETRY,
        }:
            raise ValueError("objective and scaffolded execution modes are only valid for objective or retry steps")
        if self.execution_mode in goal_modes and self.procedure_ref:
            raise ValueError("objective and scaffolded execution mode does not admit prescribed procedure")
        if self.execution_mode != WorkflowStepExecutionMode.SCRIPTED and self.procedure_ref:
            raise ValueError("procedure_ref is only valid for scripted execution mode")

    def _validate_scaffolded_mode(self) -> None:
        if self.execution_mode != WorkflowStepExecutionMode.SCAFFOLDED and self.scaffold_refs:
            raise ValueError("scaffold_refs are only valid for scaffolded execution mode")
        if self.execution_mode != WorkflowStepExecutionMode.SCAFFOLDED and self.allowed_action_families:
            raise ValueError("allowed_action_families are only valid for scaffolded execution mode")
        if self.execution_mode == WorkflowStepExecutionMode.SCAFFOLDED and not any(
            (self.scaffold_refs, self.tool_affordance_refs, self.allowed_action_families)
        ):
            raise ValueError(
                "scaffolded execution mode requires governed scaffold, tool-affordance, or action-family references"
            )

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> WorkflowStep:
        type_validators = {
            WorkflowStepType.OBJECTIVE: self._validate_objective_type,
            WorkflowStepType.DECISION: self._validate_decision_type,
            WorkflowStepType.SWITCH: self._validate_switch_type,
            WorkflowStepType.PARALLEL: self._validate_parallel_type,
            WorkflowStepType.JOIN: self._validate_join_type,
            WorkflowStepType.RETRY: self._validate_retry_type,
            WorkflowStepType.CALL: self._validate_call_type,
        }
        type_validators.get(self.type, self._validate_end_type)()
        return self

    def _validate_objective_type(self) -> None:
        if not self.objective or not self.on_success:
            raise ValueError("Objective workflow step requires 'objective' and 'on_success'")
        if any(
            (
                self.next,
                self.on_exhausted,
                self.when is not None,
                self.then_step,
                self.else_step,
                self.branches,
                self.join,
                self.max_attempts is not None,
            )
        ):
            raise ValueError(
                "Objective workflow step only supports 'objective', "
                "'on-success', optional 'on-failure', optional "
                "'compensate-with', and 'description'"
            )

    def _validate_decision_type(self) -> None:
        if self.when is None or not self.then_step or not self.else_step:
            raise ValueError("Decision workflow step requires 'when', 'then', and 'else'")
        if any(
            (
                self.objective,
                self.next,
                self.on_success,
                self.on_failure,
                self.on_exhausted,
                self.branches,
                self.join,
                self.max_attempts is not None,
                self.compensate_with,
            )
        ):
            raise ValueError("Decision workflow step only supports 'when', 'then', 'else', and 'description'")

    def _validate_switch_type(self) -> None:
        if not self.cases or not self.default_step:
            raise ValueError("Switch workflow step requires at least one 'case' and a 'default' target")
        if any(
            (
                self.objective,
                self.next,
                self.on_success,
                self.on_failure,
                self.on_exhausted,
                self.when is not None,
                self.then_step,
                self.else_step,
                self.branches,
                self.join,
                self.workflow,
                self.max_attempts is not None,
                self.compensate_with,
            )
        ):
            raise ValueError("Switch workflow step only supports 'cases', 'default', and 'description'")

    def _validate_parallel_type(self) -> None:
        if len(self.branches) < 2 or not self.join:
            raise ValueError("Parallel workflow step requires at least two 'branches' and a 'join'")
        if any(
            (
                self.objective,
                self.when is not None,
                self.next,
                self.on_success,
                self.on_exhausted,
                self.then_step,
                self.else_step,
                self.max_attempts is not None,
                self.compensate_with,
            )
        ):
            raise ValueError(
                "Parallel workflow step only supports 'branches', 'join', optional 'on-failure', and 'description'"
            )
        if len(self.branches) != len(set(self.branches)):
            raise ValueError("Parallel workflow branches must be unique")

    def _validate_join_type(self) -> None:
        if not self.next:
            raise ValueError("Join workflow step requires 'next'")
        if any(
            (
                self.objective,
                self.on_success,
                self.on_failure,
                self.on_exhausted,
                self.when is not None,
                self.then_step,
                self.else_step,
                self.branches,
                self.join,
                self.max_attempts is not None,
                self.compensate_with,
            )
        ):
            raise ValueError("Join workflow step only supports 'next' and 'description'")

    def _validate_retry_type(self) -> None:
        if not self.objective or self.max_attempts is None or not self.on_success:
            raise ValueError("Retry workflow step requires 'objective', 'max-attempts', and 'on-success'")
        if any(
            (
                self.next,
                self.when is not None,
                self.on_failure,
                self.then_step,
                self.else_step,
                self.branches,
                self.join,
                self.compensate_with,
            )
        ):
            raise ValueError(
                "Retry workflow step only supports 'objective', "
                "'max-attempts', 'on-success', optional 'on-exhausted', "
                "and 'description'"
            )

    def _validate_call_type(self) -> None:
        if not self.workflow or not self.on_success:
            raise ValueError("Call workflow step requires 'workflow' and 'on-success'")
        if any(
            (
                self.objective,
                self.next,
                self.on_exhausted,
                self.when is not None,
                self.then_step,
                self.else_step,
                self.cases,
                self.default_step,
                self.branches,
                self.join,
                self.max_attempts is not None,
            )
        ):
            raise ValueError(
                "Call workflow step only supports 'workflow', "
                "'on-success', optional 'on-failure', optional "
                "'compensate-with', and 'description'"
            )

    def _validate_end_type(self) -> None:
        if any(
            (
                self.objective,
                self.next,
                self.when is not None,
                self.on_success,
                self.on_failure,
                self.on_exhausted,
                self.then_step,
                self.else_step,
                self.cases,
                self.default_step,
                self.branches,
                self.join,
                self.workflow,
                self.max_attempts is not None,
                self.compensate_with,
            )
        ):
            raise ValueError("End workflow step only supports 'type' and 'description'")
