"""Pure declarative-objective semantic helpers (SEM-207).

:func:`analyze_objective_semantics` is the single name-level source of truth
for the SDL declarative-objective construct — actor binding, target resolution,
success interpretation over backend-neutral assertions, the
optional window (delegated to :func:`raes.semantics.objectives.analyze_objective_window`),
and the acyclic ``depends_on`` ordering relation. It returns normalized
references with their dependency-role tags, the per-objective ordering/refresh
dependency names, and a fail-closed issue list that ``raes.validator``
renders as authoring errors. ``raes_processor.compiler`` reuses the
ordering/refresh role decision (:func:`partition_objective_dependencies`) when
it maps a compiled ``evaluation.objective.*`` resource onto its dependency
tuples, and the planner then walks those edges generically.

Role allocation: success and ``depends_on`` edges order *and* refresh; window
edges only refresh; actor and target references are normalized for fail-closed
validation but carry an empty role tuple today (the compiler does not propagate
through them). Per ADR-015 this helper lives with the SDL package and has no
processor-runtime dependencies; per ADR-016 it is part of the realized artifact
set for SEM-207. Bound-to-node binding diagnostics remain a compilation-phase
concern (``evaluation.condition-ref`` is emitted on resolved addresses, not by
this name-level analyzer).

The ``partition_objective_dependencies`` role decision reads the
``OBJECTIVE_*_DEPENDENCY_ROLES`` constants from this facade module, so the
per-category role allocation stays a single monkeypatch-visible authority even
though the constants are defined in ``._constants``.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping

from ..objectives import ObjectiveDependencyRole, ObjectiveWindowAnalysis
from ._analysis import (
    _analyze_action_constraints,
    _analyze_dependencies,
    _analyze_objective_relations,
    _analyze_success,
    _analyze_targets,
    _analyze_window,
    _has_cycle,
    _never_unresolved,
    _objective_dependency_graph,
    _ordered_unique,
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
    ObjectiveRelationCatalog,
    ObjectiveResourceDependencies,
    ObjectiveSemanticAnalysis,
    WindowResourceCatalog,
)


def partition_objective_dependencies(
    *,
    success_refs: Collection[str],
    dependency_refs: Collection[str],
    window_refresh_refs: Collection[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split an objective's upstream references into (ordering, refresh) tuples.

    Each category is gated by its own ``OBJECTIVE_*_DEPENDENCY_ROLES`` constant
    so a future role change to one category (say, ``depends_on`` becoming
    refresh-only) lands in exactly one place. Works on names (validator side)
    or compiled addresses (compiler side); the result is order-preserving and
    de-duplicated within each role.
    """

    success = list(success_refs)
    deps = list(dependency_refs)
    window = list(window_refresh_refs)
    ordering: list[str] = []
    refresh: list[str] = []
    for category, roles in (
        (success, OBJECTIVE_SUCCESS_DEPENDENCY_ROLES),
        (deps, OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES),
        (window, OBJECTIVE_WINDOW_DEPENDENCY_ROLES),
    ):
        if ObjectiveDependencyRole.ORDERING in roles:
            ordering.extend(category)
        if ObjectiveDependencyRole.REFRESH in roles:
            refresh.extend(category)
    return _ordered_unique(ordering), _ordered_unique(refresh)


def analyze_objective_semantics(
    *,
    objectives_by_name: Mapping[str, object],
    relation_resources: ObjectiveRelationCatalog,
    assessment_resources: AssessmentResourceCatalog,
    window_resources: WindowResourceCatalog,
    targetable_name_index: Mapping[str, Collection[str]],
    is_unresolved: Callable[[object], bool] | None = None,
) -> ObjectiveSemanticAnalysis:
    """Resolve the objective reference graph and derive its shared semantics.

    Inputs are the name-keyed objective map, bundled relation declarations,
    assessment-pipeline and timeline resource catalogs, and the
    targetable named-reference index; ``is_unresolved`` (default: never) lets a
    caller skip references that are still ``${var}`` placeholders. Returns the
    normalized references, the per-objective ordering/refresh dependency names,
    the per-objective window analyses, and any consistency issues — per
    objective in the order actor, action, target, success, window, dependency,
    then a single global ``objective.dependency-cycle`` issue when the
    ``depends_on`` graph cycles.
    """

    unresolved = is_unresolved or _never_unresolved
    entity_name_set = set(relation_resources.entity_names)
    references: list[ObjectiveReference] = []
    issues: list[ObjectiveIssue] = []
    dependencies: list[ObjectiveResourceDependencies] = []
    window_analyses: dict[str, ObjectiveWindowAnalysis] = {}

    for objective_name, objective in objectives_by_name.items():
        relation_refs, relation_issues = _analyze_objective_relations(
            objective_name, objective, relation_resources.agents, entity_name_set, unresolved
        )
        action_refs, action_issues = _analyze_action_constraints(
            objective_name, objective, relation_resources.action_contracts, unresolved
        )
        target_refs, target_issues = _analyze_targets(objective_name, objective, targetable_name_index, unresolved)
        success_refs, success_issues, resolved_success = _analyze_success(
            objective_name, objective, assessment_resources, unresolved
        )
        window_refs, window_issues, window_analysis, window_refresh = _analyze_window(
            objective_name, objective, window_resources, unresolved
        )
        dep_refs, dep_issues, resolved_dependencies = _analyze_dependencies(
            objective_name, objective, objectives_by_name, unresolved
        )

        references.extend(relation_refs)
        references.extend(action_refs)
        references.extend(target_refs)
        references.extend(success_refs)
        references.extend(window_refs)
        references.extend(dep_refs)
        issues.extend(relation_issues)
        issues.extend(action_issues)
        issues.extend(target_issues)
        issues.extend(success_issues)
        issues.extend(window_issues)
        issues.extend(dep_issues)
        if window_analysis is not None:
            window_analyses[objective_name] = window_analysis

        ordering_names, refresh_names = partition_objective_dependencies(
            success_refs=_ordered_unique(resolved_success),
            dependency_refs=_ordered_unique(resolved_dependencies),
            window_refresh_refs=window_refresh,
        )
        dependencies.append(
            ObjectiveResourceDependencies(
                name=objective_name,
                ordering_names=ordering_names,
                refresh_names=refresh_names,
            )
        )

    dependency_graph = _objective_dependency_graph(objectives_by_name, unresolved)
    if dependency_graph and _has_cycle(dependency_graph):
        issues.append(ObjectiveIssue(code="objective.dependency-cycle", objective_name=""))

    return ObjectiveSemanticAnalysis(
        references=tuple(references),
        issues=tuple(issues),
        dependencies=tuple(dependencies),
        window_analyses=dict(window_analyses),
    )
