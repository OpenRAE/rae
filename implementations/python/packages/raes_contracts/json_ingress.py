"""Bounded, ambiguity-rejecting JSON ingress shared by portable contracts."""

from __future__ import annotations

import json
from typing import Literal

JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


class StrictJsonIngressError(ValueError):
    """A JSON document failed a safe pre-contract ingress check."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _duplicate_rejecting_object(
    pairs: list[tuple[str, JSONValue]],
) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonIngressError("duplicate-member", "duplicate JSON member")
        result[key] = value
    return result


def _reject_non_finite_number(_: str) -> float:
    raise StrictJsonIngressError("non-finite-number", "JSON contains a non-finite number")


def _reject_excessive_nesting(encoded: bytes, max_depth: int) -> None:
    """Reject excessive container nesting before the recursive JSON decoder runs."""

    if max_depth < 1:
        raise ValueError("max_depth must be positive")
    depth = 0
    in_string = False
    escaped = False
    for byte in encoded:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # double quote
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):  # [ or {
            depth += 1
            if depth > max_depth:
                raise StrictJsonIngressError(
                    "input-too-deep",
                    "JSON input exceeds the configured depth limit",
                )
        elif byte in (0x5D, 0x7D):  # ] or }
            depth -= 1


def parse_bounded_json(
    source: str | bytes | bytearray,
    *,
    max_bytes: int,
    root: Literal["object", "array"],
    max_depth: int | None = None,
) -> JSONValue:
    """Parse bounded JSON with an explicit, ambiguity-free root shape."""

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    encoded = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    if len(encoded) > max_bytes:
        raise StrictJsonIngressError("input-too-large", "JSON input exceeds the configured byte limit")
    if not encoded.strip():
        raise StrictJsonIngressError("empty-input", "JSON input is empty")
    if max_depth is not None:
        _reject_excessive_nesting(encoded, max_depth)
    try:
        payload = json.loads(
            encoded,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_non_finite_number,
        )
    except StrictJsonIngressError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrictJsonIngressError("invalid-json", "JSON input is invalid") from exc
    expected_type = dict if root == "object" else list
    if not isinstance(payload, expected_type):
        raise StrictJsonIngressError("invalid-root", f"JSON input must be an {root}")
    return payload


def parse_bounded_json_object(
    source: str | bytes | bytearray,
    *,
    max_bytes: int,
    max_depth: int | None = None,
) -> dict[str, JSONValue]:
    """Parse one bounded JSON object without duplicate members or non-finite numbers."""

    payload = parse_bounded_json(source, max_bytes=max_bytes, root="object", max_depth=max_depth)
    # The shared parser establishes the selected root type.
    if not isinstance(payload, dict):
        raise AssertionError("object-root parser returned a non-object")
    return payload


__all__ = [
    "JSONValue",
    "StrictJsonIngressError",
    "parse_bounded_json",
    "parse_bounded_json_object",
]
