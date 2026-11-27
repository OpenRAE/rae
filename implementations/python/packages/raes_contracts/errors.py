"""Shared RAES exception hierarchy (ADR-116).

Every exception class that RAES defines derives from :class:`RaesError`
through one base class. The categories below answer one question for the
code that catches them: what went wrong. A subsystem family, such as
``SDLError``, derives from the category that applies to all of its members,
or directly from :class:`RaesError` when its members have different
categories.

Built-in exceptions stay for programming errors, Pydantic validators and
protocols. ``docs/develop/exceptions-and-logging.md`` states the rules.

This module uses only the standard library and keeps Python 3.12 syntax,
because the development container bootstrap imports it with Python 3.12.
"""


class RaesError(Exception):
    """Base class of every exception that RAES raises on purpose."""


class InvalidInputError(RaesError):
    """Input from outside the program does not satisfy a governed contract."""


class ConflictError(RaesError):
    """A request conflicts with the current governed state."""


class NotFoundError(RaesError):
    """A named governed object does not exist for the caller."""


class AuthorizationError(RaesError):
    """The caller does not have authority for the operation."""


class OperationalError(RaesError):
    """A dependency, a tool, a host resource or a time budget failed."""


class EvidenceIntegrityError(RaesError):
    """Evidence does not replay against, or does not match, its governed input."""


__all__ = (
    "AuthorizationError",
    "ConflictError",
    "EvidenceIntegrityError",
    "InvalidInputError",
    "NotFoundError",
    "OperationalError",
    "RaesError",
)
