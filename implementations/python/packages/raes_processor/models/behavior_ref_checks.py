"""Participant-behavior history reference and ref-authorization violation checks."""

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from raes_contracts.participant_attribution_semantics import ParticipantAttributionCandidateKind
from raes_contracts.participant_behavior import ParticipantBehaviorHistoryEventType

from .attribution import ParticipantAttributionCandidate, ParticipantAttributionEdge
from .behavior_resources import (
    _PARTICIPANT_OBSERVATION_DETAIL_KEYS,
    _PARTICIPANT_OBSERVATION_DETAIL_REF_KEYS,
    _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS,
    ParticipantObservationBoundaryRuntime,
)
from .history_event import ParticipantBehaviorHistoryEvent


def _participant_behavior_detail_refs_result(
    value: object,
    *,
    key: str,
) -> tuple[tuple[str, ...], str | None]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        return (), f"observation details field {key!r} must be a list of strings"
    items = tuple(value)
    refs = tuple(str(ref) for ref in items if isinstance(ref, str) and ref)
    if len(refs) != len(items):
        message: str | None = f"observation details field {key!r} must contain only non-empty strings"
    elif len(set(refs)) != len(refs):
        message = f"observation details field {key!r} must not contain duplicate refs"
    else:
        message = None
    return refs, message


def _participant_behavior_detail_refs(
    event: ParticipantBehaviorHistoryEvent,
    *,
    key: str,
    locator: str,
) -> tuple[tuple[str, ...], list[tuple[str, str]]]:
    if key not in event.details:
        return (), []
    refs, message = _participant_behavior_detail_refs_result(event.details[key], key=key)
    if message is None:
        return refs, []
    return (), [(locator, message)]


def _participant_behavior_detail_shape_violations(
    event: ParticipantBehaviorHistoryEvent,
    *,
    locator: str,
) -> list[tuple[str, str]]:
    if not event.details:
        return []
    violations: list[tuple[str, str]] = []
    if event.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
        violations.append((locator, "participant behavior details are only allowed on observation_emitted events"))
    unsupported_keys = sorted(str(key) for key in event.details if key not in _PARTICIPANT_OBSERVATION_DETAIL_KEYS)
    if unsupported_keys:
        allowed = ", ".join(_PARTICIPANT_OBSERVATION_DETAIL_REF_KEYS)
        unsupported = ", ".join(unsupported_keys)
        violations.append(
            (
                locator,
                f"observation details may only contain {allowed}; unsupported fields: {unsupported}",
            )
        )
    return violations


def _participant_behavior_timeline_relations(
    boundary: ParticipantObservationBoundaryRuntime,
) -> tuple[tuple[int, dict[str, str]], ...]:
    relations: list[tuple[int, dict[str, str]]] = []
    for snapshot in boundary.view_relation_timeline:
        order = snapshot.get("effective_order")
        raw_relation = snapshot.get("view_relation", {})
        if not isinstance(order, int) or isinstance(order, bool) or not isinstance(raw_relation, Mapping):
            continue
        relations.append((order, {str(ref): str(disposition) for ref, disposition in raw_relation.items()}))
    return tuple(sorted(relations, key=lambda item: item[0]))


def _participant_behavior_initial_view_relation(
    boundary: ParticipantObservationBoundaryRuntime,
) -> dict[str, str]:
    initial_relation: dict[str, str] = {}
    for order, relation in _participant_behavior_timeline_relations(boundary):
        if order > -1:
            break
        initial_relation = dict(relation)
    return initial_relation


def _participant_behavior_view_relation_deltas_by_order(
    boundary: ParticipantObservationBoundaryRuntime,
) -> dict[int, dict[str, str]]:
    deltas: dict[int, dict[str, str]] = {}
    previous_relation: dict[str, str] | None = None
    for order, relation in _participant_behavior_timeline_relations(boundary):
        if previous_relation is None:
            previous_relation = relation
            continue
        deltas[order] = {
            ref: disposition for ref, disposition in relation.items() if previous_relation.get(ref) != disposition
        }
        previous_relation = relation
    return deltas


def _participant_behavior_transition_effective_order(transition: Mapping[str, Any]) -> int | None:
    order = transition.get("effective_order")
    if not isinstance(order, int) or isinstance(order, bool):
        return None
    return order


def _participant_behavior_transition_delta(
    transition: Mapping[str, Any],
    *,
    deltas_by_order: Mapping[int, Mapping[str, str]],
) -> dict[str, str]:
    information_ref = transition.get("information_ref")
    to_disposition = transition.get("to_disposition")
    if isinstance(information_ref, str) and information_ref and isinstance(to_disposition, str) and to_disposition:
        return {information_ref: to_disposition}
    order = _participant_behavior_transition_effective_order(transition)
    if order is None:
        return {}
    return dict(deltas_by_order.get(order, {}))


def _participant_behavior_transition_matches_relation(
    transition: Mapping[str, Any],
    *,
    relation: Mapping[str, str],
) -> bool:
    information_ref = transition.get("information_ref")
    from_disposition = transition.get("from_disposition")
    if not isinstance(information_ref, str) or not information_ref:
        return True
    if not isinstance(from_disposition, str) or not from_disposition:
        return True
    return relation.get(information_ref) == from_disposition


def _participant_behavior_observation_detail_refs(
    event: ParticipantBehaviorHistoryEvent,
    *,
    locator: str,
) -> tuple[dict[str, tuple[str, ...]], list[tuple[str, str]]]:
    detail_refs: dict[str, tuple[str, ...]] = {}
    violations: list[tuple[str, str]] = []
    for key in _PARTICIPANT_OBSERVATION_DETAIL_REF_KEYS:
        refs, ref_violations = _participant_behavior_detail_refs(event, key=key, locator=locator)
        detail_refs[key] = refs
        violations.extend(ref_violations)
    return detail_refs, violations


def _participant_behavior_resolved_ref(boundary: ParticipantObservationBoundaryRuntime, ref: str) -> str | None:
    matches = boundary.reference_aliases.get(ref, (ref,))
    return matches[0] if len(matches) == 1 else None


def _participant_behavior_ref_disposition(
    boundary: ParticipantObservationBoundaryRuntime, relation: Mapping[str, str], ref: str
) -> str | None:
    resolved = _participant_behavior_resolved_ref(boundary, ref)
    if resolved is None:
        return "ambiguous"
    disposition = relation.get(resolved)
    return "hidden" if disposition is None and resolved in boundary.hidden_refs else disposition


def _participant_behavior_disposition_ref_violations(
    *,
    locator: str,
    refs: tuple[str, ...],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
    detail_key: Literal["visible_refs", "disclosed_refs"],
) -> list[tuple[str, str]]:
    allowed_dispositions = (
        _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS if detail_key == "visible_refs" else frozenset({"disclosed"})
    )
    allowed_label = "participant-visible" if detail_key == "visible_refs" else "disclosed"
    violations: list[tuple[str, str]] = []
    for ref in refs:
        disposition = _participant_behavior_ref_disposition(boundary, relation, ref)
        if disposition in allowed_dispositions:
            continue
        violations.append(
            (
                locator,
                (
                    f"observation {detail_key} may only contain {allowed_label} refs at "
                    f"effective_order {effective_order}: "
                    f"{ref!r} has disposition {disposition!r}"
                ),
            )
        )
    return violations


def _participant_behavior_evidence_ref_violations(
    *,
    locator: str,
    refs: tuple[str, ...],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for ref in refs:
        if (
            _participant_behavior_resolved_ref(boundary, ref) in boundary.evidence_refs
            or _participant_behavior_ref_disposition(boundary, relation, ref) == "evidence_only"
        ):
            continue
        violations.append(
            (
                locator,
                (
                    "observation evidence_refs may only contain boundary evidence refs at "
                    f"effective_order {effective_order}: {ref!r}"
                ),
            )
        )
    return violations


def _participant_behavior_visibility_detail_violations(
    *,
    locator: str,
    detail_refs: Mapping[str, tuple[str, ...]],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    return [
        *_participant_behavior_disposition_ref_violations(
            locator=locator,
            refs=detail_refs["visible_refs"],
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
            detail_key="visible_refs",
        ),
        *_participant_behavior_disposition_ref_violations(
            locator=locator,
            refs=detail_refs["disclosed_refs"],
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
            detail_key="disclosed_refs",
        ),
        *_participant_behavior_evidence_ref_violations(
            locator=locator,
            refs=detail_refs["evidence_refs"],
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
        ),
    ]


def _participant_behavior_action_result_visible_ref_violations(
    *,
    locator: str,
    owner_label: str,
    field_name: str,
    refs: tuple[str, ...],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    owner_prefix = f" {owner_label}" if owner_label else ""
    for ref in refs:
        disposition = _participant_behavior_ref_disposition(boundary, relation, ref)
        if disposition is None:
            continue
        if disposition in _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS:
            continue
        violations.append(
            (
                locator,
                (
                    f"action_result{owner_prefix} {field_name} {ref!r} is not participant-visible "
                    f"at effective_order {effective_order}: disposition {disposition!r}"
                ),
            )
        )
    return violations


def _participant_behavior_action_result_evidence_ref_violations(
    *,
    locator: str,
    owner_label: str,
    field_name: str,
    refs: tuple[str, ...],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    owner_prefix = f" {owner_label}" if owner_label else ""
    for ref in refs:
        disposition = _participant_behavior_ref_disposition(boundary, relation, ref)
        if (
            _participant_behavior_resolved_ref(boundary, ref) in boundary.evidence_refs
            or disposition == "evidence_only"
        ):
            continue
        suffix = f": disposition {disposition!r}" if disposition is not None else ""
        violations.append(
            (
                locator,
                (
                    f"action_result{owner_prefix} {field_name} {ref!r} is not authorized evidence "
                    f"at effective_order {effective_order}{suffix}"
                ),
            )
        )
    return violations


def _participant_behavior_action_result_ref_authorization_violations(
    *,
    event: ParticipantBehaviorHistoryEvent,
    locator: str,
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    if event.action_result is None:
        return []
    violations: list[tuple[str, str]] = []
    for precondition in event.action_result.preconditions:
        owner_label = f"precondition {precondition.precondition_id!r}"
        violations.extend(
            _participant_behavior_action_result_visible_ref_violations(
                locator=locator,
                owner_label=owner_label,
                field_name="support_ref",
                refs=precondition.support_refs,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
        violations.extend(
            _participant_behavior_action_result_evidence_ref_violations(
                locator=locator,
                owner_label=owner_label,
                field_name="evidence_ref",
                refs=precondition.evidence_refs,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
    for effect in event.action_result.effects:
        owner_label = f"effect {effect.effect_id!r}"
        violations.extend(
            _participant_behavior_action_result_visible_ref_violations(
                locator=locator,
                owner_label=owner_label,
                field_name="target_ref",
                refs=effect.target_refs,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
        violations.extend(
            _participant_behavior_action_result_evidence_ref_violations(
                locator=locator,
                owner_label=owner_label,
                field_name="evidence_ref",
                refs=effect.evidence_refs,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
    violations.extend(
        _participant_behavior_action_result_evidence_ref_violations(
            locator=locator,
            owner_label="",
            field_name="evidence_ref",
            refs=event.action_result.evidence_refs,
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
        )
    )
    return violations


def _participant_behavior_attribution_evidence_ref_violations(
    *,
    locator: str,
    edge: ParticipantAttributionEdge,
    refs: tuple[str, ...],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for ref in refs:
        disposition = _participant_behavior_ref_disposition(boundary, relation, ref)
        if (
            _participant_behavior_resolved_ref(boundary, ref) in boundary.evidence_refs
            or disposition == "evidence_only"
        ):
            continue
        suffix = f": disposition {disposition!r}" if disposition is not None else ""
        violations.append(
            (
                locator,
                (
                    f"attribution edge {edge.edge_id!r} evidence_ref {ref!r} is not authorized evidence "
                    f"at effective_order {effective_order}{suffix}"
                ),
            )
        )
    return violations


def _participant_behavior_attribution_visibility_candidate_violations(
    *,
    locator: str,
    edge: ParticipantAttributionEdge,
    candidate: ParticipantAttributionCandidate,
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    disposition = _participant_behavior_ref_disposition(boundary, relation, candidate.ref)
    if disposition is None or disposition in _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS:
        return []
    return [
        (
            locator,
            (
                f"attribution edge {edge.edge_id!r} {candidate.candidate_kind.value} candidate "
                f"{candidate.ref!r} is not participant-visible at effective_order {effective_order}: "
                f"disposition {disposition!r}"
            ),
        )
    ]


def _participant_behavior_attribution_candidate_ref_violations(
    *,
    locator: str,
    edge: ParticipantAttributionEdge,
    candidate: ParticipantAttributionCandidate,
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    if candidate.candidate_kind == ParticipantAttributionCandidateKind.ACTION:
        return []
    if candidate.candidate_kind == ParticipantAttributionCandidateKind.EVIDENCE:
        return _participant_behavior_attribution_evidence_ref_violations(
            locator=locator,
            edge=edge,
            refs=(candidate.ref,),
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
        )
    return _participant_behavior_attribution_visibility_candidate_violations(
        locator=locator,
        edge=edge,
        candidate=candidate,
        boundary=boundary,
        relation=relation,
        effective_order=effective_order,
    )
