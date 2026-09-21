"""Neutral participant implementation binding DTOs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol, cast

from . import participant_binding_validation as _binding_validation
from .contracts import (
    ParticipantActionResultModel,
    ParticipantBehaviorHistoryEventModel,
    ParticipantDecisionSurfaceActionEntryModel,
    ParticipantDecisionSurfaceCandidateSetFormModel,
    ParticipantDecisionSurfaceConstrainedFormModel,
    ParticipantDecisionSurfaceModel,
    ParticipantDecisionSurfaceOpenEndedFormModel,
    ParticipantDecisionSurfaceSelectionModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantObservationDetailsModel,
    ParticipantTemporalRuntimeContextModel,
)
from .contracts.participant_resource_budgets import ParticipantResourceMeasurementRequirementModel
from .contracts.participant_temporal import ParticipantTemporalEvidenceModel
from .participant_action_arguments import (
    ParticipantActionArgumentScalar,
    ParticipantActionArgumentValue,
    ParticipantValidatedActionSelection,
)
from .participant_behavior import (
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEventType,
    ParticipantObservationStatus,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
)
from .participant_binding_events import (
    action_result_evidence_refs as _action_result_evidence_refs,
)
from .participant_binding_events import (
    participant_behavior_event_payload,
    participant_implementation_actor_provenance,
)
from .participant_native_execution import ParticipantNativeActionExecution
from .participant_temporal import temporal_evidence_scope_violations
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


@dataclass(frozen=True)
class ParticipantActionAdmissionRequest:
    """Backend-neutral request to admit one compiled participant action."""

    participant_address: str
    action_contract_address: str
    observation_boundary_address: str
    action_instance_id: str
    implementation_manifest: ParticipantImplementationManifestModel
    implementation_selection: ParticipantImplementationSelectionModel
    evidence_refs: tuple[str, ...] = ()
    visible_refs: tuple[str, ...] = ()
    disclosed_refs: tuple[str, ...] = ()
    observation_boundary_evidence_refs: tuple[str, ...] = ()
    temporal_contexts: tuple[ParticipantTemporalRuntimeContextModel, ...] = ()
    action_result: ParticipantActionResultModel | None = None
    validated_selection: ParticipantValidatedActionSelection | None = None
    state_transition_kind: str = "participant_action_admitted"
    post_state_digest: str | None = None
    requires_terminal_outcome: bool = False
    target_addresses: tuple[str, ...] = ()
    execution_scope_ref: str | None = None
    execution_generation: int | None = None
    resource_measurement_requirements: tuple[ParticipantResourceMeasurementRequirementModel, ...] = ()
    temporal_evidence: tuple[ParticipantTemporalEvidenceModel, ...] = ()

    def __post_init__(self) -> None:
        _validate_admission_request_basics(self)
        _validate_admission_request_selection_and_execution(self)
        _validate_and_normalize_admission_request_contexts(self)
        violations = participant_action_admission_request_violations(self)
        if violations:
            raise ValueError(violations[0])


def _validate_admission_request_basics(request: ParticipantActionAdmissionRequest) -> None:
    _binding_validation.require_non_empty(request.participant_address, "participant_address")
    _binding_validation.require_prefixed(
        request.action_contract_address,
        _binding_validation.ACTION_CONTRACT_PREFIX,
        "action_contract_address",
    )
    _binding_validation.require_prefixed(
        request.observation_boundary_address,
        _binding_validation.OBSERVATION_BOUNDARY_PREFIX,
        "observation_boundary_address",
    )
    _binding_validation.require_non_empty(request.action_instance_id, "action_instance_id")
    _binding_validation.require_non_empty(request.state_transition_kind, "state_transition_kind")
    if request.post_state_digest is not None:
        _binding_validation.require_non_empty(request.post_state_digest, "post_state_digest")
    if not isinstance(request.implementation_manifest, ParticipantImplementationManifestModel):
        raise TypeError("implementation_manifest must be a ParticipantImplementationManifestModel")
    if not isinstance(request.implementation_selection, ParticipantImplementationSelectionModel):
        raise TypeError("implementation_selection must be a ParticipantImplementationSelectionModel")
    if request.action_result is not None and not isinstance(request.action_result, ParticipantActionResultModel):
        raise TypeError("action_result must be a ParticipantActionResultModel or None")


def _validate_admission_request_selection_and_execution(request: ParticipantActionAdmissionRequest) -> None:
    selection = request.validated_selection
    if selection is not None:
        if not isinstance(selection, ParticipantValidatedActionSelection):
            raise TypeError("validated_selection must be a ParticipantValidatedActionSelection or None")
        if selection.action_contract_address != request.action_contract_address:
            raise ValueError("validated_selection action_contract_address must match the admission request")
    if not isinstance(request.requires_terminal_outcome, bool):
        raise TypeError("requires_terminal_outcome must be a bool")
    if (request.execution_scope_ref is None) != (request.execution_generation is None):
        raise ValueError("execution_scope_ref and execution_generation must be provided together")
    if request.execution_scope_ref is not None:
        _binding_validation.require_non_empty(request.execution_scope_ref, "execution_scope_ref")
        if request.execution_generation is None or request.execution_generation < 0:
            raise ValueError("execution_generation must be non-negative")
        if not request.target_addresses:
            raise ValueError("generation-bound participant actions require target_addresses")
    _binding_validation.validate_resource_measurement_requirements(request.resource_measurement_requirements)


def _validate_and_normalize_admission_request_contexts(request: ParticipantActionAdmissionRequest) -> None:
    if not isinstance(request.temporal_evidence, tuple) or any(
        not isinstance(item, ParticipantTemporalEvidenceModel) for item in request.temporal_evidence
    ):
        raise TypeError("temporal_evidence must contain typed temporal evidence")
    if any(not isinstance(item, ParticipantTemporalRuntimeContextModel) for item in request.temporal_contexts):
        raise TypeError("temporal_contexts entries must be ParticipantTemporalRuntimeContextModel")
    if len({item.temporal_contract_id for item in request.temporal_contexts}) != len(request.temporal_contexts):
        raise ValueError("temporal_contexts temporal_contract_id values must be unique")
    for field_name in (
        "evidence_refs",
        "visible_refs",
        "disclosed_refs",
        "observation_boundary_evidence_refs",
        "target_addresses",
    ):
        object.__setattr__(
            request,
            field_name,
            _binding_validation.string_tuple(getattr(request, field_name), field_name),
        )


@dataclass
class ParticipantActionApplyResult(ApplyResult):
    """Control-plane result plus the independently reported native action outcome."""

    action_result: ParticipantActionResultModel | None = None


def participant_action_admission_request_violations(request: ParticipantActionAdmissionRequest) -> tuple[str, ...]:
    """Return manifest/selection compatibility violations for a binding request."""

    return (
        *_implementation_selection_violations(request),
        *_exposure_policy_violations(request),
        *_action_result_violations(request),
        *_temporal_evidence_violations(request, request.temporal_evidence),
        *_temporal_evidence_violations(
            request, request.action_result.temporal_evidence if request.action_result else ()
        ),
    )


def _temporal_evidence_violations(
    request: ParticipantActionAdmissionRequest,
    proofs: Sequence[ParticipantTemporalEvidenceModel],
) -> tuple[str, ...]:
    contexts = [item.shared_time for item in request.temporal_contexts if item.shared_time is not None]
    return temporal_evidence_scope_violations(contexts, proofs, request.observation_boundary_address)


def bind_participant_decision_surface_selection(
    *,
    surface: ParticipantDecisionSurfaceModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
    admission_request: ParticipantActionAdmissionRequest,
    argument_shape_resolver: ParticipantDecisionSurfaceArgumentShapeResolver,
    apparatus_resolver: ParticipantDecisionSurfaceApparatusResolver,
) -> ParticipantActionAdmissionRequest:
    """Validate SEM-220 selection meaning before the existing admission path."""

    _validate_selection_surface_identity(surface, selection)
    entry = _selected_surface_entry(surface, selection)
    _validate_selected_entry(entry, selection)
    _validate_surface_form_selection(surface.form, entry, selection)
    _validate_admission_surface_agreement(surface, selection, admission_request)
    _validate_surface_apparatus(surface, admission_request, apparatus_resolver)
    validated_selection = _validate_proposal_arguments(selection, argument_shape_resolver)
    bound_request = cast(
        ParticipantActionAdmissionRequest,
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
    admission_request: ParticipantActionAdmissionRequest,
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
    admission_request: ParticipantActionAdmissionRequest,
    apparatus_resolver: ParticipantDecisionSurfaceApparatusResolver,
) -> None:
    try:
        surface_implementation_selection = apparatus_resolver(
            implementation_selection_ref=surface.implementation_selection_ref,
            exposure_policy_ref=surface.exposure_policy_ref,
        )
    except Exception as exc:
        raise ValueError("participant decision surface apparatus resolution failed") from exc
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
    try:
        validated_selection = argument_shape_resolver(
            action_contract_address=selection.action_contract_address,
            argument_shape_ref=selection.argument_shape_ref,
            proposal_ref=selection.proposal_ref,
            proposed_arguments=selection.arguments,
        )
    except Exception as exc:
        raise ValueError("participant decision surface argument-shape resolution failed") from exc
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


def _validate_bound_admission_request(admission_request: ParticipantActionAdmissionRequest) -> None:
    violations = participant_action_admission_request_violations(admission_request)
    if violations:
        raise ValueError(violations[0])


def _implementation_selection_violations(request: ParticipantActionAdmissionRequest) -> tuple[str, ...]:
    violations: list[str] = []
    manifest = request.implementation_manifest
    selection = request.implementation_selection
    if selection.participant_address != request.participant_address:
        violations.append(
            "implementation selection participant_address must match the compiled participant behavior address"
        )
    if manifest.identity.model_dump(mode="json") != selection.implementation_identity.model_dump(mode="json"):
        violations.append("implementation selection identity must match the participant implementation manifest")
    unsupported_contracts = sorted(
        set(selection.participant_contract_versions) - set(manifest.capabilities.supported_participant_contracts)
    )
    if unsupported_contracts:
        violations.append(
            "implementation selection declares participant contracts unsupported by the manifest: "
            + ", ".join(unsupported_contracts)
        )
    if selection.selected_decision_surface_mode not in manifest.capabilities.supported_decision_surface_modes:
        violations.append("selected decision-surface mode is not supported by the participant implementation manifest")
    unsupported_policies = sorted(
        set(selection.exposure_policy.exposure_policy_kinds) - set(manifest.capabilities.exposure_policy_kinds)
    )
    if unsupported_policies:
        violations.append(
            "implementation exposure policy uses kinds unsupported by the manifest: " + ", ".join(unsupported_policies)
        )
    return tuple(violations)


def _exposure_policy_violations(request: ParticipantActionAdmissionRequest) -> tuple[str, ...]:
    violations: list[str] = []
    policy = request.implementation_selection.exposure_policy
    action_result_evidence_refs = _action_result_evidence_refs(request.action_result)
    observation_evidence_refs = (
        set(request.evidence_refs)
        | action_result_evidence_refs
        | {ref for proof in request.temporal_evidence for ref in proof.evidence_refs}
    )
    emitted_refs = set(request.visible_refs) | set(request.disclosed_refs) | observation_evidence_refs
    withheld_refs = sorted(emitted_refs & set(policy.withheld_refs))
    if withheld_refs:
        violations.append(
            "participant binding refs must not include exposure policy withheld_refs: " + ", ".join(withheld_refs)
        )
    visible_allowed_refs = set(policy.disclosed_refs) | set(policy.visibility_scope_refs)
    unauthorized_visible_refs = sorted(set(request.visible_refs) - visible_allowed_refs)
    if unauthorized_visible_refs:
        violations.append(
            "visible_refs must be declared by exposure policy disclosed_refs or visibility_scope_refs: "
            + ", ".join(unauthorized_visible_refs)
        )
    unauthorized_disclosed_refs = sorted(set(request.disclosed_refs) - set(policy.disclosed_refs))
    if unauthorized_disclosed_refs:
        violations.append(
            "disclosed_refs must be declared by exposure policy disclosed_refs: "
            + ", ".join(unauthorized_disclosed_refs)
        )
    unauthorized_evidence_refs = sorted(observation_evidence_refs - set(request.observation_boundary_evidence_refs))
    if unauthorized_evidence_refs:
        violations.append(
            "evidence_refs must be declared by the compiled observation boundary: "
            + ", ".join(unauthorized_evidence_refs)
        )
    return tuple(violations)


def _action_result_violations(request: ParticipantActionAdmissionRequest) -> tuple[str, ...]:
    violations: list[str] = []
    action_result = request.action_result
    if action_result is None:
        return ()
    if action_result.participant_address != request.participant_address:
        violations.append("action_result participant_address must match the binding participant_address")
    if action_result.action_instance_id != request.action_instance_id:
        violations.append("action_result action_instance_id must match the binding action_instance_id")
    if action_result.action_contract_address != request.action_contract_address:
        violations.append("action_result action_contract_address must match the binding action_contract_address")
    observation_points = {context.observation_point for context in request.temporal_contexts}
    if observation_points and action_result.observation_point not in observation_points:
        violations.append("action_result observation_point must match a bound temporal runtime context")
    return tuple(violations)


def participant_action_binding_events(
    request: ParticipantActionAdmissionRequest,
    *,
    episode_id: str,
    timestamp: str,
    post_state_digest: str,
) -> tuple[ParticipantBehaviorHistoryEventModel, ...]:
    """Build the portable behavior-history events for an admitted action."""

    actor_provenance = participant_implementation_actor_provenance(request.implementation_selection)
    return (
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
            timestamp=timestamp,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            actor_provenance=actor_provenance,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.SELECTION_OR_ADMISSION,
            phase_realization=ParticipantPhaseRealization.RUNTIME_MEDIATED,
            admission_disposition=ParticipantAdmissionDisposition.ADMITTED,
            temporal_contexts=list(request.temporal_contexts),
        ),
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED,
            timestamp=timestamp,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.STATE_UPDATE_COMMIT,
            phase_realization=ParticipantPhaseRealization.RUNTIME_MEDIATED,
            state_transition_kind=request.state_transition_kind,
            post_state_digest=post_state_digest,
            temporal_contexts=list(request.temporal_contexts),
        ),
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
            timestamp=timestamp,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_boundary_address=request.observation_boundary_address,
            observation_status=ParticipantObservationStatus.TERMINAL,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.OBSERVATION_EMISSION,
            phase_realization=ParticipantPhaseRealization.RUNTIME_MEDIATED,
            post_state_digest=post_state_digest,
            action_result=request.action_result,
            temporal_contexts=list(request.temporal_contexts),
            details=ParticipantObservationDetailsModel(
                visible_refs=list(request.visible_refs),
                disclosed_refs=list(request.disclosed_refs),
                evidence_refs=list(request.evidence_refs),
            ),
        ),
    )


__all__ = (
    "ParticipantActionAdmissionRequest",
    "ParticipantActionArgumentScalar",
    "ParticipantActionArgumentValue",
    "ParticipantActionApplyResult",
    "ParticipantDecisionSurfaceArgumentShapeResolver",
    "ParticipantDecisionSurfaceBindingResolvers",
    "ParticipantNativeActionExecution",
    "ParticipantValidatedActionSelection",
    "bind_participant_decision_surface_selection",
    "participant_action_admission_request_violations",
    "participant_action_binding_events",
    "participant_behavior_event_payload",
    "participant_implementation_actor_provenance",
)
