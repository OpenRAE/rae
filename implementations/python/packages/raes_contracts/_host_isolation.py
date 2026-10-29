"""Isolation of host callbacks in contract validation (ADR-116, rule H2).

Contract validation calls resolvers, callbacks and trusted indexes that the host
supplies. The host refuses with ``ValueError`` or a ``RaesError``. An
``OperationalError`` is a failed host dependency, and any other exception is a
failure of host code. This module logs those failures, then the validation
refuses with one value-free ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .errors import OperationalError, RaesError
from .operational_logging import ForeignCodeFailure, foreign_failure_record, get_logger

_LOGGER = get_logger(__name__)


@contextmanager
def isolated_host_call(refusal: str, *, keep_cause: bool = True) -> Iterator[None]:
    """Change a refusal or a failure of host code into ``ValueError(refusal)``.

    With ``keep_cause=False`` the cause of a refusal is suppressed, so its values
    stay out of the output. A failure of host code is logged one time with only
    the RAES frames. The refusal then names that record as its cause, so a later
    record of the refusal carries no host type, frame or value.
    """

    record: ForeignCodeFailure | None = None
    try:
        yield
    except OperationalError as exc:
        # Isolation: a failed host dependency is reported here; the refusal replaces it.
        record = foreign_failure_record(exc)
        _LOGGER.warning("host callback dependency failed", exc_info=record)
    except (ValueError, RaesError) as exc:
        raise ValueError(refusal) from exc if keep_cause else None
    except Exception as exc:
        # Isolation: host code failed outside its refusal contract.
        record = foreign_failure_record(exc)
        _LOGGER.exception("host callback failed outside its refusal contract", exc_info=record)
    if record is not None:
        # The context manager runs while the caller handles the host exception, so Python sets
        # that exception as the context. The explicit cause hides it from every chain renderer.
        raise ValueError(refusal) from record


__all__ = ["isolated_host_call"]
