"""End-to-end exact-cut, delivery, and admission tests for SEM-220 v2."""

from __future__ import annotations

from dataclasses import replace

import pytest
from participant_crossing_fixtures import StaticCrossingResolver, evidence, identity, policy_capable_target
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import (
    ParticipantDecisionSurfaceDeliveryV2Model,
    ParticipantDecisionSurfaceSelectionV2Model,
)
from raes_contracts.participant_binding_v2 import ParticipantDecisionSurfaceBindingResolversV2
from raes_contracts.participant_decision_surface_delivery import deliver_participant_decision_surface_v2
from raes_processor.models import (
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorProjectionAnchorRequestV2,
    ParticipantBehaviorRuntime,
    ParticipantDecisionSurfaceProjectionInputV2,
    ParticipantExposureAssessment,
    ParticipantExposureAuthorizationRecordV2,
    ParticipantExposurePolicyDecisionV2,
    ParticipantExposureResolversV2,
    project_participant_decision_surface_v2,
    resolve_participant_behavior_projection_anchor_v2,
    resolve_participant_episode_readiness_anchor_v2,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneRole
from test_sem_220_participant_decision_surface import (
    BEHAVIOR,
    BOUNDARY,
    EPISODE,
    PARTICIPANT,
    SCAN,
    SCAN_AFFORDANCE,
    SCAN_ENTRY,
    _admission_request,
    _assessment,
    _projection_implementation_selection,
    _resolved_selection,
    _runtime_model,
)


def _compiled_participant_behavior() -> ParticipantBehaviorRuntime:
    return ParticipantBehaviorRuntime(
        address=PARTICIPANT,
        name="red-agent",
        spec={},
        participant_name="red-agent",
        action_contract_addresses=(SCAN,),
        observation_boundary_addresses=(BOUNDARY,),
    )


def _authorization(
    item_ref: str,
    *,
    episode_id: str,
    decision_epoch: int,
    decision_cut_ref: str,
) -> ParticipantExposureAuthorizationRecordV2:
    return ParticipantExposureAuthorizationRecordV2(
        authorization_record_ref=f"exposure-authorizations.v2.{item_ref}.epoch-{decision_epoch}",
        item_ref=item_ref,
        source_ref=item_ref,
        source_layer_ref=f"source-layers.{item_ref}",
        participant_address=PARTICIPANT,
        episode_id=episode_id,
        audience_scope_ref="audience.participant.red-agent",
        decision_epoch=decision_epoch,
        decision_cut_ref=decision_cut_ref,
        implementation_selection_ref="participant-selections.red.agent.v2",
        projection_policy_ref="projection-policy.red.v2",
        projection_policy_revision="2",
        projection_policy_decision_ref=f"projection-policy-decisions.red.epoch-{decision_epoch}",
        exposure_policy_ref="exposure-policy.red.v2",
        exposure_policy_version="2",
        exposure_policy_digest="sha256:" + "4" * 64,
        visibility_basis_ref=f"visibility-bases.{item_ref}",
        operation="disclosure",
        operation_basis_ref=f"disclosures.{item_ref}.v2",
        actor_ref="actors.runtime-projector",
        controller_ref="controllers.red-agent",
        authority_basis_ref="authorities.red-agent.v2",
        backend_support_ref="backend-support.reference.v2",
        source_marking_definition_refs=("markings.participant-visible.v2",),
        result_marking_definition_refs=("markings.participant-visible.v2",),
        source_provenance_refs=("provenance.surface.v2",),
        result_provenance_refs=("provenance.surface.v2",),
        evidence_refs=("evidence.surface.v2",),
        provenance_refs=("provenance.surface.v2",),
        loss_and_limitations=("No known projection loss",),
    )


def _projection(
    anchor,
) -> ParticipantDecisionSurfaceProjectionInputV2:
    emitted_refs = ("context.public", SCAN, SCAN_AFFORDANCE)
    return ParticipantDecisionSurfaceProjectionInputV2(
        surface_id=f"decision-surfaces.red.{anchor.episode_id}.epoch-{anchor.decision_epoch}",
        participant_address=PARTICIPANT,
        episode_id=anchor.episode_id,
        decision_epoch=anchor.decision_epoch,
        information_state_ref=f"information-states.red.{anchor.episode_id}.epoch-{anchor.decision_epoch}",
        behavior_specification_address=BEHAVIOR,
        observation_boundary_address=BOUNDARY,
        context_view_ref=f"context-views.red.{anchor.episode_id}.epoch-{anchor.decision_epoch}",
        implementation_selection_ref="participant-selections.red.agent.v2",
        decision_control_mode="autonomous",
        audience_scope_ref="audience.participant.red-agent",
        projection_policy_ref="projection-policy.red.v2",
        projection_policy_revision="2",
        projection_policy_decision_ref=f"projection-policy-decisions.red.epoch-{anchor.decision_epoch}",
        exposure_policy_ref="exposure-policy.red.v2",
        visibility_projection_ref=f"visibility-projection.red.epoch-{anchor.decision_epoch}",
        participant_memory_scope="persistent_across_episodes",
        memory_reset_authority_ref=None,
        visible_context_refs=("context.public",),
        action_assessments={SCAN: _assessment(SCAN, entry_id=SCAN_ENTRY)},
        exposure_assessments={
            item_ref: ParticipantExposureAssessment(
                item_ref=item_ref,
                authorization_record_ref=f"exposure-authorizations.v2.{item_ref}.epoch-{anchor.decision_epoch}",
            )
            for item_ref in emitted_refs
        },
        form={
            "surface_form": "candidate_action_set",
            "selection_meaning_ref": "selection-meaning.candidate.v2",
            "candidate_entry_ids": [SCAN_ENTRY],
        },
        evidence_refs=tuple(dict.fromkeys((*anchor.evidence_refs, "evidence.policy.v2", "evidence.surface.v2"))),
        provenance_refs=tuple(
            dict.fromkeys((*anchor.provenance_refs, "provenance.policy.v2", "provenance.surface.v2"))
        ),
        marking_definition_refs=("markings.participant-visible.v2",),
        redaction_policy_ref="redaction.red.v2",
        semantic_limitations=("Projection is not delivery, selection, admission, execution, or outcome",),
        derivation_anchor=anchor,
    )


def _exposure_resolvers(
    projection: ParticipantDecisionSurfaceProjectionInputV2,
    *,
    resolved_cut_ref: str | None = None,
) -> tuple[ParticipantExposureResolversV2, object]:
    emitted_refs = tuple(projection.exposure_assessments)
    selection = _projection_implementation_selection(
        decision_control_mode=projection.decision_control_mode,
        permitted_refs=emitted_refs,
    ).model_copy(
        update={
            "participant_contract_versions": [
                "participant-behavior-history-event-stream-v1",
                "participant-decision-surface-v2",
            ],
            "exposure_policy": _projection_implementation_selection(
                decision_control_mode=projection.decision_control_mode,
                permitted_refs=emitted_refs,
            ).exposure_policy.model_copy(
                update={
                    "policy_id": projection.exposure_policy_ref,
                    "policy_version": "2",
                    "policy_digest": "sha256:" + "4" * 64,
                }
            ),
        }
    )
    authorizations = {
        item_ref: _authorization(
            item_ref,
            episode_id=projection.episode_id,
            decision_epoch=projection.decision_epoch,
            decision_cut_ref=projection.decision_cut_ref,
        )
        for item_ref in emitted_refs
    }
    policy_decision = ParticipantExposurePolicyDecisionV2(
        policy_ref=projection.projection_policy_ref,
        revision=projection.projection_policy_revision,
        decision_ref=projection.projection_policy_decision_ref,
        decision_cut_ref=resolved_cut_ref or projection.decision_cut_ref,
        evidence_refs=("evidence.policy.v2",),
        provenance_refs=("provenance.policy.v2",),
        limitations=("Policy decision is scoped to the identified state cut",),
    )
    return (
        ParticipantExposureResolversV2(
            apparatus=lambda **_: selection,
            projection_policy=lambda **_: policy_decision,
            authorization=lambda *, authorization_record_ref, item_ref, decision_cut_ref: (
                authorizations.get(item_ref)
                if decision_cut_ref == projection.decision_cut_ref
                and authorizations.get(item_ref) is not None
                and authorizations[item_ref].authorization_record_ref == authorization_record_ref
                else None
            ),
        ),
        selection,
    )


def _delivery(surface) -> ParticipantDecisionSurfaceDeliveryV2Model:
    return ParticipantDecisionSurfaceDeliveryV2Model(
        delivery_ref=f"decision-surface-deliveries.{surface.participant_view.surface_id}",
        surface_id=surface.participant_view.surface_id,
        participant_address=surface.participant_view.participant_address,
        episode_id=surface.participant_view.episode_id,
        decision_epoch=surface.participant_view.decision_epoch,
        participant_view_digest=surface.assurance.participant_view_digest,
        delivery_basis="emission_is_delivery",
        delivery_cut_ref=surface.assurance.derivation_anchor.state_cut.cut_ref,
        delivery_authorization_ref=f"delivery-authorizations.epoch-{surface.participant_view.decision_epoch}",
        delivery_policy_decision_ref=f"delivery-policy-decisions.epoch-{surface.participant_view.decision_epoch}",
        observation_ref=f"participant-view-observations.epoch-{surface.participant_view.decision_epoch}",
        evidence_refs=("evidence.surface-delivery.v2",),
        provenance_refs=("provenance.surface-delivery.v2",),
        limitations=("Synchronous reference-runtime delivery",),
    )


def _initial_surface(control: RuntimeControlPlane | None = None):
    control = control or RuntimeControlPlane(create_stub_target())
    control.initialize_participant_episode(PARTICIPANT, episode_id=EPISODE)
    snapshot = control.get_snapshot().snapshot
    anchor = resolve_participant_episode_readiness_anchor_v2(
        snapshot,
        participant_address=PARTICIPANT,
        decision_epoch=0,
        evidence_refs=("evidence.episode-running",),
        provenance_refs=("provenance.runtime-control-plane",),
    )
    projection = _projection(anchor)
    resolvers, selection = _exposure_resolvers(projection)
    surface = project_participant_decision_surface_v2(
        _runtime_model(),
        snapshot,
        history_events=(),
        projection=projection,
        exposure_resolvers=resolvers,
    )
    return control, surface, selection


def _selection_for(delivered) -> ParticipantDecisionSurfaceSelectionV2Model:
    assert delivered.delivery is not None
    return ParticipantDecisionSurfaceSelectionV2Model(
        surface_id=delivered.participant_view.surface_id,
        decision_epoch=delivered.participant_view.decision_epoch,
        participant_view_digest=delivered.assurance.participant_view_digest,
        delivery_ref=delivered.delivery.delivery_ref,
        action_contract_address=SCAN,
        argument_shape_ref=delivered.participant_view.action_entries[0].selection_shape_ref,
        proposal_ref=f"proposals.scan.v2.{delivered.participant_view.episode_id}",
        arguments={},
    )


def _governed_selection_case():
    resolver = StaticCrossingResolver()
    control, projected, implementation_selection = _initial_surface(
        RuntimeControlPlane(
            policy_capable_target(),
            crossing_policy_resolver=resolver,
            enforce_final_sink_flow_control=False,
        )
    )
    delivery = _delivery(projected)
    delivered = deliver_participant_decision_surface_v2(
        projected, delivery_ref=delivery.delivery_ref, resolver=lambda **_: delivery
    )
    return control, delivered, implementation_selection, delivery


def _admit_governed_selection(control, delivered, implementation_selection, delivery, *, selection=None, **context):
    return control.admit_participant_decision_surface_selection_v2(
        replace(_compiled_participant_behavior(), authority_anchor_addresses=("authority:red-team",)),
        surface=delivered,
        selection=selection or _selection_for(delivered),
        admission_request=replace(_admission_request(), implementation_selection=implementation_selection),
        resolvers=ParticipantDecisionSurfaceBindingResolversV2(
            argument_shape=_resolved_selection,
            apparatus=lambda **_: implementation_selection,
            delivery=lambda **_: delivery,
        ),
        **context,
    )


def test_v2_selection_forwards_authenticated_context_to_governed_admission() -> None:
    control, delivered, implementation_selection, delivery = _governed_selection_case()
    receipt = _admit_governed_selection(
        control,
        delivered,
        implementation_selection,
        delivery,
        identity=identity(participant_address=PARTICIPANT),
        crossing_evidence=evidence(),
    )

    assert receipt.accepted is True
    crossing = control.get_snapshot().snapshot.participant_crossing_history[PARTICIPANT][0]
    assert crossing["participant_address"] == PARTICIPANT
    assert crossing["episode_id"] == EPISODE
    assert crossing["occurrence"]["interaction_kind"] == "candidate-selection"
    assert crossing["occurrence"]["action_or_projection_ref"] == SCAN
    assert len(control.get_snapshot().snapshot.participant_behavior_history[PARTICIPANT]) == 3


@pytest.mark.parametrize("missing", ("identity", "crossing_evidence"))
def test_v2_governed_admission_requires_caller_context(missing: str) -> None:
    control, delivered, implementation_selection, delivery = _governed_selection_case()
    context = {
        "identity": identity(participant_address=PARTICIPANT),
        "crossing_evidence": evidence(),
    }
    context.pop(missing)

    with pytest.raises((PermissionError, ValueError)):
        _admit_governed_selection(control, delivered, implementation_selection, delivery, **context)

    assert control.get_snapshot().snapshot.participant_behavior_history.get(PARTICIPANT, []) == []


@pytest.mark.parametrize("unauthorized", ("wrong_target", "wrong_role", "wrong_participant"))
def test_v2_governed_admission_rejects_unauthorized_caller(unauthorized: str) -> None:
    control, delivered, implementation_selection, delivery = _governed_selection_case()
    caller = identity(participant_address=PARTICIPANT)
    if unauthorized == "wrong_target":
        caller = replace(caller, target_name="another-target")
    elif unauthorized == "wrong_role":
        caller = replace(caller, roles=frozenset({ControlPlaneRole.AUDITOR}))
    else:
        caller = identity(participant_address="participant.behavior.other")

    with pytest.raises(PermissionError):
        _admit_governed_selection(
            control,
            delivered,
            implementation_selection,
            delivery,
            identity=caller,
            crossing_evidence=evidence(),
        )

    assert control.get_snapshot().snapshot.participant_behavior_history.get(PARTICIPANT, []) == []


def test_v2_governed_admission_rejects_a_stale_episode_cut() -> None:
    control, delivered, implementation_selection, delivery = _governed_selection_case()
    control.reset_participant_episode(PARTICIPANT, episode_id=f"{EPISODE}-reset")

    receipt = _admit_governed_selection(
        control,
        delivered,
        implementation_selection,
        delivery,
        identity=identity(participant_address=PARTICIPANT),
        crossing_evidence=evidence(),
    )

    assert receipt.accepted is False
    assert control.get_snapshot().snapshot.participant_behavior_history.get(PARTICIPANT, []) == []


def test_v2_governed_admission_rejects_mismatched_selected_action() -> None:
    control, delivered, implementation_selection, delivery = _governed_selection_case()
    selection = _selection_for(delivered).model_copy(
        update={"action_contract_address": "participant.action-contract.other"}
    )

    receipt = _admit_governed_selection(
        control,
        delivered,
        implementation_selection,
        delivery,
        selection=selection,
        identity=identity(participant_address=PARTICIPANT),
        crossing_evidence=evidence(),
    )

    assert receipt.accepted is False
    assert control.get_snapshot().snapshot.participant_behavior_history.get(PARTICIPANT, []) == []


def test_initial_epoch_projects_delivers_and_admits_only_the_exact_view() -> None:
    control, projected, implementation_selection = _initial_surface()
    delivery = _delivery(projected)
    delivered = deliver_participant_decision_surface_v2(
        projected,
        delivery_ref=delivery.delivery_ref,
        resolver=lambda **_: delivery,
    )
    selection = ParticipantDecisionSurfaceSelectionV2Model(
        surface_id=delivered.participant_view.surface_id,
        decision_epoch=0,
        participant_view_digest=delivered.assurance.participant_view_digest,
        delivery_ref=delivery.delivery_ref,
        action_contract_address=SCAN,
        argument_shape_ref=delivered.participant_view.action_entries[0].selection_shape_ref,
        proposal_ref="proposals.scan.v2.1",
        arguments={},
    )
    request = replace(_admission_request(), implementation_selection=implementation_selection)

    receipt = control.admit_participant_decision_surface_selection_v2(
        _compiled_participant_behavior(),
        surface=delivered,
        selection=selection,
        admission_request=request,
        resolvers=ParticipantDecisionSurfaceBindingResolversV2(
            argument_shape=_resolved_selection,
            apparatus=lambda **_: implementation_selection,
            delivery=lambda **_: delivery,
        ),
    )

    assert receipt.accepted is True
    assert delivered.participant_view.decision_epoch == 0
    assert delivered.assurance.derivation_anchor.state_cut.history_domain == "participant_episode_lifecycle"
    assert len(control.get_snapshot().snapshot.participant_behavior_history[PARTICIPANT]) == 3

    replay = control.admit_participant_decision_surface_selection_v2(
        _compiled_participant_behavior(),
        surface=delivered,
        selection=selection,
        admission_request=request,
        resolvers=ParticipantDecisionSurfaceBindingResolversV2(
            argument_shape=_resolved_selection,
            apparatus=lambda **_: implementation_selection,
            delivery=lambda **_: delivery,
        ),
    )
    assert replay.accepted is False
    assert len(control.get_snapshot().snapshot.participant_behavior_history[PARTICIPANT]) == 3


def test_v2_admission_requires_the_participant_implementation_to_declare_v2_support() -> None:
    control, projected, implementation_selection = _initial_surface()
    delivery = _delivery(projected)
    delivered = deliver_participant_decision_surface_v2(
        projected,
        delivery_ref=delivery.delivery_ref,
        resolver=lambda **_: delivery,
    )
    undeclared = implementation_selection.model_copy(
        update={"participant_contract_versions": ["participant-behavior-history-event-stream-v1"]}
    )

    rejected = control.admit_participant_decision_surface_selection_v2(
        _compiled_participant_behavior(),
        surface=delivered,
        selection=_selection_for(delivered),
        admission_request=replace(_admission_request(), implementation_selection=undeclared),
        resolvers=ParticipantDecisionSurfaceBindingResolversV2(
            argument_shape=_resolved_selection,
            apparatus=lambda **_: undeclared,
            delivery=lambda **_: delivery,
        ),
    )

    assert rejected.accepted is False
    assert control.get_snapshot().snapshot.participant_behavior_history.get(PARTICIPANT, []) == []


@pytest.mark.parametrize("transition", ("reset", "restart"))
def test_reset_and_restart_invalidate_prior_surfaces_and_create_a_new_epoch_zero(transition: str) -> None:
    control, projected, implementation_selection = _initial_surface()
    delivery = _delivery(projected)
    delivered = deliver_participant_decision_surface_v2(
        projected,
        delivery_ref=delivery.delivery_ref,
        resolver=lambda **_: delivery,
    )
    if transition == "restart":
        control.terminate_participant_episode(PARTICIPANT)
        control.restart_participant_episode(PARTICIPANT, episode_id=f"{EPISODE}-restarted")
    else:
        control.reset_participant_episode(PARTICIPANT, episode_id=f"{EPISODE}-reset")

    rejected = control.admit_participant_decision_surface_selection_v2(
        _compiled_participant_behavior(),
        surface=delivered,
        selection=_selection_for(delivered),
        admission_request=replace(_admission_request(), implementation_selection=implementation_selection),
        resolvers=ParticipantDecisionSurfaceBindingResolversV2(
            argument_shape=_resolved_selection,
            apparatus=lambda **_: implementation_selection,
            delivery=lambda **_: delivery,
        ),
    )
    snapshot = control.get_snapshot().snapshot
    new_episode_id = snapshot.participant_episode_results[PARTICIPANT]["episode_id"]
    anchor = resolve_participant_episode_readiness_anchor_v2(
        snapshot,
        participant_address=PARTICIPANT,
        decision_epoch=0,
        evidence_refs=(f"evidence.{transition}.episode-running",),
        provenance_refs=("provenance.runtime-control-plane",),
    )
    projection = _projection(anchor)
    exposure_resolvers, _ = _exposure_resolvers(projection)
    new_surface = project_participant_decision_surface_v2(
        _runtime_model(),
        snapshot,
        history_events=(),
        projection=projection,
        exposure_resolvers=exposure_resolvers,
    )

    assert rejected.accepted is False
    assert new_surface.participant_view.episode_id == new_episode_id
    assert new_surface.participant_view.decision_epoch == 0
    assert new_surface.assurance.participant_memory_scope == "persistent_across_episodes"


def test_reset_preserves_prior_behavior_evidence_while_the_new_episode_starts_at_epoch_zero() -> None:
    control, _, implementation_selection = _initial_surface()
    admitted = control.admit_participant_action(
        _compiled_participant_behavior(),
        replace(_admission_request(), implementation_selection=implementation_selection),
    )
    assert admitted.accepted is True
    assert len(control.get_snapshot().snapshot.participant_behavior_history[PARTICIPANT]) == 3

    control.reset_participant_episode(PARTICIPANT, episode_id=f"{EPISODE}-memory-preserved")
    snapshot = control.get_snapshot().snapshot
    assert len(snapshot.participant_behavior_history[PARTICIPANT]) == 3

    anchor = resolve_participant_episode_readiness_anchor_v2(
        snapshot,
        participant_address=PARTICIPANT,
        decision_epoch=0,
        evidence_refs=("evidence.reset.episode-running",),
        provenance_refs=("provenance.runtime-control-plane",),
    )
    projection = _projection(anchor)
    exposure_resolvers, _ = _exposure_resolvers(projection)
    surface = project_participant_decision_surface_v2(
        _runtime_model(),
        snapshot,
        history_events=(),
        projection=projection,
        exposure_resolvers=exposure_resolvers,
    )

    assert surface.participant_view.decision_epoch == 0
    assert surface.assurance.participant_memory_scope == "persistent_across_episodes"
    assert surface.assurance.memory_reset_authority_ref is None


def test_projection_policy_must_be_the_decision_at_the_exact_state_cut() -> None:
    control = RuntimeControlPlane(create_stub_target())
    control.initialize_participant_episode(PARTICIPANT, episode_id=EPISODE)
    snapshot = control.get_snapshot().snapshot
    anchor = resolve_participant_episode_readiness_anchor_v2(
        snapshot,
        participant_address=PARTICIPANT,
        decision_epoch=0,
        evidence_refs=("evidence.episode-running",),
        provenance_refs=("provenance.runtime-control-plane",),
    )
    projection = _projection(anchor)
    resolvers, _ = _exposure_resolvers(projection, resolved_cut_ref="participant-state-cuts.stale")
    runtime_model = _runtime_model()

    with pytest.raises(ValueError, match="decision_cut_ref"):
        project_participant_decision_surface_v2(
            runtime_model,
            snapshot,
            history_events=(),
            projection=projection,
            exposure_resolvers=resolvers,
        )


def test_delivery_fails_closed_when_no_delivery_time_authority_resolves() -> None:
    _, projected, _ = _initial_surface()
    delivery = _delivery(projected)

    with pytest.raises(ValueError, match="delivery_ref did not resolve"):
        deliver_participant_decision_surface_v2(
            projected,
            delivery_ref=delivery.delivery_ref,
            resolver=lambda **_: None,
        )


def test_admission_rejects_a_surface_whose_derivation_cut_became_stale() -> None:
    control, projected, implementation_selection = _initial_surface()
    delivery = _delivery(projected)
    delivered = deliver_participant_decision_surface_v2(
        projected,
        delivery_ref=delivery.delivery_ref,
        resolver=lambda **_: delivery,
    )
    control.admit_participant_action(
        _compiled_participant_behavior(),
        replace(_admission_request(), implementation_selection=implementation_selection),
    )
    selection = ParticipantDecisionSurfaceSelectionV2Model(
        surface_id=delivered.participant_view.surface_id,
        decision_epoch=0,
        participant_view_digest=delivered.assurance.participant_view_digest,
        delivery_ref=delivery.delivery_ref,
        action_contract_address=SCAN,
        argument_shape_ref=delivered.participant_view.action_entries[0].selection_shape_ref,
        proposal_ref="proposals.scan.v2.stale",
        arguments={},
    )

    rejected = control.admit_participant_decision_surface_selection_v2(
        _compiled_participant_behavior(),
        surface=delivered,
        selection=selection,
        admission_request=replace(_admission_request(), implementation_selection=implementation_selection),
        resolvers=ParticipantDecisionSurfaceBindingResolversV2(
            argument_shape=_resolved_selection,
            apparatus=lambda **_: implementation_selection,
            delivery=lambda **_: delivery,
        ),
    )

    assert rejected.accepted is False
    assert len(control.get_snapshot().snapshot.participant_behavior_history[PARTICIPANT]) == 3


def test_later_epoch_uses_behavior_cut_without_reinterpreting_decision_epoch_as_history_order() -> None:
    control, _, implementation_selection = _initial_surface()
    control.admit_participant_action(
        _compiled_participant_behavior(),
        replace(_admission_request(), implementation_selection=implementation_selection),
    )
    snapshot = control.get_snapshot().snapshot
    history = tuple(
        ParticipantBehaviorHistoryEvent.from_payload(payload)
        for payload in snapshot.participant_behavior_history[PARTICIPANT]
    )
    runtime_model = _runtime_model()
    boundary = runtime_model.observation_boundaries[BOUNDARY]
    runtime_model = replace(
        runtime_model,
        observation_boundaries={
            BOUNDARY: replace(
                boundary,
                view_transitions=(),
                view_relation_timeline=(boundary.view_relation_timeline[0],),
            )
        },
    )
    anchor = resolve_participant_behavior_projection_anchor_v2(
        snapshot,
        runtime_model=runtime_model,
        request=ParticipantBehaviorProjectionAnchorRequestV2(
            participant_address=PARTICIPANT,
            episode_id=EPISODE,
            decision_epoch=1,
            behavior_history_order=2,
            evidence_refs=("evidence.scan-result",),
            provenance_refs=("provenance.runtime-control-plane",),
        ),
    )
    projection = _projection(anchor)
    resolvers, _ = _exposure_resolvers(projection)

    surface = project_participant_decision_surface_v2(
        runtime_model,
        snapshot,
        history_events=history,
        projection=projection,
        exposure_resolvers=resolvers,
    )

    assert surface.participant_view.decision_epoch == 1
    assert surface.assurance.derivation_anchor.state_cut.anchor_order == 2
    assert surface.assurance.derivation_anchor.state_cut.history_prefix_length == 3
