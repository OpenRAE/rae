"""Deny-first, time-indexed SEM-226 participant exposure selection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from raes_contracts.contracts import ParticipantExposurePolicyModel
from raes_contracts.participant_behavior import ParticipantBehaviorHistoryEventType

from .behavior_resources import _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS
from .history_event import ParticipantBehaviorHistoryEvent
from .participant_exposure_authority import (
    ParticipantExposureAssessment,
    ParticipantExposureAuthorizationRecord,
    ParticipantExposureOccurrenceRecord,
    ParticipantExposurePolicyRevision,
    ParticipantExposureProjection,
    ParticipantExposureResolvers,
)
from .participant_exposure_policy import (
    _effective_projection_policy,
    _policy_permits_item,
    _resolve_authorization,
    _resolved_projection_policy_revisions,
    _selected_exposure_policy,
    _validate_authorization_scope,
    _validate_authorization_shape,
    _validate_exposure_operation,
    resolve_from_host,
)


def _serialized_surface_refs(
    projection: ParticipantExposureProjection,
    entries: list[dict[str, object]],
    surface_affordances: list[str],
) -> set[str]:
    return {
        *projection.visible_context_refs,
        *(str(entry["action_contract_address"]) for entry in entries),
        *surface_affordances,
    }


def _event_evidence_refs(event: ParticipantBehaviorHistoryEvent) -> tuple[str, ...]:
    refs: list[str] = []
    details = event.details.get("evidence_refs")
    if not isinstance(details, (str, bytes, Mapping)) and isinstance(details, Iterable):
        refs.extend(ref for ref in details if isinstance(ref, str) and ref)
    if event.action_result is not None:
        refs.extend(event.action_result.evidence_refs)
        for precondition in event.action_result.preconditions:
            refs.extend(precondition.evidence_refs)
        for effect in event.action_result.effects:
            refs.extend(effect.evidence_refs)
    for edge in event.attribution_edges:
        refs.extend(edge.evidence_refs)
    return tuple(dict.fromkeys(refs))


def _observation_ref(event: ParticipantBehaviorHistoryEvent) -> str:
    return f"participant-observation:{event.participant_address}:{event.episode_id}:{event.action_instance_id}"


def _occurrence_ref(event: ParticipantBehaviorHistoryEvent, delivery_order: int) -> str:
    return f"{_observation_ref(event)}:order-{delivery_order}"


def _resolve_occurrence(
    assessment: ParticipantExposureAssessment,
    projection: ParticipantExposureProjection,
    resolvers: ParticipantExposureResolvers,
) -> ParticipantExposureOccurrenceRecord | None:
    realization = assessment.realization
    if realization is None:
        return None
    if not realization.occurrence_ref:
        raise ValueError("realized exposure requires an occurrence_ref")
    occurrence = resolve_from_host(
        "occurrence",
        "realized exposure occurrence resolution failed",
        lambda: resolvers.occurrence(occurrence_ref=realization.occurrence_ref),
    )
    if occurrence is None or occurrence.occurrence_ref != realization.occurrence_ref:
        raise ValueError("realized exposure occurrence_ref did not resolve")
    if occurrence.item_ref != assessment.item_ref:
        raise ValueError("realized exposure occurrence item_ref must match the exposed item")
    if occurrence.delivery_order < 0 or occurrence.delivery_order > projection.observation_order:
        raise ValueError("realized exposure delivery_order must identify an occurrence at or before the surface")
    return occurrence


def _matching_observation_event(
    occurrence: ParticipantExposureOccurrenceRecord,
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
) -> ParticipantBehaviorHistoryEvent:
    matching_events = tuple(
        event
        for event in history_events
        if event.event_type == ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED
        and event.participant_address == occurrence.participant_address
        and event.episode_id == occurrence.episode_id
        and event.action_instance_id == occurrence.action_instance_id
        and event.observation_boundary_address == occurrence.observation_boundary_address
    )
    if len(matching_events) != 1:
        raise ValueError("realized exposure must resolve to an observation history occurrence")
    return matching_events[0]


def _validate_delivery_authorization(
    occurrence: ParticipantExposureOccurrenceRecord,
    projection: ParticipantExposureProjection,
    policy_revisions: Sequence[ParticipantExposurePolicyRevision],
    resolvers: ParticipantExposureResolvers,
) -> None:
    delivery_authorization = _resolve_authorization(
        authorization_record_ref=occurrence.authorization_record_ref,
        item_ref=occurrence.item_ref,
        resolver=resolvers.authorization,
    )
    delivery_policy = _selected_exposure_policy(
        projection,
        resolvers.apparatus,
        observation_order=occurrence.delivery_order,
    )
    delivery_revision = _effective_projection_policy(
        policy_revisions,
        observation_order=occurrence.delivery_order,
        expected_revision=delivery_authorization.projection_policy_revision,
    )
    _validate_authorization_scope(
        delivery_authorization,
        projection,
        delivery_policy,
        observation_order=occurrence.delivery_order,
        projection_policy_revision=delivery_revision.revision,
    )
    _validate_authorization_shape(delivery_authorization)
    _validate_exposure_operation(delivery_authorization)
    if not _policy_permits_item(delivery_policy, occurrence.item_ref):
        raise ValueError(f"delivery exposure policy does not permit item {occurrence.item_ref!r}")


def _validate_occurrence_coordinates(
    occurrence: ParticipantExposureOccurrenceRecord,
    event: ParticipantBehaviorHistoryEvent,
    projection: ParticipantExposureProjection,
) -> None:
    expected = {
        "participant_address": event.participant_address,
        "episode_id": event.episode_id,
        "action_instance_id": event.action_instance_id,
        "observation_boundary_address": event.observation_boundary_address,
        "observation_ref": _observation_ref(event),
        "occurrence_ref": _occurrence_ref(event, occurrence.delivery_order),
    }
    mismatches = sorted(name for name, value in expected.items() if getattr(occurrence, name) != value)
    if mismatches:
        raise ValueError("realized exposure occurrence disagrees with behavior history: " + ", ".join(mismatches))
    if (
        occurrence.participant_address != projection.participant_address
        or occurrence.episode_id != projection.episode_id
    ):
        raise ValueError("realized exposure occurrence is outside the surface participant and episode")


def _validate_occurrence_evidence(
    occurrence: ParticipantExposureOccurrenceRecord,
    event: ParticipantBehaviorHistoryEvent,
) -> None:
    event_evidence = _event_evidence_refs(event)
    event_provenance = (event.actor_provenance,) if event.actor_provenance is not None else ()
    if set(occurrence.evidence_refs) != set(event_evidence):
        raise ValueError("realized exposure evidence_refs must agree with the observation history occurrence")
    if set(occurrence.provenance_refs) != set(event_provenance):
        raise ValueError("realized exposure provenance_refs must agree with the observation history occurrence")


def _validate_occurrence_required_refs(occurrence: ParticipantExposureOccurrenceRecord) -> None:
    required = (
        occurrence.delivery_basis_ref,
        occurrence.item_ref,
        occurrence.authorization_record_ref,
        *occurrence.evidence_refs,
        *occurrence.provenance_refs,
        *occurrence.limitations,
    )
    if any(not isinstance(value, str) or not value for value in required):
        raise ValueError("realized exposure requires delivery, evidence, provenance, and limitation refs")
    required_collections = (occurrence.evidence_refs, occurrence.provenance_refs, occurrence.limitations)
    if any(not values for values in required_collections):
        raise ValueError("realized exposure requires evidence, provenance, and limitations")


def _validate_realized_exposure(
    assessment: ParticipantExposureAssessment,
    projection: ParticipantExposureProjection,
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    policy_revisions: Sequence[ParticipantExposurePolicyRevision],
    resolvers: ParticipantExposureResolvers,
) -> ParticipantExposureOccurrenceRecord | None:
    occurrence = _resolve_occurrence(assessment, projection, resolvers)
    if occurrence is None:
        return None
    event = _matching_observation_event(occurrence, history_events)
    _validate_delivery_authorization(occurrence, projection, policy_revisions, resolvers)
    _validate_occurrence_coordinates(occurrence, event, projection)
    _validate_occurrence_evidence(occurrence, event)
    _validate_occurrence_required_refs(occurrence)
    return occurrence


def _exposure_binding_payload(
    authorization: ParticipantExposureAuthorizationRecord,
    occurrence: ParticipantExposureOccurrenceRecord | None,
    projection: ParticipantExposureProjection,
    *,
    policy_version: str,
    policy_digest: str,
) -> dict[str, object]:
    return {
        "item_ref": authorization.item_ref,
        "authorization_record_ref": authorization.authorization_record_ref,
        "source_ref": authorization.source_ref,
        "source_layer_ref": authorization.source_layer_ref,
        "participant_address": projection.participant_address,
        "episode_id": projection.episode_id,
        "audience_scope_ref": authorization.audience_scope_ref,
        "observation_point": projection.observation_point,
        "observation_order": projection.observation_order,
        "visibility_basis_ref": authorization.visibility_basis_ref,
        "projection_policy_ref": projection.projection_policy_ref,
        "projection_policy_revision": projection.projection_policy_revision,
        "exposure_policy_ref": projection.exposure_policy_ref,
        "exposure_policy_version": policy_version,
        "exposure_policy_digest": policy_digest,
        "operation": authorization.operation,
        "operation_basis_ref": authorization.operation_basis_ref,
        "actor_ref": authorization.actor_ref,
        "controller_ref": authorization.controller_ref,
        "authority_basis_ref": authorization.authority_basis_ref,
        "source_marking_definition_refs": list(authorization.source_marking_definition_refs),
        "result_marking_definition_refs": list(authorization.result_marking_definition_refs),
        "source_provenance_refs": list(authorization.source_provenance_refs),
        "result_provenance_refs": list(authorization.result_provenance_refs),
        "declassification_basis_ref": authorization.declassification_basis_ref,
        "redaction_policy_ref": authorization.redaction_policy_ref,
        "transformation_rule_ref": authorization.transformation_rule_ref,
        "evidence_refs": list(authorization.evidence_refs),
        "provenance_refs": list(authorization.provenance_refs),
        "loss_and_limitations": list(authorization.loss_and_limitations),
        "realization": (
            {
                "occurrence_ref": occurrence.occurrence_ref,
                "item_ref": occurrence.item_ref,
                "authorization_record_ref": occurrence.authorization_record_ref,
                "delivery_basis_ref": occurrence.delivery_basis_ref,
                "delivery_order": occurrence.delivery_order,
                "observation_ref": occurrence.observation_ref,
                "evidence_refs": list(occurrence.evidence_refs),
                "provenance_refs": list(occurrence.provenance_refs),
                "limitations": list(occurrence.limitations),
            }
            if occurrence is not None
            else None
        ),
    }


def _validate_binding_admission(
    item_ref: str,
    authorization: ParticipantExposureAuthorizationRecord,
    relation: Mapping[str, str],
    projection: ParticipantExposureProjection,
    policy: ParticipantExposurePolicyModel,
) -> None:
    if relation.get(item_ref) not in _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS:
        raise ValueError(f"exposure item {item_ref!r} is not participant-visible at observation_order")
    if not _policy_permits_item(policy, item_ref):
        raise ValueError(f"selected exposure policy does not permit item {item_ref!r}")
    carried_refs = (
        ("evidence_refs", authorization.evidence_refs, projection.evidence_refs),
        ("provenance_refs", authorization.provenance_refs, projection.provenance_refs),
        ("result markings", authorization.result_marking_definition_refs, projection.marking_definition_refs),
    )
    for label, authorization_refs, projection_refs in carried_refs:
        if not set(authorization_refs).issubset(projection_refs):
            raise ValueError(f"exposure authorization {item_ref!r} {label} must be carried by the surface")
    if (
        authorization.redaction_policy_ref is not None
        and authorization.redaction_policy_ref != projection.redaction_policy_ref
    ):
        raise ValueError(f"exposure authorization {item_ref!r} redaction policy must match the surface")


def _project_exposure_binding(
    item_ref: str,
    relation: Mapping[str, str],
    projection: ParticipantExposureProjection,
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    policy_revisions: Sequence[ParticipantExposurePolicyRevision],
    policy: ParticipantExposurePolicyModel,
    resolvers: ParticipantExposureResolvers,
) -> dict[str, object]:
    assessment = projection.exposure_assessments[item_ref]
    if assessment.item_ref != item_ref:
        raise ValueError(f"exposure assessment key {item_ref!r} must match its item_ref")
    authorization = _resolve_authorization(
        authorization_record_ref=assessment.authorization_record_ref,
        item_ref=assessment.item_ref,
        resolver=resolvers.authorization,
    )
    _validate_authorization_scope(
        authorization,
        projection,
        policy,
        observation_order=projection.observation_order,
        projection_policy_revision=projection.projection_policy_revision,
    )
    _validate_authorization_shape(authorization)
    _validate_exposure_operation(authorization)
    occurrence = _validate_realized_exposure(
        assessment,
        projection,
        history_events,
        policy_revisions,
        resolvers,
    )
    _validate_binding_admission(item_ref, authorization, relation, projection, policy)
    return _exposure_binding_payload(
        authorization,
        occurrence,
        projection,
        policy_version=policy.policy_version,
        policy_digest=policy.policy_digest,
    )


def project_participant_exposure_bindings(
    relation: Mapping[str, str],
    projection: ParticipantExposureProjection,
    entries: list[dict[str, object]],
    surface_affordances: list[str],
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    resolvers: ParticipantExposureResolvers,
) -> list[dict[str, object]]:
    """Resolve and serialize the governed exposure basis for every emitted ref."""

    policy_revisions = _resolved_projection_policy_revisions(projection, resolvers.projection_policy)
    _effective_projection_policy(
        policy_revisions,
        observation_order=projection.observation_order,
        expected_revision=projection.projection_policy_revision,
    )
    policy = _selected_exposure_policy(
        projection,
        resolvers.apparatus,
        observation_order=projection.observation_order,
    )
    expected = _serialized_surface_refs(projection, entries, surface_affordances)
    if set(projection.exposure_assessments) != expected:
        raise ValueError("exposure_assessments must exactly cover every serialized surface ref")
    return [
        _project_exposure_binding(
            item_ref,
            relation,
            projection,
            history_events,
            policy_revisions,
            policy,
            resolvers,
        )
        for item_ref in sorted(expected)
    ]
