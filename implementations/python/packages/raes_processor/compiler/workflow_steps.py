"""Per-step workflow compilation machinery and workflow compilation state."""

from dataclasses import dataclass, field

from raes.orchestration import (
    Workflow,
    WorkflowPredicate,
    WorkflowStep,
    WorkflowStepExecutionMode,
    WorkflowStepType,
)
from raes.scenario import InstantiatedScenario
from raes_backend_protocols.capabilities import (
    WorkflowFeature,
    WorkflowStatePredicateFeature,
)
from raes_contracts.workflow.semantics import workflow_step_semantic_contract

from ..models import (
    AssertionRuntime,
    Diagnostic,
    WorkflowPredicateRuntime,
    WorkflowStepOutcome,
    WorkflowStepRuntime,
    WorkflowStepStatePredicateRuntime,
    WorkflowSwitchCaseRuntime,
)
from .addresses import _assertion_address, _objective_address, _workflow_address
from .ref_resolution import (
    _resolve_named_refs,
)
from .support import _address, _dedupe


@dataclass(frozen=True)
class _WorkflowPredicateCompilation:
    predicate: WorkflowPredicateRuntime
    assertion_addresses: tuple[str, ...]
    predicate_addresses: tuple[str, ...]
    objective_addresses: tuple[str, ...]
    step_state_predicates: tuple[WorkflowStepStatePredicateRuntime, ...]


@dataclass
class _WorkflowCompilationState:
    join_owners: dict[str, str]
    control_steps: dict[str, WorkflowStepRuntime] = field(default_factory=dict)
    control_edges: dict[str, tuple[str, ...]] = field(default_factory=dict)
    referenced_objectives: list[str] = field(default_factory=list)
    step_assertion_addresses: dict[str, tuple[str, ...]] = field(default_factory=dict)
    step_predicate_addresses: dict[str, tuple[str, ...]] = field(default_factory=dict)
    required_features: list[WorkflowFeature] = field(default_factory=list)
    required_state_predicate_features: list[WorkflowStatePredicateFeature] = field(default_factory=list)
    compensation_targets: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _WorkflowStepContext:
    scenario: InstantiatedScenario
    workflow: Workflow
    workflow_address: str
    state: _WorkflowCompilationState
    assertions: dict[str, AssertionRuntime]
    diagnostics: list[Diagnostic]


_WORKFLOW_STEP_TYPE_FEATURES = {
    WorkflowStepType.DECISION: WorkflowFeature.DECISION,
    WorkflowStepType.SWITCH: WorkflowFeature.SWITCH,
    WorkflowStepType.PARALLEL: WorkflowFeature.PARALLEL_BARRIER,
    WorkflowStepType.RETRY: WorkflowFeature.RETRY,
    WorkflowStepType.CALL: WorkflowFeature.CALL,
}

_WORKFLOW_STEP_MODE_FEATURES = {
    WorkflowStepExecutionMode.OBJECTIVE: WorkflowFeature.OBJECTIVE_STEPS,
    WorkflowStepExecutionMode.SCAFFOLDED: WorkflowFeature.SCAFFOLDED_STEPS,
}


def _compile_workflow_predicate(
    predicate_source: WorkflowPredicate,
    *,
    scenario: InstantiatedScenario,
    assertions: dict[str, AssertionRuntime],
    predicate_address: str,
    diagnostics: list[Diagnostic],
) -> _WorkflowPredicateCompilation:
    assertion_addresses, workflow_diagnostics = _resolve_named_refs(
        ref_names=list(predicate_source.assertions),
        available_names={assertion.name for assertion in assertions.values()},
        address_builder=_assertion_address,
        owner_address=predicate_address,
        domain="orchestration",
        code_prefix="orchestration.assertion-ref",
        resource_label="assertion",
    )
    objective_addresses, objective_diagnostics = _resolve_named_refs(
        ref_names=list(predicate_source.objectives),
        available_names=set(scenario.objectives),
        address_builder=_objective_address,
        owner_address=predicate_address,
        domain="orchestration",
        code_prefix="orchestration.objective-ref",
        resource_label="objective",
    )
    diagnostics.extend(
        [
            *workflow_diagnostics,
            *objective_diagnostics,
        ]
    )
    step_state_predicates = tuple(
        WorkflowStepStatePredicateRuntime(
            step_name=ref.step,
            outcomes=tuple(WorkflowStepOutcome(outcome.value) for outcome in ref.outcomes),
            min_attempts=ref.min_attempts,
        )
        for ref in predicate_source.steps
        if isinstance(ref.step, str) and ref.step
    )
    predicate_addresses = _dedupe(
        [
            *assertion_addresses,
            *objective_addresses,
        ]
    )
    return _WorkflowPredicateCompilation(
        predicate=WorkflowPredicateRuntime(
            assertion_addresses=assertion_addresses,
            objective_addresses=tuple(objective_addresses),
            step_state_predicates=step_state_predicates,
        ),
        assertion_addresses=assertion_addresses,
        predicate_addresses=predicate_addresses,
        objective_addresses=tuple(objective_addresses),
        step_state_predicates=step_state_predicates,
    )


def _workflow_step_edges_and_features(step: WorkflowStep) -> tuple[tuple[str, ...], tuple[WorkflowFeature, ...]]:
    edge_values = {
        WorkflowStepType.OBJECTIVE: (step.on_success, step.on_failure),
        WorkflowStepType.DECISION: (step.then_step, step.else_step),
        WorkflowStepType.SWITCH: (*[case.next_step for case in step.cases], step.default_step),
        WorkflowStepType.PARALLEL: (*step.branches, step.on_failure),
        WorkflowStepType.JOIN: (step.next,),
        WorkflowStepType.RETRY: (step.on_success, step.on_exhausted),
        WorkflowStepType.CALL: (step.on_success, step.on_failure),
    }.get(step.type, ())
    feature = _WORKFLOW_STEP_TYPE_FEATURES.get(step.type)
    return _dedupe([edge for edge in edge_values if edge]), (() if feature is None else (feature,))


def _workflow_cross_cutting_features(step: WorkflowStep, workflow: Workflow) -> tuple[WorkflowFeature, ...]:
    features: list[WorkflowFeature] = []
    if step.on_failure or step.on_exhausted:
        features.append(WorkflowFeature.FAILURE_TRANSITIONS)
    if workflow.timeout is not None:
        features.append(WorkflowFeature.TIMEOUTS)
    if workflow.compensation is not None and workflow.compensation.mode.value != "disabled":
        features.append(WorkflowFeature.COMPENSATION)
    return tuple(features)


def _workflow_step_primary_addresses(
    scenario: InstantiatedScenario,
    *,
    workflow_address: str,
    step: WorkflowStep,
    state: _WorkflowCompilationState,
    diagnostics: list[Diagnostic],
) -> tuple[str, str]:
    objective_address = ""
    called_workflow_address = ""
    if step.objective:
        objective_addresses, objective_diagnostics = _resolve_named_refs(
            ref_names=[step.objective],
            available_names=set(scenario.objectives),
            address_builder=_objective_address,
            owner_address=workflow_address,
            domain="orchestration",
            code_prefix="orchestration.objective-ref",
            resource_label="objective",
        )
        diagnostics.extend(objective_diagnostics)
        state.referenced_objectives.extend(objective_addresses)
        objective_address = objective_addresses[0] if objective_addresses else ""
    elif step.workflow:
        workflow_addresses, workflow_diagnostics = _resolve_named_refs(
            ref_names=[step.workflow],
            available_names=set(scenario.workflows),
            address_builder=_workflow_address,
            owner_address=workflow_address,
            domain="orchestration",
            code_prefix="orchestration.workflow-ref",
            resource_label="workflow",
        )
        diagnostics.extend(workflow_diagnostics)
        called_workflow_address = workflow_addresses[0] if workflow_addresses else ""
    return objective_address, called_workflow_address


def _workflow_step_compensation_address(
    scenario: InstantiatedScenario,
    *,
    workflow_address: str,
    step_name: str,
    step: WorkflowStep,
    state: _WorkflowCompilationState,
    diagnostics: list[Diagnostic],
) -> str:
    if not step.compensate_with:
        return ""
    workflow_addresses, workflow_diagnostics = _resolve_named_refs(
        ref_names=[step.compensate_with],
        available_names=set(scenario.workflows),
        address_builder=_workflow_address,
        owner_address=workflow_address,
        domain="orchestration",
        code_prefix="orchestration.workflow-ref",
        resource_label="workflow",
    )
    diagnostics.extend(workflow_diagnostics)
    compensation_workflow_address = workflow_addresses[0] if workflow_addresses else ""
    if compensation_workflow_address:
        state.compensation_targets[step_name] = compensation_workflow_address
        state.required_features.append(WorkflowFeature.COMPENSATION)
    return compensation_workflow_address


def _apply_workflow_predicate_compilation(
    state: _WorkflowCompilationState,
    step_name: str,
    compilation: _WorkflowPredicateCompilation,
) -> None:
    state.referenced_objectives.extend(compilation.objective_addresses)
    state.step_assertion_addresses[step_name] = compilation.assertion_addresses
    state.step_predicate_addresses[step_name] = compilation.predicate_addresses
    _apply_step_state_predicate_features(state, compilation.step_state_predicates)


def _apply_step_state_predicate_features(
    state: _WorkflowCompilationState,
    step_state_predicates: tuple[WorkflowStepStatePredicateRuntime, ...],
) -> None:
    if step_state_predicates:
        state.required_state_predicate_features.append(WorkflowStatePredicateFeature.OUTCOME_MATCHING)
    if any(state_predicate.min_attempts is not None for state_predicate in step_state_predicates):
        state.required_state_predicate_features.append(WorkflowStatePredicateFeature.ATTEMPT_COUNTS)


def _compile_switch_cases(
    scenario: InstantiatedScenario,
    *,
    workflow_address: str,
    step_name: str,
    step: WorkflowStep,
    state: _WorkflowCompilationState,
    assertions: dict[str, AssertionRuntime],
    diagnostics: list[Diagnostic],
) -> tuple[WorkflowSwitchCaseRuntime, ...]:
    compiled_cases: list[WorkflowSwitchCaseRuntime] = []
    switch_assertion_addresses: list[str] = []
    switch_predicate_addresses: list[str] = []
    for case_index, case in enumerate(step.cases):
        compilation = _compile_workflow_predicate(
            case.when,
            scenario=scenario,
            assertions=assertions,
            predicate_address=_address(workflow_address, "step", step_name, "case", str(case_index)),
            diagnostics=diagnostics,
        )
        state.referenced_objectives.extend(compilation.objective_addresses)
        switch_assertion_addresses.extend(compilation.assertion_addresses)
        switch_predicate_addresses.extend(compilation.predicate_addresses)
        _apply_step_state_predicate_features(state, compilation.step_state_predicates)
        compiled_cases.append(
            WorkflowSwitchCaseRuntime(case_index=case_index, predicate=compilation.predicate, next_step=case.next_step)
        )
    if switch_assertion_addresses:
        state.step_assertion_addresses[step_name] = _dedupe(switch_assertion_addresses)
    if switch_predicate_addresses:
        state.step_predicate_addresses[step_name] = _dedupe(switch_predicate_addresses)
    return tuple(compiled_cases)


def _compile_workflow_step_predicates(
    scenario: InstantiatedScenario,
    *,
    workflow_address: str,
    step_name: str,
    step: WorkflowStep,
    state: _WorkflowCompilationState,
    assertions: dict[str, AssertionRuntime],
    diagnostics: list[Diagnostic],
) -> tuple[WorkflowPredicateRuntime | None, tuple[WorkflowSwitchCaseRuntime, ...]]:
    if step.when is not None:
        compilation = _compile_workflow_predicate(
            step.when,
            scenario=scenario,
            assertions=assertions,
            predicate_address=_address(workflow_address, "step", step_name),
            diagnostics=diagnostics,
        )
        _apply_workflow_predicate_compilation(state, step_name, compilation)
        return compilation.predicate, ()
    if step.type != WorkflowStepType.SWITCH:
        return None, ()
    return None, _compile_switch_cases(
        scenario,
        workflow_address=workflow_address,
        step_name=step_name,
        step=step,
        state=state,
        assertions=assertions,
        diagnostics=diagnostics,
    )


def _compile_workflow_step(context: _WorkflowStepContext, *, step_name: str, step: WorkflowStep) -> None:
    state = context.state
    edges, type_features = _workflow_step_edges_and_features(step)
    state.control_edges[step_name] = edges
    state.required_features.extend(type_features)
    mode_feature = _WORKFLOW_STEP_MODE_FEATURES.get(step.execution_mode)
    if mode_feature is not None:
        state.required_features.append(mode_feature)
    objective_address, called_workflow_address = _workflow_step_primary_addresses(
        context.scenario,
        workflow_address=context.workflow_address,
        step=step,
        state=state,
        diagnostics=context.diagnostics,
    )
    compensation_workflow_address = _workflow_step_compensation_address(
        context.scenario,
        workflow_address=context.workflow_address,
        step_name=step_name,
        step=step,
        state=state,
        diagnostics=context.diagnostics,
    )
    predicate, switch_cases = _compile_workflow_step_predicates(
        context.scenario,
        workflow_address=context.workflow_address,
        step_name=step_name,
        step=step,
        state=state,
        assertions=context.assertions,
        diagnostics=context.diagnostics,
    )
    state.required_features.extend(_workflow_cross_cutting_features(step, context.workflow))
    state.control_steps[step_name] = WorkflowStepRuntime(
        name=step_name,
        step_type=step.type.value,
        execution_mode=step.execution_mode.value,
        objective_address=objective_address,
        procedure_ref=step.procedure_ref,
        scaffold_refs=tuple(step.scaffold_refs),
        allowed_action_families=tuple(step.allowed_action_families),
        tool_affordance_refs=tuple(step.tool_affordance_refs),
        capability_refs=tuple(step.capability_refs),
        fact_binding_refs=tuple(step.fact_binding_refs),
        predicate=predicate,
        next_step=step.next,
        on_success=step.on_success,
        on_failure=step.on_failure,
        on_exhausted=step.on_exhausted,
        then_step=step.then_step,
        else_step=step.else_step,
        switch_cases=switch_cases,
        default_step=step.default_step,
        branches=tuple(step.branches),
        join_step=step.join,
        owning_parallel_step=state.join_owners.get(step_name, ""),
        called_workflow_address=called_workflow_address,
        compensation_workflow_address=compensation_workflow_address,
        max_attempts=step.max_attempts,
        state_contract=workflow_step_semantic_contract(step.type.value),
    )
