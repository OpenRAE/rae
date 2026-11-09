"""Semantic validation helpers for participant decision-surface v2."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_contract_digest

if TYPE_CHECKING:
    from .participant_decision_surface_exposure_v2 import ParticipantDecisionSurfaceExposureBindingV2Model
    from .participant_decision_surface_v2 import (
        ParticipantDecisionSurfaceAssuranceV2Model,
        ParticipantDecisionSurfaceDeliveryV2Model,
        ParticipantDecisionSurfaceV2Model,
        ParticipantDecisionSurfaceViewV2Model,
    )


def _mismatched_names(comparisons: tuple[tuple[str, object, object], ...]) -> list[str]:
    return [name for name, actual, expected in comparisons if actual != expected]


def _validate_surface_coordinates(
    view: ParticipantDecisionSurfaceViewV2Model,
    assurance: ParticipantDecisionSurfaceAssuranceV2Model,
) -> None:
    mismatched = _mismatched_names(
        (
            ("participant_address", assurance.participant_address, view.participant_address),
            ("episode_id", assurance.episode_id, view.episode_id),
            ("decision_epoch", assurance.decision_epoch, view.decision_epoch),
        )
    )
    if mismatched:
        raise ValueError("assurance disagrees with the participant view on: " + ", ".join(mismatched))


def _validate_participant_view_digest(
    view: ParticipantDecisionSurfaceViewV2Model,
    assurance: ParticipantDecisionSurfaceAssuranceV2Model,
) -> None:

    if assurance.participant_view_digest != canonical_contract_digest(view):
        raise ValueError("assurance participant_view_digest must match the canonical participant view")


def _view_exposed_refs(view: ParticipantDecisionSurfaceViewV2Model) -> set[str]:
    return {
        *view.visible_context_refs,
        *(entry.action_contract_address for entry in view.action_entries),
        *view.affordance_refs,
    }


def _validate_exposure_binding_coverage(
    view: ParticipantDecisionSurfaceViewV2Model,
    assurance: ParticipantDecisionSurfaceAssuranceV2Model,
) -> None:
    item_refs = [binding.item_ref for binding in assurance.exposure_bindings]
    if len(item_refs) != len(set(item_refs)):
        raise ValueError("exposure_bindings.item_ref must not contain duplicates")
    actual = set(item_refs)
    expected = _view_exposed_refs(view)
    if actual == expected:
        return
    details = []
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        details.append("missing " + ", ".join(missing))
    if unexpected:
        details.append("unexpected " + ", ".join(unexpected))
    raise ValueError("exposure_bindings must exactly cover participant view refs: " + "; ".join(details))


def _validate_exposure_binding(
    binding: ParticipantDecisionSurfaceExposureBindingV2Model,
    view: ParticipantDecisionSurfaceViewV2Model,
    assurance: ParticipantDecisionSurfaceAssuranceV2Model,
) -> None:
    mismatched = _mismatched_names(
        (
            ("participant_address", binding.participant_address, view.participant_address),
            ("episode_id", binding.episode_id, view.episode_id),
            ("decision_epoch", binding.decision_epoch, view.decision_epoch),
            ("decision_cut_ref", binding.decision_cut_ref, assurance.derivation_anchor.state_cut.cut_ref),
            ("audience_scope_ref", binding.audience_scope_ref, assurance.audience_scope_ref),
            ("projection_policy_ref", binding.projection_policy_ref, assurance.projection_policy_ref),
            (
                "projection_policy_revision",
                binding.projection_policy_revision,
                assurance.projection_policy_revision,
            ),
            (
                "projection_policy_decision_ref",
                binding.projection_policy_decision_ref,
                assurance.projection_policy_decision_ref,
            ),
            ("exposure_policy_ref", binding.exposure_policy_ref, assurance.exposure_policy_ref),
        )
    )
    if mismatched:
        raise ValueError(
            f"exposure binding {binding.item_ref!r} disagrees with the surface on: " + ", ".join(mismatched)
        )
    if not set(binding.evidence_refs).issubset(assurance.evidence_refs):
        raise ValueError(f"exposure binding {binding.item_ref!r} evidence must be carried by assurance")
    if not set(binding.provenance_refs).issubset(assurance.provenance_refs):
        raise ValueError(f"exposure binding {binding.item_ref!r} provenance must be carried by assurance")


def _validate_exposure_bindings(
    view: ParticipantDecisionSurfaceViewV2Model,
    assurance: ParticipantDecisionSurfaceAssuranceV2Model,
) -> None:
    _validate_exposure_binding_coverage(view, assurance)
    for binding in assurance.exposure_bindings:
        _validate_exposure_binding(binding, view, assurance)


def _validate_delivery_coordinates(
    delivery: ParticipantDecisionSurfaceDeliveryV2Model,
    view: ParticipantDecisionSurfaceViewV2Model,
    assurance: ParticipantDecisionSurfaceAssuranceV2Model,
) -> None:
    mismatched = _mismatched_names(
        (
            ("surface_id", delivery.surface_id, view.surface_id),
            ("participant_address", delivery.participant_address, view.participant_address),
            ("episode_id", delivery.episode_id, view.episode_id),
            ("decision_epoch", delivery.decision_epoch, view.decision_epoch),
            ("participant_view_digest", delivery.participant_view_digest, assurance.participant_view_digest),
        )
    )
    if mismatched:
        raise ValueError("delivery disagrees with the participant view on: " + ", ".join(mismatched))


def _validate_delivery_state(surface: ParticipantDecisionSurfaceV2Model) -> None:
    if surface.surface_state == "projected" and surface.delivery is not None:
        raise ValueError("projected surfaces must not carry delivery")
    if surface.surface_state == "delivered" and surface.delivery is None:
        raise ValueError("delivered surfaces require delivery")
    if surface.delivery is not None:
        _validate_delivery_coordinates(surface.delivery, surface.participant_view, surface.assurance)


def _validate_participant_decision_surface_v2(surface: ParticipantDecisionSurfaceV2Model) -> None:
    _validate_surface_coordinates(surface.participant_view, surface.assurance)
    _validate_participant_view_digest(surface.participant_view, surface.assurance)
    _validate_exposure_bindings(surface.participant_view, surface.assurance)
    _validate_delivery_state(surface)
