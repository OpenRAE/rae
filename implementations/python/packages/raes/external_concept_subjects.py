"""SDL-owned exact subject adapter for portable external concept bindings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from raes_contracts.contracts.external_concept_bindings import (
    ExternalConceptLifecyclePhase,
    ExternalConceptSubjectModel,
)

from ._base import contains_variable_token
from ._declarations import build_declaration_index
from .canonical import canonical_instantiated_sdl_digest, canonical_sdl_digest
from .scenario import ExpandedScenario, InstantiatedScenario, Scenario, ScenarioContent


@dataclass(frozen=True, slots=True)
class _SubjectRule:
    model_type: type[ScenarioContent]
    owning_contract_id: str
    lifecycle_phase: ExternalConceptLifecyclePhase
    digest: Callable[[ScenarioContent], str]


def _authoring_digest(scenario: ScenarioContent) -> str:
    if not isinstance(scenario, (Scenario, ExpandedScenario)) or isinstance(scenario, InstantiatedScenario):
        raise TypeError("authoring subject rule requires a normalized or expanded scenario")
    return canonical_sdl_digest(scenario).value


def _instantiated_digest(scenario: ScenarioContent) -> str:
    if not isinstance(scenario, InstantiatedScenario):
        raise TypeError("instantiated subject rule requires an instantiated scenario")
    return canonical_instantiated_sdl_digest(scenario).value


_SUBJECT_RULES = (
    _SubjectRule(
        model_type=InstantiatedScenario,
        owning_contract_id="instantiated-scenario-v1",
        lifecycle_phase=ExternalConceptLifecyclePhase.INSTANTIATED,
        digest=_instantiated_digest,
    ),
    _SubjectRule(
        model_type=ExpandedScenario,
        owning_contract_id="sdl-authoring-input-v1",
        lifecycle_phase=ExternalConceptLifecyclePhase.EXPANDED_AUTHORING,
        digest=_authoring_digest,
    ),
    _SubjectRule(
        model_type=Scenario,
        owning_contract_id="sdl-authoring-input-v1",
        lifecycle_phase=ExternalConceptLifecyclePhase.NORMALIZED_AUTHORING,
        digest=_authoring_digest,
    ),
)


def external_concept_subjects(scenario: ScenarioContent) -> tuple[ExternalConceptSubjectModel, ...]:
    """Project canonical, collision-checked SDL declarations into resolver inputs."""

    rule = next((candidate for candidate in _SUBJECT_RULES if isinstance(scenario, candidate.model_type)), None)
    if rule is None:
        raise TypeError("unsupported SDL lifecycle phase for external concept subject resolution")
    artifact_digest = rule.digest(scenario)
    index = build_declaration_index(scenario)
    declarations = tuple(
        ExternalConceptSubjectModel(
            subject_kind=declaration.kind,
            owning_contract_id=rule.owning_contract_id,
            lifecycle_phase=rule.lifecycle_phase,
            canonical_ref=declaration.address,
            artifact_digest=artifact_digest,
        )
        for declaration in index.declarations
    )
    # Route identities are assertion subjects only, not new native reference
    # aliases, objective targets or capability-bearing declarations. Preserve
    # candidate multiplicity so admission rejects any coordinate collision.
    routes = tuple(
        ExternalConceptSubjectModel(
            subject_kind="runtime-application-route",
            owning_contract_id=rule.owning_contract_id,
            lifecycle_phase=rule.lifecycle_phase,
            canonical_ref=f"nodes.{name}.runtime.applications.{application.application_id}.routes.{route.route_id}",
            artifact_digest=artifact_digest,
        )
        for name, node in scenario.nodes.items()
        if node.runtime is not None
        for application in node.runtime.applications
        for route in application.routes
        if not contains_variable_token(application.application_id) and not contains_variable_token(route.route_id)
    )
    return (*declarations, *routes)


__all__ = ["external_concept_subjects"]
