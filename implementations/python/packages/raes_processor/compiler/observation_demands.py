"""Compile SDL evidence carriers into the shared observation-demand contract."""

from __future__ import annotations

from raes.observation_scope import (
    canonical_observation_reference,
    observation_reference_scope,
    resolve_observation_scope,
)
from raes.scenario import InstantiatedScenario
from raes_contracts.observation_demand import (
    EffectiveObservationDemand,
    ObservationDemandDocument,
    ObservationDemandMode,
    ObservationDemandRule,
    ObservationLifecycleDecision,
    ObservationPurpose,
    ObservationSelector,
    normalize_observation_demands,
)
from raes_contracts.realization_structure import RealizationClosure, RealizationCollectionProfile

from ..semantics.realization_concerns import registered_realization_concern_descriptors
from .alias_index import _runtime_addressable_ref_index


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _runtime_component_references(
    scenario: InstantiatedScenario,
    index: object,
    references: tuple[str, ...],
    *,
    require_addressable: bool = True,
) -> tuple[str, ...]:
    """Resolve authored component refs into the compiled runtime address domain."""

    addressable = _runtime_addressable_ref_index(scenario)
    resolved = []
    for reference in references:
        declaration_address = canonical_observation_reference(index, reference)
        candidates = {
            *addressable.get(reference, ()),
            *addressable.get(declaration_address, ()),
        }
        if len(candidates) > 1 or require_addressable and not candidates:
            raise ValueError(f"observation component reference '{reference}' is not runtime-addressable")
        if candidates:
            resolved.append(next(iter(candidates)))
    return tuple(dict.fromkeys(resolved))


def _canonical_rule(
    rule: ObservationDemandRule,
    scenario: InstantiatedScenario,
    index: object,
    profiles: tuple[RealizationCollectionProfile, ...],
) -> ObservationDemandRule:
    if rule.authority_ref != "author":
        raise ValueError("SDL observation demand cannot assert a non-author policy authority")
    found, canonical_scope = resolve_observation_scope(scenario, rule.scope, collection_profiles=profiles)
    if not found or canonical_scope is None:
        raise ValueError(f"observation scope does not resolve: {rule.scope}")
    if rule.selector is None:
        return rule.model_copy(update={"scope": canonical_scope})
    found, canonical_selector_scope = resolve_observation_scope(
        scenario,
        rule.selector.semantic_scope,
        collection_profiles=profiles,
    )
    if not found or canonical_selector_scope is None:
        raise ValueError(f"observation scope does not resolve: {rule.selector.semantic_scope}")
    exclusions = []
    for excluded in rule.selector.excluded_scopes:
        found, canonical_exclusion = resolve_observation_scope(scenario, excluded, collection_profiles=profiles)
        if not found or canonical_exclusion is None:
            raise ValueError(f"observation exclusion does not resolve: {excluded}")
        exclusions.append(canonical_exclusion)
    selector = ObservationSelector.model_validate(
        {
            **rule.selector.model_dump(),
            "semantic_scope": canonical_selector_scope,
            "excluded_scopes": tuple(exclusions),
            "component_refs": _runtime_component_references(
                scenario,
                index,
                tuple(rule.selector.component_refs),
            ),
        }
    )
    return rule.model_copy(update={"scope": canonical_scope, "selector": selector})


def _legacy_rules(
    name: str,
    requirement: object,
    scenario: InstantiatedScenario,
    index: object,
    profiles: tuple[RealizationCollectionProfile, ...],
) -> tuple[ObservationDemandRule, ...]:
    authored_source_refs = tuple(getattr(requirement, "source_refs", ()))
    source_refs = _runtime_component_references(
        scenario,
        index,
        authored_source_refs,
        require_addressable=False,
    )
    scope_refs = tuple(
        canonical_observation_reference(index, reference) for reference in getattr(requirement, "scope_refs", ())
    )
    scopes = tuple(
        observation_reference_scope(
            index,
            reference,
            scenario,
            collection_profiles=profiles,
        )
        for reference in (
            scope_refs or tuple(canonical_observation_reference(index, reference) for reference in authored_source_refs)
        )
    ) or ("",)
    channel = _value(getattr(requirement, "channel", None) or "evidence")
    retention = _value(getattr(requirement, "retention", "not_retained"))
    return tuple(
        ObservationDemandRule(
            rule_id=name if len(scopes) == 1 else f"{name}:{position}",
            scope=scope,
            purpose=ObservationPurpose.EXPERIMENTAL,
            mode=ObservationDemandMode.SELECTED,
            selector=ObservationSelector(
                semantic_scope=scope,
                component_refs=source_refs,
                data_kind="stream",
                names=(channel,),
                window_refs=tuple(
                    value
                    for value in (
                        str(getattr(requirement, "window", "")),
                        str(getattr(requirement, "trigger_ref", "")),
                        str(getattr(requirement, "boundary_ref", "")),
                    )
                    if value
                ),
            ),
            collection=ObservationLifecycleDecision.REQUIRE,
            retention=(
                ObservationLifecycleDecision.DISABLE
                if retention == "not_retained"
                else ObservationLifecycleDecision.REQUIRE
            ),
            export=ObservationLifecycleDecision.DISABLE,
            redaction=_value(getattr(requirement, "redaction", "none")),
            integrity=_value(getattr(requirement, "integrity", "none")),
            required=False,
            authority_ref=f"evidence_requirements.{name}",
        )
        for position, scope in enumerate(scopes)
    )


def compile_observation_demands(
    scenario: InstantiatedScenario,
    *,
    declaration_index: object,
) -> tuple[EffectiveObservationDemand, ...]:
    """Normalize explicit demand carriers once during compilation."""

    profiles = _observation_collection_profiles(scenario)
    rules = tuple(
        rule
        for name, requirement in scenario.evidence_requirements.items()
        for rule in (
            (_canonical_rule(requirement.observation_demand, scenario, declaration_index, profiles),)
            if requirement.observation_demand is not None
            else _legacy_rules(name, requirement, scenario, declaration_index, profiles)
        )
    )
    if not rules:
        return ()
    document = ObservationDemandDocument(
        schema_version="observation-demand/v1",
        document_id=f"scenario:{scenario.name}",
        scope_profile="recursive-realization-constraint/v1",
        rules=rules,
    )
    target_scopes = tuple(
        dict.fromkeys(
            scope
            for rule in rules
            for scope in (
                rule.scope,
                *((rule.selector.semantic_scope,) if rule.selector else ()),
            )
        )
    )
    resolution = normalize_observation_demands(document, target_scopes=target_scopes)
    if not resolution.is_valid:
        codes = ", ".join(sorted({diagnostic.code for diagnostic in resolution.diagnostics}))
        raise ValueError(f"observation demand normalization failed: {codes}")
    return resolution.effective


def _observation_collection_profiles(
    scenario: InstantiatedScenario,
) -> tuple[RealizationCollectionProfile, ...]:
    closure = RealizationClosure(
        posture="closed",
        universe="sdl-collection-members/v1",
        profile="recursive-realization-constraint/v1",
    )
    return tuple(
        RealizationCollectionProfile(
            field_pointer="/" + "/".join(_escape(token) for token in registered.field_path.split(".")),
            collection_kind=registered.descriptor.concern_kind,
            identity_fields=registered.descriptor.collection_identity_fields,
            closure=closure,
        )
        for registered in registered_realization_concern_descriptors(
            declaration_names={"nodes": scenario.nodes, "content": scenario.content}
        )
        if registered.descriptor.collection_identity_fields
    )


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


__all__ = ["compile_observation_demands"]
