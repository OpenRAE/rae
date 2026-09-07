"""Operation-bound RUN-319 participant ingress mediation."""

from __future__ import annotations

from dataclasses import asdict, replace

from raes_contracts.contracts import ParticipantFlowSinkKind
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingDirection,
    ParticipantCrossingInteractionKind,
    ParticipantCrossingOperation,
    ParticipantCrossingSubjectKind,
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import OperationReceipt, OperationState
from raes_processor.models import ParticipantBehaviorRuntime

from .control_plane_execution import apply_authorized_participant_action
from .control_plane_lifecycle import runtime_owned
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
from .participant_crossing_mediation import (
    ParticipantCrossingEvidence,
    ParticipantCrossingIntent,
    PreparedParticipantCrossing,
    prepare_participant_crossing,
)
from .participant_crossing_records import _expected_history_heads
from .participant_crossing_state_cut import canonical_crossing_digest as _digest
from .participant_flow_sink import (
    apply_flow_sink_details,
    commit_flow_sink_denial,
    early_crossing_receipt,
    resolve_participant_flow_sink_decision,
)

_CONTROL_INTERACTIONS = {
    "proposal": ParticipantCrossingInteractionKind.ACTION_PROPOSAL,
    "approval": ParticipantCrossingInteractionKind.APPROVAL,
    "denial": ParticipantCrossingInteractionKind.DENIAL,
    "external-direction": ParticipantCrossingInteractionKind.EXTERNAL_DIRECTION,
    "intervention": ParticipantCrossingInteractionKind.INTERVENTION,
    "handoff": ParticipantCrossingInteractionKind.HANDOFF,
    "override": ParticipantCrossingInteractionKind.OVERRIDE,
    "cancellation": ParticipantCrossingInteractionKind.CANCELLATION,
}


class ParticipantCrossingControlIngressMixin:
    """Own one RUN-319 decision and RUN-310 transition under one state cut."""

    @runtime_owned
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

            sink_decision = resolve_participant_flow_sink_decision(
                self,
                crossing,
                sink_kind=ParticipantFlowSinkKind.PARTICIPANT_CROSSING,
            )
            if sink_decision is not None and not sink_decision.permitted:
                return commit_flow_sink_denial(
                    self,
                    crossing,
                    sink_decision,
                    action="record_participant_control",
                )

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

        sink_decision = resolve_participant_flow_sink_decision(
            control_plane,
            crossing,
            sink_kind=ParticipantFlowSinkKind.ACTION_ARGUMENT,
        )
        if sink_decision is not None and not sink_decision.permitted:
            return commit_flow_sink_denial(
                control_plane,
                crossing,
                sink_decision,
                action="record_participant_crossing",
            )

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


def _control_crossing_intent(
    participant_address: str,
    control_intent: ParticipantControlIntent,
    evidence: ParticipantCrossingEvidence,
    *,
    controller_ref: str,
    authority_basis_refs: tuple[str, ...],
    effective_order: int,
) -> ParticipantCrossingIntent:
    return ParticipantCrossingIntent.model_validate(
        {
            **evidence.model_dump(mode="json"),
            "participant_address": participant_address,
            "episode_id": control_intent.episode_id,
            "direction": ParticipantCrossingDirection.INGRESS,
            "interaction_kind": _CONTROL_INTERACTIONS[control_intent.kind],
            "subject": _control_subject(participant_address, control_intent),
            "controller_ref": controller_ref,
            "authority_basis_refs": list(authority_basis_refs),
            "requested_operation": ParticipantCrossingOperation.ADMISSION,
            "action_or_projection_ref": _control_operation_ref(participant_address, control_intent),
            "effective_order": effective_order,
            "order_model": "logical_clock",
        },
    )


def _action_crossing_intent(
    control_plane: object,
    behavior: ParticipantBehaviorRuntime,
    request: ParticipantActionAdmissionRequest,
    evidence: ParticipantCrossingEvidence,
    identity: ControlPlaneIdentity,
) -> ParticipantCrossingIntent:
    episode_id = _action_episode_id(control_plane, request)
    controller_refs = {
        binding.controller_ref
        for binding in identity.participant_control_subjects
        if binding.participant_address == request.participant_address
    }
    if len(controller_refs) > 1:
        raise PermissionError("participant action requires one exact controller binding")
    controller_ref = next(iter(controller_refs), "runtime.unbound-participant-controller")
    interaction = (
        ParticipantCrossingInteractionKind.CANDIDATE_SELECTION
        if request.validated_selection is not None
        else ParticipantCrossingInteractionKind.ACTION_PROPOSAL
    )
    authority_basis_refs = tuple(behavior.authority_anchor_addresses or behavior.authority_anchor_refs)
    if not authority_basis_refs:
        raise ValueError("participant action crossing requires compiled authority anchors")
    return ParticipantCrossingIntent.model_validate(
        {
            **evidence.model_dump(mode="json"),
            "participant_address": request.participant_address,
            "episode_id": episode_id,
            "direction": ParticipantCrossingDirection.INGRESS,
            "interaction_kind": interaction,
            "subject": _action_subject(control_plane, request),
            "controller_ref": controller_ref,
            "authority_basis_refs": list(authority_basis_refs),
            "requested_operation": ParticipantCrossingOperation.ADMISSION,
            "action_or_projection_ref": request.action_contract_address,
            "effective_order": _next_effective_order(control_plane, request.participant_address),
            "order_model": "logical_clock",
        },
    )


def _control_subject(
    participant_address: str,
    intent: ParticipantControlIntent,
) -> ParticipantCrossingSubjectReferenceModel:
    payload = intent.model_dump(mode="json")
    return ParticipantCrossingSubjectReferenceModel(
        subject_kind=ParticipantCrossingSubjectKind.PARTICIPANT_CONTROL_OCCURRENCE,
        contract_id="participant-control-intent-v1",
        subject_ref=f"participant-control-intent:{participant_address}:{intent.client_correlation_id}",
        subject_digest=_digest(payload),
        participant_address=participant_address,
        episode_id=intent.episode_id,
    )


def _action_subject(
    control_plane: object,
    request: ParticipantActionAdmissionRequest,
) -> ParticipantCrossingSubjectReferenceModel:
    episode_id = _action_episode_id(control_plane, request)
    return ParticipantCrossingSubjectReferenceModel(
        subject_kind=ParticipantCrossingSubjectKind.PARTICIPANT_ACTION_ADMISSION,
        contract_id="participant-action-admission-v1",
        subject_ref=(
            f"participant-action-admission:{request.participant_address}:{episode_id}:{request.action_instance_id}"
        ),
        subject_digest=_digest(asdict(request)),
        participant_address=request.participant_address,
        episode_id=episode_id,
    )


def _action_episode_id(control_plane: object, request: ParticipantActionAdmissionRequest) -> str:
    if request.action_result is not None:
        return request.action_result.episode_id
    state = control_plane._snapshot.participant_episode_results.get(request.participant_address, {})
    value = state.get("episode_id")
    if not isinstance(value, str) or not value:
        raise ValueError("participant action crossing requires an active episode identity")
    return value


def _control_operation_ref(participant_address: str, intent: ParticipantControlIntent) -> str:
    if intent.kind == "proposal":
        return intent.action_contract_ref
    return _control_subject(participant_address, intent).subject_ref


def _next_effective_order(control_plane: object, participant_address: str) -> int:
    histories = (
        control_plane._snapshot.participant_behavior_history,
        control_plane._snapshot.participant_control_history,
        control_plane._snapshot.participant_crossing_history,
    )
    return sum(len(history.get(participant_address, ())) for history in histories) + 1


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
