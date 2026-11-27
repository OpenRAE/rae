"""OCR-compatible duration parsing for SDL orchestration models."""

import math
import re
from decimal import ROUND_CEILING, Decimal

from raes_contracts.variable_references import is_variable_ref

# OCR uses duration-str's fixed calendar conversions: 30d/month, 365d/year.
_DURATION_UNITS = {
    "y": Decimal("31536000"),
    "year": Decimal("31536000"),
    "years": Decimal("31536000"),
    "mon": Decimal("2592000"),
    "month": Decimal("2592000"),
    "months": Decimal("2592000"),
    "w": Decimal("604800"),
    "week": Decimal("604800"),
    "weeks": Decimal("604800"),
    "d": Decimal("86400"),
    "day": Decimal("86400"),
    "days": Decimal("86400"),
    "h": Decimal("3600"),
    "hr": Decimal("3600"),
    "hour": Decimal("3600"),
    "hours": Decimal("3600"),
    "m": Decimal("60"),
    "min": Decimal("60"),
    "mins": Decimal("60"),
    "minute": Decimal("60"),
    "minutes": Decimal("60"),
    "s": Decimal("1"),
    "sec": Decimal("1"),
    "secs": Decimal("1"),
    "second": Decimal("1"),
    "seconds": Decimal("1"),
    "ms": Decimal("0.001"),
    "msec": Decimal("0.001"),
    "millisecond": Decimal("0.001"),
    "milliseconds": Decimal("0.001"),
    "us": Decimal("0.000001"),
    "usec": Decimal("0.000001"),
    "usecond": Decimal("0.000001"),
    "microsecond": Decimal("0.000001"),
    "microseconds": Decimal("0.000001"),
    "ns": Decimal("0.000000001"),
    "nsec": Decimal("0.000000001"),
    "nanosecond": Decimal("0.000000001"),
    "nanoseconds": Decimal("0.000000001"),
}

_DURATION_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _numeric_duration(value: int | float) -> int:
    if value < 0:
        raise ValueError(f"Invalid duration: {value!r}")
    if value == 0:
        return 0
    return math.ceil(value)


def _accumulate_units(normalized: str, *, value: str | int | float) -> int:
    total = Decimal("0")
    position = 0
    parsed_any = False
    units = sorted(_DURATION_UNITS, key=len, reverse=True)

    while position < len(normalized):
        if normalized[position] == "+":
            position += 1
            continue

        match = _DURATION_NUMBER.match(normalized, position)
        if match is None:
            raise ValueError(f"Invalid duration: {value!r}")

        parsed_any = True
        amount = Decimal(match.group(0))
        position = match.end()

        unit = None
        for candidate in units:
            if normalized.startswith(candidate, position):
                unit = candidate
                position += len(candidate)
                break

        # duration-str treats bare numbers as seconds
        multiplier = _DURATION_UNITS[unit] if unit else Decimal("1")
        total += amount * multiplier

    if not parsed_any:
        raise ValueError(f"Invalid duration: {value!r}")

    return int(total.to_integral_value(rounding=ROUND_CEILING))


def _string_duration(value: str | int | float) -> int:
    value_str = str(value).strip()
    if not value_str:
        raise ValueError(f"Invalid duration: {value!r}")
    if value_str == "0":
        return 0

    normalized = value_str.replace("_", "").replace(" ", "").replace("µ", "u").lower()

    if re.fullmatch(r"\d+(?:\.\d+)?", normalized):
        return int(Decimal(normalized).to_integral_value(rounding=ROUND_CEILING))

    return _accumulate_units(normalized, value=value)


def parse_duration(value: str | int | float) -> int | str:
    """Parse an OCR-compatible human-readable duration into seconds."""
    if is_variable_ref(value):
        return value
    if isinstance(value, bool):
        raise ValueError(f"Invalid duration: {value!r}")
    if isinstance(value, (int, float)):
        return _numeric_duration(value)
    return _string_duration(value)
