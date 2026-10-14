"""Observation-boundary view-relation timeline compilation helpers."""

from typing import Any

from raes.participant_behavior_specification import tool_affordance_reference
from raes.scenario import InstantiatedScenario

from .addresses import _action_contract_address, _tool_affordance_address
from .alias_index import _runtime_addressable_ref_index

_VISIBLE_VIEW_DISPOSITIONS = frozenset({"observable", "discovered", "inferred", "disclosed", "deceptive"})


def _information_keys(scenario: InstantiatedScenario) -> dict[str, frozenset[str]]:
    """Map authored action-contract and tool-affordance refs to compiled address candidates.

    Only the section-qualified authoring address of a declared action contract or
    tool-affordance binding is keyed. Every other information ref stays an opaque,
    boundary-local token. The existing runtime alias index contributes any other
    declaration the same token names, so an ambiguous token keeps every candidate.
    """

    candidates: dict[str, set[str]] = {}
    for name in scenario.action_contracts:
        candidates.setdefault(f"action_contracts.{name}", set()).add(_action_contract_address(name))
    for spec_name, behavior_spec in scenario.behavior_specifications.items():
        for affordance_id in behavior_spec.tool_affordances:
            candidates.setdefault(tool_affordance_reference(spec_name, affordance_id), set()).add(
                _tool_affordance_address(spec_name, affordance_id)
            )
    aliases = _runtime_addressable_ref_index(scenario)
    return {ref: frozenset(addresses | aliases.get(ref, set())) for ref, addresses in candidates.items()}


def _information_key(boundary_name: str, ref: str, keys: dict[str, frozenset[str]]) -> str:
    addresses = keys.get(ref)
    if addresses is None:
        return ref
    if len(addresses) != 1:
        raise ValueError(f"observation boundary {boundary_name} information_ref {ref} is ambiguous")
    return next(iter(addresses))


def _keyed_view_items(boundary_name: str, items: list[Any], keys: dict[str, frozenset[str]]) -> list[Any]:
    return [
        {**item, "information_ref": _information_key(boundary_name, str(item["information_ref"]), keys)}
        if isinstance(item, dict) and item.get("information_ref")
        else item
        for item in items
    ]


def _keyed_view_inputs(
    boundary_name: str,
    *,
    view_rules: list[Any],
    view_transitions: list[Any],
    keys: dict[str, frozenset[str]],
) -> tuple[list[Any], list[Any]]:
    """Key one boundary's view rules and transitions by compiled address.

    Two authored view rules that compile to one key would let one disposition
    silently replace the other, so they fail compilation instead.
    """

    keyed_rules = _keyed_view_items(boundary_name, view_rules, keys)
    authored_by_key: dict[str, str] = {}
    for rule, keyed_rule in zip(view_rules, keyed_rules, strict=True):
        if not isinstance(rule, dict) or not rule.get("information_ref"):
            continue
        authored = str(rule["information_ref"])
        key = str(keyed_rule["information_ref"])
        previous = authored_by_key.setdefault(key, authored)
        if previous != authored:
            raise ValueError(
                f"observation boundary {boundary_name} classifies {key} more than once: {previous}, {authored}"
            )
    return keyed_rules, _keyed_view_items(boundary_name, view_transitions, keys)


def _initial_view_relation(*, view_rules: list[Any]) -> dict[str, str]:
    view_relation: dict[str, str] = {}
    for rule in view_rules:
        if not isinstance(rule, dict):
            continue
        information_ref = rule.get("information_ref")
        disposition = rule.get("disposition")
        if not information_ref or not disposition:
            continue
        ref = str(information_ref)
        view_relation[ref] = str(disposition)
    return view_relation


def _view_relation_refs(view_relation: dict[str, str], dispositions: set[str] | frozenset[str]) -> tuple[str, ...]:
    return tuple(ref for ref, disposition in sorted(view_relation.items()) if disposition in dispositions)


def _view_relation_snapshot(
    *,
    transition_id: str,
    effective_from: str,
    effective_order: int,
    view_relation: dict[str, str],
    transition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = {
        "transition_id": transition_id,
        "effective_from": effective_from,
        "effective_order": effective_order,
        "view_relation": dict(sorted(view_relation.items())),
        "visible_refs": _view_relation_refs(view_relation, _VISIBLE_VIEW_DISPOSITIONS),
        "hidden_refs": _view_relation_refs(view_relation, {"hidden"}),
        "evidence_only_refs": _view_relation_refs(view_relation, {"evidence_only"}),
        "disclosed_refs": _view_relation_refs(view_relation, {"disclosed"}),
        "discovered_refs": _view_relation_refs(view_relation, {"discovered"}),
        "inferred_refs": _view_relation_refs(view_relation, {"inferred"}),
        "concealed_refs": _view_relation_refs(view_relation, {"concealed"}),
        "deceptive_refs": _view_relation_refs(view_relation, {"deceptive"}),
    }
    if transition is not None:
        snapshot.update(
            {
                "transition_kind": str(transition.get("transition_kind") or ""),
                "information_ref": str(transition.get("information_ref") or ""),
                "history_event_type": str(transition.get("history_event_type") or ""),
                "action_instance_id": (
                    str(transition.get("action_instance_id"))
                    if transition.get("action_instance_id") is not None
                    else ""
                ),
            }
        )
    return snapshot


def _ordered_view_transitions(view_transitions: list[Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        sorted(
            (dict(transition) for transition in view_transitions if isinstance(transition, dict)),
            key=lambda transition: int(transition.get("effective_order", 0)),
        )
    )


def _compile_view_relation_timeline(
    *,
    view_rules: list[Any],
    view_transitions: list[Any],
) -> tuple[dict[str, Any], ...]:
    view_relation = _initial_view_relation(view_rules=view_rules)
    timeline: list[dict[str, Any]] = [
        _view_relation_snapshot(
            transition_id="initial",
            effective_from="initial",
            effective_order=-1,
            view_relation=view_relation,
        )
    ]
    for transition in _ordered_view_transitions(view_transitions):
        information_ref = transition.get("information_ref")
        to_disposition = transition.get("to_disposition")
        if not information_ref or not to_disposition:
            continue
        view_relation[str(information_ref)] = str(to_disposition)
        timeline.append(
            _view_relation_snapshot(
                transition_id=str(transition.get("transition_id") or ""),
                effective_from=str(transition.get("effective_from") or ""),
                effective_order=int(transition.get("effective_order", 0)),
                view_relation=view_relation,
                transition=transition,
            )
        )
    return tuple(timeline)
