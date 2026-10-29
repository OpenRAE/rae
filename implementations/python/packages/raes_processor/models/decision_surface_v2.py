"""State-cut-derived SEM-220 participant decision-surface v2 projection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from raes_contracts.contracts import (
    ParticipantDecisionSurfaceDerivationAnchorV2Model,
    ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model,
    ParticipantDecisionSurfaceSequenceCutModel,
    ParticipantDecisionSurfaceV2Model,
    ParticipantDecisionSurfaceViewV2Model,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.satisfiability import canonical_contract_digest

from .behavior_anchor_checks import participant_observation_effective_relation
from .behavior_anchor_index import _participant_behavior_history_anchor_indexes
from .behavior_ref_checks import _participant_behavior_initial_view_relation
from .behavior_resources import (
    _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS,
    ParticipantBehaviorSpecificationRuntime,
    ParticipantObservationBoundaryRuntime,
)
from .decision_surface import (
    ParticipantDecisionSurfaceActionAssessment,
    _action_affordance_addresses,
    _surface_action_assessments,
    _validate_participant_projection_scope,
)
from .decision_surface_anchor_v2 import (
    ParticipantBehaviorProjectionAnchorRequestV2,
    resolve_participant_behavior_projection_anchor_v2,
    resolve_participant_episode_readiness_anchor_v2,
)
from .history_event import ParticipantBehaviorHistoryEvent
from .participant_exposure import ParticipantExposureAssessment
from .participant_exposure_authority_v2 import ParticipantExposureResolversV2
from .participant_exposure_v2 import project_participant_exposure_bindings_v2
from .runtime_model import RuntimeModel


@dataclass(frozen=True)
class ParticipantDecisionSurfaceProjectionInputV2:
    """Governed inputs for one participant view at one decision epoch."""

    surface_id: str
    participant_address: str
    episode_id: str
    decision_epoch: int
    information_state_ref: str
    behavior_specification_address: str
    observation_boundary_address: str
    context_view_ref: str
    implementation_selection_ref: str
    decision_control_mode: str
    audience_scope_ref: str
    projection_policy_ref: str
    projection_policy_revision: str
    projection_policy_decision_ref: str
    exposure_policy_ref: str
    visibility_projection_ref: str
    participant_memory_scope: str
    memory_reset_authority_ref: str | None
    visible_context_refs: tuple[str, ...]
    action_assessments: Mapping[str, ParticipantDecisionSurfaceActionAssessment]
    exposure_assessments: Mapping[str, ParticipantExposureAssessment]
    form: Mapping[str, object]
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    marking_definition_refs: tuple[str, ...]
    redaction_policy_ref: str | None
    semantic_limitations: tuple[str, ...]
    derivation_anchor: ParticipantDecisionSurfaceDerivationAnchorV2Model

    @property
    def decision_cut_ref(self) -> str:
        return self.derivation_anchor.state_cut.cut_ref


def _resolve_projection_scope(
    runtime_model: RuntimeModel,
    projection: ParticipantDecisionSurfaceProjectionInputV2,
) -> tuple[ParticipantBehaviorSpecificationRuntime, ParticipantObservationBoundaryRuntime]:
    behavior = runtime_model.behavior_specifications.get(projection.behavior_specification_address)
    if behavior is None:
        raise ValueError("behavior_specification_address does not resolve in the compiled runtime model")
    if projection.participant_address not in behavior.participant_addresses:
        raise ValueError("participant_address is outside the compiled behavior specification")
    if projection.observation_boundary_address not in behavior.observation_boundary_addresses:
        raise ValueError("observation_boundary_address is outside the compiled behavior specification")
    _validate_participant_projection_scope(
        runtime_model,
        participant_address=projection.participant_address,
        boundary_address=projection.observation_boundary_address,
    )
    boundary = runtime_model.observation_boundaries.get(projection.observation_boundary_address)
    if boundary is None:
        raise ValueError("observation_boundary_address does not resolve in the compiled runtime model")
    return behavior, boundary


def _validate_anchor_projection_agreement(
    anchor: ParticipantDecisionSurfaceDerivationAnchorV2Model,
    projection: ParticipantDecisionSurfaceProjectionInputV2,
) -> None:
    coordinates = (
        ("participant_address", anchor.participant_address, projection.participant_address),
        ("episode_id", anchor.episode_id, projection.episode_id),
        ("decision_epoch", anchor.decision_epoch, projection.decision_epoch),
    )
    mismatched = [name for name, anchor_value, projected_value in coordinates if anchor_value != projected_value]
    if mismatched:
        raise ValueError("derivation anchor disagrees with projection input on: " + ", ".join(mismatched))


def _validate_anchor_assurance_carriage(
    anchor: ParticipantDecisionSurfaceDerivationAnchorV2Model,
    projection: ParticipantDecisionSurfaceProjectionInputV2,
) -> None:
    if not set(anchor.evidence_refs).issubset(projection.evidence_refs):
        raise ValueError("derivation anchor evidence must be carried by assurance")
    if not set(anchor.provenance_refs).issubset(projection.provenance_refs):
        raise ValueError("derivation anchor provenance must be carried by assurance")


def _resolve_readiness_projection_anchor(
    runtime_snapshot: RuntimeSnapshot,
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    projection: ParticipantDecisionSurfaceProjectionInputV2,
) -> None:
    anchor = projection.derivation_anchor
    assert isinstance(anchor, ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model)
    resolved = resolve_participant_episode_readiness_anchor_v2(
        runtime_snapshot,
        participant_address=projection.participant_address,
        decision_epoch=projection.decision_epoch,
        evidence_refs=anchor.evidence_refs,
        provenance_refs=anchor.provenance_refs,
    )
    if history_events:
        raise ValueError("initial decision epoch requires empty current-episode behavior history")
    if resolved != anchor:
        raise ValueError("episode-readiness anchor does not match the current trusted snapshot")


def _resolve_behavior_projection_anchor(
    runtime_model: RuntimeModel,
    runtime_snapshot: RuntimeSnapshot,
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    projection: ParticipantDecisionSurfaceProjectionInputV2,
) -> int:
    anchor = projection.derivation_anchor
    assert not isinstance(anchor, ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model)
    if not isinstance(anchor.state_cut, ParticipantDecisionSurfaceSequenceCutModel):
        raise ValueError("the reference projector cannot resolve a causal-frontier behavior anchor")
    request = ParticipantBehaviorProjectionAnchorRequestV2(
        participant_address=projection.participant_address,
        episode_id=projection.episode_id,
        decision_epoch=projection.decision_epoch,
        behavior_history_order=anchor.state_cut.anchor_order,
        evidence_refs=anchor.evidence_refs,
        provenance_refs=anchor.provenance_refs,
    )
    resolved = resolve_participant_behavior_projection_anchor_v2(
        runtime_snapshot,
        runtime_model=runtime_model,
        request=request,
    )
    if resolved != anchor:
        raise ValueError("behavior derivation anchor does not match the current trusted snapshot")
    current = tuple(
        ParticipantBehaviorHistoryEvent.from_payload(payload)
        for payload in runtime_snapshot.participant_behavior_history.get(projection.participant_address, [])
        if payload.get("episode_id") == projection.episode_id
    )
    if tuple(history_events) != current:
        raise ValueError("behavior projection requires the exact current behavior-history prefix")
    return anchor.state_cut.anchor_order


def _validate_and_resolve_anchor(
    runtime_model: RuntimeModel,
    runtime_snapshot: RuntimeSnapshot,
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    projection: ParticipantDecisionSurfaceProjectionInputV2,
) -> int | None:
    anchor = projection.derivation_anchor
    _validate_anchor_projection_agreement(anchor, projection)
    _validate_anchor_assurance_carriage(anchor, projection)
    if isinstance(anchor, ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model):
        _resolve_readiness_projection_anchor(runtime_snapshot, history_events, projection)
        return None
    return _resolve_behavior_projection_anchor(
        runtime_model,
        runtime_snapshot,
        history_events,
        projection,
    )


def _visibility_relation(
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    *,
    history_order: int | None,
    boundary_address: str,
    boundary: ParticipantObservationBoundaryRuntime,
) -> Mapping[str, str]:
    if history_order is None:
        return _participant_behavior_initial_view_relation(boundary)
    action_attempts, state_transitions, observations = _participant_behavior_history_anchor_indexes(history_events)
    relation, _ = participant_observation_effective_relation(
        observation_index=history_order,
        boundary_address=boundary_address,
        boundary=boundary,
        action_attempts=action_attempts,
        state_transitions=state_transitions,
        observations=observations,
    )
    return relation


def _validate_visible_refs(
    relation: Mapping[str, str],
    refs: Sequence[str],
    *,
    state_cut_ref: str,
) -> None:
    hidden = sorted(ref for ref in refs if relation.get(ref) not in _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS)
    if hidden:
        raise ValueError(f"refs are not participant-visible at state cut {state_cut_ref!r}: " + ", ".join(hidden))


def _project_action(
    runtime_model: RuntimeModel,
    behavior: ParticipantBehaviorSpecificationRuntime,
    relation: Mapping[str, str],
    assessment: ParticipantDecisionSurfaceActionAssessment,
    *,
    state_cut_ref: str,
    participant_address: str,
    observation_boundary_address: str,
) -> tuple[dict[str, object], tuple[str, ...]]:
    action_address = assessment.action_contract_address
    if action_address not in behavior.action_contract_addresses:
        raise ValueError(f"action {action_address!r} is outside the compiled behavior specification")
    _validate_participant_projection_scope(
        runtime_model, participant_address=participant_address, action_address=action_address
    )
    action_contract = runtime_model.action_contracts.get(action_address)
    if action_contract is None:
        raise ValueError(f"action {action_address!r} does not resolve in the compiled runtime model")
    if not action_contract.argument_shape_ref or assessment.selection_shape_ref != action_contract.argument_shape_ref:
        raise ValueError(f"action {action_address!r} selection shape does not match its compiled argument shape")
    affordances = _action_affordance_addresses(
        runtime_model,
        behavior_affordance_addresses=behavior.tool_affordance_addresses,
        action_address=action_address,
        participant_address=participant_address,
        observation_boundary_address=observation_boundary_address,
    )
    _validate_visible_refs(relation, (action_address, *affordances), state_cut_ref=state_cut_ref)
    dispositions = {relation[ref] for ref in (action_address, *affordances)}
    if len(dispositions) != 1:
        raise ValueError(f"action {action_address!r} has conflicting view dispositions at the state cut")
    visibility = next(iter(dispositions))
    return (
        {
            "entry_id": assessment.entry_id,
            "action_contract_address": action_address,
            "presentation_basis_ref": assessment.presentation_basis_ref,
            "visibility": visibility,
            "eligibility": assessment.eligibility,
            "eligibility_reason_refs": list(assessment.eligibility_reason_refs),
            "constraint_refs": list(assessment.constraint_refs),
            "selection_shape_ref": action_contract.argument_shape_ref,
            "support": assessment.support,
            "support_refs": list(assessment.support_refs),
            "affordance_refs": list(affordances),
            "realization_refs": list(assessment.realization_refs),
        },
        affordances,
    )


def project_participant_decision_surface_v2(
    runtime_model: RuntimeModel,
    runtime_snapshot: RuntimeSnapshot,
    *,
    history_events: Sequence[ParticipantBehaviorHistoryEvent],
    projection: ParticipantDecisionSurfaceProjectionInputV2,
    exposure_resolvers: ParticipantExposureResolversV2,
) -> ParticipantDecisionSurfaceV2Model:
    """Derive a projected v2 surface from an exact trusted state cut."""

    behavior, boundary = _resolve_projection_scope(runtime_model, projection)
    history_order = _validate_and_resolve_anchor(
        runtime_model,
        runtime_snapshot,
        history_events,
        projection,
    )
    relation = _visibility_relation(
        history_events,
        history_order=history_order,
        boundary_address=projection.observation_boundary_address,
        boundary=boundary,
    )
    _validate_visible_refs(
        relation,
        projection.visible_context_refs,
        state_cut_ref=projection.decision_cut_ref,
    )
    entries: list[dict[str, object]] = []
    affordances: list[str] = []
    for assessment in _surface_action_assessments(projection):
        entry, entry_affordances = _project_action(
            runtime_model,
            behavior,
            relation,
            assessment,
            state_cut_ref=projection.decision_cut_ref,
            participant_address=projection.participant_address,
            observation_boundary_address=projection.observation_boundary_address,
        )
        entries.append(entry)
        affordances.extend(entry_affordances)
    surface_affordances = list(dict.fromkeys(affordances))
    exposure_bindings, _ = project_participant_exposure_bindings_v2(
        relation,
        projection,
        entries,
        surface_affordances,
        exposure_resolvers,
    )
    participant_view_payload = {
        "surface_id": projection.surface_id,
        "participant_address": projection.participant_address,
        "episode_id": projection.episode_id,
        "decision_epoch": projection.decision_epoch,
        "information_state_ref": projection.information_state_ref,
        "context_view_ref": projection.context_view_ref,
        "decision_control_mode": projection.decision_control_mode,
        "visible_context_refs": list(projection.visible_context_refs),
        "action_entries": entries,
        "affordance_refs": surface_affordances,
        "form": dict(projection.form),
        "marking_definition_refs": list(projection.marking_definition_refs),
        "redaction_policy_ref": projection.redaction_policy_ref,
        "semantic_limitations": list(projection.semantic_limitations),
    }
    view_model = ParticipantDecisionSurfaceViewV2Model.model_validate(participant_view_payload)
    assurance_payload = {
        "participant_address": projection.participant_address,
        "episode_id": projection.episode_id,
        "decision_epoch": projection.decision_epoch,
        "behavior_specification_address": projection.behavior_specification_address,
        "observation_boundary_address": projection.observation_boundary_address,
        "implementation_selection_ref": projection.implementation_selection_ref,
        "audience_scope_ref": projection.audience_scope_ref,
        "projection_policy_ref": projection.projection_policy_ref,
        "projection_policy_revision": projection.projection_policy_revision,
        "projection_policy_decision_ref": projection.projection_policy_decision_ref,
        "exposure_policy_ref": projection.exposure_policy_ref,
        "visibility_projection_ref": projection.visibility_projection_ref,
        "participant_memory_scope": projection.participant_memory_scope,
        "memory_reset_authority_ref": projection.memory_reset_authority_ref,
        "participant_view_digest": canonical_contract_digest(view_model),
        "derivation_anchor": projection.derivation_anchor.model_dump(mode="json"),
        "exposure_bindings": exposure_bindings,
        "evidence_refs": list(projection.evidence_refs),
        "provenance_refs": list(projection.provenance_refs),
    }
    return ParticipantDecisionSurfaceV2Model.model_validate(
        {
            "schema_version": "participant-decision-surface/v2",
            "surface_state": "projected",
            "participant_view": participant_view_payload,
            "assurance": assurance_payload,
        }
    )
