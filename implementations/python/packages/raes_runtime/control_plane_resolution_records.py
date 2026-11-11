"""Durable classification of linked administrative resolution records."""

from __future__ import annotations

from enum import Enum

from raes_contracts.errors import AuthorizationError
from raes_contracts.operation_lifecycle import OperationAdmissionContext

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


def authorize_resolution(
    control_plane: object,
    parent: ControlPlaneOperationRecord,
    context: OperationAdmissionContext,
    identity: object | None,
) -> None:
    roles = {getattr(role, "value", role) for role in getattr(identity, "roles", ())}
    target_name = getattr(identity, "target_name", None)
    required_subjects = {
        scope for scope in parent.status.context.authorization_scope if scope.startswith("participant-control:")
    }
    supplied_scopes = set(context.authorization_scope)
    allowed = (
        "operator" in roles
        and target_name == control_plane._target.name
        and parent.status.context.target_scope == context.target_scope
        and parent.status.context.run_scope == context.run_scope
        and required_subjects.issubset(supplied_scopes)
    )
    if allowed:
        return
    control_plane.record_audit(
        action="resolve_indeterminate_operation",
        identity=getattr(identity, "identity", "unattributed"),
        allowed=False,
        target=parent.status.context.target_scope,
        operation_id=parent.receipt.operation_id,
        reason="resolution-forbidden",
    )
    raise AuthorizationError("indeterminate resolution is forbidden")


__all__ = ("IndeterminateResolutionDisposition", "is_valid_resolution_child")
