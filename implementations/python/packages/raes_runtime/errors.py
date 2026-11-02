"""Runtime exception families (ADR-116).

The categories in :mod:`raes_contracts.errors` cover most runtime failures.
This module holds only the runtime families that a caller must tell apart
from the rest of their category.
"""

from raes_contracts.errors import ConflictError, OperationalError


class RuntimeBudgetExhaustedError(OperationalError):
    """A runtime time budget or allowance ran out before the work completed.

    The work may have taken effect. Handlers that treat a system timeout as an
    uncertain effect catch this class together with ``TimeoutError``.
    """


class IdempotencyClaimConflictError(ConflictError):
    """An idempotency claim does not match the original request that holds the key."""


__all__ = ("IdempotencyClaimConflictError", "RuntimeBudgetExhaustedError")
