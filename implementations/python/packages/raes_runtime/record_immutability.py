"""Invariant errors for values that a durable operation claim fixes (ADR-116).

A replacement record must not change a value that its durable claim fixed. Only a
defect or a writer outside the runtime can change such a value, so the error stays a
``ValueError`` (rule E2). The ``immutable_value`` attribute lets a handler tell this
error apart from other invariant errors without reading its message (rule E7).
"""

from __future__ import annotations


def immutable_value_error(message: str) -> ValueError:
    """Return the invariant error for a change to a value that a durable claim fixes."""

    error = ValueError(message)
    error.immutable_value = True
    return error


def is_immutable_value_error(error: BaseException) -> bool:
    """Return whether ``error`` reports a change to a value that a durable claim fixes."""

    return getattr(error, "immutable_value", False) is True


__all__ = ("immutable_value_error", "is_immutable_value_error")
