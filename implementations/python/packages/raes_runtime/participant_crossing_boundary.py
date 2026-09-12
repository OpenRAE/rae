"""Operation-bound RUN-319 participant ingress mediation."""

from __future__ import annotations

from dataclasses import replace

from raes_contracts.contracts import ParticipantFlowSinkKind
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import OperationKind, OperationReceipt, OperationState
from raes_processor.models import ParticipantBehaviorRuntime

from .control_plane_execution import apply_authorized_participant_action
from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, external_control_plane_call, mutation_entry
from .control_plane_security import ControlPlaneIdentity
from .participant_control_intents import ParticipantControlIntent, ParticipantControlIntentBase
from .participant_control_mediation import (
    bind_participant_control_request,
    prepare_participant_control_transition,
    record_participant_control,
)
from .participant_crossing_action import (
    ActionIngressExecution,
    action_operation_record,
    combined_crossing_audit,
)
from .participant_crossing_intents import (
    action_crossing_intent as _action_crossing_intent,
)
from .participant_crossing_intents import (
    action_subject as _action_subject,
)
from .participant_crossing_intents import (
    control_crossing_intent as _control_crossing_intent,
)
from .participant_crossing_intents import (
    control_subject as _control_subject,
)
from .participant_crossing_mediation import (
    ParticipantCrossingEvidence,
    ParticipantCrossingIntent,
    PreparedParticipantCrossing,
    prepare_participant_crossing,
)
from .participant_crossing_records import _expected_history_heads
from .participant_flow_sink import (
    apply_flow_sink_details,
    early_crossing_receipt,
    resolve_flow_sink_denial,
)


class ParticipantCrossingControlIngressMixin:
    """Own one RUN-319 decision and RUN-310 transition under one state cut."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_CONTROL)
    def record_participant_control(
        self,
        participant_address: str,
        intent: ParticipantControlIntent,
        *,
        identity: object,
        idempotency_key: str = "",
        crossing_evidence: ParticipantCrossingEvidence | None = None,
    ) -> OperationReceipt:
        if getattr(self, "_crossing_policy_resolver", None) is None:
            if crossing_evidence is not None:
                raise ValueError("participant crossing policy resolver is required")
            receipt = record_participant_control(
                self,
                participant_address=participant_address,
                intent=intent,
                identity=identity,
                idempotency_key=idempotency_key,
            )
        else:
            receipt = self._record_governed_participant_control(
                participant_address,
                intent,
                identity=identity,
                idempotency_key=idempotency_key,
                crossing_evidence=crossing_evidence,
            )
        return receipt

    def _record_governed_participant_control(
        self,
        participant_address: str,
        intent: ParticipantControlIntent,
        *,
        identity: object,
        idempotency_key: str,
        crossing_evidence: ParticipantCrossingEvidence | None,
    ) -> OperationReceipt:
        if crossing_evidence is None:
            raise ValueError("configured participant ingress requires crossing evidence")
        if not isinstance(identity, ControlPlaneIdentity):
            raise PermissionError("participant control requires an authenticated identity")
        with control_plane_mutation(self, OperationKind.PARTICIPANT_CONTROL):
            return self._record_governed_participant_control_authorized(
                participant_address,
                intent,
                identity=identity,
                idempotency_key=idempotency_key,
                crossing_evidence=crossing_evidence,
            )

    def _record_governed_participant_control_authorized(
        self,
        participant_address: str,
        intent: ParticipantControlIntent,
        *,
        identity: ControlPlaneIdentity,
        idempotency_key: str,
        crossing_evidence: ParticipantCrossingEvidence,
    ) -> OperationReceipt:
        with self._participant_control_lock:
            self._reload_derived_state()
            bound = bind_participant_control_request(
                self,
                participant_address,
                intent,
                identity,
                idempotency_key,
            )
            canonical = _control_crossing_intent(
                participant_address,
                intent,
                crossing_evidence,
                controller_ref=bound.state.controller_address,
                authority_basis_refs=tuple(bound.state.authority_basis_addresses or bound.state.authority_basis_refs),
                effective_order=bound.transition.effective_order,
            )
            crossing = prepare_participant_crossing(
                self,
                canonical,
                identity=identity,
                idempotency_key=idempotency_key,
                incumbent_carrier=intent,
            )
            early = early_crossing_receipt(self, crossing)
            if early is not None:
                return early

            sink_decision, sink_receipt = resolve_flow_sink_denial(
                self,
                crossing,
                sink_kind=ParticipantFlowSinkKind.PARTICIPANT_CROSSING,
                action="record_participant_control",
            )
            if sink_receipt is not None:
                return sink_receipt

            governed_intent = _governed_control_intent(self, crossing, intent)
            governed_bound = bind_participant_control_request(
                self,
                participant_address,
                governed_intent,
                identity,
                idempotency_key,
            )
            _require_governed_subject(
                crossing,
                _control_subject(participant_address, governed_intent),
            )
            transition = prepare_participant_control_transition(
                self,
                participant_address,
                governed_intent,
                identity,
                governed_bound,
            )
            next_snapshot = transition.next_snapshot.with_entries(
                dict(transition.next_snapshot.entries),
                participant_crossing_history=crossing.next_snapshot.participant_crossing_history,
            )
            record = replace(
                transition.record,
                request_fingerprint=crossing.record.request_fingerprint,
                idempotency_key=crossing.record.idempotency_key,
                decision_history_heads=crossing.record.decision_history_heads,
                result_history_heads=_expected_history_heads(next_snapshot, participant_address),
            )
            audit = combined_crossing_audit(
                transition.audit_event,
                crossing,
                action="record_participant_control",
                allowed=record.status.state is OperationState.SUCCEEDED,
            )
            if sink_decision is not None:
                audit = apply_flow_sink_details(audit, sink_decision)
            running = replace(
                record,
                status=replace(
                    record.status,
                    state=OperationState.RUNNING,
                    diagnostics=[],
                    changed_addresses=[],
                ),
            )
            claimed = self._claim_record(running)
            receipt = claimed.receipt
            if claimed.receipt.operation_id == running.receipt.operation_id:
                self._commit_participant_transition(
                    expected_history_heads=crossing.expected_history_heads,
                    snapshot=next_snapshot,
                    record=record,
                    audit_event=audit,
                )
                receipt = record.receipt
            return receipt


def execute_action_ingress_crossing(
    control_plane: object,
    participant_behavior: ParticipantBehaviorRuntime,
    request: ParticipantActionAdmissionRequest,
    execution: ActionIngressExecution,
) -> OperationReceipt:
    """Durably authorize, execute, and finalize one action admission."""

    if execution.crossing_evidence is None:
        raise ValueError("configured participant ingress requires crossing evidence")
    if not isinstance(execution.identity, ControlPlaneIdentity):
        raise PermissionError("participant crossing requires an authenticated identity")
    with control_plane_mutation(control_plane, OperationKind.PARTICIPANT_CROSSING):
        return _execute_action_ingress_crossing_authorized(
            control_plane,
            participant_behavior,
            request,
            execution,
        )


def _execute_action_ingress_crossing_authorized(
    control_plane: object,
    participant_behavior: ParticipantBehaviorRuntime,
    request: ParticipantActionAdmissionRequest,
    execution: ActionIngressExecution,
) -> OperationReceipt:
    with control_plane._participant_control_lock:
        control_plane._reload_derived_state()
        canonical = _action_crossing_intent(
            control_plane,
            participant_behavior,
            request,
            execution.crossing_evidence,
            execution.identity,
        )
        crossing = prepare_participant_crossing(
            control_plane,
            canonical,
            identity=execution.identity,
            idempotency_key=execution.idempotency_key,
            incumbent_carrier=request,
        )
        early = early_crossing_receipt(control_plane, crossing)
        if early is not None:
            return early

        sink_decision, sink_receipt = resolve_flow_sink_denial(
            control_plane,
            crossing,
            sink_kind=ParticipantFlowSinkKind.ACTION_ARGUMENT,
            action="record_participant_crossing",
        )
        if sink_receipt is not None:
            return sink_receipt

        governed_request = _governed_action_request(control_plane, crossing, request)
        _require_action_binding(participant_behavior, governed_request)
        _require_governed_subject(crossing, _action_subject(control_plane, governed_request))
        authorization_record = replace(
            crossing.record,
            status=replace(crossing.record.status, state=OperationState.RUNNING),
        )
        authorization_audit = combined_crossing_audit(
            crossing.audit_event,
            crossing,
            action="authorize_participant_action",
            allowed=True,
            reason="authorized",
        )
        if sink_decision is not None:
            authorization_audit = apply_flow_sink_details(authorization_audit, sink_decision)
        control_plane._commit_participant_transition(
            expected_history_heads=crossing.expected_history_heads,
            snapshot=crossing.next_snapshot,
            record=authorization_record,
            audit_event=authorization_audit,
        )

        with control_plane._mutation_authority.external_call():
            result = apply_authorized_participant_action(
                method=execution.method,
                request=governed_request,
                snapshot=control_plane._snapshot,
                address=execution.address,
                information_state_context_resolver=getattr(
                    control_plane,
                    "_information_state_context_resolver",
                    None,
                ),
            )
        next_snapshot = result.snapshot.with_entries(
            dict(result.snapshot.entries),
            participant_crossing_history=crossing.next_snapshot.participant_crossing_history,
        )
        record = replace(
            action_operation_record(crossing, result),
            result_history_heads=_expected_history_heads(next_snapshot, request.participant_address),
        )
        audit = combined_crossing_audit(
            crossing.audit_event,
            crossing,
            action="admit_participant_action",
            allowed=result.success,
            reason="accepted" if result.success else "backend-admission-failed",
        )
        if sink_decision is not None:
            audit = apply_flow_sink_details(audit, sink_decision)
        control_plane._commit_participant_transition(
            expected_history_heads=crossing.record.result_history_heads,
            snapshot=next_snapshot,
            record=record,
            audit_event=audit,
        )
        return record.receipt


def _governed_control_intent(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    incumbent: ParticipantControlIntent,
) -> ParticipantControlIntent:
    if crossing.governed_subject == crossing.intent.subject:
        return incumbent
    transformer = getattr(control_plane._crossing_policy_resolver, "transform_ingress", None)
    if not callable(transformer):
        raise ValueError("transformed participant ingress requires a trusted carrier transformer")
    with external_control_plane_call(control_plane):
        governed = transformer(crossing.intent, crossing.governed_subject, incumbent)
    if not isinstance(governed, ParticipantControlIntentBase):
        raise ValueError("participant control transformation returned an invalid governed carrier")
    return governed


def _governed_action_request(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    incumbent: ParticipantActionAdmissionRequest,
) -> ParticipantActionAdmissionRequest:
    if crossing.governed_subject == crossing.intent.subject:
        return incumbent
    transformer = getattr(control_plane._crossing_policy_resolver, "transform_ingress", None)
    if not callable(transformer):
        raise ValueError("transformed participant ingress requires a trusted carrier transformer")
    with external_control_plane_call(control_plane):
        governed = transformer(crossing.intent, crossing.governed_subject, incumbent)
    if not isinstance(governed, ParticipantActionAdmissionRequest):
        raise ValueError("participant action transformation returned an invalid governed carrier")
    return governed


def _require_governed_subject(
    crossing: PreparedParticipantCrossing,
    actual: ParticipantCrossingSubjectReferenceModel,
) -> None:
    if actual != crossing.governed_subject:
        raise ValueError("trusted transformation result does not match the governed carrier identity")


def _require_action_binding(
    behavior: ParticipantBehaviorRuntime,
    request: ParticipantActionAdmissionRequest,
) -> None:
    if request.participant_address != behavior.address:
        raise ValueError("governed action participant does not match the compiled behavior")
    if request.action_contract_address not in behavior.action_contract_addresses:
        raise ValueError("governed action is not declared by the compiled participant behavior")
    if request.observation_boundary_address not in behavior.observation_boundary_addresses:
        raise ValueError("governed observation boundary is not declared by the compiled participant behavior")


__all__ = (
    "ParticipantCrossingControlIngressMixin",
    "ParticipantCrossingEvidence",
    "ParticipantCrossingIntent",
    "execute_action_ingress_crossing",
)
