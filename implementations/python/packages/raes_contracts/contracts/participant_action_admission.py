"""Backend-neutral admission request for one compiled participant action and its checks.

The request binds an implementation manifest, its selection, the exposure policy
and the temporal evidence of one action. ``participant_action_admission_request_violations``
returns every compatibility violation; the constructor refuses the first one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..participant_action_arguments import ParticipantValidatedActionSelection
from .participant_binding_validation import (
    ACTION_CONTRACT_PREFIX,
    OBSERVATION_BOUNDARY_PREFIX,
    require_non_empty,
    require_prefixed,
    string_tuple,
    validate_resource_measurement_requirements,
)
from .participant_manifests import ParticipantImplementationManifestModel, ParticipantImplementationSelectionModel
from .participant_resource_budgets import ParticipantResourceMeasurementRequirementModel
from .participant_runtime import ParticipantActionResultModel, ParticipantTemporalRuntimeContextModel
from .participant_temporal import ParticipantTemporalEvidenceModel
from .participant_temporal_assessment import temporal_evidence_scope_violations


def action_result_evidence_refs(action_result: ParticipantActionResultModel | None) -> set[str]:
    """Collect every evidence ref carried by one portable action result."""

    if action_result is None:
        return set()
    evidence_refs = set(action_result.evidence_refs)
    for precondition in action_result.preconditions:
        evidence_refs.update(precondition.evidence_refs)
    for effect in action_result.effects:
        evidence_refs.update(effect.evidence_refs)
    for proof in action_result.temporal_evidence:
        evidence_refs.update(proof.evidence_refs)
    return evidence_refs


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
    require_non_empty(request.participant_address, "participant_address")
    require_prefixed(
        request.action_contract_address,
        ACTION_CONTRACT_PREFIX,
        "action_contract_address",
    )
    require_prefixed(
        request.observation_boundary_address,
        OBSERVATION_BOUNDARY_PREFIX,
        "observation_boundary_address",
    )
    require_non_empty(request.action_instance_id, "action_instance_id")
    require_non_empty(request.state_transition_kind, "state_transition_kind")
    if request.post_state_digest is not None:
        require_non_empty(request.post_state_digest, "post_state_digest")
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
        require_non_empty(request.execution_scope_ref, "execution_scope_ref")
        if request.execution_generation is None or request.execution_generation < 0:
            raise ValueError("execution_generation must be non-negative")
        if not request.target_addresses:
            raise ValueError("generation-bound participant actions require target_addresses")
    validate_resource_measurement_requirements(request.resource_measurement_requirements)


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
            string_tuple(getattr(request, field_name), field_name),
        )


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
    result_evidence_refs = action_result_evidence_refs(request.action_result)
    observation_evidence_refs = (
        set(request.evidence_refs)
        | result_evidence_refs
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


__all__ = (
    "ParticipantActionAdmissionRequest",
    "action_result_evidence_refs",
    "participant_action_admission_request_violations",
)
