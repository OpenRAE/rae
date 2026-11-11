"""Observation-boundary view-relation timeline compilation helpers."""

from typing import Any

from raes_contracts.errors import InvalidInputError

_VISIBLE_VIEW_DISPOSITIONS = frozenset({"observable", "discovered", "inferred", "disclosed", "deceptive"})


def _normalize_visibility_references(
    boundary_spec: dict[str, Any], addressable_ref_index: dict[str, set[str]]
) -> dict[str, Any]:
    """Resolve observation references without modifying the authored specification."""

    def resolve(ref: str) -> str:
        matches = addressable_ref_index.get(ref, set())
        if len(matches) > 1:
            raise InvalidInputError("ambiguous observation visibility reference: " + ref[:128])
        return next(iter(matches)) if matches else ref

    normalized = dict(boundary_spec)
    for field in ("observable_refs", "hidden_refs", "evidence_refs"):
        normalized[field] = list(dict.fromkeys(resolve(str(ref)) for ref in boundary_spec.get(field, [])))
    for field in ("view_rules", "view_transitions"):
        normalized[field] = [
            {**item, "information_ref": resolve(str(item["information_ref"]))} for item in boundary_spec.get(field, [])
        ]
    return normalized


def _visibility_aliases_by_address(
    address_index: dict[str, set[str]],
) -> dict[str, dict[str, tuple[str, ...]]]:
    """Index aliases once; retain ambiguity for fail-closed history checks."""
    aliases: dict[str, dict[str, tuple[str, ...]]] = {}
    for ref, matches in address_index.items():
        targets = tuple(sorted(matches))
        if targets == (ref,):
            continue
        for address in targets:
            aliases.setdefault(address, {})[ref] = targets
    return aliases


def _boundary_reference_aliases(
    spec: dict[str, Any], aliases_by_address: dict[str, dict[str, tuple[str, ...]]]
) -> dict[str, tuple[str, ...]]:
    """Carry only aliases that can refer to this boundary's policy items."""
    refs = {ref for field in ("observable_refs", "hidden_refs", "evidence_refs") for ref in spec.get(field, [])}
    refs.update(item["information_ref"] for field in ("view_rules", "view_transitions") for item in spec.get(field, []))
    aliases: dict[str, tuple[str, ...]] = {}
    for ref in sorted(refs):
        aliases.update(aliases_by_address.get(ref, {}))
    return dict(sorted(aliases.items()))


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
        if ref in view_relation and view_relation[ref] != str(disposition):
            raise InvalidInputError("conflicting observation visibility dispositions: " + ref[:128])
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
        ref = str(information_ref)
        if ref in view_relation and transition.get("from_disposition") != view_relation[ref]:
            raise InvalidInputError("conflicting observation visibility transition: " + ref[:128])
        view_relation[ref] = str(to_disposition)
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
