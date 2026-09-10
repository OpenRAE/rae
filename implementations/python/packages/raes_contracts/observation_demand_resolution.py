"""Authority-aware normalization for scoped observation demand."""

from __future__ import annotations

from collections.abc import Sequence

from .diagnostics import Diagnostic
from .observation_demand import (
    EffectiveObservationDemand,
    ObservationBasis,
    ObservationDemandDocument,
    ObservationDemandMode,
    ObservationDemandResolution,
    ObservationDemandRule,
    ObservationLifecycleDecision,
    ObservationLifecycleStage,
    ObservationPurpose,
    ObservationSelector,
)
from .realization_structure import RealizationConstraintLimits, semantic_address_contains


def _scope_applies(parent: str, child: str) -> bool:
    return semantic_address_contains(parent, child)


def _depth(rule: ObservationDemandRule) -> int:
    return rule.scope.count("/")


def _default_mode(purpose: ObservationPurpose) -> ObservationDemandMode:
    return (
        ObservationDemandMode.OPERATIONAL_ONLY
        if purpose is ObservationPurpose.OPERATIONAL
        else ObservationDemandMode.NONE
    )


def _default_basis(purpose: ObservationPurpose) -> ObservationBasis:
    if purpose is ObservationPurpose.REALIZATION_DESCRIPTION:
        return ObservationBasis.BACKEND_SELECTED
    return ObservationBasis.OPERATIONAL if purpose is ObservationPurpose.OPERATIONAL else ObservationBasis.OBSERVED


def _conflict(scope: str, axis: str, rules: Sequence[ObservationDemandRule]) -> Diagnostic:
    origins = ", ".join(sorted(f"{rule.authority_ref}:{rule.rule_id}" for rule in rules))
    return Diagnostic(
        code="observation.authority-conflict",
        domain="observation-demand",
        address=scope or "observation-demand.root",
        message=f"Independent observation authorities conflict on '{axis}' ({origins}).",
    )


def _axis(
    rules: Sequence[ObservationDemandRule],
    axis: str,
    default: object,
    diagnostics: list[Diagnostic],
    scope: str,
) -> tuple[object, str]:
    forbidden = [rule for rule in rules if getattr(getattr(rule, axis), "value", getattr(rule, axis)) == "forbid"]
    declared = [
        rule
        for rule in rules
        if getattr(rule, axis) is not None
        and getattr(getattr(rule, axis), "value", getattr(rule, axis)) not in {"inherit", "forbid"}
    ]
    if not declared:
        origin = ",".join(sorted(rule.rule_id for rule in forbidden)) if forbidden else "root-default"
        return default, origin
    mandatory = [rule for rule in declared if rule.required]
    candidates = mandatory or [rule for rule in declared if _depth(rule) == max(map(_depth, declared))]
    values = {getattr(rule, axis) for rule in candidates}
    if len(values) > 1:
        diagnostics.append(_conflict(scope, axis, candidates))
    winner = min(candidates, key=lambda rule: (rule.authority_ref, rule.rule_id))
    return getattr(winner, axis), ",".join(sorted(rule.rule_id for rule in candidates))


def _selector_rules(rules: Sequence[ObservationDemandRule]) -> tuple[ObservationDemandRule, ...]:
    selected: list[ObservationDemandRule] = []
    for authority in sorted({rule.authority_ref for rule in rules}):
        authority_rules = [rule for rule in rules if rule.authority_ref == authority]
        required = [rule for rule in authority_rules if rule.required and rule.selector is not None]
        ordinary = [rule for rule in authority_rules if not rule.required and rule.selector is not None]
        selected.extend(required)
        if ordinary:
            depth = max(map(_depth, ordinary))
            selected.extend(rule for rule in ordinary if _depth(rule) == depth)
    return tuple(sorted(selected, key=lambda rule: (rule.authority_ref, rule.rule_id)))


def _clipped_selector(selector: ObservationSelector, scope: str) -> ObservationSelector | None:
    if semantic_address_contains(selector.semantic_scope, scope):
        selected_scope = scope
    elif semantic_address_contains(scope, selector.semantic_scope):
        selected_scope = selector.semantic_scope
    else:
        return None
    if any(semantic_address_contains(excluded, selected_scope) for excluded in selector.excluded_scopes):
        return None
    return selector.model_copy(
        update={
            "semantic_scope": selected_scope,
            "excluded_scopes": tuple(
                excluded for excluded in selector.excluded_scopes if semantic_address_contains(selected_scope, excluded)
            ),
        }
    )


def _policy_rules(
    applicable: Sequence[ObservationDemandRule],
    selected: ObservationDemandRule,
) -> tuple[ObservationDemandRule, ...]:
    """Keep selector policies local; selectorless authority rules govern the scope."""

    return tuple(
        rule
        for rule in applicable
        if rule is selected
        or rule.authority_ref == selected.authority_ref
        and (
            rule.selector is None
            or not rule.required
            and rule.scope != selected.scope
            and semantic_address_contains(rule.scope, selected.scope)
        )
        or rule.selector is None
        and (
            rule.required
            or rule.prohibited_stages
            or ObservationLifecycleDecision.FORBID in (rule.collection, rule.retention, rule.export)
        )
    )


def _effective_for(
    rules: Sequence[ObservationDemandRule],
    scope: str,
    purpose: ObservationPurpose,
    diagnostics: list[Diagnostic],
    selected: ObservationDemandRule | None = None,
) -> EffectiveObservationDemand:
    applicable = tuple(rule for rule in rules if rule.purpose is purpose and _scope_applies(rule.scope, scope))
    default_mode = (
        ObservationDemandMode.SELECTED
        if selected is not None and purpose is not ObservationPurpose.OPERATIONAL
        else _default_mode(purpose)
    )
    mode, mode_origin = _axis(applicable, "mode", default_mode, diagnostics, scope)
    effective_rules = applicable
    if mode is ObservationDemandMode.NONE:
        mode_winner = _axis_winner(applicable, "mode")
        if mode_winner is not None:
            effective_rules = tuple(rule for rule in applicable if _depth(rule) >= _depth(mode_winner))
    selector = (
        _clipped_selector(selected.selector, scope)
        if selected is not None and selected in effective_rules and selected.selector is not None
        else None
    )
    selectors = (selector,) if selector is not None else ()
    default_collection = (
        ObservationLifecycleDecision.REQUIRE
        if purpose is not ObservationPurpose.REALIZATION_DESCRIPTION
        and mode
        in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE, ObservationDemandMode.OPERATIONAL_ONLY}
        and selectors
        else ObservationLifecycleDecision.DISABLE
    )
    collection, collection_origin = _axis(effective_rules, "collection", default_collection, diagnostics, scope)
    retention, retention_origin = _axis(
        effective_rules, "retention", ObservationLifecycleDecision.DISABLE, diagnostics, scope
    )
    export, export_origin = _axis(effective_rules, "export", ObservationLifecycleDecision.DISABLE, diagnostics, scope)
    basis, basis_origin = _axis(effective_rules, "basis", _default_basis(purpose), diagnostics, scope)
    redaction, redaction_origin = _axis(effective_rules, "redaction", None, diagnostics, scope)
    integrity, integrity_origin = _axis(effective_rules, "integrity", None, diagnostics, scope)
    prohibited = tuple(
        sorted(
            {
                *(stage for rule in applicable for stage in rule.prohibited_stages),
                *(
                    stage
                    for rule in applicable
                    for stage, decision in (
                        (ObservationLifecycleStage.COLLECTION, rule.collection),
                        (ObservationLifecycleStage.RETENTION, rule.retention),
                        (ObservationLifecycleStage.EXPORT, rule.export),
                    )
                    if decision is ObservationLifecycleDecision.FORBID
                ),
            },
            key=lambda stage: stage.value,
        )
    )
    if mode is ObservationDemandMode.NONE:
        if selectors or any(value is ObservationLifecycleDecision.REQUIRE for value in (collection, retention, export)):
            diagnostics.append(_conflict(scope, "mode/lifecycle", applicable))
        selectors = ()
        collection = retention = export = ObservationLifecycleDecision.DISABLE
    elif mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE} and not selectors:
        diagnostics.append(_conflict(scope, "mode/selectors", applicable))
        mode = ObservationDemandMode.NONE
        collection = retention = export = ObservationLifecycleDecision.DISABLE
    if retention is ObservationLifecycleDecision.REQUIRE or export is ObservationLifecycleDecision.REQUIRE:
        if collection is not ObservationLifecycleDecision.REQUIRE:
            diagnostics.append(_conflict(scope, "collection/lifecycle", applicable))
            retention = export = ObservationLifecycleDecision.DISABLE
    return EffectiveObservationDemand(
        scope=scope,
        purpose=purpose,
        mode=mode,
        selectors=selectors,
        collection=collection,
        retention=retention,
        export=export,
        basis=basis,
        prohibited_stages=prohibited,
        redaction=redaction,
        integrity=integrity,
        required=any(rule.required for rule in applicable),
        origins={
            **({"selector": selected.rule_id, "authority": selected.authority_ref} if selected is not None else {}),
            "mode": mode_origin,
            "collection": collection_origin,
            "retention": retention_origin,
            "export": export_origin,
            "basis": basis_origin,
            "redaction": redaction_origin,
            "integrity": integrity_origin,
        },
    )


def _axis_winner(rules: Sequence[ObservationDemandRule], axis: str) -> ObservationDemandRule | None:
    declared = [
        rule
        for rule in rules
        if getattr(rule, axis) is not None
        and getattr(getattr(rule, axis), "value", getattr(rule, axis)) not in {"inherit", "forbid"}
    ]
    if not declared:
        return None
    mandatory = [rule for rule in declared if rule.required]
    candidates = mandatory or [rule for rule in declared if _depth(rule) == max(map(_depth, declared))]
    return min(candidates, key=lambda rule: (rule.authority_ref, rule.rule_id))


def _partition_descendant_policies(
    demands: tuple[EffectiveObservationDemand, ...],
) -> tuple[EffectiveObservationDemand, ...]:
    partitioned = []
    for demand in demands:
        selectors = []
        for selector in demand.selectors:
            if any(
                candidate.purpose is demand.purpose
                and candidate.scope != demand.scope
                and candidate.scope == selector.semantic_scope
                for candidate in demands
            ):
                # This narrower effective scope owns the entire selector region.
                continue
            descendant_scopes = {
                candidate.scope
                for candidate in demands
                if candidate is not demand
                and candidate.purpose is demand.purpose
                and candidate.scope != selector.semantic_scope
                and semantic_address_contains(selector.semantic_scope, candidate.scope)
            }
            selectors.append(
                selector.model_copy(
                    update={"excluded_scopes": tuple(sorted({*selector.excluded_scopes, *descendant_scopes}))}
                )
            )
        if selectors or not demand.selectors:
            partitioned.append(demand.model_copy(update={"selectors": tuple(selectors)}))
    return tuple(partitioned)


def _scope_demands(
    rules: Sequence[ObservationDemandRule],
    scope: str,
    purpose: ObservationPurpose,
    diagnostics: list[Diagnostic],
) -> tuple[EffectiveObservationDemand, ...]:
    applicable = tuple(rule for rule in rules if rule.purpose is purpose and _scope_applies(rule.scope, scope))
    selected = tuple(
        rule
        for rule in _selector_rules(applicable)
        if rule.selector is not None and _clipped_selector(rule.selector, scope) is not None
    )
    if not selected:
        return (
            _effective_for(tuple(rule for rule in applicable if rule.selector is None), scope, purpose, diagnostics),
        )
    policies = tuple(_policy_rules(applicable, rule) for rule in selected)
    effective = tuple(
        _effective_for(policy, scope, purpose, diagnostics, rule)
        for policy, rule in zip(policies, selected, strict=True)
    )
    for position, demand in enumerate(effective):
        for other_position in range(position + 1, len(effective)):
            if _lifecycle_overlap_conflicts(
                demand,
                effective[other_position],
                policies[position],
                policies[other_position],
            ):
                diagnostics.append(_conflict(scope, "overlapping-selector/lifecycle", selected))
    return effective


def _lifecycle_overlap_conflicts(
    left: EffectiveObservationDemand,
    right: EffectiveObservationDemand,
    left_rules: Sequence[ObservationDemandRule],
    right_rules: Sequence[ObservationDemandRule],
) -> bool:
    """Selector-local prohibitions still constrain other uses of the same data."""

    if not any(_selectors_overlap(a, b) for a in left.selectors for b in right.selectors):
        return False
    for stage in ObservationLifecycleStage:
        left_decision, right_decision = getattr(left, stage.value), getattr(right, stage.value)
        if left_decision is ObservationLifecycleDecision.REQUIRE and stage in right.prohibited_stages:
            return True
        if right_decision is ObservationLifecycleDecision.REQUIRE and stage in left.prohibited_stages:
            return True
        if left.required and right.required and left_decision is not right_decision:
            disabled_rules = left_rules if left_decision is ObservationLifecycleDecision.DISABLE else right_rules
            if _axis_winner(disabled_rules, stage.value) is not None:
                return True
    return False


def _selectors_overlap(left: ObservationSelector, right: ObservationSelector) -> bool:
    if left.data_kind != right.data_kind or not set(left.names).intersection(right.names):
        return False
    if left.component_refs and right.component_refs and not set(left.component_refs).intersection(right.component_refs):
        return False
    # Distinct named windows are not proof of disjoint time intervals.
    return (
        _clipped_selector(left, right.semantic_scope) is not None
        and _clipped_selector(right, left.semantic_scope) is not None
    )


def resolve_observation_demands(
    document: ObservationDemandDocument | None,
    *,
    target_scopes: Sequence[str],
    limits: RealizationConstraintLimits,
) -> ObservationDemandResolution:
    if not target_scopes or len(target_scopes) > limits.max_members:
        raise ValueError("observation-demand-limit-exceeded")
    if len(set(target_scopes)) != len(target_scopes):
        raise ValueError("observation-demand-duplicate-scope")
    rules = document.rules if document is not None else ()
    if len(rules) > limits.max_nodes:
        raise ValueError("observation-demand-limit-exceeded")
    if any(len(scope.encode("utf-8")) > limits.max_scalar_bytes for scope in target_scopes):
        raise ValueError("observation-demand-limit-exceeded")
    purposes = {ObservationPurpose.EXPERIMENTAL, *(rule.purpose for rule in rules)}
    diagnostics: list[Diagnostic] = []
    effective = tuple(
        demand
        for scope in target_scopes
        for purpose in sorted(purposes, key=lambda item: item.value)
        if purpose is ObservationPurpose.EXPERIMENTAL
        or any(rule.purpose is purpose and _scope_applies(rule.scope, scope) for rule in rules)
        for demand in _scope_demands(rules, scope, purpose, diagnostics)
    )
    return ObservationDemandResolution(_partition_descendant_policies(effective), tuple(diagnostics))


__all__ = ["resolve_observation_demands"]
