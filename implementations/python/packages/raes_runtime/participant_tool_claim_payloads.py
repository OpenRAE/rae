"""Immutable claim coordinates shared by invocation owners."""

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
