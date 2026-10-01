"""Private helpers for validating instantiated scenarios."""

from collections.abc import Mapping

from ._base import VARIABLE_TOKEN_RE


def collect_variable_tokens(value: object) -> list[str]:
    """Return the names of every ``${name}`` token found in string values.

    Mirrors ``instantiate._substitute_value``: every string is a substitution
    site and mapping keys are not. An instantiated scenario is fully concrete,
    so no token may survive in any string value.
    """
    found: list[str] = []
    if isinstance(value, Mapping):
        for nested in value.values():
            found.extend(collect_variable_tokens(nested))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(collect_variable_tokens(item))
    elif isinstance(value, str):
        found.extend(VARIABLE_TOKEN_RE.findall(value))
    return found


def resolve_json_pointer(payload: object, pointer: str) -> object:
    """Resolve an RFC 6901-style JSON pointer against a scenario payload."""
    current = payload
    for raw_segment in pointer.split("/")[1:]:
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            if not segment.isascii() or not segment.isdigit() or (segment != "0" and segment.startswith("0")):
                raise ValueError("JSON Pointer array index must be a canonical non-negative integer")
            current = current[int(segment)]
        else:
            raise TypeError("JSON Pointer traverses a scalar value")
    return current
