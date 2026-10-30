"""Authoring diagnostics for objective-semantics issues."""

from .._reference_targetability import ReferencePurpose
from ._core import eligible_element

# Renders an objective-semantics issue (machine-readable code from
# ``raes.semantics.objective_semantics``) into the authoring-error string
# the SDL surface has always used. Keyed by issue code so a new code is a new
# line here rather than a new branch in a growing conditional.
OBJECTIVE_ISSUE_RENDERERS = {
    "objective.assignment-undeclared": (
        lambda i: f"Objective '{i.objective_name}' references undefined agent '{i.ref}'"
    ),
    "objective.owner-undeclared": (lambda i: f"Objective '{i.objective_name}' references undefined entity '{i.ref}'"),
    "objective.action-not-declared": (
        lambda i: f"Objective '{i.objective_name}' action '{i.ref}' is not declared by agent '{i.actor_name}'"
    ),
    "objective.action-contract-undeclared": (
        lambda i: f"Objective '{i.objective_name}' action '{i.ref}' must reference a declared action_contract"
    ),
    "objective.target-unresolvable": (
        lambda i: (
            f"Objective '{i.objective_name}' target '{i.ref}' does not reference any defined "
            f"{eligible_element(ReferencePurpose.OBJECTIVE_SUBJECT)}"
        )
    ),
    "objective.success-assertion-undeclared": (
        lambda i: f"Objective '{i.objective_name}' references undefined assertion '{i.ref}' in success criteria"
    ),
    "objective.window.story-unbound": (
        lambda i: f"Objective '{i.objective_name}' references undefined story '{i.ref}' in window"
    ),
    "objective.window.script-unbound": (
        lambda i: f"Objective '{i.objective_name}' references undefined script '{i.ref}' in window"
    ),
    "objective.window.script-outside-window-stories": (
        lambda i: f"Objective '{i.objective_name}' window script '{i.ref}' is not included by the referenced stories"
    ),
    "objective.window.event-unbound": (
        lambda i: f"Objective '{i.objective_name}' references undefined event '{i.ref}' in window"
    ),
    "objective.window.event-outside-window-scripts": (
        lambda i: f"Objective '{i.objective_name}' window event '{i.ref}' is not included by the referenced scripts"
    ),
    "objective.window.workflow-unbound": (
        lambda i: f"Objective '{i.objective_name}' references undefined workflow '{i.ref}' in window"
    ),
    "objective.window.step-requires-workflow-window": (
        lambda i: f"Objective '{i.objective_name}' window steps require at least one referenced workflow"
    ),
    "objective.window.step-invalid-format": (
        lambda i: f"Objective '{i.objective_name}' window step '{i.ref}' must use '<workflow>.<step>' syntax"
    ),
    "objective.window.step-workflow-unbound": (
        lambda i: (
            f"Objective '{i.objective_name}' window step '{i.ref}' references undefined workflow '{i.workflow_name}'"
        )
    ),
    "objective.window.step-workflow-outside-window": (
        lambda i: f"Objective '{i.objective_name}' window step '{i.ref}' is not part of the referenced workflows"
    ),
    "objective.window.step-unbound": (
        lambda i: f"Objective '{i.objective_name}' window step '{i.ref}' references undefined step '{i.step_name}'"
    ),
    "objective.dependency-undeclared": (
        lambda i: f"Objective '{i.objective_name}' depends on undefined objective '{i.ref}'"
    ),
    "objective.dependency-cycle": lambda _i: "Objective dependency graph contains a cycle",
}

__all__ = ["OBJECTIVE_ISSUE_RENDERERS"]
