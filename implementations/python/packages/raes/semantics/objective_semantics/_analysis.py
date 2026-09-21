"""Per-objective reference resolution and diagnostic helpers for objective semantics."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Collection, Mapping

from ..assessment import AssessmentResourceKind
from ..objectives import (
    ObjectiveWindowAnalysis,
    analyze_objective_window,
)
from ._constants import (
    OBJECTIVE_ACTION_CONSTRAINT_DEPENDENCY_ROLES,
    OBJECTIVE_ASSIGNMENT_DEPENDENCY_ROLES,
    OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES,
    OBJECTIVE_OWNER_DEPENDENCY_ROLES,
    OBJECTIVE_SUCCESS_DEPENDENCY_ROLES,
    OBJECTIVE_TARGET_DEPENDENCY_ROLES,
    OBJECTIVE_WINDOW_DEPENDENCY_ROLES,
)
from ._types import (
    AssessmentResourceCatalog,
    ObjectiveIssue,
    ObjectiveReference,
    ObjectiveReferenceKind,
    WindowResourceCatalog,
)


def _ordered_unique(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _never_unresolved(_value: object) -> bool:
    return False


def _has_cycle(graph: Mapping[str, list[str]]) -> bool:
    """Return True if the directed ``graph`` (node -> deps) contains a cycle."""

    in_degree: dict[str, int] = defaultdict(int)
    for node in graph:
        in_degree.setdefault(node, 0)
    for deps in graph.values():
        for dep in deps:
            in_degree[dep] += 1
    queue = deque(node for node, degree in in_degree.items() if degree == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for dep in graph.get(node, []):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)
    return visited != len(in_degree)


_SUCCESS_REFERENCE_SECTIONS: tuple[tuple[str, AssessmentResourceKind, str], ...] = (
    ("assertions", AssessmentResourceKind.ASSERTION, "objective.success-assertion-undeclared"),
)


def _check_agent_actions(
    objective_name: str,
    objective: object,
    agent_name: str,
    agent: object,
    unresolved: Callable[[object], bool],
) -> list[ObjectiveIssue]:
    allowed = set(getattr(agent, "actions", []) or [])
    return [
        ObjectiveIssue(
            code="objective.action-not-declared",
            objective_name=objective_name,
            ref=action,
            actor_name=agent_name,
        )
        for action in getattr(objective, "actions", []) or []
        if not unresolved(action) and action not in allowed
    ]


def _check_agent(
    objective_name: str,
    objective: object,
    agents_by_name: Mapping[str, object],
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue]]:
    name = getattr(objective, "assigned_participant", "") or ""
    if not name or unresolved(name):
        return [], []
    if name not in agents_by_name:
        return [], [ObjectiveIssue(code="objective.assignment-undeclared", objective_name=objective_name, ref=name)]
    ref = ObjectiveReference(
        raw=name,
        canonical_name=name,
        reference_kind=ObjectiveReferenceKind.ASSIGNMENT,
        source_name=objective_name,
        dependency_roles=OBJECTIVE_ASSIGNMENT_DEPENDENCY_ROLES,
    )
    return [ref], _check_agent_actions(objective_name, objective, name, agents_by_name[name], unresolved)


def _check_entity(
    objective_name: str,
    objective: object,
    entity_name_set: set[str],
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue]]:
    name = getattr(objective, "owner", "") or ""
    if not name or unresolved(name):
        return [], []
    if name not in entity_name_set:
        return [], [ObjectiveIssue(code="objective.owner-undeclared", objective_name=objective_name, ref=name)]
    ref = ObjectiveReference(
        raw=name,
        canonical_name=f"entities.{name}",
        reference_kind=ObjectiveReferenceKind.OWNER,
        source_name=objective_name,
        dependency_roles=OBJECTIVE_OWNER_DEPENDENCY_ROLES,
    )
    return [ref], []


def _analyze_objective_relations(
    objective_name: str,
    objective: object,
    agents_by_name: Mapping[str, object],
    entity_name_set: set[str],
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue]]:
    agent_refs, agent_issues = _check_agent(objective_name, objective, agents_by_name, unresolved)
    entity_refs, entity_issues = _check_entity(objective_name, objective, entity_name_set, unresolved)
    return [*agent_refs, *entity_refs], [*agent_issues, *entity_issues]


def _analyze_action_constraints(
    objective_name: str,
    objective: object,
    action_contracts: Mapping[str, object],
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue]]:
    references: list[ObjectiveReference] = []
    issues: list[ObjectiveIssue] = []
    for action in dict.fromkeys(getattr(objective, "actions", []) or []):
        if unresolved(action):
            continue
        if action not in action_contracts:
            issues.append(
                ObjectiveIssue(code="objective.action-contract-undeclared", objective_name=objective_name, ref=action)
            )
        else:
            references.append(
                ObjectiveReference(
                    raw=action,
                    canonical_name=f"action_contracts.{action}",
                    reference_kind=ObjectiveReferenceKind.ACTION_CONSTRAINT,
                    source_name=objective_name,
                    dependency_roles=OBJECTIVE_ACTION_CONSTRAINT_DEPENDENCY_ROLES,
                )
            )
    return references, issues


def _analyze_targets(
    objective_name: str,
    objective: object,
    targetable_name_index: Mapping[str, Collection[str]],
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue]]:
    refs: list[ObjectiveReference] = []
    issues: list[ObjectiveIssue] = []
    for target in getattr(objective, "targets", []) or []:
        if unresolved(target):
            continue
        candidates = targetable_name_index.get(target)
        if not candidates:
            issues.append(
                ObjectiveIssue(
                    code="objective.target-unresolvable",
                    objective_name=objective_name,
                    ref=target,
                )
            )
            continue
        if len(candidates) > 1:
            issues.append(
                ObjectiveIssue(
                    code="objective.target-ambiguous",
                    objective_name=objective_name,
                    ref=target,
                    candidates=tuple(sorted(candidates)),
                )
            )
            continue
        (canonical_target,) = tuple(candidates)
        refs.append(
            ObjectiveReference(
                raw=target,
                canonical_name=canonical_target,
                reference_kind=ObjectiveReferenceKind.TARGET,
                source_name=objective_name,
                dependency_roles=OBJECTIVE_TARGET_DEPENDENCY_ROLES,
            )
        )
    return refs, issues


def _analyze_success(
    objective_name: str,
    objective: object,
    assessment_resources: AssessmentResourceCatalog,
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue], list[str]]:
    """Resolve backend-neutral ``success.assertions``.

    Resolved names are kind-qualified before they enter the derived
    ordering/refresh tuples, preserving the kind-qualifier seam even though
    ``conditions`` is the only success reference kind today.
    """

    refs: list[ObjectiveReference] = []
    issues: list[ObjectiveIssue] = []
    resolved: list[str] = []
    success = getattr(objective, "success", None)
    sections = ((assessment_resources.assertions, _SUCCESS_REFERENCE_SECTIONS[0]),)
    for section, (attr, kind, code) in sections:
        for ref_name in getattr(success, attr, []) or []:
            if unresolved(ref_name):
                continue
            if ref_name not in section:
                issues.append(ObjectiveIssue(code=code, objective_name=objective_name, ref=ref_name))
                continue
            qualified_name = f"{kind.value}.{ref_name}"
            refs.append(
                ObjectiveReference(
                    raw=ref_name,
                    canonical_name=qualified_name,
                    reference_kind=ObjectiveReferenceKind.SUCCESS,
                    source_name=objective_name,
                    dependency_roles=OBJECTIVE_SUCCESS_DEPENDENCY_ROLES,
                    success_resource_kind=kind,
                )
            )
            resolved.append(qualified_name)
    return refs, issues, resolved


def _window_reference_lists(
    window: object,
    unresolved: Callable[[object], bool],
) -> dict[str, list[object]]:
    """Filter each window keyspace's authored refs down to the resolved ones."""

    def kept(attribute: str) -> list[object]:
        return [ref for ref in getattr(window, attribute, []) or [] if not unresolved(ref)]

    return {
        "story_refs": kept("stories"),
        "script_refs": kept("scripts"),
        "event_refs": kept("events"),
        "workflow_refs": kept("workflows"),
        "step_refs": kept("steps"),
    }


def _analyze_window(
    objective_name: str,
    objective: object,
    window_resources: WindowResourceCatalog,
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue], ObjectiveWindowAnalysis | None, list[str]]:
    """Delegate window resolution to the SEM-202 helper and re-tag the result."""

    window = getattr(objective, "window", None)
    if window is None:
        return [], [], None, []

    analysis = analyze_objective_window(
        **_window_reference_lists(window, unresolved),
        stories_by_name=window_resources.stories,
        scripts_by_name=window_resources.scripts,
        events_by_name=window_resources.events,
        workflows_by_name=window_resources.workflows,
    )
    refs = [
        # The SEM-207 role constant is the single authority for objective-side
        # window roles; the lower-level ``ObjectiveWindowReference.dependency_roles``
        # is the SEM-202 helper's own metadata and must not double as the
        # planner-facing role decision.
        ObjectiveReference(
            raw=window_ref.raw,
            canonical_name=window_ref.canonical_name,
            reference_kind=ObjectiveReferenceKind.WINDOW,
            source_name=objective_name,
            dependency_roles=OBJECTIVE_WINDOW_DEPENDENCY_ROLES,
            window_reference_kind=window_ref.reference_kind,
            workflow_name=window_ref.workflow_name,
            step_name=window_ref.step_name,
            namespace_path=window_ref.namespace_path,
        )
        for window_ref in analysis.references
    ]
    issues = [
        ObjectiveIssue(
            code=f"objective.window.{window_issue.code}",
            objective_name=objective_name,
            ref=window_issue.ref,
            workflow_name=window_issue.workflow_name,
            step_name=window_issue.step_name,
        )
        for window_issue in analysis.issues
    ]
    # Each window keyspace gets its kind prefix so it cannot collide with
    # success-side or depends_on-side names in ``refresh_names``.
    refresh = [
        *(f"story.{name}" for name in analysis.story_names),
        *(f"script.{name}" for name in analysis.script_names),
        *(f"event.{name}" for name in analysis.event_names),
        *(f"workflow.{name}" for name in analysis.workflow_names),
        *(f"workflow.{name}" for name in analysis.refresh_workflow_names),
    ]
    return refs, issues, analysis, refresh


def _analyze_dependencies(
    objective_name: str,
    objective: object,
    objectives_by_name: Mapping[str, object],
    unresolved: Callable[[object], bool],
) -> tuple[list[ObjectiveReference], list[ObjectiveIssue], list[str]]:
    refs: list[ObjectiveReference] = []
    issues: list[ObjectiveIssue] = []
    resolved: list[str] = []
    for dep_name in getattr(objective, "depends_on", []) or []:
        if unresolved(dep_name):
            continue
        if dep_name not in objectives_by_name:
            issues.append(
                ObjectiveIssue(
                    code="objective.dependency-undeclared",
                    objective_name=objective_name,
                    ref=dep_name,
                )
            )
            continue
        qualified_dep = f"objective.{dep_name}"
        refs.append(
            ObjectiveReference(
                raw=dep_name,
                canonical_name=qualified_dep,
                reference_kind=ObjectiveReferenceKind.DEPENDENCY,
                source_name=objective_name,
                dependency_roles=OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES,
            )
        )
        resolved.append(qualified_dep)
    return refs, issues, resolved


def _objective_dependency_graph(
    objectives_by_name: Mapping[str, object],
    unresolved: Callable[[object], bool],
) -> dict[str, list[str]]:
    return {
        name: [
            dep
            for dep in getattr(objective, "depends_on", []) or []
            if not unresolved(dep) and dep in objectives_by_name
        ]
        for name, objective in objectives_by_name.items()
    }
