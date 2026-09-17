"""Backend-neutral, read-only crash-recovery effect observation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from raes_contracts.operation_lifecycle import OperationKind
from raes_contracts.runtime_state import RuntimeSnapshot, validate_changed_addresses


class RecoveryEffectClassification(str, Enum):
    """Closed operational classification for an interrupted effect."""

    EFFECT_ABSENT = "effect-absent"
    EFFECT_APPLIED = "effect-applied"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class RecoveryObservationRequest:
    """Minimum value-free context used to bind one recovery readback."""

    operation_id: str
    operation_kind: OperationKind
    target_scope: str
    run_scope: str
    request_commitment: str
    baseline_snapshot: RuntimeSnapshot

    def __post_init__(self) -> None:
        for name in ("operation_id", "target_scope", "run_scope", "request_commitment"):
            value = getattr(self, name)
            if not value or len(value) > 256:
                raise ValueError(f"{name} must contain between 1 and 256 characters")
        if not isinstance(self.operation_kind, OperationKind):
            raise TypeError("operation_kind must be an OperationKind")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", self.request_commitment):
            raise ValueError("request_commitment must be a canonical sha256 digest")
        if not isinstance(self.baseline_snapshot, RuntimeSnapshot):
            raise TypeError("baseline_snapshot must be a RuntimeSnapshot")


@dataclass(frozen=True)
class RecoveryObservationResult:
    """Bound recovery classification and optional neutral applied state."""

    classification: RecoveryEffectClassification
    operation_id: str
    request_commitment: str
    snapshot: RuntimeSnapshot | None = None
    changed_addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.operation_id or len(self.operation_id) > 256:
            raise ValueError("operation_id must contain between 1 and 256 characters")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", self.request_commitment):
            raise ValueError("request_commitment must be a canonical sha256 digest")
        if not isinstance(self.classification, RecoveryEffectClassification):
            raise TypeError("classification must be a RecoveryEffectClassification")
        validate_changed_addresses(list(self.changed_addresses))
        applied = self.classification is RecoveryEffectClassification.EFFECT_APPLIED
        if applied != (self.snapshot is not None):
            raise ValueError("effect-applied requires a snapshot and other classifications forbid one")
        if not applied and self.changed_addresses:
            raise ValueError("only effect-applied may report changed addresses")


class RecoveryObserver(Protocol):
    """Read-only operational observer used during startup reconciliation."""

    def observe_effect(self, request: RecoveryObservationRequest) -> RecoveryObservationResult: ...


__all__ = (
    "RecoveryEffectClassification",
    "RecoveryObservationRequest",
    "RecoveryObservationResult",
    "RecoveryObserver",
)
