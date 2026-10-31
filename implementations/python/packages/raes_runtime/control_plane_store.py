"""Durable storage for the per-target runtime control plane."""

# ruff: noqa: F822, I001

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from raes_contracts.contracts import InjectOccurrenceModel, InjectOccurrenceOutcomeModel
from raes_contracts.contracts.participant_inject_application import ParticipantInjectContentModel
from raes_contracts.contracts.participant_control_occurrence_v2 import ParticipantControlOccurrenceV2Model
from raes_backend_protocols.inject_execution import InjectExecutionEvidence

from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)

from .control_plane_audit import require_audit_event_fields
from .control_plane_store_transitions import (
    _require_operation_record_identity,
    _require_operation_record_transition,
    _require_terminal_operation_transition,
)
from .operation_invocation_ledger import InvocationLedger
from .operation_reconciliation_ledger import InvocationReconciliation
from .control_plane_store_revision import (
    SnapshotRevisionConflict,
    SnapshotState,
)
from . import control_plane_store_history as _store_history
from . import control_plane_store_types as _store_types
from raes_contracts.errors import ConflictError, InvalidInputError
from .errors import IdempotencyClaimConflictError

ParticipantCrossingHistoryPresence = _store_types.ParticipantCrossingHistoryPresence
TerminalCommitMode = _store_types.TerminalCommitMode
_require_expected_control_head = _store_history.require_expected_control_head
_require_expected_history_heads = _store_history.require_expected_history_heads
_snapshot_from_payload = _store_types._snapshot_from_payload
_snapshot_payload = _store_types._snapshot_payload
participant_crossing_history_presence = _store_types.participant_crossing_history_presence

_IDEMPOTENCY_KEY_CONFLICT = "idempotency key already belongs to another operation"
IDEMPOTENCY_CLAIM_CONFLICT = "idempotency claim conflicts with the original request"

IdempotencyClaimIdentity = tuple[str, OperationKind, str]
NewClaimBlock = Literal["current-state", "indeterminate", "stale-base-snapshot"] | None
_MAX_IDEMPOTENCY_KEY_LENGTH = 256
_MIXED_CLAIM_KINDS = frozenset(
    {OperationKind.COMPOSITION_PHASE, OperationKind.PARTICIPANT_ACTION, OperationKind.PARTICIPANT_CROSSING}
)
_ACTIVE_CLAIM_STATES = frozenset({OperationState.ACCEPTED, OperationState.RUNNING, OperationState.INDETERMINATE})


def mixed_claim_conflicts(
    new: ControlPlaneOperationRecord,
    existing_records: Iterable[ControlPlaneOperationRecord],
) -> bool:
    """Serialize external mixed effects in one run at the store claim."""

    context = new.status.context
    if context.operation_kind not in _MIXED_CLAIM_KINDS:
        return False
    mixed_keys = {
        key
        for key in (*new.decision_history_heads, *new.result_history_heads)
        if key.startswith("mixed_composition_history:")
    }
    if not mixed_keys:
        return False
    from .operation_reconciliation_ledger import valid_reconciliation_child

    records = tuple(existing_records)
    return any(
        _active_mixed_claim_overlaps(context, mixed_keys, existing)
        and not any(valid_reconciliation_child(existing, child) for child in records)
        for existing in records
    )


def _active_mixed_claim_overlaps(
    context: OperationAdmissionContext,
    mixed_keys: set[str],
    existing: ControlPlaneOperationRecord,
) -> bool:
    prior = existing.status.context
    if (prior.target_scope, prior.run_scope) != (context.target_scope, context.run_scope):
        return False
    if prior.operation_kind not in _MIXED_CLAIM_KINDS or existing.status.state not in _ACTIVE_CLAIM_STATES:
        return False
    prior_keys = set(existing.decision_history_heads) | set(existing.result_history_heads)
    return bool(mixed_keys.intersection(prior_keys))


@dataclass(frozen=True)
class AuditEvent:
    """Append-only security and control-plane audit event."""

    timestamp: str
    action: str
    identity: str
    allowed: bool
    target: str
    operation_id: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_audit_event_fields(
            timestamp=self.timestamp,
            action=self.action,
            identity=self.identity,
            target=self.target,
            operation_id=self.operation_id,
            reason=self.reason,
            details=self.details,
        )


@dataclass(frozen=True)
class ControlPlaneOperationRecord:
    """Persisted receipt/status pair for one operation."""

    receipt: OperationReceipt
    status: OperationStatus
    request_fingerprint: str = ""
    idempotency_key: str = ""
    result_payload: dict[str, Any] | None = None
    decision_history_heads: dict[str, str | None] = field(default_factory=dict)
    result_history_heads: dict[str, str | None] = field(default_factory=dict)
    legacy_request_commitment: bool = False
    invocation: InvocationLedger | None = None
    reconciliation: InvocationReconciliation | None = None
    inject_occurrence: InjectOccurrenceModel | None = None
    inject_outcome: InjectOccurrenceOutcomeModel | None = None
    inject_evidence: InjectExecutionEvidence | None = None
    inject_delivery: ParticipantInjectContentModel | None = None
    inject_delivery_control: ParticipantControlOccurrenceV2Model | None = None

    def __post_init__(self) -> None:
        _require_operation_record_identity(self)


INTERRUPTED_OPERATION_DIAGNOSTIC_CODE = "runtime.control-plane.operation-interrupted"


def idempotency_claim_identity(
    context: OperationAdmissionContext,
    key: str,
) -> IdempotencyClaimIdentity:
    """Return the provider-private claim identity inside one target/run store."""

    return (context.actor_id, context.operation_kind, key)


def require_idempotency_key(key: str) -> str:
    """Validate the one client-key shape used by every operation family."""

    if not isinstance(key, str):
        raise TypeError("Idempotency-Key must be a string")
    if key and (len(key) > _MAX_IDEMPOTENCY_KEY_LENGTH or any(character < "!" or character > "~" for character in key)):
        raise InvalidInputError("Idempotency-Key must be 1-256 visible ASCII characters")
    return key


def _require_same_idempotency_replay(
    existing: ControlPlaneOperationRecord,
    candidate: ControlPlaneOperationRecord,
    *,
    legacy_request_fingerprint: str = "",
) -> None:
    """Authorize one replay without disclosing the incumbent on mismatch."""

    existing_context = existing.receipt.context
    candidate_context = candidate.receipt.context
    context_matches = existing_context == candidate_context
    fingerprint_matches = existing.request_fingerprint == candidate.request_fingerprint
    if existing.legacy_request_commitment and legacy_request_fingerprint:
        context_matches = (
            existing_context.model_copy(update={"request_commitment": candidate_context.request_commitment})
            == candidate_context
        )
        fingerprint_matches = existing.request_fingerprint == legacy_request_fingerprint
    if (
        not context_matches
        or not fingerprint_matches
        or candidate.decision_history_heads not in (existing.decision_history_heads, existing.result_history_heads)
    ):
        raise IdempotencyClaimConflictError(IDEMPOTENCY_CLAIM_CONFLICT)


def _raise_new_claim_block(block: NewClaimBlock) -> None:
    if block == "current-state":
        raise NewClaimRejected
    if block == "indeterminate":
        raise IndeterminateClaimBlocked("indeterminate operation requires resolution before effectful mutation")
    if block == "stale-base-snapshot":
        raise ConflictError("explicit base snapshot does not match the authoritative runtime snapshot")


class NewClaimRejected(ConflictError):
    """Signal that current state forbids creation after incumbent resolution."""


class IndeterminateClaimBlocked(ConflictError):
    """An unresolved indeterminate operation blocks a new claim; recovery stays open."""


def terminal_operation_audit(record: ControlPlaneOperationRecord) -> AuditEvent:
    """Build the canonical actor-bound audit for one accepted terminal operation."""

    context = record.status.context
    state = record.status.state
    return AuditEvent(
        timestamp=record.status.updated_at,
        action=f"{context.operation_kind.value}_terminal",
        identity=context.actor_id,
        allowed=True,
        target=context.target_scope,
        operation_id=record.receipt.operation_id,
        reason=f"operation-{state.value}",
        details={"state": state.value},
    )


def _require_terminal_operation_audit(
    record: ControlPlaneOperationRecord,
    audit_event: AuditEvent,
) -> None:
    expected = terminal_operation_audit(record)
    if audit_event != expected:
        raise ValueError("terminal audit does not match the immutable operation context")


def _require_operation_audit_binding(
    record: ControlPlaneOperationRecord,
    audit_event: AuditEvent,
) -> None:
    """Reject audit events that are not bound to their immutable operation actor."""
    if (
        audit_event.operation_id != record.receipt.operation_id
        or audit_event.identity != record.status.context.actor_id
        or audit_event.timestamp != record.status.updated_at
    ):
        raise ValueError("operation audit is not actor-bound to the immutable operation context")


def _require_terminal_commit_mode(mode: TerminalCommitMode) -> None:
    if not isinstance(mode, TerminalCommitMode):
        raise TypeError("terminal commit mode must be a TerminalCommitMode")


def _require_terminal_retry_mode(
    *,
    current_revision: int,
    expected_revision: int,
    mode: TerminalCommitMode,
) -> None:
    committed_revision = expected_revision + 1 if mode is TerminalCommitMode.SNAPSHOT_BEARING else expected_revision
    if current_revision != committed_revision:
        raise ValueError("terminal operation retry does not match the durable commit mode")


class ControlPlaneStore(Protocol):
    """Durable persistence capabilities for control-plane state."""

    def load_snapshot(self) -> RuntimeSnapshot: ...

    def load_snapshot_state(self) -> SnapshotState: ...

    def save_snapshot(
        self,
        snapshot: RuntimeSnapshot,
        *,
        expected_revision: int,
    ) -> SnapshotState: ...

    def load_records(self) -> dict[str, ControlPlaneOperationRecord]: ...

    def save_record(self, record: ControlPlaneOperationRecord) -> None: ...

    def find_by_idempotency(
        self,
        key: str,
        *,
        context: OperationAdmissionContext | None = None,
    ) -> ControlPlaneOperationRecord | None: ...

    def append_audit(self, event: AuditEvent) -> None: ...

    def read_audit(self) -> list[AuditEvent]: ...

    def commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> SnapshotState: ...

    def commit_participant_transition(
        self,
        *,
        expected_history_heads: dict[str, str | None],
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> SnapshotState: ...


class AtomicControlPlaneStore(ControlPlaneStore, Protocol):
    """Crash-atomic claim and terminal commit capabilities."""

    def claim_record(
        self,
        record: ControlPlaneOperationRecord,
        *,
        legacy_request_fingerprint: str = "",
        new_claim_blocked: NewClaimBlock = None,
    ) -> ControlPlaneOperationRecord: ...

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        audit_event: AuditEvent | None = None,
        mode: TerminalCommitMode = TerminalCommitMode.SNAPSHOT_BEARING,
        expected_revision: int,
    ) -> SnapshotState: ...


@runtime_checkable
class RuntimeAdmittedControlPlaneStore(Protocol):
    """Durable provider that must be admitted before any store access."""

    def admit_runtime(self, *, target_scope: str, run_scope: str) -> object: ...

    def close(self) -> None: ...


def require_operation_record_scopes(
    records: dict[str, ControlPlaneOperationRecord], *, target_scope: str, run_scope: str
) -> None:
    """Reject persisted operations outside the runtime-admitted store scope."""

    for record in records.values():
        context = record.status.context
        if (context.target_scope, context.run_scope) != (target_scope, run_scope):
            raise ConflictError("persisted operation scope does not match control-plane runtime admission")


from .control_plane_store_memory import InMemoryControlPlaneStore  # noqa: E402


def __getattr__(name: str) -> object:
    if name == "LocalControlPlaneStore":
        from .control_plane_store_local import LocalControlPlaneStore

        return LocalControlPlaneStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AtomicControlPlaneStore",
    "AuditEvent",
    "ControlPlaneOperationRecord",
    "ControlPlaneStore",
    "IDEMPOTENCY_CLAIM_CONFLICT",
    "IdempotencyClaimIdentity",
    "INTERRUPTED_OPERATION_DIAGNOSTIC_CODE",
    "InMemoryControlPlaneStore",
    "LocalControlPlaneStore",
    "ParticipantCrossingHistoryPresence",
    "SnapshotRevisionConflict",
    "SnapshotState",
    "RuntimeAdmittedControlPlaneStore",
    "TerminalCommitMode",
    "_require_expected_control_head",
    "_require_expected_history_heads",
    "_require_operation_record_transition",
    "_require_same_idempotency_replay",
    "_require_terminal_operation_transition",
    "_snapshot_from_payload",
    "_snapshot_payload",
    "participant_crossing_history_presence",
    "idempotency_claim_identity",
    "require_operation_record_scopes",
    "require_idempotency_key",
    "terminal_operation_audit",
]
