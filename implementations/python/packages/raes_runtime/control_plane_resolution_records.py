"""Durable classification of linked administrative resolution records."""

from __future__ import annotations

from enum import Enum

from .control_plane_store import ControlPlaneOperationRecord
from .mixed_runtime_recovery import has_mixed_resolution_cut
from .operation_reconciliation_ledger import _matches_resolution_parent, valid_reconciliation_child


class IndeterminateResolutionDisposition(str, Enum):
    """Closed administrative acceptance of the currently stored state cut."""

    ACCEPT_CURRENT_SNAPSHOT = "accept-current-snapshot"


def is_valid_resolution_child(
    parent: ControlPlaneOperationRecord,
    child: ControlPlaneOperationRecord,
) -> bool:
    """Recognize a child only when it can safely discharge its parent."""

    if parent.invocation is not None and parent.invocation.reserved:
        return valid_reconciliation_child(parent, child)
    return (
        not has_mixed_resolution_cut(parent)
        and _matches_resolution_parent(parent, child)
        and bool(child.idempotency_key)
        and child.idempotency_key != parent.idempotency_key
        and child.result_payload
        == {"resolution_disposition": IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT.value}
    )


__all__ = ("IndeterminateResolutionDisposition", "is_valid_resolution_child")
