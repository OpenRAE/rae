"""Runtime admission for exact-cut participant decision surfaces."""

from __future__ import annotations

from raes_contracts.contracts import (
    ParticipantDecisionSurfaceSelectionV2Model,
    ParticipantDecisionSurfaceV2Model,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_binding_v2 import (
    ParticipantDecisionSurfaceBindingResolversV2,
    bind_participant_decision_surface_selection_v2,
)
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationKind, OperationReceipt
from raes_processor.models import (
    ParticipantBehaviorRuntime,
    validate_participant_decision_surface_v2_anchor,
)

from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, external_control_plane_call, mutation_entry
from .participant_control_diagnostics import (
    _NO_PARTICIPANT_RUNTIME_MESSAGE,
    _participant_binding_address,
    _participant_binding_diagnostic,
)


class ParticipantDecisionSurfaceV2ControlMixin:
    """Exact-cut decision-surface operations mixed into the control plane."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def admit_participant_decision_surface_selection_v2(
        self,
        participant_behavior: ParticipantBehaviorRuntime,
        *,
        surface: ParticipantDecisionSurfaceV2Model,
        selection: ParticipantDecisionSurfaceSelectionV2Model,
        admission_request: ParticipantActionAdmissionRequest,
        resolvers: ParticipantDecisionSurfaceBindingResolversV2,
        idempotency_key: str = "",
        request_fingerprint: str = "",
    ) -> OperationReceipt:
        """Re-resolve v2 state and delivery before ordinary action admission."""

        if self._target.participant_runtime is None:
            return self._reject_submission(
                domain=RuntimeDomain.PARTICIPANT,
                message=_NO_PARTICIPANT_RUNTIME_MESSAGE,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        with control_plane_mutation(self, OperationKind.PARTICIPANT_ACTION):
            try:
                validate_participant_decision_surface_v2_anchor(self._snapshot, surface)
                with external_control_plane_call(self):
                    request = bind_participant_decision_surface_selection_v2(
                        surface=surface,
                        selection=selection,
                        admission_request=admission_request,
                        argument_shape_resolver=resolvers.argument_shape,
                        apparatus_resolver=resolvers.apparatus,
                        delivery_resolver=resolvers.delivery,
                    )
            except (TypeError, ValueError) as exc:
                return self._reject_diagnostics(
                    domain=RuntimeDomain.PARTICIPANT,
                    diagnostics=[
                        _participant_binding_diagnostic(_participant_binding_address(participant_behavior), str(exc))
                    ],
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                )
            return self.admit_participant_action(
                participant_behavior,
                request,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )


__all__ = ("ParticipantDecisionSurfaceV2ControlMixin",)
