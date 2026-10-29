"""Shared operational logging utilities (ADR-116).

Library code gets its logger with :func:`get_logger`. The logger carries one
filter that makes each record value-free before any handler gets it: the
filter replaces exception information with the exception types and the
file, line and function of each frame, removes stack information, merges the
arguments into the message and escapes control characters. Thus a host
formatter cannot show exception messages, notes, source lines or local
values.

RAES applications configure logging at their entry point with
:func:`configure_application_logging` or :func:`run_application`. Library
code never configures logging. ``docs/develop/exceptions-and-logging.md``
states the rules.

This module uses only the standard library and keeps Python 3.12 syntax,
because the development container bootstrap imports it with Python 3.12.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import traceback
from collections.abc import Callable, Iterator
from types import FrameType, TracebackType
from typing import TextIO

from .errors import OperationalError

__all__ = (
    "ForeignCodeFailure",
    "ValueFreeFormatter",
    "configure_application_logging",
    "describe_exception",
    "foreign_failure_record",
    "get_logger",
    "run_application",
    "set_application_log_level",
)

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_MAX_CHAIN = 8
_MAX_FRAMES = 40
_MAX_GROUP_DEPTH = 4
_MAX_GROUP_MEMBERS = 16
_MAX_MESSAGE_CHARACTERS = 8192
_APPLICATION_HANDLER_ATTRIBUTE = "_raes_application_handler"
_VALUE_FREE_ATTRIBUTE = "_raes_value_free"
_CAUSE = "The above exception was the direct cause of the following exception:"
_CONTEXT = "During handling of the above exception, another exception occurred:"
_SUPPRESSED_CONTEXT = (
    "During handling of the above exception, another exception occurred (the context was suppressed with 'from None'):"
)
_UNSAFE_CHARACTERS = re.compile("[\x00-\x1f\x7f-\x9f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
_NAMED_ESCAPES = {"\t": "\\t", "\n": "\\n", "\r": "\\r"}


def _escape_character(match: re.Match[str]) -> str:
    character = match.group()
    named = _NAMED_ESCAPES.get(character)
    if named is not None:
        return named
    code = ord(character)
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


def _escape(text: str) -> str:
    """Escape characters that can forge or hide log lines."""

    return _UNSAFE_CHARACTERS.sub(_escape_character, text)


def _type_name(exception_type: type[BaseException]) -> str:
    module = exception_type.__module__
    name = exception_type.__qualname__
    return _escape(name if module == "builtins" else f"{module}.{name}")


def _source_location(filename: str) -> str:
    """Show a file relative to its import root, so host paths stay out of records."""

    best = ""
    for entry in sys.path:
        root = os.path.abspath(entry) if entry else os.getcwd()
        prefix = root.rstrip(os.sep) + os.sep
        if filename.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    return _escape(filename[len(best) :] if best else os.path.basename(filename))


def _frames(trace: TracebackType | None) -> tuple[list[tuple[str, int, str]], int]:
    frames = [
        (_source_location(frame.f_code.co_filename), line, _escape(frame.f_code.co_qualname))
        for frame, line in traceback.walk_tb(trace)
    ]
    omitted = max(0, len(frames) - _MAX_FRAMES)
    return frames[omitted:], omitted


def _chain(exception: BaseException) -> list[tuple[BaseException, str | None]]:
    """Return the chain oldest first; each item carries how the next item links to it."""

    items: list[tuple[BaseException, str | None]] = []
    seen: set[int] = set()
    current: BaseException | None = exception
    link: str | None = None
    while current is not None and id(current) not in seen and len(items) < _MAX_CHAIN:
        seen.add(id(current))
        items.append((current, link))
        if current.__cause__ is not None:
            current, link = current.__cause__, _CAUSE
        elif current.__context__ is not None:
            link = _SUPPRESSED_CONTEXT if current.__suppress_context__ else _CONTEXT
            current = current.__context__
        else:
            current = None
    items.reverse()
    return items


def _render_one(exception: BaseException, depth: int) -> list[str]:
    frames, omitted = _frames(exception.__traceback__)
    lines = []
    if frames:
        lines.append("Traceback (most recent call last; values omitted):")
        if omitted:
            lines.append(f"  [{omitted} earlier frames omitted]")
        lines.extend(f'  File "{filename}", line {line}, in {function}' for filename, line, function in frames)
    lines.append(_type_name(type(exception)))
    if isinstance(exception, BaseExceptionGroup) and depth < _MAX_GROUP_DEPTH:
        members = exception.exceptions
        for index, member in enumerate(members[:_MAX_GROUP_MEMBERS], start=1):
            lines.append(f"  Group member {index} of {len(members)}:")
            lines.extend(f"    {line}" for line in _render_chain(member, depth + 1))
        if len(members) > _MAX_GROUP_MEMBERS:
            lines.append(f"  [{len(members) - _MAX_GROUP_MEMBERS} more group members omitted]")
    return lines


def _render_chain(exception: BaseException, depth: int = 0) -> list[str]:
    lines: list[str] = []
    for item, link in _chain(exception):
        lines.extend(_render_one(item, depth))
        if link is not None:
            lines.extend(("", link, ""))
    return lines


def _short(exception: BaseException) -> str:
    name = _type_name(type(exception))
    if isinstance(exception, BaseExceptionGroup):
        members = ", ".join(_type_name(type(member)) for member in exception.exceptions[:_MAX_GROUP_MEMBERS])
        name = f"{name}[{members}]"
    frames, _ = _frames(exception.__traceback__)
    if not frames:
        return name
    filename, line, function = frames[-1]
    return f"{name} ({filename}:{line} in {function})"


class ForeignCodeFailure(OperationalError):
    """Log record of a failure in untrusted foreign code, such as a backend or a provider.

    RAES never raises this class. An isolation handler logs it in place of the
    foreign exception. The type, message, chain and frames of foreign code are
    foreign content, so the record keeps only the RAES frames of the failure.
    """


def _tracebacks(trace: TracebackType | None) -> Iterator[TracebackType]:
    while trace is not None:
        yield trace
        trace = trace.tb_next


def _first_party(frame: FrameType) -> bool:
    name = str(frame.f_globals.get("__name__", ""))
    return name == "raes" or name.startswith(("raes.", "raes_"))


def foreign_failure_record(error: BaseException) -> ForeignCodeFailure:
    """Return the ``exc_info`` value to log for a failure of untrusted foreign code."""

    kept = [item for item in _tracebacks(error.__traceback__) if _first_party(item.tb_frame)]
    trace: TracebackType | None = None
    for item in reversed(kept):
        trace = TracebackType(trace, item.tb_frame, item.tb_lasti, item.tb_lineno)
    return ForeignCodeFailure("foreign code failed").with_traceback(trace)


def describe_exception(exception: BaseException) -> str:
    """Describe an exception chain on one line by type and code location only."""

    return " <- ".join(_short(item) for item, _ in reversed(_chain(exception)))


def _record_message(record: logging.LogRecord) -> str:
    try:
        return record.getMessage()
    # A log call must never raise into its caller (OWASP Logging Cheat Sheet), and an
    # argument's __str__ can raise any exception. The failure is not swallowed: the
    # emitted record names it in place of the message.
    except Exception as exc:  # noqa: BLE001
        template = record.msg if isinstance(record.msg, str) else "<log message object>"
        return f"{template} [message arguments did not match: {_type_name(type(exc))}]"


def _make_value_free(record: logging.LogRecord) -> None:
    if getattr(record, _VALUE_FREE_ATTRIBUTE, False):
        return
    message = _escape(_record_message(record))
    if len(message) > _MAX_MESSAGE_CHARACTERS:
        message = f"{message[:_MAX_MESSAGE_CHARACTERS]} [message truncated]"
    record.msg = message
    record.args = ()
    exception = record.exc_info[1] if record.exc_info else None
    record.exc_text = "\n".join(_render_chain(exception)) if exception is not None else None
    record.exc_info = None
    record.stack_info = None
    setattr(record, _VALUE_FREE_ATTRIBUTE, True)


class _ValueFreeRecordFilter(logging.Filter):
    """Make each record of a first-party logger value-free before a handler gets it."""

    def filter(self, record: logging.LogRecord) -> bool:
        _make_value_free(record)
        return True


_VALUE_FREE_FILTER = _ValueFreeRecordFilter()


def get_logger(name: str) -> logging.Logger:
    """Return the standard logger for ``name`` with the value-free record filter."""

    logger = logging.getLogger(name)
    logger.addFilter(_VALUE_FREE_FILTER)
    return logger


class ValueFreeFormatter(logging.Formatter):
    """Format any record, also from other libraries, without values from exceptions."""

    def __init__(self, fmt: str | None = None, datefmt: str | None = None) -> None:
        super().__init__(fmt=_DEFAULT_FORMAT if fmt is None else fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        safe_record = logging.makeLogRecord(record.__dict__)
        _make_value_free(safe_record)
        return super().format(safe_record)

    def formatException(self, ei) -> str:
        exception = ei[1]
        return "\n".join(_render_chain(exception)) if exception is not None else ""

    def formatStack(self, stack_info: str) -> str:
        return ""


def _level(level: int | str) -> int:
    if isinstance(level, str) and level.upper() in _LEVELS:
        return _LEVELS[level.upper()]
    if isinstance(level, int) and not isinstance(level, bool) and level in _LEVELS.values():
        return level
    raise ValueError(f"unsupported log level {level!r}; use one of {', '.join(_LEVELS)}")


def configure_application_logging(
    *, level: int | str = logging.WARNING, stream: TextIO | None = None
) -> logging.Handler:
    """Configure logging for a RAES application entry point.

    Install one standard error handler with :class:`ValueFreeFormatter` on the
    root logger and set the root level. A second call keeps that handler and
    changes only the level, and the stream when one is given. Handlers that
    the host installed stay in place.
    """

    root_level = _level(level)
    root = logging.getLogger()
    handler = next((item for item in root.handlers if getattr(item, _APPLICATION_HANDLER_ATTRIBUTE, False)), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stderr if stream is None else stream)
        setattr(handler, _APPLICATION_HANDLER_ATTRIBUTE, True)
        handler.setFormatter(ValueFreeFormatter())
        root.addHandler(handler)
    elif stream is not None and isinstance(handler, logging.StreamHandler):
        handler.setStream(stream)
    root.setLevel(root_level)
    return handler


def set_application_log_level(level: int | str) -> None:
    """Change the root level of an application without installing a handler.

    A command option uses this after :func:`run_application` configured the
    handler, so a command that runs inside a host or a test adds no handler.
    """

    logging.getLogger().setLevel(_level(level))


_LOGGER = get_logger(__name__)


def run_application(
    main: Callable[[], int | None],
    *,
    level: int | str = logging.WARNING,
    unexpected_status: int = 1,
) -> int:
    """Run an application entry point and return its exit status.

    The function configures logging, runs ``main`` and returns its status. An
    unexpected exception produces one value-free log record and
    ``unexpected_status``. ``SystemExit`` and ``KeyboardInterrupt`` propagate
    unchanged.
    """

    configure_application_logging(level=level)
    try:
        status = main()
    except Exception:
        _LOGGER.exception("application stopped after an unexpected error")
        return unexpected_status
    return 0 if status is None else status
