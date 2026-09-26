"""Durable classification of linked administrative resolution records."""

from __future__ import annotations

from enum import Enum

from raes_contracts.runtime_state import OperationKind, OperationState

from .control_plane_store import ControlPlaneOperationRecord
from .mixed_runtime_recovery import has_mixed_resolution_cut


class IndeterminateResolutionDisposition(str, Enum):
    """Closed administrative acceptance of the currently stored state cut."""

    ACCEPT_CURRENT_SNAPSHOT = "accept-current-snapshot"


def is_valid_resolution_child(
    parent: ControlPlaneOperationRecord,
    child: ControlPlaneOperationRecord,
) -> bool:
    """Recognize a child only when it can safely discharge its parent."""

    context = child.status.context
    return (
        not has_mixed_resolution_cut(parent)
        and parent.status.state is OperationState.INDETERMINATE
        and child.status.state is OperationState.SUCCEEDED
        and context.operation_kind is OperationKind.INDETERMINATE_RESOLUTION
        and context.parent_operation_id == parent.receipt.operation_id
        and context.target_scope == parent.status.context.target_scope
        and context.run_scope == parent.status.context.run_scope
        and "role:operator" in context.authorization_scope
        and bool(child.idempotency_key)
        and child.idempotency_key != parent.idempotency_key
        and child.result_payload
        == {"resolution_disposition": IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT.value}
    )


__all__ = ("IndeterminateResolutionDisposition", "is_valid_resolution_child")
