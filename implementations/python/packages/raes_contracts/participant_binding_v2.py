"""Exact-cut participant decision-surface v2 binding DTOs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol, cast

from raes_contracts.contracts.participant_action_admission import (
    ParticipantActionAdmissionRequest,
    participant_action_admission_request_violations,
)
from raes_contracts.contracts.participant_decision_surface import (
    ParticipantDecisionSurfaceActionEntryModel,
    ParticipantDecisionSurfaceCandidateSetFormModel,
    ParticipantDecisionSurfaceConstrainedFormModel,
)
from raes_contracts.contracts.participant_decision_surface_v2 import (
    ParticipantDecisionSurfaceSelectionV2Model,
    ParticipantDecisionSurfaceV2Model,
)
from raes_contracts.contracts.participant_manifests import ParticipantImplementationSelectionModel

from ._host_isolation import isolated_host_call
from .participant_action_arguments import ParticipantValidatedActionSelection
from .participant_binding import ParticipantDecisionSurfaceArgumentShapeResolver
from .participant_decision_surface_delivery import (
    ParticipantDecisionSurfaceDeliveryResolverV2,
    validate_participant_decision_surface_v2_delivery,
)


class ParticipantDecisionSurfaceApparatusResolverV2(Protocol):
    """Resolve the run selection at the exact cut used to derive a v2 surface."""

    def __call__(
        self,
        *,
        implementation_selection_ref: str,
        exposure_policy_ref: str,
        decision_cut_ref: str,
    ) -> ParticipantImplementationSelectionModel | None: ...


@dataclass(frozen=True)
class ParticipantDecisionSurfaceBindingResolversV2:
    """Governed dependencies for a delivered v2 surface selection."""

    argument_shape: ParticipantDecisionSurfaceArgumentShapeResolver
    apparatus: ParticipantDecisionSurfaceApparatusResolverV2
    delivery: ParticipantDecisionSurfaceDeliveryResolverV2


def _validate_selection_identity(
    surface: ParticipantDecisionSurfaceV2Model,
    selection: ParticipantDecisionSurfaceSelectionV2Model,
) -> None:
    view = surface.participant_view
    delivery = surface.delivery
    assert delivery is not None
    comparisons = (
        (selection.surface_id, view.surface_id, "selection surface_id must match the participant decision surface"),
        (
            selection.decision_epoch,
            view.decision_epoch,
            "selection decision_epoch must match the participant decision surface",
        ),
        (
            selection.participant_view_digest,
            surface.assurance.participant_view_digest,
            "selection participant_view_digest must match the canonical participant view",
        ),
        (
            selection.delivery_ref,
            delivery.delivery_ref,
            "selection delivery_ref must match the authoritative surface delivery",
        ),
    )
    for actual, expected, message in comparisons:
        if actual != expected:
            raise ValueError(message)


def _selected_action_entry(
    surface: ParticipantDecisionSurfaceV2Model,
    selection: ParticipantDecisionSurfaceSelectionV2Model,
) -> ParticipantDecisionSurfaceActionEntryModel:
    entries = {entry.action_contract_address: entry for entry in surface.participant_view.action_entries}
    entry = entries.get(selection.action_contract_address)
    if entry is None:
        raise ValueError("selection action_contract_address is not carried by the participant decision surface")
    return entry


def _validate_selected_entry(
    entry: ParticipantDecisionSurfaceActionEntryModel,
    selection: ParticipantDecisionSurfaceSelectionV2Model,
) -> None:
    if entry.eligibility != "eligible":
        raise ValueError("participant decision surface selection is not eligible")
    if entry.support != "supported":
        raise ValueError("participant decision surface selection is not supported")
    if entry.selection_shape_ref != selection.argument_shape_ref:
        raise ValueError("selection argument_shape_ref must match the participant decision surface action entry")


def _validate_form_selection(
    surface: ParticipantDecisionSurfaceV2Model,
    entry: ParticipantDecisionSurfaceActionEntryModel,
    selection: ParticipantDecisionSurfaceSelectionV2Model,
) -> None:
    form = surface.participant_view.form
    if isinstance(form, ParticipantDecisionSurfaceCandidateSetFormModel):
        if entry.entry_id not in form.candidate_entry_ids:
            raise ValueError("selection action is not a member of the participant candidate-action set")
        return
    if isinstance(form, ParticipantDecisionSurfaceConstrainedFormModel):
        if entry.entry_id != form.action_entry_id or selection.argument_shape_ref != form.argument_shape_ref:
            raise ValueError("selection does not match the constrained-form action and argument shape")
        return
    if selection.action_contract_address not in form.allowed_action_contract_addresses:
        raise ValueError("open-ended proposal does not bind to an allowed governed action contract")
    if selection.argument_shape_ref != form.argument_shape_ref:
        raise ValueError("open-ended proposal does not bind to the governed argument shape")


def _validate_admission_agreement(
    surface: ParticipantDecisionSurfaceV2Model,
    selection: ParticipantDecisionSurfaceSelectionV2Model,
    admission_request: ParticipantActionAdmissionRequest,
) -> None:
    view = surface.participant_view
    assurance = surface.assurance
    comparisons = (
        (
            admission_request.participant_address,
            view.participant_address,
            "admission request participant_address must match the participant decision surface",
        ),
        (
            admission_request.action_contract_address,
            selection.action_contract_address,
            "admission request action_contract_address must match the validated selection",
        ),
        (
            admission_request.observation_boundary_address,
            assurance.observation_boundary_address,
            "admission request observation_boundary_address must match the participant decision surface",
        ),
        (
            admission_request.implementation_selection.selected_decision_surface_mode,
            view.decision_control_mode,
            "admission request decision-control mode must match the participant decision surface",
        ),
    )
    for actual, expected, message in comparisons:
        if actual != expected:
            raise ValueError(message)
    supported_versions = admission_request.implementation_selection.participant_contract_versions
    if "participant-decision-surface-v2" not in supported_versions:
        raise ValueError("participant implementation selection must declare participant-decision-surface-v2 support")


def _resolve_apparatus_selection(
    surface: ParticipantDecisionSurfaceV2Model,
    admission_request: ParticipantActionAdmissionRequest,
    resolver: ParticipantDecisionSurfaceApparatusResolverV2,
) -> None:
    assurance = surface.assurance
    with isolated_host_call("participant decision surface exact-cut apparatus resolution failed"):
        resolved = resolver(
            implementation_selection_ref=assurance.implementation_selection_ref,
            exposure_policy_ref=assurance.exposure_policy_ref,
            decision_cut_ref=assurance.derivation_anchor.state_cut.cut_ref,
        )
    if resolved is None:
        raise ValueError("participant decision surface apparatus refs did not resolve at the derivation cut")
    if resolved.model_dump(mode="json") != admission_request.implementation_selection.model_dump(mode="json"):
        raise ValueError("admission request implementation selection and exposure policy must match the surface refs")


def _resolve_validated_selection(
    selection: ParticipantDecisionSurfaceSelectionV2Model,
    resolver: ParticipantDecisionSurfaceArgumentShapeResolver,
) -> ParticipantValidatedActionSelection:
    with isolated_host_call("participant decision surface argument-shape resolution failed"):
        validated = resolver(
            action_contract_address=selection.action_contract_address,
            argument_shape_ref=selection.argument_shape_ref,
            proposal_ref=selection.proposal_ref,
            proposed_arguments=selection.arguments,
        )
    if not isinstance(validated, ParticipantValidatedActionSelection):
        raise ValueError("participant decision surface proposal failed governed argument-shape validation")
    coordinates = (
        validated.action_contract_address,
        validated.argument_shape_ref,
        validated.proposal_ref,
    )
    expected = (
        selection.action_contract_address,
        selection.argument_shape_ref,
        selection.proposal_ref,
    )
    if coordinates != expected:
        raise ValueError("validated participant action selection must match the governed proposal coordinates")
    return validated


def _bind_validated_selection(
    admission_request: ParticipantActionAdmissionRequest,
    validated_selection: ParticipantValidatedActionSelection,
) -> ParticipantActionAdmissionRequest:
    bound_request = cast(
        ParticipantActionAdmissionRequest,
        replace(admission_request, validated_selection=validated_selection),
    )
    violations = participant_action_admission_request_violations(bound_request)
    if violations:
        raise ValueError(violations[0])
    return bound_request


def bind_participant_decision_surface_selection_v2(
    *,
    surface: ParticipantDecisionSurfaceV2Model,
    selection: ParticipantDecisionSurfaceSelectionV2Model,
    admission_request: ParticipantActionAdmissionRequest,
    argument_shape_resolver: ParticipantDecisionSurfaceArgumentShapeResolver,
    apparatus_resolver: ParticipantDecisionSurfaceApparatusResolverV2,
    delivery_resolver: ParticipantDecisionSurfaceDeliveryResolverV2,
) -> ParticipantActionAdmissionRequest:
    """Validate a selection from an exact, currently delivered v2 view."""

    validate_participant_decision_surface_v2_delivery(surface, delivery_resolver)
    _validate_selection_identity(surface, selection)
    entry = _selected_action_entry(surface, selection)
    _validate_selected_entry(entry, selection)
    _validate_form_selection(surface, entry, selection)
    _validate_admission_agreement(surface, selection, admission_request)
    _resolve_apparatus_selection(surface, admission_request, apparatus_resolver)
    validated_selection = _resolve_validated_selection(selection, argument_shape_resolver)
    return _bind_validated_selection(admission_request, validated_selection)


__all__ = (
    "ParticipantDecisionSurfaceApparatusResolverV2",
    "ParticipantDecisionSurfaceBindingResolversV2",
    "bind_participant_decision_surface_selection_v2",
)
