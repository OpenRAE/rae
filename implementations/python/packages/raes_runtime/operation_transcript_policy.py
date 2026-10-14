"""Finite transcript partitions retain authority and reserve operator recovery."""

AUTOMATIC_CONTROL_LIMIT = 128
MANUAL_CONTROL_LIMITS = {"observe": 64, "cancel": 32, "reconcile": 32}
ORDINARY_RESPONSE_LIMIT = 768


def automatic_poll_interval_ms(execution_ms):
    return max(250, (execution_ms + AUTOMATIC_CONTROL_LIMIT - 1) // AUTOMATIC_CONTROL_LIMIT)


def require_transcript_capacity(invocation):
    automatic = set(invocation.automatic_controls)
    control_ids = {control.control_id for control in invocation.controls}
    if len(automatic) != len(invocation.automatic_controls) or not automatic <= control_ids:
        raise ValueError("automatic observation requires unique retained intent")
    if len(automatic) > AUTOMATIC_CONTROL_LIMIT:
        raise ValueError("automatic observation capacity exhausted")
    if any(control.control_id in automatic and control.action == "cancel" for control in invocation.controls):
        raise ValueError("cancellation cannot be classified as automatic observation")
    for action, limit in MANUAL_CONTROL_LIMITS.items():
        count = sum(control.action == action and control.control_id not in automatic for control in invocation.controls)
        if count > limit:
            raise ValueError("operator control capacity exhausted")
    recovery = {
        control.control_id
        for control in invocation.controls
        if control.action in {"cancel", "reconcile"} and control.control_id not in automatic
    }
    ordinary, seen = 0, set()
    for response in invocation.responses:
        message = response.message
        control_id = getattr(message, "control_id", None)
        if control_id is not None:
            key = control_id, message.kind
            if key in seen:
                raise ValueError("control response identity was already retained")
            seen.add(key)
        if control_id not in recovery and message.kind != "outcome":
            ordinary += 1
    if ordinary > ORDINARY_RESPONSE_LIMIT:
        raise ValueError("ordinary response capacity exhausted")


def append_control(invocation, control, *, automatic=False):
    update = {"controls": (*invocation.controls, control)}
    if automatic:
        update["automatic_controls"] = (*invocation.automatic_controls, control.control_id)
    replacement = invocation.model_copy(update=update)
    require_transcript_capacity(replacement)
    return replacement
