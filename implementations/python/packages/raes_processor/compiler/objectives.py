"""Objective compilation, including objective-window resolution."""

from dataclasses import dataclass

from raes.objectives import Objective
from raes.scenario import InstantiatedScenario
from raes.semantics.objective_semantics import (
    OBJECTIVE_WINDOW_DEPENDENCY_ROLES,
    partition_objective_dependencies,
)
from raes.semantics.objectives import ObjectiveWindowIssue, analyze_objective_window

from ..models import (
    AssertionRuntime,
    Diagnostic,
    ObjectiveRuntime,
    ObjectiveWindowReferenceRuntime,
)
from .addresses import (
    _assertion_address,
    _event_address,
    _objective_address,
    _participant_behavior_address,
    _script_address,
    _story_address,
    _workflow_address,
)
from .ref_resolution import _evaluation_contracts, _resolve_named_refs
from .support import _dedupe, _dump


@dataclass(frozen=True)
class _ObjectiveWindowCompilation:
    story_addresses: tuple[str, ...] = ()
    script_addresses: tuple[str, ...] = ()
    event_addresses: tuple[str, ...] = ()
    workflow_addresses: tuple[str, ...] = ()
    step_refs: tuple[str, ...] = ()
    step_workflow_addresses: tuple[str, ...] = ()
    references: tuple[ObjectiveWindowReferenceRuntime, ...] = ()


_OBJECTIVE_WINDOW_ISSUE_DIAGNOSTICS = {
    "story-unbound": ("evaluation.story-ref-unbound", "Reference '{ref}' does not resolve to a defined story."),
    "script-unbound": ("evaluation.script-ref-unbound", "Reference '{ref}' does not resolve to a defined script."),
    "script-outside-window-stories": (
        "evaluation.script-ref-outside-window-stories",
        "Reference '{ref}' is not included by the objective window's referenced stories.",
    ),
    "event-unbound": ("evaluation.event-ref-unbound", "Reference '{ref}' does not resolve to a defined event."),
    "event-outside-window-scripts": (
        "evaluation.event-ref-outside-window-scripts",
        "Reference '{ref}' is not included by the objective window's referenced scripts.",
    ),
    "workflow-unbound": (
        "evaluation.workflow-ref-unbound",
        "Reference '{ref}' does not resolve to a defined workflow.",
    ),
    "step-requires-workflow-window": (
        "evaluation.workflow-step-ref-window-missing-workflow",
        "Workflow step references require at least one referenced workflow.",
    ),
    "step-invalid-format": (
        "evaluation.workflow-step-ref-invalid-format",
        "Reference '{ref}' must use '<workflow>.<step>' syntax.",
    ),
    "step-workflow-unbound": (
        "evaluation.workflow-step-ref-workflow-unbound",
        "Reference '{ref}' does not resolve to a defined workflow.",
    ),
    "step-workflow-outside-window": (
        "evaluation.workflow-step-ref-workflow-outside-window",
        "Reference '{ref}' is not part of the objective window's referenced workflows.",
    ),
    "step-unbound": (
        "evaluation.workflow-step-ref-step-unbound",
        "Reference '{ref}' does not resolve to a defined workflow step.",
    ),
}


def _objective_success_addresses(
    assertions: dict[str, AssertionRuntime],
    objective: Objective,
    objective_address: str,
    diagnostics: list[Diagnostic],
) -> list[str]:
    assertion_addresses, assertion_diagnostics = _resolve_named_refs(
        ref_names=list(objective.success.assertions),
        available_names={assertion.name for assertion in assertions.values()},
        address_builder=_assertion_address,
        owner_address=objective_address,
        domain="evaluation",
        code_prefix="evaluation.assertion-ref",
        resource_label="assertion",
    )
    diagnostics.extend(assertion_diagnostics)
    return list(assertion_addresses)


def _objective_dependency_addresses(
    scenario: InstantiatedScenario,
    objective: Objective,
    objective_address: str,
    diagnostics: list[Diagnostic],
) -> tuple[str, ...]:
    objective_dependencies, objective_dependency_diagnostics = _resolve_named_refs(
        ref_names=list(objective.depends_on),
        available_names=set(scenario.objectives),
        address_builder=_objective_address,
        owner_address=objective_address,
        domain="evaluation",
        code_prefix="evaluation.objective-ref",
        resource_label="objective",
    )
    diagnostics.extend(objective_dependency_diagnostics)
    return objective_dependencies


def _objective_window_issue_diagnostic(issue: ObjectiveWindowIssue, objective_address: str) -> Diagnostic | None:
    spec = _OBJECTIVE_WINDOW_ISSUE_DIAGNOSTICS.get(issue.code)
    if spec is None:
        return None
    code, message_template = spec
    return Diagnostic(
        code=code,
        domain="evaluation",
        address=objective_address,
        message=message_template.format(ref=issue.ref),
    )


def _compile_objective_window(
    scenario: InstantiatedScenario,
    objective: Objective,
    objective_address: str,
    diagnostics: list[Diagnostic],
) -> _ObjectiveWindowCompilation:
    if objective.window is None:
        return _ObjectiveWindowCompilation()
    window_analysis = analyze_objective_window(
        story_refs=list(objective.window.stories),
        script_refs=list(objective.window.scripts),
        event_refs=list(objective.window.events),
        workflow_refs=list(objective.window.workflows),
        step_refs=list(objective.window.steps),
        stories_by_name=scenario.stories,
        scripts_by_name=scenario.scripts,
        events_by_name=scenario.events,
        workflows_by_name=scenario.workflows,
    )
    for issue in window_analysis.issues:
        diagnostic = _objective_window_issue_diagnostic(issue, objective_address)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    window_role_values = tuple(role.value for role in OBJECTIVE_WINDOW_DEPENDENCY_ROLES)
    return _ObjectiveWindowCompilation(
        story_addresses=_dedupe([_story_address(name) for name in window_analysis.story_names]),
        script_addresses=_dedupe([_script_address(name) for name in window_analysis.script_names]),
        event_addresses=_dedupe([_event_address(name) for name in window_analysis.event_names]),
        workflow_addresses=_dedupe([_workflow_address(name) for name in window_analysis.workflow_names]),
        step_refs=window_analysis.workflow_step_refs,
        step_workflow_addresses=_dedupe(
            [_workflow_address(workflow_name) for workflow_name in window_analysis.refresh_workflow_names]
        ),
        references=tuple(
            ObjectiveWindowReferenceRuntime(
                raw=ref.raw,
                canonical_name=ref.canonical_name,
                reference_kind=ref.reference_kind.value,
                dependency_roles=window_role_values,
                workflow_name=ref.workflow_name or "",
                step_name=ref.step_name or "",
                namespace_path=ref.namespace_path,
            )
            for ref in window_analysis.references
        ),
    )


def _compile_objectives(
    scenario: InstantiatedScenario,
    assertions: dict[str, AssertionRuntime],
    diagnostics: list[Diagnostic],
) -> dict[str, ObjectiveRuntime]:
    objectives: dict[str, ObjectiveRuntime] = {}
    for name, objective in scenario.objectives.items():
        objective_address = _objective_address(name)
        success_addresses = _objective_success_addresses(
            assertions,
            objective,
            objective_address,
            diagnostics,
        )
        objective_dependencies = _objective_dependency_addresses(scenario, objective, objective_address, diagnostics)
        window = _compile_objective_window(scenario, objective, objective_address, diagnostics)
        ordering_dependencies, refresh_dependencies = partition_objective_dependencies(
            success_refs=success_addresses,
            dependency_refs=objective_dependencies,
            window_refresh_refs=[
                *window.story_addresses,
                *window.script_addresses,
                *window.event_addresses,
                *window.workflow_addresses,
                *window.step_workflow_addresses,
            ],
        )
        result_contract, execution_contract = _evaluation_contracts("objective")
        objectives[objective_address] = ObjectiveRuntime(
            address=objective_address,
            name=name,
            owner_name=objective.owner or "",
            assigned_participant_name=objective.assigned_participant or "",
            assigned_participant_address=(
                _participant_behavior_address(objective.assigned_participant) if objective.assigned_participant else ""
            ),
            success_addresses=tuple(success_addresses),
            objective_dependencies=objective_dependencies,
            window_story_addresses=window.story_addresses,
            window_script_addresses=window.script_addresses,
            window_event_addresses=window.event_addresses,
            window_workflow_addresses=window.workflow_addresses,
            window_step_refs=window.step_refs,
            window_step_workflow_addresses=window.step_workflow_addresses,
            window_references=window.references,
            ordering_dependencies=ordering_dependencies,
            refresh_dependencies=refresh_dependencies,
            spec=_dump(objective),
            result_contract=result_contract,
            execution_contract=execution_contract,
        )
    return objectives
