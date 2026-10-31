"""Neutral participant implementation binding DTOs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol, cast

from raes_contracts.contracts.participant_decision_surface import (
    ParticipantDecisionSurfaceActionEntryModel,
    ParticipantDecisionSurfaceCandidateSetFormModel,
    ParticipantDecisionSurfaceConstrainedFormModel,
    ParticipantDecisionSurfaceModel,
    ParticipantDecisionSurfaceOpenEndedFormModel,
    ParticipantDecisionSurfaceSelectionModel,
)
from raes_contracts.contracts.participant_manifests import (
    ParticipantImplementationSelectionModel,
)
from raes_contracts.contracts.participant_runtime import (
    ParticipantActionResultModel,
)

from ._host_isolation import isolated_host_call
from .contracts.participant_action_admission import (
    ParticipantActionAdmissionRequest as _ParticipantActionAdmissionRequest,
)
from .contracts.participant_action_admission import (
    participant_action_admission_request_violations as _participant_action_admission_request_violations,
)
from .participant_action_arguments import (
    ParticipantActionArgumentScalar,
    ParticipantActionArgumentValue,
    ParticipantValidatedActionSelection,
)
from .participant_binding_events import (
    participant_behavior_event_payload,
    participant_implementation_actor_provenance,
)
from .participant_binding_history import participant_action_binding_events
from .participant_native_execution import ParticipantNativeActionExecution
from .runtime_state import ApplyResult


class ParticipantDecisionSurfaceArgumentShapeResolver(Protocol):
    """Resolve and normalize one proposal against a governed argument shape."""

    def __call__(
        self,
        *,
        action_contract_address: str,
        argument_shape_ref: str,
        proposal_ref: str,
        proposed_arguments: Mapping[str, object],
    ) -> ParticipantValidatedActionSelection | None: ...


class ParticipantDecisionSurfaceApparatusResolver(Protocol):
    """Resolve the run selection and exposure policy referenced by one surface."""

    def __call__(
        self,
        *,
        implementation_selection_ref: str,
        exposure_policy_ref: str,
    ) -> ParticipantImplementationSelectionModel | None: ...


@dataclass(frozen=True)
class ParticipantDecisionSurfaceBindingResolvers:
    """Governed dependencies used to validate one decision-surface selection."""

    argument_shape: ParticipantDecisionSurfaceArgumentShapeResolver
    apparatus: ParticipantDecisionSurfaceApparatusResolver


@dataclass
class ParticipantActionApplyResult(ApplyResult):
    """Control-plane result plus the independently reported native action outcome."""

    action_result: ParticipantActionResultModel | None = None


def bind_participant_decision_surface_selection(
    *,
    surface: ParticipantDecisionSurfaceModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
    admission_request: _ParticipantActionAdmissionRequest,
    argument_shape_resolver: ParticipantDecisionSurfaceArgumentShapeResolver,
    apparatus_resolver: ParticipantDecisionSurfaceApparatusResolver,
) -> _ParticipantActionAdmissionRequest:
    """Validate SEM-220 selection meaning before the existing admission path."""

    _validate_selection_surface_identity(surface, selection)
    entry = _selected_surface_entry(surface, selection)
    _validate_selected_entry(entry, selection)
    _validate_surface_form_selection(surface.form, entry, selection)
    _validate_admission_surface_agreement(surface, selection, admission_request)
    _validate_surface_apparatus(surface, admission_request, apparatus_resolver)
    validated_selection = _validate_proposal_arguments(selection, argument_shape_resolver)
    bound_request = cast(
        _ParticipantActionAdmissionRequest,
        replace(admission_request, validated_selection=validated_selection),
    )
    _validate_bound_admission_request(bound_request)
    return bound_request


def _validate_selection_surface_identity(
    surface: ParticipantDecisionSurfaceModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
) -> None:
    if selection.surface_id != surface.surface_id:
        raise ValueError("selection surface_id must match the participant decision surface")
    if selection.observation_order != surface.observation_order:
        raise ValueError("selection observation_order must match the participant decision surface")


def _selected_surface_entry(
    surface: ParticipantDecisionSurfaceModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
) -> ParticipantDecisionSurfaceActionEntryModel:
    entries = {entry.action_contract_address: entry for entry in surface.action_entries}
    entry = entries.get(selection.action_contract_address)
    if entry is None:
        raise ValueError("selection action_contract_address is not carried by the participant decision surface")
    return entry


def _validate_selected_entry(
    entry: ParticipantDecisionSurfaceActionEntryModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
) -> None:
    if entry.eligibility != "eligible":
        raise ValueError("participant decision surface selection is not eligible")
    if entry.support != "supported":
        raise ValueError("participant decision surface selection is not supported")
    if entry.selection_shape_ref != selection.argument_shape_ref:
        raise ValueError("selection argument_shape_ref must match the participant decision surface action entry")


def _validate_surface_form_selection(
    form: ParticipantDecisionSurfaceCandidateSetFormModel
    | ParticipantDecisionSurfaceConstrainedFormModel
    | ParticipantDecisionSurfaceOpenEndedFormModel,
    entry: ParticipantDecisionSurfaceActionEntryModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
) -> None:
    if isinstance(form, ParticipantDecisionSurfaceCandidateSetFormModel):
        if entry.entry_id not in form.candidate_entry_ids:
            raise ValueError("selection action is not a member of the participant candidate-action set")
    elif isinstance(form, ParticipantDecisionSurfaceConstrainedFormModel):
        if entry.entry_id != form.action_entry_id or selection.argument_shape_ref != form.argument_shape_ref:
            raise ValueError("selection does not match the constrained-form action and argument shape")
    else:
        if selection.action_contract_address not in form.allowed_action_contract_addresses:
            raise ValueError("open-ended proposal does not bind to an allowed governed action contract")
        if selection.argument_shape_ref != form.argument_shape_ref:
            raise ValueError("open-ended proposal does not bind to the governed argument shape")


def _validate_admission_surface_agreement(
    surface: ParticipantDecisionSurfaceModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
    admission_request: _ParticipantActionAdmissionRequest,
) -> None:
    if admission_request.participant_address != surface.participant_address:
        raise ValueError("admission request participant_address must match the participant decision surface")
    if admission_request.action_contract_address != selection.action_contract_address:
        raise ValueError("admission request action_contract_address must match the validated selection")
    if admission_request.observation_boundary_address != surface.observation_boundary_address:
        raise ValueError("admission request observation_boundary_address must match the participant decision surface")
    if admission_request.implementation_selection.selected_decision_surface_mode != surface.decision_control_mode:
        raise ValueError("admission request decision-control mode must match the participant decision surface")


def _validate_surface_apparatus(
    surface: ParticipantDecisionSurfaceModel,
    admission_request: _ParticipantActionAdmissionRequest,
    apparatus_resolver: ParticipantDecisionSurfaceApparatusResolver,
) -> None:
    with isolated_host_call("participant decision surface apparatus resolution failed"):
        surface_implementation_selection = apparatus_resolver(
            implementation_selection_ref=surface.implementation_selection_ref,
            exposure_policy_ref=surface.exposure_policy_ref,
        )
    if surface_implementation_selection is None:
        raise ValueError("participant decision surface apparatus refs did not resolve")
    if surface_implementation_selection.model_dump(
        mode="json"
    ) != admission_request.implementation_selection.model_dump(mode="json"):
        raise ValueError("admission request implementation selection and exposure policy must match the surface refs")


def _validate_proposal_arguments(
    selection: ParticipantDecisionSurfaceSelectionModel,
    argument_shape_resolver: ParticipantDecisionSurfaceArgumentShapeResolver,
) -> ParticipantValidatedActionSelection:
    with isolated_host_call("participant decision surface argument-shape resolution failed"):
        validated_selection = argument_shape_resolver(
            action_contract_address=selection.action_contract_address,
            argument_shape_ref=selection.argument_shape_ref,
            proposal_ref=selection.proposal_ref,
            proposed_arguments=selection.arguments,
        )
    if not isinstance(validated_selection, ParticipantValidatedActionSelection):
        raise ValueError("participant decision surface proposal failed governed argument-shape validation")
    expected = (
        selection.action_contract_address,
        selection.argument_shape_ref,
        selection.proposal_ref,
    )
    actual = (
        validated_selection.action_contract_address,
        validated_selection.argument_shape_ref,
        validated_selection.proposal_ref,
    )
    if actual != expected:
        raise ValueError("validated participant action selection must match the governed proposal coordinates")
    return validated_selection


def _validate_bound_admission_request(admission_request: _ParticipantActionAdmissionRequest) -> None:
    violations = _participant_action_admission_request_violations(admission_request)
    if violations:
        raise ValueError(violations[0])


__all__ = (
    "ParticipantActionArgumentScalar",
    "ParticipantActionArgumentValue",
    "ParticipantActionApplyResult",
    "ParticipantDecisionSurfaceArgumentShapeResolver",
    "ParticipantDecisionSurfaceBindingResolvers",
    "ParticipantNativeActionExecution",
    "ParticipantValidatedActionSelection",
    "bind_participant_decision_surface_selection",
    "participant_action_binding_events",
    "participant_behavior_event_payload",
    "participant_implementation_actor_provenance",
)
