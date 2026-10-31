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

TOOL_ACTION_RECORD_KIND = "participant-invocation-tool-action/v1"
TOOL_ADMISSION_PARENT_NOT_LIVE = "parent-not-live"
TOOL_ADMISSION_STOPPED = "effect-admission-stopped"
TOOL_ADMISSION_UNRESOLVED = "unresolved-indeterminate"
TOOL_ACTION_IDEMPOTENCY_PREFIX = "invocation-tool-action:"
_CLAIM_PAYLOAD_KEYS = frozenset(
    {
        "kind",
        "tool_call_id",
        "invocation_action_instance_id",
        "participant_address",
        "episode_id",
        "participant_implementation_ref",
        "tool_affordance_address",
        "action_contract_address",
        "observation_boundary_address",
        "target_addresses",
        "execution_scope_ref",
        "execution_generation",
    }
)


def tool_action_claim_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    """Return the claim-time binding fields of a tool-action payload, or ``None``."""

    if not isinstance(payload, dict) or payload.get("kind") != TOOL_ACTION_RECORD_KIND:
        return None
    claim = {key: payload[key] for key in _CLAIM_PAYLOAD_KEYS if key in payload}
    return claim if set(claim) == _CLAIM_PAYLOAD_KEYS else None


def invocation_tool_child_of(parent: object, child: object) -> bool:
    """Return whether ``child`` is a validated tool action hosted by the running ``parent``."""

    context = child.status.context
    parent_context = parent.status.context
    claim = tool_action_claim_payload(child.result_payload)
    operation_id = child.receipt.operation_id
    return bool(
        claim is not None
        and child.invocation is None
        and operation_id.startswith(TOOL_ACTION_ID_PREFIX)
        and child.idempotency_key == TOOL_ACTION_IDEMPOTENCY_PREFIX + operation_id
        and context.operation_kind is OperationKind.PARTICIPANT_ACTION
        and context.request_commitment == canonical_json_digest(claim)
        and context.parent_operation_id == parent.receipt.operation_id
        and parent.status.state is OperationState.RUNNING
        and parent_context.operation_kind is OperationKind.COMPOSITION_PHASE
        and (context.actor_id, context.authorization_scope, context.target_scope, context.run_scope)
        == (
            parent_context.actor_id,
            parent_context.authorization_scope,
            parent_context.target_scope,
            parent_context.run_scope,
        )
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
