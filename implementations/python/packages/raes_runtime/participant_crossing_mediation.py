"""RUN-319 operation-bound mediation types and transaction preparation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import Field
from raes_contracts.contracts.base import ContractModel, NonEmptyString
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDirection,
    ParticipantCrossingGateDisposition,
    ParticipantCrossingInteractionKind,
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingOperation,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
    ParticipantOpacityRuntimeEnforcementBindingModel,
    ParticipantOpacityRuntimeSupportModel,
)
from raes_contracts.contracts.participant_crossing_validation import (
    validate_participant_crossing_occurrence_context,
)
from raes_contracts.contracts.participant_runtime import ParticipantRuntimeOrderingBasis
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_opacity_runtime import validate_participant_opacity_runtime_enforcement
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    operation_terminal_diagnostics,
)
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .control_plane_mutation import external_control_plane_call
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity, ParticipantAudienceSubjectBinding
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .participant_opacity_enforcement import (
    bind_active_participant_opacity_support,
    normalize_participant_opacity_resolution,
    validate_persisted_participant_opacity,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ParticipantCrossingIntent(ContractModel):
    """Trusted operation-bound intent; policy gates and outcomes are runtime-owned."""

    participant_address: NonEmptyString
    episode_id: NonEmptyString
    direction: ParticipantCrossingDirection
    interaction_kind: ParticipantCrossingInteractionKind
    audience_scope_ref: NonEmptyString
    subject: ParticipantCrossingSubjectReferenceModel
    controller_ref: NonEmptyString
    authority_basis_refs: list[NonEmptyString] = Field(min_length=1)
    requested_operation: ParticipantCrossingOperation
    action_or_projection_ref: NonEmptyString
    required_evidence_refs: list[NonEmptyString] = Field(min_length=1)
    effective_order: int = Field(ge=0)
    order_model: ParticipantRuntimeOrderingBasis
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    object_marking_refs: list[NonEmptyString] = Field(min_length=1)
    authorization_scope: NonEmptyString
    loss_and_limitations: list[NonEmptyString] = Field(min_length=1)


class ParticipantCrossingEvidence(ContractModel):
    """Caller-owned evidence metadata with no incumbent-operation coordinates."""

    audience_scope_ref: NonEmptyString
    required_evidence_refs: list[NonEmptyString] = Field(min_length=1)
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    object_marking_refs: list[NonEmptyString] = Field(min_length=1)
    authorization_scope: NonEmptyString
    loss_and_limitations: list[NonEmptyString] = Field(min_length=1)


@dataclass(frozen=True)
class ParticipantCrossingSemanticGates:
    """Trusted semantic gate results excluding runtime-owned identity/capability gates."""

    participant_authority: ParticipantCrossingGateDisposition
    action_admission: ParticipantCrossingGateDisposition
    visibility: ParticipantCrossingGateDisposition
    marking_authorization: ParticipantCrossingGateDisposition
    declassification: ParticipantCrossingGateDisposition
    transformation_validity: ParticipantCrossingGateDisposition


@dataclass(frozen=True)
class ParticipantCrossingPolicyResolution:
    """One trusted exact-cut policy resolution."""

    policy: ParticipantCrossingPolicyReferenceModel
    gates: ParticipantCrossingSemanticGates
    reason_code: str
    required_operation: ParticipantCrossingOperation | None = None
    required_support_level: ParticipantFeatureSupportLevel = ParticipantFeatureSupportLevel.EXACT
    allowed_downgrades: dict[str, ParticipantFeatureSupportLevel] = field(default_factory=dict)
    downgrade_policy_ref: str | None = None
    downgrade_provenance_ref: str | None = None
    transformation: ParticipantCrossingTransformationResolution | None = None
    opacity_enforcement: ParticipantOpacityRuntimeEnforcementBindingModel | None = None


@dataclass(frozen=True)
class ParticipantCrossingTransformationResolution:
    """Trusted non-mutating result of one governed crossing transformation."""

    result_subject: ParticipantCrossingSubjectReferenceModel
    rule_ref: str
    rule_revision: str
    result_marking_refs: tuple[str, ...]
    declassification_basis_ref: str | None = None
    losses: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class ParticipantCrossingValidationContext:
    """Trusted indexes needed by API-423 cross-record validation."""

    known_subjects: tuple[ParticipantCrossingSubjectReferenceModel, ...]
    policies: tuple[ParticipantCrossingPolicyReferenceModel, ...]
    known_evidence_refs: frozenset[str]
    known_authority_basis_refs: frozenset[str]
    opacity_enforcement_supports: tuple[ParticipantOpacityRuntimeSupportModel, ...] = ()


class ParticipantCrossingPolicyResolver(Protocol):
    """Resolve current policy and historical validation context from trusted state."""

    def resolve(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantCrossingPolicyResolution: ...

    def validation_context(
        self,
        snapshot: RuntimeSnapshot,
        participant_address: str,
    ) -> ParticipantCrossingValidationContext: ...

    def resolve_participant_view_evidence(
        self,
        *,
        snapshot: RuntimeSnapshot,
        participant_address: str,
        episode_id: str,
        interaction_kind: ParticipantCrossingInteractionKind,
        projection_ref: str,
        audience_binding: ParticipantAudienceSubjectBinding,
    ) -> ParticipantCrossingEvidence:
        """Resolve trusted egress evidence for an authenticated API adapter."""

        ...


@dataclass(frozen=True)
class PreparedParticipantCrossing:
    """Uncommitted crossing decision bound to one exact runtime state cut."""

    intent: ParticipantCrossingIntent
    identity: ControlPlaneIdentity
    next_snapshot: RuntimeSnapshot
    expected_history_heads: dict[str, str | None]
    record: ControlPlaneOperationRecord
    audit_event: AuditEvent
    decision: ParticipantCrossingOccurrenceModel | None
    disposition: ParticipantCrossingDecisionDisposition | None
    governed_subject: ParticipantCrossingSubjectReferenceModel
    existing_receipt: OperationReceipt | None = None


def _resolve_crossing_policy(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    resolver: ParticipantCrossingPolicyResolver,
    incumbent_carrier: object | None,
) -> ParticipantCrossingPolicyResolution:
    operation_resolver = getattr(resolver, "resolve_operation", None)
    with external_control_plane_call(control_plane):
        resolution = (
            operation_resolver(intent, control_plane._snapshot, incumbent_carrier)
            if callable(operation_resolver)
            else resolver.resolve(intent, control_plane._snapshot)
        )
        context = resolver.validation_context(
            control_plane._snapshot,
            intent.participant_address,
        )
    resolution = bind_active_participant_opacity_support(
        resolution,
        context.opacity_enforcement_supports,
    )
    if resolution.opacity_enforcement is None:
        return resolution
    support = next(
        (
            candidate
            for candidate in context.opacity_enforcement_supports
            if candidate.binding == resolution.opacity_enforcement
        ),
        None,
    )
    if support is None:
        raise ValueError("participant opacity runtime binding is not admitted by the resolver context")
    validate_participant_opacity_runtime_enforcement(
        resolution.opacity_enforcement,
        support=support,
        participant_address=intent.participant_address,
        audience_scope_ref=intent.audience_scope_ref,
    )
    return normalize_participant_opacity_resolution(resolution)


def prepare_participant_crossing(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    *,
    identity: object,
    idempotency_key: str,
    incumbent_carrier: object | None = None,
) -> PreparedParticipantCrossing:
    """Resolve one crossing without releasing the owning operation boundary."""

    from .participant_crossing_policy import (
        _applicable_semantic_gates,
        _decision_disposition,
        _decision_gates,
        _require_crossing_identity,
        _resolve_backend_support,
    )
    from .participant_crossing_records import (
        _CrossingDecisionPreparation,
        _expected_history_heads,
        _prepare_crossing_decision,
        _scoped_idempotency_key,
        _semantic_fingerprint,
    )

    authenticated = _require_crossing_identity(control_plane, intent, identity)
    resolver = getattr(control_plane, "_crossing_policy_resolver", None)
    if resolver is None:
        raise ValueError("participant crossing policy resolver is required")
    expected_heads = _expected_history_heads(control_plane._snapshot, intent.participant_address)
    scoped_key = _scoped_idempotency_key(
        control_plane,
        intent,
        authenticated,
        idempotency_key,
    )
    existing = control_plane._store.find_by_idempotency(scoped_key) if scoped_key else None
    fingerprint_heads = expected_heads
    if existing is not None:
        _require_replay_state_cut(existing, expected_heads)
        fingerprint_heads = existing.decision_history_heads
    try:
        resolution = _resolve_crossing_policy(
            control_plane,
            intent,
            resolver,
            incumbent_carrier,
        )
    except (TypeError, ValueError):
        return _prepare_policy_unresolved(
            control_plane,
            intent,
            authenticated,
            idempotency_key,
            expected_heads=expected_heads,
            scoped_key=scoped_key,
            existing=existing,
        )
    support = _resolve_backend_support(control_plane, intent, resolution)
    gates = _decision_gates(_applicable_semantic_gates(intent, resolution), support.gate)
    disposition = _decision_disposition(gates, resolution)
    semantic_fingerprint = _semantic_fingerprint(
        control_plane,
        intent,
        authenticated,
        resolution,
        support,
        fingerprint_heads,
    )
    if existing is not None:
        if existing.request_fingerprint != semantic_fingerprint:
            raise ValueError("Idempotency-Key was reused with different semantics.")
        control_plane._operations[existing.receipt.operation_id] = existing
        return _existing_preparation(
            control_plane,
            intent,
            authenticated,
            expected_heads,
            existing,
        )
    return _prepare_crossing_decision(
        control_plane,
        intent,
        _CrossingDecisionPreparation(
            identity=authenticated,
            resolution=resolution,
            support=support,
            gates=gates,
            disposition=disposition,
            expected_heads=expected_heads,
            semantic_fingerprint=semantic_fingerprint,
            scoped_key=scoped_key,
        ),
    )


def _existing_preparation(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    expected_heads: dict[str, str | None],
    existing: ControlPlaneOperationRecord,
) -> PreparedParticipantCrossing:
    return PreparedParticipantCrossing(
        intent=intent,
        identity=identity,
        next_snapshot=control_plane._snapshot,
        expected_history_heads=expected_heads,
        record=existing,
        audit_event=AuditEvent(
            timestamp=existing.status.updated_at,
            action="participant_crossing_replay",
            identity=identity.identity,
            allowed=existing.status.state is OperationState.SUCCEEDED,
            target=intent.participant_address,
            operation_id=existing.receipt.operation_id,
            reason="idempotent-replay",
        ),
        decision=None,
        disposition=None,
        governed_subject=intent.subject,
        existing_receipt=existing.receipt,
    )


def _prepare_policy_unresolved(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    idempotency_key: str,
    *,
    expected_heads: dict[str, str | None],
    scoped_key: str,
    existing: ControlPlaneOperationRecord | None,
) -> PreparedParticipantCrossing:
    del idempotency_key
    fingerprint_heads = existing.decision_history_heads if existing is not None else expected_heads
    stable_intent = intent.model_dump(mode="json")
    stable_intent.pop("effective_order", None)
    fingerprint_payload = {
        "target": control_plane.target_name,
        "identity": identity.identity,
        "decision_history_heads": fingerprint_heads,
        "intent": stable_intent,
        "outcome": "policy-unresolved",
    }
    semantic_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if existing is not None:
        if existing.request_fingerprint != semantic_fingerprint:
            raise ValueError("Idempotency-Key was reused with different semantics.")
        control_plane._operations[existing.receipt.operation_id] = existing
        return _existing_preparation(
            control_plane,
            intent,
            identity,
            expected_heads,
            existing,
        )
    operation_id = str(uuid4())
    submitted_at = _utc_now()
    diagnostic = Diagnostic(
        code="runtime.participant-crossing-policy-unresolved",
        domain="participant",
        address=intent.participant_address,
        message="Participant crossing policy could not be resolved.",
    )
    operation_context = operation_admission_context(
        control_plane,
        kind=OperationKind.PARTICIPANT_CROSSING,
        request=intent,
        identity=identity,
        run_scope=f"run:{intent.episode_id}",
    )
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        submitted_at=submitted_at,
        accepted=True,
        context=operation_context,
        diagnostics=operation_terminal_diagnostics(OperationState.FAILED, [diagnostic]),
    )
    record = ControlPlaneOperationRecord(
        receipt=receipt,
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.FAILED,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=operation_context,
            diagnostics=operation_terminal_diagnostics(OperationState.FAILED, [diagnostic]),
            changed_addresses=[intent.participant_address],
        ),
        request_fingerprint=semantic_fingerprint,
        idempotency_key=scoped_key,
        decision_history_heads=expected_heads,
        result_history_heads=expected_heads,
    )
    audit_event = AuditEvent(
        timestamp=submitted_at,
        action="record_participant_crossing",
        identity=identity.identity,
        allowed=False,
        target=intent.participant_address,
        operation_id=operation_id,
        reason="policy-unresolved",
        details={
            "episode_id": intent.episode_id,
            "audience_scope_ref": intent.audience_scope_ref,
        },
    )
    return PreparedParticipantCrossing(
        intent=intent,
        identity=identity,
        next_snapshot=control_plane._snapshot,
        expected_history_heads=expected_heads,
        record=record,
        audit_event=audit_event,
        decision=None,
        disposition=None,
        governed_subject=intent.subject,
    )


def _require_replay_state_cut(
    existing: ControlPlaneOperationRecord,
    current_heads: dict[str, str | None],
) -> None:
    if not existing.decision_history_heads or not existing.result_history_heads:
        raise ValueError("idempotent participant crossing is missing its state-cut binding")
    if current_heads != existing.result_history_heads:
        raise ValueError("Idempotency-Key cannot replay after the participant state cut advanced.")


def validate_persisted_crossing_history(
    snapshot: RuntimeSnapshot,
    resolver: ParticipantCrossingPolicyResolver,
) -> None:
    """Fail closed when persisted API-423 history cannot resolve on restart."""

    for participant_address, values in snapshot.participant_crossing_history.items():
        records = [ParticipantCrossingOccurrenceModel.model_validate(value) for value in values]
        context = resolver.validation_context(snapshot, participant_address)
        validate_participant_crossing_occurrence_context(
            records,
            known_subjects=context.known_subjects,
            policies=context.policies,
            known_evidence_refs=context.known_evidence_refs,
            known_authority_basis_refs=context.known_authority_basis_refs,
        )
        validate_persisted_participant_opacity(records, context)


__all__ = (
    "ParticipantCrossingEvidence",
    "ParticipantCrossingIntent",
    "ParticipantCrossingPolicyResolution",
    "ParticipantCrossingPolicyResolver",
    "ParticipantCrossingSemanticGates",
    "ParticipantCrossingTransformationResolution",
    "ParticipantCrossingValidationContext",
    "PreparedParticipantCrossing",
    "prepare_participant_crossing",
    "validate_persisted_crossing_history",
)
