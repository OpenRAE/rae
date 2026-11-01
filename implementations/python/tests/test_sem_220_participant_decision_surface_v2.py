from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import (
    ParticipantDecisionSurfaceAssuranceV2Model,
    ParticipantDecisionSurfaceBehaviorAnchorV2Model,
    ParticipantDecisionSurfaceCausalCutModel,
    ParticipantDecisionSurfaceDeliveryV2Model,
    ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model,
    ParticipantDecisionSurfaceExposureBindingV2Model,
    ParticipantDecisionSurfaceSelectionV2Model,
    ParticipantDecisionSurfaceSequenceCutModel,
    ParticipantDecisionSurfaceV2Model,
    ParticipantDecisionSurfaceViewV2Model,
)
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "control-plane" / "participant-decision-surface-v2"


def _sequence_cut() -> ParticipantDecisionSurfaceSequenceCutModel:
    return ParticipantDecisionSurfaceSequenceCutModel(
        cut_kind="sequence_prefix",
        cut_ref="participant-state-cuts.red.episode-1.initial",
        history_domain="participant_episode_lifecycle",
        order_model="control_plane_order",
        anchor_event_ref="participant-episode-event:sha256:" + "a" * 64,
        anchor_order=1,
        history_prefix_length=2,
        predecessor_event_refs=["participant-episode-event:sha256:" + "b" * 64],
    )


def _anchor() -> ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model:
    return ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model(
        anchor_kind="episode_readiness",
        participant_address="participants.red",
        episode_id="episode-1",
        decision_epoch=0,
        event_ref="participant-episode-event:sha256:" + "a" * 64,
        state_cut=_sequence_cut(),
        event_type="episode_running",
        episode_sequence_number=0,
        evidence_refs=["evidence.episode-running"],
        provenance_refs=[
            "provenance.episode-running",
            "participant-episode-event:sha256:" + "a" * 64,
        ],
    )


def _view() -> ParticipantDecisionSurfaceViewV2Model:
    return ParticipantDecisionSurfaceViewV2Model(
        surface_id="decision-surfaces.red.episode-1.epoch-0",
        participant_address="participants.red",
        episode_id="episode-1",
        decision_epoch=0,
        information_state_ref="information-states.red.episode-1.epoch-0",
        context_view_ref="context-views.red.episode-1.epoch-0",
        decision_control_mode="agent",
        visible_context_refs=["context.network-segment"],
        action_entries=[
            {
                "entry_id": "scan",
                "action_contract_address": "actions.scan",
                "presentation_basis_ref": "presentation.scan",
                "visibility": "observable",
                "eligibility": "eligible",
                "eligibility_reason_refs": [],
                "constraint_refs": ["constraints.scan"],
                "selection_shape_ref": "argument-shapes.scan",
                "support": "supported",
                "support_refs": ["support.scan"],
                "affordance_refs": ["affordances.scanner"],
                "realization_refs": ["realizations.scan"],
            }
        ],
        affordance_refs=["affordances.scanner"],
        form={
            "surface_form": "candidate_action_set",
            "selection_meaning_ref": "selection-meaning.candidate.v1",
            "candidate_entry_ids": ["scan"],
        },
        marking_definition_refs=["markings.participant"],
        redaction_policy_ref="redaction.participant",
        semantic_limitations=["limitations.bounded-surface"],
    )


def _binding(
    item_ref: str = "actions.scan",
    *,
    suffix: str = "scan",
) -> ParticipantDecisionSurfaceExposureBindingV2Model:
    return ParticipantDecisionSurfaceExposureBindingV2Model(
        item_ref=item_ref,
        authorization_record_ref=f"authorizations.{suffix}",
        source_ref=item_ref,
        source_layer_ref="source-layer.scenario",
        participant_address="participants.red",
        episode_id="episode-1",
        audience_scope_ref="audiences.red",
        decision_epoch=0,
        decision_cut_ref="participant-state-cuts.red.episode-1.initial",
        visibility_basis_ref="view-rules.scan",
        projection_policy_ref="projection-policies.red",
        projection_policy_revision="revision-1",
        projection_policy_decision_ref="policy-decisions.red.initial",
        exposure_policy_ref="exposure-policies.red",
        exposure_policy_version="1",
        exposure_policy_digest="sha256:" + "c" * 64,
        operation="projection",
        operation_basis_ref="operations.project",
        actor_ref="actors.runtime",
        controller_ref="controllers.runtime",
        authority_basis_ref="authority.participant",
        source_marking_definition_refs=["markings.participant"],
        result_marking_definition_refs=["markings.participant"],
        source_provenance_refs=[f"provenance.{suffix}"],
        result_provenance_refs=[f"provenance.{suffix}"],
        evidence_refs=[f"evidence.authorization.{suffix}"],
        provenance_refs=[f"provenance.{suffix}"],
        loss_and_limitations=["limitations.authorization"],
    )


def _assurance(view: ParticipantDecisionSurfaceViewV2Model) -> ParticipantDecisionSurfaceAssuranceV2Model:
    return ParticipantDecisionSurfaceAssuranceV2Model(
        participant_address=view.participant_address,
        episode_id=view.episode_id,
        decision_epoch=view.decision_epoch,
        behavior_specification_address="behavior-specifications.red",
        observation_boundary_address="observation-boundaries.red",
        implementation_selection_ref="implementation-selections.red",
        audience_scope_ref="audiences.red",
        projection_policy_ref="projection-policies.red",
        projection_policy_revision="revision-1",
        projection_policy_decision_ref="policy-decisions.red.initial",
        exposure_policy_ref="exposure-policies.red",
        visibility_projection_ref="visibility-projections.red.initial",
        participant_memory_scope="persistent_across_episodes",
        memory_reset_authority_ref=None,
        participant_view_digest=canonical_contract_digest(view),
        derivation_anchor=_anchor(),
        exposure_bindings=[
            _binding("context.network-segment", suffix="context.network-segment"),
            _binding(),
            _binding("affordances.scanner", suffix="affordances.scanner"),
        ],
        evidence_refs=[
            "evidence.episode-running",
            "evidence.authorization.context.network-segment",
            "evidence.authorization.scan",
            "evidence.authorization.affordances.scanner",
        ],
        provenance_refs=[
            "provenance.episode-running",
            "participant-episode-event:sha256:" + "a" * 64,
            "provenance.context.network-segment",
            "provenance.scan",
            "provenance.affordances.scanner",
        ],
    )


def _projected_surface() -> ParticipantDecisionSurfaceV2Model:
    view = _view()
    return ParticipantDecisionSurfaceV2Model(
        schema_version="participant-decision-surface/v2",
        surface_state="projected",
        participant_view=view,
        assurance=_assurance(view),
    )


def _delivery(surface: ParticipantDecisionSurfaceV2Model) -> ParticipantDecisionSurfaceDeliveryV2Model:
    view = surface.participant_view
    return ParticipantDecisionSurfaceDeliveryV2Model(
        delivery_ref="decision-surface-deliveries.red.episode-1.epoch-0",
        surface_id=view.surface_id,
        participant_address=view.participant_address,
        episode_id=view.episode_id,
        decision_epoch=view.decision_epoch,
        participant_view_digest=surface.assurance.participant_view_digest,
        delivery_basis="emission_is_delivery",
        delivery_cut_ref=surface.assurance.derivation_anchor.state_cut.cut_ref,
        delivery_authorization_ref="delivery-authorizations.red.episode-1.epoch-0",
        delivery_policy_decision_ref="delivery-policy-decisions.red.episode-1.epoch-0",
        observation_ref="participant-observations.red.episode-1.epoch-0",
        evidence_refs=["evidence.surface-delivery"],
        provenance_refs=["provenance.surface-delivery"],
        limitations=["limitations.synchronous-delivery"],
    )


def test_v2_separates_participant_view_from_derivation_and_evidence() -> None:
    surface = _projected_surface()

    participant_payload = surface.participant_view.model_dump(mode="json")
    assurance_payload = surface.assurance.model_dump(mode="json")

    assert participant_payload["decision_epoch"] == 0
    assert "derivation_anchor" not in participant_payload
    assert "evidence_refs" not in participant_payload
    assert "provenance_refs" not in participant_payload
    assert assurance_payload["derivation_anchor"]["state_cut"]["anchor_order"] == 1
    assert assurance_payload["participant_view_digest"] == canonical_contract_digest(surface.participant_view)


def test_v2_rejects_a_sequence_cut_whose_prefix_does_not_end_at_its_anchor() -> None:
    payload = _sequence_cut().model_dump(mode="json")
    payload["history_prefix_length"] = 1

    with pytest.raises(ValidationError, match="history_prefix_length must equal anchor_order \\+ 1"):
        ParticipantDecisionSurfaceSequenceCutModel.model_validate(payload)


def test_v2_causal_cut_preserves_a_frontier_without_inventing_a_scalar_order() -> None:
    frontier = [
        "participant-behavior-event:sha256:" + "a" * 64,
        "participant-behavior-event:sha256:" + "b" * 64,
    ]
    cut = ParticipantDecisionSurfaceCausalCutModel(
        cut_kind="causal_frontier",
        cut_ref="participant-state-cuts.red.concurrent",
        history_domain="participant_behavior_history",
        order_model="causal_partial_order",
        frontier_event_refs=frontier,
        predecessor_closure_ref="participant-state-cut-closures.red.concurrent",
    )
    anchor = ParticipantDecisionSurfaceBehaviorAnchorV2Model(
        anchor_kind="behavior_event",
        participant_address="participants.red",
        episode_id="episode-1",
        decision_epoch=1,
        event_ref=frontier[0],
        state_cut=cut,
        event_type="observation_emitted",
        action_instance_id="scan-1",
        evidence_refs=["evidence.concurrent"],
        provenance_refs=[frontier[0]],
    )

    payload = anchor.model_dump(mode="json")
    assert payload["state_cut"]["frontier_event_refs"] == frontier
    assert "anchor_order" not in payload["state_cut"]


def test_v2_rejects_assurance_bound_to_a_different_decision_epoch() -> None:
    surface = _projected_surface()
    payload = surface.model_dump(mode="json")
    payload["assurance"]["decision_epoch"] = 1

    with pytest.raises(ValidationError, match="decision_epoch"):
        ParticipantDecisionSurfaceV2Model.model_validate(payload)


def test_v2_rejects_a_participant_view_digest_mismatch() -> None:
    surface = _projected_surface()
    payload = surface.model_dump(mode="json")
    payload["assurance"]["participant_view_digest"] = "sha256:" + "d" * 64

    with pytest.raises(ValidationError, match="participant_view_digest"):
        ParticipantDecisionSurfaceV2Model.model_validate(payload)


def test_v2_memory_scope_does_not_treat_episode_reset_as_memory_erasure() -> None:
    surface = _projected_surface()

    assert surface.assurance.participant_memory_scope == "persistent_across_episodes"
    assert surface.assurance.memory_reset_authority_ref is None

    payload = surface.model_dump(mode="json")
    payload["assurance"]["participant_memory_scope"] = "episode_local_reset"
    with pytest.raises(ValidationError, match="requires memory_reset_authority_ref"):
        ParticipantDecisionSurfaceV2Model.model_validate(payload)


def test_v2_episode_local_memory_scope_requires_and_carries_reset_authority() -> None:
    surface = _projected_surface()
    payload = surface.model_dump(mode="json")
    payload["assurance"]["participant_memory_scope"] = "episode_local_reset"
    payload["assurance"]["memory_reset_authority_ref"] = "memory-reset-authorities.red.episode-1"

    local = ParticipantDecisionSurfaceV2Model.model_validate(payload)
    assert local.assurance.memory_reset_authority_ref == "memory-reset-authorities.red.episode-1"

    payload["assurance"]["participant_memory_scope"] = "persistent_across_episodes"
    with pytest.raises(ValidationError, match="must not claim a reset authority"):
        ParticipantDecisionSurfaceV2Model.model_validate(payload)


def test_v2_requires_delivery_only_for_the_delivered_lifecycle_state() -> None:
    projected = _projected_surface()
    delivered_payload = projected.model_dump(mode="json")
    delivered_payload["surface_state"] = "delivered"

    with pytest.raises(ValidationError, match="delivered surfaces require delivery"):
        ParticipantDecisionSurfaceV2Model.model_validate(delivered_payload)

    projected_payload = projected.model_dump(mode="json")
    projected_payload["delivery"] = _delivery(projected).model_dump(mode="json")
    with pytest.raises(ValidationError, match="projected surfaces must not carry delivery"):
        ParticipantDecisionSurfaceV2Model.model_validate(projected_payload)


def test_v2_delivery_must_bind_the_exact_participant_view_digest_and_epoch() -> None:
    projected = _projected_surface()
    payload = projected.model_dump(mode="json")
    payload["surface_state"] = "delivered"
    delivery = _delivery(projected).model_dump(mode="json")
    delivery["decision_epoch"] = 1
    payload["delivery"] = delivery

    with pytest.raises(ValidationError, match="delivery disagrees with the participant view"):
        ParticipantDecisionSurfaceV2Model.model_validate(payload)


def test_v2_selection_binds_delivery_and_the_canonical_participant_view() -> None:
    projected = _projected_surface()
    delivered_payload = projected.model_dump(mode="json")
    delivered_payload["surface_state"] = "delivered"
    delivered_payload["delivery"] = _delivery(projected).model_dump(mode="json")
    delivered = ParticipantDecisionSurfaceV2Model.model_validate(delivered_payload)

    selection = ParticipantDecisionSurfaceSelectionV2Model(
        surface_id=delivered.participant_view.surface_id,
        decision_epoch=delivered.participant_view.decision_epoch,
        participant_view_digest=delivered.assurance.participant_view_digest,
        delivery_ref=delivered.delivery.delivery_ref if delivered.delivery else "",
        action_contract_address="actions.scan",
        argument_shape_ref="argument-shapes.scan",
        proposal_ref="proposals.scan.1",
        arguments={},
    )

    assert selection.delivery_ref == "decision-surface-deliveries.red.episode-1.epoch-0"
    assert "observation_order" not in selection.model_dump(mode="json")


def test_v2_is_closed_against_legacy_or_hidden_order_fields() -> None:
    payload = _projected_surface().model_dump(mode="json")
    payload["observation_order"] = 0
    payload["participant_view"]["anchor_order"] = 1
    invalid_payload = copy.deepcopy(payload)

    with pytest.raises(ValidationError):
        ParticipantDecisionSurfaceV2Model.model_validate(invalid_payload)


def test_v2_published_schema_and_fixtures_match_the_contract_model() -> None:
    schema = schema_bundle()["participant-decision-surface-v2"]
    validator = Draft202012Validator(schema)
    valid_paths = sorted((FIXTURE_ROOT / "valid").glob("*.json"))
    invalid_paths = sorted((FIXTURE_ROOT / "invalid").glob("*.json"))

    assert {path.stem for path in valid_paths} == {"delivered-initial", "projected-initial"}
    assert {path.stem for path in invalid_paths} == {
        "delivered-without-delivery",
        "episode-local-without-reset-authority",
        "legacy-observation-order",
    }
    for path in valid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(payload)
        ParticipantDecisionSurfaceV2Model.model_validate(payload)
    for path in invalid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload))
        with pytest.raises(ValidationError):
            ParticipantDecisionSurfaceV2Model.model_validate(payload)
