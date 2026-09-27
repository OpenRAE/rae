"""Backend guarantees required by authored trial execution choices (#1361).

RAE, not the author or the backend, derives these from choices the author has
already made. Absent choices require nothing: a single attempt that is not
cancelled on timeout places no supervision obligation on any backend.
"""

from __future__ import annotations

from .backend_operation import OperationGuarantee
from .trial_cleanup import ExecutionRetryPolicyModel


def required_operation_guarantees(
    on_timeout: str,
    retry_policy: ExecutionRetryPolicyModel,
) -> tuple[OperationGuarantee, ...]:
    """Return the canonical guarantee set a backend must provide for these choices.

    - Cancelling on timeout needs backend cancellation.
    - Another attempt must not overlap the previous one, so it needs evidence that
      the previous attempt's effects ceased.
    - A retry that forbids repeating after effects must also establish that no
      effect occurred.

    Reset and compensation obligations stay with the cleanup-capability gate.
    """

    required: set[OperationGuarantee] = set()
    if on_timeout == "cancel":
        required.add("cancellation")
    if retry_policy.max_attempts > 1:
        required.add("cessation-evidence")
        if retry_policy.after_effect_policy == "disallow":
            required.add("effect-observation")
    return tuple(sorted(required))


__all__ = ["required_operation_guarantees"]
