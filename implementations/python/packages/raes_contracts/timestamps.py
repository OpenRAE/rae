"""UTC wall-clock reads, UTC text and the named timestamp parsers (ADR-118).

:func:`utc_now` reads the system wall clock. Each owner that reads the time
takes a :data:`WallClock` argument that defaults to it, so a test supplies a
fixed clock through a public constructor. This wall clock is not a semantic
clock (ADR-090), a monotonic watchdog or Temporal workflow time.

Each parser keeps its own grammar, offset rule and messages:

- :func:`parse_rfc3339_datetime`: the governed RFC 3339 grammar, including
  lowercase ``t`` and ``z`` and valid leap seconds; the offset is kept.
- :func:`parse_offset_timestamp_utc`: ISO 8601 text with an explicit offset; the
  result is in UTC and every refusal has one value-free message.
- :func:`parse_offset_datetime`: ISO 8601 text with an explicit offset, where
  ``Z`` and ``z`` mean UTC; the offset is kept and refusals name the field.
- :func:`parse_timestamp_assuming_utc`: ISO 8601 text where a value without an
  offset is UTC; parser errors pass through unchanged.

This module uses only the standard library.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

__all__ = (
    "EXPLICIT_OFFSET_TIMESTAMP_ERROR",
    "WallClock",
    "isoformat_z",
    "parse_offset_datetime",
    "parse_offset_timestamp_utc",
    "parse_rfc3339_datetime",
    "parse_timestamp_assuming_utc",
    "utc_now",
)

#: A callable that returns the current instant as an aware UTC ``datetime``.
type WallClock = Callable[[], datetime]

#: The ISO 8601 text of a zero UTC offset.
_UTC_OFFSET = "+00:00"

#: The one refusal message of :func:`parse_offset_timestamp_utc`.
EXPLICIT_OFFSET_TIMESTAMP_ERROR = "timestamp must be an ISO-8601 value with an explicit UTC offset"

_RFC3339_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt](?:[01]\d|2[0-3]):[0-5]\d:(?P<second>[0-5]\d|60)"
    r"(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


_VALID_UTC_LEAP_SECOND_DATES = frozenset(
    {
        (1972, 6, 30),
        (1972, 12, 31),
        (1973, 12, 31),
        (1974, 12, 31),
        (1975, 12, 31),
        (1976, 12, 31),
        (1977, 12, 31),
        (1978, 12, 31),
        (1979, 12, 31),
        (1981, 6, 30),
        (1982, 6, 30),
        (1983, 6, 30),
        (1985, 6, 30),
        (1987, 12, 31),
        (1989, 12, 31),
        (1990, 12, 31),
        (1992, 6, 30),
        (1993, 6, 30),
        (1994, 6, 30),
        (1995, 12, 31),
        (1997, 6, 30),
        (1998, 12, 31),
        (2005, 12, 31),
        (2008, 12, 31),
        (2012, 6, 30),
        (2015, 6, 30),
        (2016, 12, 31),
    }
)


def utc_now() -> datetime:
    """Read the system wall clock as an aware UTC ``datetime``."""

    return datetime.now(UTC)


def isoformat_z(instant: datetime) -> str:
    """Return ``instant.isoformat()`` with ``Z`` in place of the ``+00:00`` offset."""

    return instant.isoformat().replace(_UTC_OFFSET, "Z")


def parse_rfc3339_datetime(field_name: str, value: str) -> datetime:
    """Parse governed RFC 3339 text; a valid leap second rolls forward to the next second."""

    match = _RFC3339_DATETIME_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"{field_name} must be a valid RFC 3339 date-time")
    normalized_value = f"{value[:-1]}{_UTC_OFFSET}" if value.endswith(("Z", "z")) else value
    if match.group("second") == "60":
        normalized_value = f"{normalized_value[:17]}59{normalized_value[19:]}"
    try:
        parsed = datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid RFC 3339 date-time") from exc
    if match.group("second") == "60":
        utc_leap_second = parsed.astimezone(UTC)
        if (
            (utc_leap_second.year, utc_leap_second.month, utc_leap_second.day) not in _VALID_UTC_LEAP_SECOND_DATES
            or utc_leap_second.hour != 23
            or utc_leap_second.minute != 59
            or utc_leap_second.second != 59
        ):
            raise ValueError(f"{field_name} must use a valid RFC 3339 leap-second instant")
        parsed += timedelta(seconds=1)
    return parsed


def parse_offset_timestamp_utc(raw: str) -> datetime:
    """Parse one explicit-offset ISO-8601 timestamp and normalize it to UTC."""

    if not isinstance(raw, str) or not raw:
        raise ValueError(EXPLICIT_OFFSET_TIMESTAMP_ERROR)
    normalized = raw[:-1] + _UTC_OFFSET if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
        offset = parsed.utcoffset()
    except OverflowError, TypeError, ValueError:
        raise ValueError(EXPLICIT_OFFSET_TIMESTAMP_ERROR) from None
    if parsed.tzinfo is None or offset is None:
        raise ValueError(EXPLICIT_OFFSET_TIMESTAMP_ERROR)
    try:
        return parsed.astimezone(UTC)
    except OverflowError:
        # A valid local time near the datetime range limit can have no UTC form.
        raise ValueError(EXPLICIT_OFFSET_TIMESTAMP_ERROR) from None


def parse_offset_datetime(value: object, field_name: str = "timestamp") -> datetime:
    """Parse an ISO 8601 date-time that carries an explicit UTC offset.

    Naive and date-only values have no defined instant and would make later
    order comparisons raise ``TypeError``, so they are rejected here. The
    message names the field and the rule, never the rejected value.
    """

    message = f"{field_name} must be an ISO 8601 date-time with an explicit UTC offset"
    if not isinstance(value, str):
        raise ValueError(message)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", _UTC_OFFSET).replace("z", _UTC_OFFSET))
    except ValueError:
        raise ValueError(message) from None
    if parsed.utcoffset() is None:
        raise ValueError(message)
    return parsed


def parse_timestamp_assuming_utc(raw: str) -> datetime:
    """Parse ISO 8601 text; a value without an offset is UTC."""

    if raw.endswith("Z"):
        raw = raw[:-1] + _UTC_OFFSET
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
