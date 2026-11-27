"""Typed failures of the packaged behavioral-relation profile and catalog authorities (ADR-116).

A request can name a profile, a profile revision or a catalog revision that RAES
does not package. The caller can correct that request, so it is an input refusal.
A packaged profile or catalog that does not load is a damaged installation. The
loaders check strict JSON, the contract and the registry identity of the
artifact, but they verify no digest, so damage is an operational failure and not
an evidence-integrity failure.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .errors import InvalidInputError, OperationalError


class BehavioralAuthorityUnsupportedError(InvalidInputError):
    """A requested behavioral-relation profile, profile revision or catalog revision is not packaged."""


class BehavioralAuthorityArtifactError(OperationalError):
    """A packaged behavioral-relation profile or catalog artifact is damaged or does not match its registry entry."""


@contextmanager
def unsupported_authority_as_value_error(message: str) -> Iterator[None]:
    """Report an unsupported authority as ``ValueError`` in a function that checks fields (E3).

    A damaged artifact is not a field finding, so it propagates unchanged.
    """

    try:
        yield
    except BehavioralAuthorityUnsupportedError as exc:
        raise ValueError(message) from exc


__all__ = (
    "BehavioralAuthorityArtifactError",
    "BehavioralAuthorityUnsupportedError",
    "unsupported_authority_as_value_error",
)
