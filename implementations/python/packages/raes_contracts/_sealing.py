"""Sealing switch for derived contract fields (issue #1929).

Contract models verify that each derived field (a self-digest or a derived
identifier) equals the value computed from the rest of the document. The seal
engine in :mod:`raes_contracts.contract_seals` needs a validated model to compute
that value, so it validates with this switch set. Only the engine sets it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_SEALING: ContextVar[bool] = ContextVar("raes_contract_sealing", default=False)


def sealing_active() -> bool:
    """Return whether the seal engine is computing derived fields."""
    return _SEALING.get()


@contextmanager
def sealing() -> Iterator[None]:
    """Validate inside this block without comparing derived fields."""
    token = _SEALING.set(True)
    try:
        yield
    finally:
        _SEALING.reset(token)
