"""Read cancellation claims from durable control and execution-owner evidence."""

from __future__ import annotations

from contextlib import nullcontext
from typing import Literal

from pydantic import Field
from raes_contracts.contracts.base import ContractModel
from raes_contracts.contracts.participant_control import ParticipantCancellationEffect
from raes_contracts.contracts.participant_control_coordinates import ControlRef
from raes_contracts.runtime_state import OperationKind, OperationState

from .control_plane_lifecycle import runtime_owned, store_authoritative_state
from .control_plane_mutation import mutation_entry


def control_supervision(plane, intent):
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


def cancellation_link(plane, intent, occurrence, *, target_operation=None):
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


def _prevention_witness(plane, intent, occurrence):
    if occurrence.occurrence.disposition != "accepted" or intent.target_kind.value not in {"proposal", "decision"}:
        return None
    if any(
        event.get("episode_id") == intent.episode_id and event.get("event_type") == "action_attempted"
        for event in plane._snapshot.participant_behavior_history.get(occurrence.participant_address, ())
    ):
        return None
    for operation in plane._operations.values():
        if operation.receipt.context.operation_kind not in {
            OperationKind.PARTICIPANT_ACTION,
            OperationKind.PARTICIPANT_CROSSING,
        } or operation.status.state not in {
            OperationState.ACCEPTED,
            OperationState.RUNNING,
            OperationState.INDETERMINATE,
        }:
            continue
        scopes = [
            scope for scope in operation.receipt.context.authorization_scope if scope.startswith("participant-control:")
        ]
        if not scopes or any(
            scope.startswith(f"participant-control:{occurrence.participant_address}:") for scope in scopes
        ):
            return None
    return {
        "occurrence_ref": occurrence.event_id,
        "target_kind": intent.target_kind.value,
        "target_ref": intent.target_ref,
        "target_revision": intent.target_revision,
        "snapshot_revision": plane._snapshot_state.revision,
        "evidence_refs": [occurrence.event_id],
    }


def _link(plane, operation_id, identity):
    record = plane._operations.get(operation_id)
    if record is None or identity is None or not plane._operation_read_allowed(record, identity):
        raise KeyError("control operation not found")
    link = (record.result_payload or {}).get("participant_control_cancellation")
    if link is None:
        raise KeyError("control operation not found")
    if not any(
        item.participant_address == link["participant_address"] for item in identity.participant_control_subjects
    ):
        raise KeyError("control operation not found")
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
    return record, link


class ParticipantCancellationMixin:
    """Independently authorized, value-safe status and resumable delivery."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_CONTROL)
    def dispatch_participant_cancellation(self, operation_id, *, identity):
        """Resume one retained intent without lending the drain caller's authority."""

        from .control_plane_supervision import authorize_supervisor
        from .participant_control_receipts import origin_principal

        with self._mutation_authority.supervision():
            self._reload_derived_state()
            record, link = _link(self, operation_id, identity)
            if link["disposition"] == "accepted" and link["target_operation_id"] is not None:
                parent = self._operations.get(link["target_operation_id"])
                if (
                    parent is None
                    or parent.invocation is None
                    or parent.invocation.request.binding.model_dump(mode="json") != link["binding"]
                ):
                    raise ValueError("cancellation target binding is unverifiable")
                principal = origin_principal(self, record, link["participant_address"])
                authorize_supervisor(self, principal, parent)
                retained = any(control.control_id == link["control_id"] for control in parent.invocation.controls)
                control = self.cancel_operation(
                    parent.receipt.operation_id, control_id=link["control_id"], identity=principal
                )
                self._reload_derived_state()
                parent = self._operations[parent.receipt.operation_id]
                if (
                    retained
                    and not parent.invocation.native
                    and parent.invocation.consumed
                    and parent.invocation.reserved
                    and link["control_id"] not in parent.invocation.delivered_controls
                ):
                    from .operation_control_budget import remaining_control_budget

                    remaining_control_budget(self, control)
                    if self._distributed_execution is None:
                        from .operation_provider_control import deliver_control

                        deliver_control(self, parent, control)
                    else:
                        with self._mutation_authority.external_call():
                            self._execution_adapter.call(
                                "control",
                                self._distributed_execution.deliver_control,
                                parent.invocation.request,
                                control,
                                timeout_ms=remaining_control_budget(self, control),
                            )
        return self.participant_cancellation_status(operation_id, identity=identity)

    @runtime_owned
    @store_authoritative_state
    def participant_cancellation_status(self, operation_id, *, identity):
        """Project only outcomes proved by this cancellation's actual target owner."""

        record, link = _link(self, operation_id, identity)
        status = ParticipantCancellationStatus(
            control_operation_id=operation_id,
            occurrence_ref=link["occurrence_ref"],
            control_disposition=link["disposition"],
            target_operation_id=link["target_operation_id"],
            backend_control_id=link["control_id"] if link["target_operation_id"] else None,
        )
        if link["disposition"] != "accepted":
            return status
        if link["target_operation_id"] is None:
            witness = link.get("prevention_witness")
            if witness is not None:
                if (
                    link["target_kind"] not in {"proposal", "decision"}
                    or any(
                        witness[key] != link[key]
                        for key in ("occurrence_ref", "target_kind", "target_ref", "target_revision")
                    )
                    or witness["evidence_refs"] != [link["occurrence_ref"]]
                ):
                    raise ValueError("cancellation prevention witness does not bind its committed target")
                return status.model_copy(
                    update={
                        "cancellation_effect": ParticipantCancellationEffect.PREVENTED,
                        "evidence_refs": witness["evidence_refs"],
                    }
                )
            return status
        parent = self._operations.get(link["target_operation_id"])
        if (
            parent is None
            or parent.invocation is None
            or parent.invocation.request.binding.model_dump(mode="json") != link["binding"]
        ):
            raise ValueError("cancellation target binding is unverifiable")
        if not self._operation_read_allowed(parent, identity):
            raise KeyError("control operation not found")
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
        return status


def _project_settled_evidence(status, parent):
    for response in reversed(parent.invocation.responses):
        message = response.message
        if message.kind != "outcome" or message.proposed_state != parent.status.state:
            continue
        effects = message.effects
        if not effects.cessation_established or not effects.evidence_refs:
            return
        if effects.effect == "absent" and message.cancellation_established:
            status.cancellation_effect = ParticipantCancellationEffect.PREVENTED
        elif effects.effect == "partial" and effects.residual_state is not None and effects.residual_scope:
            status.cancellation_effect = ParticipantCancellationEffect.PARTIAL_LIMITATION
        elif effects.effect == "complete" or parent.status.state is OperationState.SUCCEEDED:
            status.cancellation_effect = ParticipantCancellationEffect.TOO_LATE
        status.evidence_refs = [item.artifact_id for item in effects.evidence_refs]
        return
