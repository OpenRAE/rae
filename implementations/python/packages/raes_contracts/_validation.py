"""Small validation helpers for shared contract dataclasses."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum


def enum_value[EnumT: Enum](enum_type: type[EnumT], raw: object) -> EnumT:
    if isinstance(raw, enum_type):
        return raw
    return enum_type(str(raw))


def optional_enum_value[EnumT: Enum](enum_type: type[EnumT], raw: object) -> EnumT | None:
    if raw is None:
        return None
    return enum_value(enum_type, raw)


def require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")


def require_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")


def require_optional_string(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")


def require_optional_non_empty_string(value: object, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        raise TypeError(f"{field_name} must be a non-empty string or None")


def require_optional_bool(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool or None")


def require_optional_numeric(value: object, field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise TypeError(f"{field_name} must be numeric or None")


def require_optional_int(value: object, field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise TypeError(f"{field_name} must be an int or None")


def require_non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def require_dict(value: object, field_name: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")


def require_list(value: object, field_name: str) -> None:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")


def require_strings(values: Iterable[object], field_name: str) -> None:
    if any(not isinstance(value, str) for value in values):
        raise TypeError(f"{field_name} must contain only strings")
