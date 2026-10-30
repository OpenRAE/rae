"""One array-index rule for RFC 6901 JSON Pointer walkers.

An array-index token is ``0`` or ASCII digits without a leading zero that name
an existing list position (RFC 6901 section 4). The incumbent scenario resolver
``raes._scenario_instantiation.resolve_json_pointer`` uses the same rule, so
each list position has one canonical spelling and ``/items/01`` never aliases
``/items/1``. ``str.isdigit()`` also accepts Unicode digits that ``int()``
refuses, and ``int()`` refuses a digit string beyond the interpreter digit
limit. Thus a walker that calls these helpers never raises for an authored token.

This module uses only the standard library.
"""

from __future__ import annotations

__all__ = ("array_index", "is_array_index_token")


def is_array_index_token(token: str) -> bool:
    """Report whether a pointer token has the canonical RFC 6901 array-index form."""

    # int() refuses some Unicode digits that str.isdigit() accepts, so require ASCII digits.
    # Only the one-digit token "0" can start with a zero.
    return token.isascii() and token.isdigit() and (len(token) == 1 or not token.startswith("0"))


def array_index(token: str, length: int) -> int | None:
    """Return the list position that a pointer token names, or None when it names none."""

    if not is_array_index_token(token):
        return None
    # int() refuses a string beyond the interpreter digit limit, so compare the digit count first.
    if len(token) > len(str(length)) or int(token) >= length:
        return None
    return int(token)
