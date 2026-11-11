"""Operation claim columns that the store queries read, derived from each operation record.

A store keeps these columns next to the record payload so that idempotency lookups can use an index.
The payload digest does not cover them. Thus every read compares them with the record they index.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from raes_contracts.errors import EvidenceIntegrityError

if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneOperationRecord

# Builds before the composite claim derived these participant keys from the request. The schema migration
# quarantines them because the original client key is not recoverable.
LEGACY_OPAQUE_KEY_PREFIXES = ("participant-control:", "participant-crossing:")
_CLAIM_COLUMN_MISMATCH = "operation claim columns do not match the operation record"


def local_operation_claim_columns(record: ControlPlaneOperationRecord) -> tuple[str, str, str, str, str, str, int, str]:
    """Return the values of the local `operations` columns `idempotency_key`, `actor_id`, `operation_kind`,
    `target_scope`, `run_scope`, `request_commitment`, `legacy_opaque_claim` and `request_fingerprint`."""

    context = record.receipt.context
    legacy_opaque = record.legacy_request_commitment and record.idempotency_key.startswith(LEGACY_OPAQUE_KEY_PREFIXES)
    return (
        record.idempotency_key,
        context.actor_id,
        context.operation_kind.value,
        context.target_scope,
        context.run_scope,
        context.request_commitment,
        int(legacy_opaque),
        record.request_fingerprint,
    )


def ledger_operation_claim_columns(record: ControlPlaneOperationRecord) -> tuple[str, str, str]:
    """Return the values of the ledger columns `actor_id`, `operation_kind` and `idempotency_key`."""

    context = record.receipt.context
    return (context.actor_id, context.operation_kind.value, record.idempotency_key)


def require_claim_columns(expected: tuple[object, ...], stored: Sequence[object]) -> None:
    """Refuse a stored row whose claim columns do not match the record that it carries."""

    if expected != tuple(stored):
        raise EvidenceIntegrityError(_CLAIM_COLUMN_MISMATCH)


__all__ = (
    "LEGACY_OPAQUE_KEY_PREFIXES",
    "ledger_operation_claim_columns",
    "local_operation_claim_columns",
    "require_claim_columns",
)
