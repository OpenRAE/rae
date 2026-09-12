"""Participant runtime control-plane operations."""

from __future__ import annotations

from raes_contracts.contracts import (
    ParticipantDecisionSurfaceModel,
    ParticipantDecisionSurfaceSelectionModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantDecisionSurfaceBindingResolvers,
    bind_participant_decision_surface_selection,
)
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationKind, OperationReceipt
from raes_processor.models import ParticipantBehaviorRuntime

from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, external_control_plane_call, mutation_entry
from .participant_control_diagnostics import (
    _NO_PARTICIPANT_RUNTIME_MESSAGE,
    _participant_binding_address,
    _participant_binding_diagnostic,
)
from .participant_control_intents import (
    ParticipantApprovalControlIntent,
    ParticipantCancellationControlIntent,
    ParticipantControlIntent,
    ParticipantDenialControlIntent,
    ParticipantExternalDirectionControlIntent,
    ParticipantHandoffControlIntent,
    ParticipantInterventionControlIntent,
    ParticipantOverrideControlIntent,
    ParticipantProposalControlIntent,
)
from .participant_crossing_boundary import (
    ParticipantCrossingControlIngressMixin,
    ParticipantCrossingEvidence,
)
from .participant_decision_surface_control_v2 import ParticipantDecisionSurfaceV2ControlMixin
from .participant_episode_control import ParticipantEpisodeControlMixin
from .participant_submission_options import ParticipantSubmissionOptions, submit_bound_participant_action


def _participant_binding_diagnostics(
    participant_behavior: object,
    *,
    admission_request: object,
    admission_fields: dict[str, object],
) -> tuple[ParticipantActionAdmissionRequest | None, list[Diagnostic]]:
    address = _participant_binding_address(participant_behavior)
    if not isinstance(participant_behavior, ParticipantBehaviorRuntime):
        return None, [
            _participant_binding_diagnostic(
                address,
                "participant_behavior must be a compiled ParticipantBehaviorRuntime",
            )
        ]
    request, diagnostics = _participant_admission_request(
        participant_behavior,
        admission_request=admission_request,
        admission_fields=admission_fields,
    )
    if diagnostics:
        return None, diagnostics
    diagnostics.extend(_participant_binding_request_diagnostics(participant_behavior, request))
    return (request if not diagnostics else None), diagnostics


def _participant_admission_request(
    participant_behavior: ParticipantBehaviorRuntime,
    *,
    admission_request: object,
    admission_fields: dict[str, object],
) -> tuple[ParticipantActionAdmissionRequest | None, list[Diagnostic]]:
    address = _participant_binding_address(participant_behavior)
    if admission_request is not None:
        return _explicit_participant_admission_request(address, admission_request, admission_fields)
    field_diagnostics = _participant_binding_field_diagnostics(participant_behavior, admission_fields)
    if field_diagnostics:
        return None, field_diagnostics
    return _participant_admission_request_from_fields(participant_behavior, admission_fields)


def _explicit_participant_admission_request(
    address: str,
    admission_request: object,
    admission_fields: dict[str, object],
) -> tuple[ParticipantActionAdmissionRequest | None, list[Diagnostic]]:
    if admission_fields:
        return None, [
            _participant_binding_diagnostic(
                address,
                "admission_request cannot be combined with admission keyword fields",
            )
        ]
    return _validated_participant_admission_request(address, admission_request)


def _participant_admission_request_from_fields(
    participant_behavior: ParticipantBehaviorRuntime,
    admission_fields: dict[str, object],
) -> tuple[ParticipantActionAdmissionRequest | None, list[Diagnostic]]:
    address = _participant_binding_address(participant_behavior)
    try:
        return (
            ParticipantActionAdmissionRequest(
                participant_address=participant_behavior.address,
                **admission_fields,
            ),
            [],
        )
    except (TypeError, ValueError) as exc:
        return None, [_participant_binding_diagnostic(address, str(exc))]


def _validated_participant_admission_request(
    address: str,
    admission_request: object,
) -> tuple[ParticipantActionAdmissionRequest | None, list[Diagnostic]]:
    if isinstance(admission_request, ParticipantActionAdmissionRequest):
        return admission_request, []
    return None, [
        _participant_binding_diagnostic(
            address,
            "admission_request must be a ParticipantActionAdmissionRequest",
        )
    ]


def _participant_binding_field_diagnostics(
    participant_behavior: ParticipantBehaviorRuntime,
    admission_fields: dict[str, object],
) -> list[Diagnostic]:
    address = _participant_binding_address(participant_behavior)
    diagnostics: list[Diagnostic] = []
    action_contract_address = admission_fields.get("action_contract_address")
    if (
        isinstance(action_contract_address, str)
        and action_contract_address not in participant_behavior.action_contract_addresses
    ):
        diagnostics.append(
            _participant_binding_diagnostic(
                address,
                (
                    f"action_contract_address {action_contract_address!r} is not declared by compiled "
                    f"participant behavior {participant_behavior.address!r}"
                ),
            )
        )
    observation_boundary_address = admission_fields.get("observation_boundary_address")
    if (
        isinstance(observation_boundary_address, str)
        and observation_boundary_address not in participant_behavior.observation_boundary_addresses
    ):
        diagnostics.append(
            _participant_binding_diagnostic(
                address,
                (
                    f"observation_boundary_address {observation_boundary_address!r} is not declared by compiled "
                    f"participant behavior {participant_behavior.address!r}"
                ),
            )
        )
    return diagnostics


def _participant_binding_request_diagnostics(
    participant_behavior: ParticipantBehaviorRuntime,
    request: ParticipantActionAdmissionRequest | None,
) -> list[Diagnostic]:
    if request is None:
        return []
    address = _participant_binding_address(participant_behavior)
    diagnostics: list[Diagnostic] = []
    if request.participant_address != participant_behavior.address:
        diagnostics.append(
            _participant_binding_diagnostic(
                address,
                "admission_request participant_address must match the compiled participant behavior address",
            )
        )
    if request.action_contract_address not in participant_behavior.action_contract_addresses:
        diagnostics.append(
            _participant_binding_diagnostic(
                address,
                (
                    f"action_contract_address {request.action_contract_address!r} is not declared by compiled "
                    f"participant behavior {participant_behavior.address!r}"
                ),
            )
        )
    if request.observation_boundary_address not in participant_behavior.observation_boundary_addresses:
        diagnostics.append(
            _participant_binding_diagnostic(
                address,
                (
                    f"observation_boundary_address {request.observation_boundary_address!r} "
                    "is not declared by compiled "
                    f"participant behavior {participant_behavior.address!r}"
                ),
            )
        )
    return diagnostics


class ParticipantControlMixin(
    ParticipantEpisodeControlMixin,
    ParticipantCrossingControlIngressMixin,
    ParticipantDecisionSurfaceV2ControlMixin,
):
    """Participant runtime methods for the shared runtime control plane."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def admit_participant_action(
        self,
        participant_behavior: ParticipantBehaviorRuntime,
        admission_request: ParticipantActionAdmissionRequest | None = None,
        *,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
        crossing_evidence: ParticipantCrossingEvidence | None = None,
        **admission_fields: object,
    ) -> OperationReceipt:
        if self._target.participant_runtime is None:
            return self._reject_submission(
                domain=RuntimeDomain.PARTICIPANT,
                message=_NO_PARTICIPANT_RUNTIME_MESSAGE,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                identity=identity,
                request={
                    "operation": "participant-action",
                    "participant_address": getattr(participant_behavior, "address", "unknown"),
                },
            )
        request, diagnostics = _participant_binding_diagnostics(
            participant_behavior,
            admission_request=admission_request,
            admission_fields=admission_fields,
        )
        if diagnostics:
            return self._reject_diagnostics(
                domain=RuntimeDomain.PARTICIPANT,
                diagnostics=diagnostics,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                identity=identity,
                request={
                    "operation": "participant-action",
                    "participant_address": getattr(participant_behavior, "address", "unknown"),
                },
            )
        assert request is not None
        options = ParticipantSubmissionOptions(
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
            crossing_evidence=crossing_evidence,
        )
        return submit_bound_participant_action(self, participant_behavior, request, options)

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def admit_participant_decision_surface_selection(
        self,
        participant_behavior: ParticipantBehaviorRuntime,
        *,
        surface: ParticipantDecisionSurfaceModel,
        selection: ParticipantDecisionSurfaceSelectionModel,
        admission_request: ParticipantActionAdmissionRequest,
        resolvers: ParticipantDecisionSurfaceBindingResolvers,
        **submission_options: object,
    ) -> OperationReceipt:
        """Validate a SEM-220 selection before reusing normal action admission."""

        options = ParticipantSubmissionOptions.from_fields(submission_options)
        if self._target.participant_runtime is None:
            return self._reject_submission(
                domain=RuntimeDomain.PARTICIPANT,
                message=_NO_PARTICIPANT_RUNTIME_MESSAGE,
                idempotency_key=options.idempotency_key,
                request_fingerprint=options.request_fingerprint,
                identity=options.identity,
                request={
                    "operation": "participant-decision-surface-selection",
                    "participant_address": getattr(participant_behavior, "address", "unknown"),
                },
            )
        try:
            with external_control_plane_call(self):
                request = bind_participant_decision_surface_selection(
                    surface=surface,
                    selection=selection,
                    admission_request=admission_request,
                    argument_shape_resolver=resolvers.argument_shape,
                    apparatus_resolver=resolvers.apparatus,
                )
        except (TypeError, ValueError) as exc:
            return self._reject_diagnostics(
                domain=RuntimeDomain.PARTICIPANT,
                diagnostics=[
                    _participant_binding_diagnostic(_participant_binding_address(participant_behavior), str(exc))
                ],
                idempotency_key=options.idempotency_key,
                request_fingerprint=options.request_fingerprint,
                identity=options.identity,
                request={
                    "operation": "participant-decision-surface-selection",
                    "participant_address": getattr(participant_behavior, "address", "unknown"),
                },
            )
        with control_plane_mutation(self, OperationKind.PARTICIPANT_ACTION):
            try:
                with external_control_plane_call(self):
                    request = bind_participant_decision_surface_selection(
                        surface=surface,
                        selection=selection,
                        admission_request=admission_request,
                        argument_shape_resolver=resolvers.argument_shape,
                        apparatus_resolver=resolvers.apparatus,
                    )
            except (TypeError, ValueError) as exc:
                return self._reject_diagnostics(
                    domain=RuntimeDomain.PARTICIPANT,
                    diagnostics=[
                        _participant_binding_diagnostic(_participant_binding_address(participant_behavior), str(exc))
                    ],
                    idempotency_key=options.idempotency_key,
                    request_fingerprint=options.request_fingerprint,
                    identity=options.identity,
                    request={
                        "operation": "participant-decision-surface-selection",
                        "participant_address": getattr(participant_behavior, "address", "unknown"),
                    },
                )
            return self.admit_participant_action(
                participant_behavior,
                request,
                idempotency_key=options.idempotency_key,
                request_fingerprint=options.request_fingerprint,
                identity=options.identity,
                crossing_evidence=options.crossing_evidence,
            )


__all__ = (
    "ParticipantApprovalControlIntent",
    "ParticipantCancellationControlIntent",
    "ParticipantControlIntent",
    "ParticipantControlMixin",
    "ParticipantDenialControlIntent",
    "ParticipantExternalDirectionControlIntent",
    "ParticipantHandoffControlIntent",
    "ParticipantInterventionControlIntent",
    "ParticipantOverrideControlIntent",
    "ParticipantProposalControlIntent",
)
