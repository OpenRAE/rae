"""Authorized, revision-bound ACT-618 report production on the existing store."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from raes_contracts.contracts.participant_outcomes import ParticipantOutcomeReportV2Model
from raes_contracts.operation_lifecycle import OperationAdmissionContext
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationKind, OperationReceipt, OperationState, OperationStatus
from raes_processor.models import ParticipantBehaviorRuntime, ParticipantOutcomeInterpretationRuleRuntime, RuntimeModel

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, mutation_entry
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord, SnapshotRevisionConflict
from .control_plane_store_history import participant_history_head
from .participant_control_mediation import _require_participant_binding
from .participant_outcome_state import ParticipantOutcomeUpdateRequest, produce_participant_outcome

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


def _authorized_outcome_request(
    control_plane: RuntimeControlPlane, request: ParticipantOutcomeUpdateRequest, identity: ControlPlaneIdentity
) -> ParticipantOutcomeInterpretationRuleRuntime:
    if not isinstance(identity, ControlPlaneIdentity) or ControlPlaneRole.OPERATOR not in identity.roles:
        raise PermissionError("participant outcome updates require an authenticated operator")
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        raise PermissionError("participant outcome identity is not authorized for this target")
    _require_participant_binding(identity, request.participant_address)
    model = control_plane._participant_outcome_model
    if model is None:
        raise ValueError("participant outcome compiled model is unavailable")
    participant = model.participant_behaviors.get(request.participant_address)
    rule = model.outcome_interpretation_rules.get(request.rule_address)
    if participant is None or rule is None:
        raise ValueError("participant outcome participant or rule binding is invalid")
    _require_declared_rule(model, participant, rule)
    return rule


def _outcome_operation(
    request: ParticipantOutcomeUpdateRequest,
    report: ParticipantOutcomeReportV2Model,
    identity: ControlPlaneIdentity,
    context: OperationAdmissionContext,
) -> tuple[ControlPlaneOperationRecord, AuditEvent]:
    operation_id = str(uuid4())
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        submitted_at=report.recorded_at,
        accepted=True,
        context=context,
    )
    status = OperationStatus(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        state=OperationState.SUCCEEDED,
        submitted_at=report.recorded_at,
        updated_at=report.recorded_at,
        context=context,
        changed_addresses=[request.participant_address],
    )
    record = ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        request_fingerprint=context.request_commitment,
        idempotency_key=f"outcome:{request.event_id}",
    )
    audit = AuditEvent(
        timestamp=report.recorded_at,
        action="record_participant_outcome",
        identity=identity.identity,
        allowed=True,
        target=request.participant_address,
        operation_id=operation_id,
        reason="accepted",
    )
    return record, audit


class ParticipantOutcomeControlMixin:
    """Embedded operator boundary; outcome reports are not participant-visible views."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_CONTROL)
    def record_participant_outcome(
        self, request: ParticipantOutcomeUpdateRequest, *, identity: ControlPlaneIdentity
    ) -> OperationReceipt:
        if not isinstance(request, ParticipantOutcomeUpdateRequest):
            raise ValueError("participant outcome update requires a typed request")
        # Revalidate model_copy/model_construct carriers at the mutation boundary.
        try:
            request = ParticipantOutcomeUpdateRequest.model_validate(request.model_dump(mode="json"))
        except (TypeError, ValueError):
            raise ValueError("participant outcome update contract is invalid") from None
        rule = _authorized_outcome_request(self, request, identity)
        with control_plane_mutation(self, OperationKind.PARTICIPANT_CONTROL), self._participant_control_lock:
            self._reload_derived_state()
            context = operation_admission_context(
                self, kind=OperationKind.PARTICIPANT_CONTROL, request=request.model_dump(mode="json"), identity=identity
            )
            prior = self._store.find_by_idempotency(f"outcome:{request.event_id}", context=context)
            if prior is not None:
                if prior.request_fingerprint != context.request_commitment:
                    raise ValueError("participant outcome retry payload differs")
                return prior.receipt
            if request.expected_snapshot_revision != self._snapshot_state.revision:
                raise SnapshotRevisionConflict()
            if any(
                raw["event_id"] == request.event_id
                for records in self._snapshot.participant_outcome_history.values()
                for raw in records
            ):
                raise ValueError("participant outcome event identity already exists")
            report = produce_participant_outcome(
                self._snapshot,
                rule,
                request,
                timestamp=_utc_now(),
                actor_ref=identity.identity,
                authorization_scope="role:operator",
            )
            history = {key: list(records) for key, records in self._snapshot.participant_outcome_history.items()}
            history.setdefault(request.participant_address, []).append(report.model_dump(mode="json"))
            following = self._snapshot.with_entries(dict(self._snapshot.entries), participant_outcome_history=history)
            record, audit = _outcome_operation(request, report, identity, context)
            running = replace(
                record,
                status=replace(record.status, state=OperationState.RUNNING, diagnostics=[], changed_addresses=[]),
            )
            claimed = self._claim_record(running)
            if claimed.receipt.operation_id != record.receipt.operation_id:
                return claimed.receipt
            key = f"participant_outcome_history:{request.participant_address}"
            self._commit_participant_transition(
                expected_history_heads={key: participant_history_head(self._snapshot, key)},
                snapshot=following,
                record=record,
                audit_event=audit,
            )
            return record.receipt


def _require_declared_rule(
    model: RuntimeModel, participant: ParticipantBehaviorRuntime, rule: ParticipantOutcomeInterpretationRuleRuntime
) -> None:
    role = participant.role
    if not any(
        rule.address in specification.outcome_interpretation_rule_addresses
        and (participant.address in specification.participant_addresses or role in specification.participant_role_refs)
        for specification in model.behavior_specifications.values()
    ):
        raise ValueError("participant outcome behavior-specification binding is invalid")
    for layer, ref in zip(rule.source_layers, rule.source_refs, strict=True):
        if layer == "participant_action_outcome" and ref not in participant.action_contract_addresses:
            raise ValueError("participant outcome rule action binding is invalid")
