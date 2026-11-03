"""Claim compatibility for tool actions hosted by a supervised due operation (issue #1740).

A supervised due operation reserves the run's effect lane while its autonomous
invocation runs. A tool action of that invocation is a child operation record.
Its claim is compatible with the parent reservation only when the record proves
the exact parent, scope, actor and tool-action binding. A parent id alone grants
nothing, and unrelated claims stay excluded.
"""

from __future__ import annotations

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.operation_lifecycle import OperationKind, OperationState
from raes_contracts.participant_tool_actions import TOOL_ACTION_ID_PREFIX

from .participant_delivery_invocation_records import (
    delivery_invocation_binding,
    delivery_tool_binding,
    delivery_tool_origin_matches,
)
from .participant_tool_claim_payloads import (
    TOOL_ACTION_IDEMPOTENCY_PREFIX,
    TOOL_ACTION_RECORD_KIND,
    TOOL_ADMISSION_PARENT_NOT_LIVE,
    TOOL_ADMISSION_STOPPED,
    TOOL_ADMISSION_UNRESOLVED,
    tool_action_claim_payload,
)


def invocation_tool_child_of(parent: object, child: object) -> bool:
    """Return whether ``child`` is a validated tool action hosted by the running ``parent``."""

    context = child.status.context
    parent_context = parent.status.context
    claim = tool_action_claim_payload(child.result_payload)
    delivery = delivery_invocation_binding(parent)
    if delivery is not None and (
        not delivery_tool_origin_matches(delivery, claim) or delivery_tool_binding(child) is None
    ):
        return False
    return _valid_child_claim(child, claim) and _valid_parent_context(parent, context, parent_context)


def _valid_child_claim(child: object, claim: object) -> bool:
    context, operation_id = child.status.context, child.receipt.operation_id
    return bool(
        claim is not None
        and child.invocation is None
        and operation_id.startswith(TOOL_ACTION_ID_PREFIX)
        and child.idempotency_key == TOOL_ACTION_IDEMPOTENCY_PREFIX + operation_id
        and context.operation_kind is OperationKind.PARTICIPANT_ACTION
        and context.request_commitment == canonical_json_digest(claim)
    )


def _valid_parent_context(parent: object, context: object, parent_context: object) -> bool:
    return bool(
        context.parent_operation_id == parent.receipt.operation_id
        and parent.status.state is OperationState.RUNNING
        and parent_context.operation_kind is OperationKind.COMPOSITION_PHASE
        and _same_parent_authority(context, parent_context)
    )


__all__ = (
    "TOOL_ACTION_IDEMPOTENCY_PREFIX",
    "TOOL_ACTION_RECORD_KIND",
    "TOOL_ADMISSION_PARENT_NOT_LIVE",
    "TOOL_ADMISSION_STOPPED",
    "TOOL_ADMISSION_UNRESOLVED",
    "invocation_tool_child_of",
    "tool_action_claim_payload",
)


def _same_parent_authority(context: object, parent_context: object) -> bool:
    return (context.actor_id, context.authorization_scope, context.target_scope, context.run_scope) == (
        parent_context.actor_id,
        parent_context.authorization_scope,
        parent_context.target_scope,
        parent_context.run_scope,
    )
