"""Authority-aware normalization for scoped observation demand."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
from .observation_demand_scope import (
    clipped_observation_selector as _clipped_selector,
)
from .observation_demand_scope import (
    observation_axis_winner as _axis_winner,
)
from .observation_demand_scope import (
    observation_rule_depth as _depth,
)
from .observation_demand_scope import (
    partition_descendant_observation_policies as _partition_descendant_policies,
)
from .observation_demand_scope import (
    selector_lifecycle_overlap_conflicts as _lifecycle_overlap_conflicts,
)
from .realization_structure import RealizationConstraintLimits, semantic_address_contains


def _scope_applies(parent: str, child: str) -> bool:
    return semantic_address_contains(parent, child)


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


def _policy_rules(
    applicable: Sequence[ObservationDemandRule],
    selected: ObservationDemandRule,
) -> tuple[ObservationDemandRule, ...]:
    """Keep selector policies local; selectorless authority rules govern the scope."""

    return tuple(rule for rule in applicable if _rule_applies_to_selected_policy(rule, selected))


def _rule_applies_to_selected_policy(rule: ObservationDemandRule, selected: ObservationDemandRule) -> bool:
    if rule is selected:
        return True
    same_authority = rule.authority_ref == selected.authority_ref
    inherited_authority_policy = (
        rule.selector is None
        or not rule.required
        and rule.scope != selected.scope
        and semantic_address_contains(rule.scope, selected.scope)
    )
    independent_constraint = rule.selector is None and (
        rule.required
        or bool(rule.prohibited_stages)
        or ObservationLifecycleDecision.FORBID in (rule.collection, rule.retention, rule.export)
    )
    return same_authority and inherited_authority_policy or independent_constraint


@dataclass(frozen=True)
class _ResolvedPolicyAxes:
    collection: ObservationLifecycleDecision
    retention: ObservationLifecycleDecision
    export: ObservationLifecycleDecision
    basis: ObservationBasis
    redaction: str | None
    integrity: str | None
    origins: dict[str, str]


def _effective_for(
    rules: Sequence[ObservationDemandRule],
    scope: str,
    purpose: ObservationPurpose,
    diagnostics: list[Diagnostic],
    selected: ObservationDemandRule | None = None,
) -> EffectiveObservationDemand:
    applicable = tuple(rule for rule in rules if rule.purpose is purpose and _scope_applies(rule.scope, scope))
    default_mode = _selected_default_mode(selected, purpose)
    mode, mode_origin = _axis(applicable, "mode", default_mode, diagnostics, scope)
    effective_rules = _rules_at_effective_mode_depth(applicable, mode)
    selector = _effective_selector(selected, effective_rules, scope)
    selectors = (selector,) if selector is not None else ()
    axes = _resolve_policy_axes(
        effective_rules,
        purpose=purpose,
        mode=mode,
        has_selectors=bool(selectors),
        diagnostics=diagnostics,
        scope=scope,
    )
    mode, selectors, axes = _normalize_effective_axes(
        mode,
        selectors,
        axes,
        applicable=applicable,
        diagnostics=diagnostics,
        scope=scope,
    )
    return EffectiveObservationDemand(
        scope=scope,
        purpose=purpose,
        mode=mode,
        selectors=selectors,
        collection=axes.collection,
        retention=axes.retention,
        export=axes.export,
        basis=axes.basis,
        prohibited_stages=_prohibited_stages(applicable),
        redaction=axes.redaction,
        integrity=axes.integrity,
        required=any(rule.required for rule in applicable),
        origins={
            **({"selector": selected.rule_id, "authority": selected.authority_ref} if selected is not None else {}),
            "mode": mode_origin,
            **axes.origins,
        },
    )


def _selected_default_mode(
    selected: ObservationDemandRule | None,
    purpose: ObservationPurpose,
) -> ObservationDemandMode:
    if selected is not None and purpose is not ObservationPurpose.OPERATIONAL:
        return ObservationDemandMode.SELECTED
    return _default_mode(purpose)


def _rules_at_effective_mode_depth(
    applicable: tuple[ObservationDemandRule, ...],
    mode: object,
) -> tuple[ObservationDemandRule, ...]:
    if mode is not ObservationDemandMode.NONE:
        return applicable
    winner = _axis_winner(applicable, "mode")
    if winner is None:
        return applicable
    return tuple(rule for rule in applicable if _depth(rule) >= _depth(winner))


def _effective_selector(
    selected: ObservationDemandRule | None,
    effective_rules: tuple[ObservationDemandRule, ...],
    scope: str,
) -> ObservationSelector | None:
    if selected is None or selected not in effective_rules or selected.selector is None:
        return None
    return _clipped_selector(selected.selector, scope)


def _default_collection(
    purpose: ObservationPurpose,
    mode: object,
    has_selectors: bool,
) -> ObservationLifecycleDecision:
    collecting_mode = mode in {
        ObservationDemandMode.SELECTED,
        ObservationDemandMode.EXHAUSTIVE,
        ObservationDemandMode.OPERATIONAL_ONLY,
    }
    if purpose is not ObservationPurpose.REALIZATION_DESCRIPTION and collecting_mode and has_selectors:
        return ObservationLifecycleDecision.REQUIRE
    return ObservationLifecycleDecision.DISABLE


def _resolve_policy_axes(
    rules: tuple[ObservationDemandRule, ...],
    *,
    purpose: ObservationPurpose,
    mode: object,
    has_selectors: bool,
    diagnostics: list[Diagnostic],
    scope: str,
) -> _ResolvedPolicyAxes:
    collection, collection_origin = _axis(
        rules,
        "collection",
        _default_collection(purpose, mode, has_selectors),
        diagnostics,
        scope,
    )
    retention, retention_origin = _axis(rules, "retention", ObservationLifecycleDecision.DISABLE, diagnostics, scope)
    export, export_origin = _axis(rules, "export", ObservationLifecycleDecision.DISABLE, diagnostics, scope)
    basis, basis_origin = _axis(rules, "basis", _default_basis(purpose), diagnostics, scope)
    redaction, redaction_origin = _axis(rules, "redaction", None, diagnostics, scope)
    integrity, integrity_origin = _axis(rules, "integrity", None, diagnostics, scope)
    return _ResolvedPolicyAxes(
        collection=collection,
        retention=retention,
        export=export,
        basis=basis,
        redaction=redaction,
        integrity=integrity,
        origins={
            "collection": collection_origin,
            "retention": retention_origin,
            "export": export_origin,
            "basis": basis_origin,
            "redaction": redaction_origin,
            "integrity": integrity_origin,
        },
    )


def _disabled_lifecycle_axes(axes: _ResolvedPolicyAxes) -> _ResolvedPolicyAxes:
    return _ResolvedPolicyAxes(
        collection=ObservationLifecycleDecision.DISABLE,
        retention=ObservationLifecycleDecision.DISABLE,
        export=ObservationLifecycleDecision.DISABLE,
        basis=axes.basis,
        redaction=axes.redaction,
        integrity=axes.integrity,
        origins=axes.origins,
    )


def _normalize_effective_axes(
    mode: object,
    selectors: tuple[ObservationSelector, ...],
    axes: _ResolvedPolicyAxes,
    *,
    applicable: tuple[ObservationDemandRule, ...],
    diagnostics: list[Diagnostic],
    scope: str,
) -> tuple[object, tuple[ObservationSelector, ...], _ResolvedPolicyAxes]:
    lifecycle = (axes.collection, axes.retention, axes.export)
    if mode is ObservationDemandMode.NONE:
        if selectors or ObservationLifecycleDecision.REQUIRE in lifecycle:
            diagnostics.append(_conflict(scope, "mode/lifecycle", applicable))
        selectors = ()
        axes = _disabled_lifecycle_axes(axes)
    elif mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE} and not selectors:
        diagnostics.append(_conflict(scope, "mode/selectors", applicable))
        mode = ObservationDemandMode.NONE
        axes = _disabled_lifecycle_axes(axes)
    elif ObservationLifecycleDecision.REQUIRE in (axes.retention, axes.export) and (
        axes.collection is not ObservationLifecycleDecision.REQUIRE
    ):
        diagnostics.append(_conflict(scope, "collection/lifecycle", applicable))
        axes = _disabled_lifecycle_axes(axes)
    return mode, selectors, axes


def _prohibited_stages(rules: Sequence[ObservationDemandRule]) -> tuple[ObservationLifecycleStage, ...]:
    prohibited = {stage for rule in rules for stage in rule.prohibited_stages}
    decisions = (
        (ObservationLifecycleStage.COLLECTION, "collection"),
        (ObservationLifecycleStage.RETENTION, "retention"),
        (ObservationLifecycleStage.EXPORT, "export"),
    )
    prohibited.update(
        stage
        for rule in rules
        for stage, axis in decisions
        if getattr(rule, axis) is ObservationLifecycleDecision.FORBID
    )
    return tuple(sorted(prohibited, key=lambda stage: stage.value))


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
