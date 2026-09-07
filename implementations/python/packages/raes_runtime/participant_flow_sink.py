"""SEM-233 final-sink flow-control permit resolved at the RUN-319 boundary.

ADR-101 places the last RAES-controlled boundary immediately before a
``RuntimeTarget`` component performs an external action or a participant/external
value is serialized. Issue #1003 wires the published SEM-233 final-sink permit
(#1002) into that boundary: inside the operation-bound crossing transaction, a
fresh exact-cut permit is resolved from trusted resolver-side evidence,
validated by the published validator, bound to the live state cut, and committed
atomically before any effect.

This module delegates every semantic join to
``validate_participant_flow_control_resolved_context`` and reuses the RUN-319
expected-head state cut. It introduces no store, policy engine, audit channel,
exception hierarchy, serializer, or generic dispatcher, and it never
re-implements a validator. SEM-233 enforcement is opt-in per resolver
capability: a resolver that does not expose ``resolve_flow_sink_decision``
leaves every legacy API-423 path unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import cast

from raes_contracts.contracts import (
    ParticipantFlowControlRelationModel,
    ParticipantFlowControlValidationContext,
    ParticipantFlowFinalDisposition,
    ParticipantFlowSinkKind,
    validate_participant_flow_control_resolved_context,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import OperationReceipt, OperationState, operation_terminal_diagnostics

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .participant_crossing_action import combined_crossing_audit
from .participant_crossing_commit import commit_prepared_crossing, participant_crossing_permitted
from .participant_crossing_mediation import PreparedParticipantCrossing
from .participant_crossing_state_cut import expected_participant_history_heads


@dataclass(frozen=True)
class ParticipantFlowSinkResolution:
    """Trusted resolver-side evidence for one exact-cut SEM-233 final sink."""

    relation: ParticipantFlowControlRelationModel
    context: ParticipantFlowControlValidationContext


@dataclass(frozen=True)
class ParticipantFlowSinkDecision:
    """Bounded, value-independent final-sink decision committed before an effect."""

    permitted: bool
    disposition: ParticipantFlowFinalDisposition
    decision_id: str
    document_id: str
    document_revision: str
    reason_code: str


def flow_sink_history_head_refs(control_plane: object, participant_address: str) -> tuple[str, ...]:
    """Render the live RUN-319 state cut into canonical sorted history-head refs."""

    heads = expected_participant_history_heads(control_plane._snapshot, participant_address)
    refs = tuple(sorted({f"{key}={value if value is not None else 'none'}" for key, value in heads.items()}))
    if not refs:
        raise ValueError("participant flow-sink state cut resolved no history heads")
    return refs


def _denied(disposition: ParticipantFlowFinalDisposition, reason_code: str) -> ParticipantFlowSinkDecision:
    return ParticipantFlowSinkDecision(
        permitted=False,
        disposition=disposition,
        decision_id="",
        document_id="",
        document_revision="",
        reason_code=reason_code,
    )


def _from_relation(
    *,
    permitted: bool,
    disposition: ParticipantFlowFinalDisposition,
    decision: object,
    relation: ParticipantFlowControlRelationModel,
) -> ParticipantFlowSinkDecision:
    return ParticipantFlowSinkDecision(
        permitted=permitted,
        disposition=disposition,
        decision_id=decision.decision_id,
        document_id=relation.document_id,
        document_revision=relation.document_revision,
        reason_code=decision.reason_code,
    )


def resolve_participant_flow_sink_decision(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    *,
    sink_kind: ParticipantFlowSinkKind,
) -> ParticipantFlowSinkDecision | None:
    """Resolve, validate, and bind the SEM-233 final-sink permit for one effect.

    Returns ``None`` only when the active control plane has explicitly opted out
    of SEM-233 final-sink enforcement (``enforce_final_sink_flow_control`` is
    false) and the resolver exposes no ``resolve_flow_sink_decision`` hook;
    callers then run the legacy API-423-only path. When enforcement is required
    but the hook is absent, the sink is denied fail-closed rather than silently
    permitted. Otherwise this returns a permitted decision when every conjunct
    agrees on the live cut and the concrete sink kind, or a denied decision for
    every non-permit class. A resolver exception never leaks and never widens
    permission.
    """

    resolver = getattr(control_plane, "_crossing_policy_resolver", None)
    hook = getattr(resolver, "resolve_flow_sink_decision", None)
    if not callable(hook):
        if getattr(control_plane, "_enforce_final_sink_flow_control", False):
            return _denied(ParticipantFlowFinalDisposition.UNRESOLVED, "flow-sink-enforcement-required")
        return None
    return _resolved_flow_sink_decision(control_plane, crossing, hook, sink_kind)


def _resolved_flow_sink_decision(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    hook: Callable[..., object],
    sink_kind: ParticipantFlowSinkKind,
) -> ParticipantFlowSinkDecision:
    decision_occurrence = crossing.decision
    if decision_occurrence is None:
        return _denied(ParticipantFlowFinalDisposition.UNRESOLVED, "flow-sink-unresolved")
    head_refs = flow_sink_history_head_refs(control_plane, crossing.intent.participant_address)
    resolution = _resolve_flow_sink_relation(control_plane, crossing, hook, sink_kind, head_refs)
    if not isinstance(resolution, ParticipantFlowSinkResolution):
        return resolution
    return _bind_flow_sink_decision(
        resolution.relation,
        crossing,
        sink_kind,
        head_refs,
        decision_occurrence.occurrence.decision_id,
    )


def _resolve_flow_sink_relation(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    hook: Callable[..., object],
    sink_kind: ParticipantFlowSinkKind,
    head_refs: tuple[str, ...],
) -> ParticipantFlowSinkResolution | ParticipantFlowSinkDecision:
    try:
        resolution = hook(
            snapshot=control_plane._snapshot,
            intent=crossing.intent,
            crossing=crossing,
            sink_kind=sink_kind,
            expected_history_head_refs=head_refs,
        )
    except Exception:
        # Fail closed for every resolver failure (BaseException such as
        # KeyboardInterrupt/SystemExit still propagates by design).
        return _denied(ParticipantFlowFinalDisposition.UNRESOLVED, "flow-sink-unresolved")
    if not isinstance(resolution, ParticipantFlowSinkResolution):
        return _denied(ParticipantFlowFinalDisposition.UNRESOLVED, "flow-sink-unresolved")
    return _validated_flow_sink_relation(resolution)


def _validated_flow_sink_relation(
    resolution: ParticipantFlowSinkResolution,
) -> ParticipantFlowSinkResolution | ParticipantFlowSinkDecision:
    try:
        validate_participant_flow_control_resolved_context(
            resolution.relation,
            lambda _document, _scope: resolution.context,
        )
    except Exception:
        return _denied(ParticipantFlowFinalDisposition.UNRESOLVED, "flow-sink-context-invalid")
    return resolution


def _bind_flow_sink_decision(
    relation: ParticipantFlowControlRelationModel,
    crossing: PreparedParticipantCrossing,
    sink_kind: ParticipantFlowSinkKind,
    head_refs: tuple[str, ...],
    reference: str,
) -> ParticipantFlowSinkDecision:
    matches = [decision for decision in relation.sink_decisions if decision.api_423_decision_ref == reference]
    if len(matches) != 1:
        return _denied(ParticipantFlowFinalDisposition.UNRESOLVED, "flow-sink-unresolved")
    decision = matches[0]
    if (
        decision.sink.sink_kind != sink_kind
        or decision.subject.participant_address != crossing.intent.participant_address
        or decision.subject.episode_id != crossing.intent.episode_id
        or tuple(decision.expected_history_head_refs) != head_refs
        or decision.sink.audience_scope_ref != crossing.intent.audience_scope_ref
    ):
        return _denied(ParticipantFlowFinalDisposition.UNRESOLVED, "flow-sink-binding-mismatch")
    return _from_relation(
        permitted=decision.final_disposition == ParticipantFlowFinalDisposition.PERMIT,
        disposition=decision.final_disposition,
        decision=decision,
        relation=relation,
    )


def flow_sink_audit_details(decision: ParticipantFlowSinkDecision) -> dict[str, str]:
    """Return only safe, bounded, value-independent SEM-233 audit references."""

    return {
        "flow_sink_decision_id": decision.decision_id,
        "flow_relation_document_id": decision.document_id,
        "flow_relation_document_revision": decision.document_revision,
        "flow_final_disposition": decision.disposition.value,
    }


def apply_flow_sink_details(audit: AuditEvent, decision: ParticipantFlowSinkDecision) -> AuditEvent:
    """Fold the SEM-233 final-sink reference into a committed crossing audit event."""

    return cast(AuditEvent, replace(audit, details={**audit.details, **flow_sink_audit_details(decision)}))


def flow_sink_denied_record(crossing: PreparedParticipantCrossing) -> ControlPlaneOperationRecord:
    """Return the rejected operation record for a SEM-233 final-sink denial."""

    diagnostic = Diagnostic(
        code="runtime.participant-flow-sink-denied",
        domain="participant",
        address=crossing.intent.participant_address,
        message="Participant flow-control final sink was not permitted.",
    )
    rejected_status = replace(
        crossing.record.status,
        state=OperationState.FAILED,
        diagnostics=operation_terminal_diagnostics(OperationState.FAILED, [diagnostic]),
    )
    return cast(
        ControlPlaneOperationRecord,
        replace(crossing.record, status=rejected_status),
    )


def commit_flow_sink_denial(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    decision: ParticipantFlowSinkDecision,
    *,
    action: str,
) -> OperationReceipt:
    """Durably record a SEM-233 final-sink denial with zero downstream effect."""

    record = flow_sink_denied_record(crossing)
    audit = combined_crossing_audit(
        crossing.audit_event,
        crossing,
        action=action,
        allowed=False,
        reason="flow-sink-denied",
    )
    audit = apply_flow_sink_details(audit, decision)
    running = replace(
        record,
        status=replace(record.status, state=OperationState.RUNNING, diagnostics=[], changed_addresses=[]),
    )
    claimed = control_plane._claim_record(running)
    if claimed.receipt.operation_id != running.receipt.operation_id:
        return claimed.receipt
    control_plane._commit_participant_transition(
        expected_history_heads=crossing.expected_history_heads,
        snapshot=crossing.next_snapshot,
        record=record,
        audit_event=audit,
    )
    return record.receipt


def resolve_flow_sink_denial(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    *,
    sink_kind: ParticipantFlowSinkKind,
    action: str,
) -> tuple[ParticipantFlowSinkDecision | None, OperationReceipt | None]:
    """Resolve a final-sink decision and atomically commit a denial when needed."""

    decision = resolve_participant_flow_sink_decision(control_plane, crossing, sink_kind=sink_kind)
    receipt = None
    if decision is not None and not decision.permitted:
        receipt = commit_flow_sink_denial(control_plane, crossing, decision, action=action)
    return decision, receipt


def early_crossing_receipt(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
) -> OperationReceipt | None:
    """Return an idempotent replay or committed denial receipt, else None to continue.

    Runs immediately before the SEM-233 final-sink guard at each governed sink: an
    already-decided (idempotent) or API-423-denied crossing short-circuits here with
    zero further effect; a live accepted crossing proceeds to the final-sink permit.
    """

    if crossing.existing_receipt is not None:
        return crossing.existing_receipt
    if not participant_crossing_permitted(crossing):
        return commit_prepared_crossing(control_plane, crossing)
    return None


__all__ = (
    "ParticipantFlowSinkDecision",
    "ParticipantFlowSinkResolution",
    "apply_flow_sink_details",
    "commit_flow_sink_denial",
    "early_crossing_receipt",
    "flow_sink_audit_details",
    "flow_sink_denied_record",
    "flow_sink_history_head_refs",
    "resolve_participant_flow_sink_decision",
    "resolve_flow_sink_denial",
)
