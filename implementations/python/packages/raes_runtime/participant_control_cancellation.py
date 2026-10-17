"""Read cancellation claims from durable control and execution-owner evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from typing import Any

    from raes_contracts.contracts.backend_operation import BackendOperationControlModel
    from raes_contracts.contracts.backend_operation_response import BackendOperationOutcomeModel
    from raes_contracts.contracts.participant_control_occurrence_v2 import ParticipantControlOccurrenceV2Model

    from .control_plane import RuntimeControlPlane
    from .control_plane_security import ControlPlaneIdentity
    from .control_plane_store import ControlPlaneOperationRecord
    from .participant_control_intents import ParticipantControlIntent


from contextlib import nullcontext
from typing import Literal

from pydantic import Field
from raes_contracts.contracts.base import ContractModel
from raes_contracts.contracts.participant_control import ParticipantCancellationEffect
from raes_contracts.contracts.participant_control_coordinates import ControlRef
from raes_contracts.runtime_state import OperationKind, OperationState

from .control_plane_lifecycle import runtime_owned, store_authoritative_state
from .control_plane_mutation import mutation_entry


def control_supervision(plane: RuntimeControlPlane, intent: ParticipantControlIntent) -> AbstractContextManager[None]:
    """Keep cancellation on the incumbent bounded supervisory writer lane."""

    return (
        plane._mutation_authority.supervision()
        if intent.kind == "cancellation" and intent.application is not None
        else nullcontext()
    )


class ParticipantCancellationStatus(ContractModel):
    """Control success never silently becomes a target-operation outcome."""

    control_operation_id: str
    occurrence_ref: ControlRef
    control_disposition: Literal["accepted", "rejected"]
    target_operation_id: str | None = None
    backend_control_id: str | None = None
    backend_disposition: str | None = None
    cancellation_effect: ParticipantCancellationEffect | None = None
    evidence_refs: list[str] = Field(default_factory=list)


def cancellation_link(
    plane: RuntimeControlPlane,
    intent: ParticipantControlIntent,
    occurrence: ParticipantControlOccurrenceV2Model,
    *,
    target_operation: ControlPlaneOperationRecord | None = None,
) -> dict[str, object]:
    """Retain exact identity before any backend control can be delivered."""

    return {
        "participant_control_cancellation": {
            "participant_address": occurrence.participant_address,
            "episode_id": occurrence.episode_id,
            "occurrence_ref": occurrence.event_id,
            "disposition": occurrence.occurrence.disposition,
            "target_kind": intent.target_kind.value,
            "target_ref": intent.target_ref,
            "target_revision": intent.target_revision,
            "target_operation_id": None if target_operation is None else target_operation.receipt.operation_id,
            "binding": None
            if target_operation is None
            else target_operation.invocation.request.binding.model_dump(mode="json"),
            "control_id": occurrence.event_id,
            "prevention_witness": _prevention_witness(plane, intent, occurrence),
        }
    }


_CONTROL_NOT_FOUND = "control operation not found"


def _prevention_witness(
    plane: RuntimeControlPlane, intent: ParticipantControlIntent, occurrence: ParticipantControlOccurrenceV2Model
) -> dict[str, object] | None:
    if not _prevention_eligible(plane, intent, occurrence):
        return None
    return {
        "occurrence_ref": occurrence.event_id,
        "target_kind": intent.target_kind.value,
        "target_ref": intent.target_ref,
        "target_revision": intent.target_revision,
        "snapshot_revision": plane._snapshot_state.revision,
        "evidence_refs": [occurrence.event_id],
    }


def _prevention_eligible(
    plane: RuntimeControlPlane, intent: ParticipantControlIntent, occurrence: ParticipantControlOccurrenceV2Model
) -> bool:
    if occurrence.occurrence.disposition != "accepted" or intent.target_kind.value not in {"proposal", "decision"}:
        return False
    if any(
        event.get("episode_id") == intent.episode_id and event.get("event_type") == "action_attempted"
        for event in plane._snapshot.participant_behavior_history.get(occurrence.participant_address, ())
    ):
        return False
    return not any(
        _pending_participant_work(operation, occurrence.participant_address) for operation in plane._operations.values()
    )


def _pending_participant_work(operation: ControlPlaneOperationRecord, participant: str) -> bool:
    if operation.receipt.context.operation_kind not in {
        OperationKind.PARTICIPANT_ACTION,
        OperationKind.PARTICIPANT_CROSSING,
    } or operation.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING, OperationState.INDETERMINATE}:
        return False
    scopes = [
        scope for scope in operation.receipt.context.authorization_scope if scope.startswith("participant-control:")
    ]
    return not scopes or any(scope.startswith(f"participant-control:{participant}:") for scope in scopes)


def _link(
    plane: RuntimeControlPlane, operation_id: str, identity: ControlPlaneIdentity
) -> tuple[ControlPlaneOperationRecord, dict[str, Any]]:
    record = plane._operations.get(operation_id)
    if record is None or identity is None or not plane._operation_read_allowed(record, identity):
        raise KeyError(_CONTROL_NOT_FOUND)
    link = (record.result_payload or {}).get("participant_control_cancellation")
    if link is None:
        raise KeyError(_CONTROL_NOT_FOUND)
    if not any(
        item.participant_address == link["participant_address"] for item in identity.participant_control_subjects
    ):
        raise KeyError(_CONTROL_NOT_FOUND)
    _require_committed_link(plane, record, link)
    return record, link


def _require_committed_link(
    plane: RuntimeControlPlane, record: ControlPlaneOperationRecord, link: dict[str, Any]
) -> None:
    expected = OperationState.SUCCEEDED if link["disposition"] == "accepted" else OperationState.FAILED
    committed = [
        event
        for event in plane._snapshot.participant_control_history.get(link["participant_address"], ())
        if event.get("event_id") == link["occurrence_ref"]
    ]
    if (
        record.status.state is not expected
        or len(committed) != 1
        or committed[0]["occurrence"]["disposition"] != link["disposition"]
    ):
        raise ValueError("cancellation control occurrence is not committed")


def _target_parent(plane: RuntimeControlPlane, link: dict[str, Any]) -> ControlPlaneOperationRecord:
    parent = plane._operations.get(link["target_operation_id"])
    if (
        parent is None
        or parent.invocation is None
        or parent.invocation.request.binding.model_dump(mode="json") != link["binding"]
    ):
        raise ValueError("cancellation target binding is unverifiable")
    return parent


def _dispatch_link(plane: RuntimeControlPlane, record: ControlPlaneOperationRecord, link: dict[str, Any]) -> None:
    from .control_plane_supervision import authorize_supervisor
    from .participant_control_receipts import origin_principal

    parent = _target_parent(plane, link)
    principal = origin_principal(plane, record, link["participant_address"])
    authorize_supervisor(plane, principal, parent)
    retained = any(control.control_id == link["control_id"] for control in parent.invocation.controls)
    control = plane.cancel_operation(parent.receipt.operation_id, control_id=link["control_id"], identity=principal)
    plane._reload_derived_state()
    parent = plane._operations[parent.receipt.operation_id]
    if retained and _delivery_pending(parent, link):
        _resume_delivery(plane, parent, control)


def _delivery_pending(parent: ControlPlaneOperationRecord, link: dict[str, Any]) -> bool:
    invocation = parent.invocation
    return (
        not invocation.native
        and invocation.consumed
        and invocation.reserved
        and link["control_id"] not in invocation.delivered_controls
    )


def _resume_delivery(
    plane: RuntimeControlPlane, parent: ControlPlaneOperationRecord, control: BackendOperationControlModel
) -> None:
    from .operation_control_budget import remaining_control_budget

    remaining_control_budget(plane, control)
    if plane._distributed_execution is None:
        from .operation_provider_control import deliver_control

        deliver_control(plane, parent, control)
    else:
        with plane._mutation_authority.external_call():
            plane._execution_adapter.call(
                "control",
                plane._distributed_execution.deliver_control,
                parent.invocation.request,
                control,
                timeout_ms=remaining_control_budget(plane, control),
            )


class ParticipantCancellationMixin:
    """Independently authorized, value-safe status and resumable delivery."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_CONTROL)
    def dispatch_participant_cancellation(
        self, operation_id: str, *, identity: ControlPlaneIdentity
    ) -> ParticipantCancellationStatus:
        """Resume one retained intent without lending the drain caller's authority."""
        with self._mutation_authority.supervision():
            self._reload_derived_state()
            record, link = _link(self, operation_id, identity)
            if link["disposition"] == "accepted" and link["target_operation_id"] is not None:
                _dispatch_link(self, record, link)
        return self.participant_cancellation_status(operation_id, identity=identity)

    @runtime_owned
    @store_authoritative_state
    def participant_cancellation_status(
        self, operation_id: str, *, identity: ControlPlaneIdentity
    ) -> ParticipantCancellationStatus:
        """Project only outcomes proved by this cancellation's actual target owner."""
        _, link = _link(self, operation_id, identity)
        status = ParticipantCancellationStatus(
            control_operation_id=operation_id,
            occurrence_ref=link["occurrence_ref"],
            control_disposition=link["disposition"],
            target_operation_id=link["target_operation_id"],
            backend_control_id=link["control_id"] if link["target_operation_id"] else None,
        )
        if link["disposition"] == "accepted":
            if link["target_operation_id"] is None:
                _project_prevention(status, link)
            else:
                _project_parent_status(self, status, link, identity)
        return status


def _project_prevention(status: ParticipantCancellationStatus, link: dict[str, Any]) -> None:
    witness = link.get("prevention_witness")
    if witness is None:
        return
    if (
        link["target_kind"] not in {"proposal", "decision"}
        or any(witness[key] != link[key] for key in ("occurrence_ref", "target_kind", "target_ref", "target_revision"))
        or witness["evidence_refs"] != [link["occurrence_ref"]]
    ):
        raise ValueError("cancellation prevention witness does not bind its committed target")
    status.cancellation_effect = ParticipantCancellationEffect.PREVENTED
    status.evidence_refs = list(witness["evidence_refs"])


def _project_parent_status(
    plane: RuntimeControlPlane,
    status: ParticipantCancellationStatus,
    link: dict[str, Any],
    identity: ControlPlaneIdentity,
) -> None:
    parent = _target_parent(plane, link)
    if not plane._operation_read_allowed(parent, identity):
        raise KeyError(_CONTROL_NOT_FOUND)
    invocation = parent.invocation
    for response in reversed(invocation.responses):
        if getattr(response.message, "control_id", None) == link["control_id"]:
            status.backend_disposition = getattr(response.message, "disposition", None)
            break
    if parent.status.state is OperationState.CANCELLED and not invocation.consumed:
        status.cancellation_effect = ParticipantCancellationEffect.PREVENTED
        status.evidence_refs = [parent.receipt.operation_id, link["control_id"]]
    elif invocation.release_commitment is not None and not invocation.reserved:
        _project_settled_evidence(status, parent)


def _project_settled_evidence(status: ParticipantCancellationStatus, parent: ControlPlaneOperationRecord) -> None:
    for response in reversed(parent.invocation.responses):
        message = response.message
        if message.kind != "outcome" or message.proposed_state != parent.status.state:
            continue
        effects = message.effects
        if not effects.cessation_established or not effects.evidence_refs:
            return
        status.cancellation_effect = _settled_effect(message, parent.status.state)
        status.evidence_refs = [item.artifact_id for item in effects.evidence_refs]
        return


def _settled_effect(
    message: BackendOperationOutcomeModel, state: OperationState
) -> ParticipantCancellationEffect | None:
    effect = None
    effects = message.effects
    if effects.effect == "absent" and message.cancellation_established:
        effect = ParticipantCancellationEffect.PREVENTED
    elif effects.effect == "partial" and effects.residual_state is not None and effects.residual_scope:
        effect = ParticipantCancellationEffect.PARTIAL_LIMITATION
    elif effects.effect == "complete" or state is OperationState.SUCCEEDED:
        effect = ParticipantCancellationEffect.TOO_LATE
    return effect
