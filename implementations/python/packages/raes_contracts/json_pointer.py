"""RFC 6901 JSON Pointer reference tokens and array-index rules.

``escape_token`` replaces ``~`` before ``/`` (RFC 6901 section 3), and
``unescape_token`` replaces ``~1`` before ``~0`` (section 4), so ``~01`` decodes
to ``~1``. The pointer ``""`` names the whole document and ``"/"`` names the
member with the empty name. These functions convert tokens only; callers keep
their own pointer validation and resolution rules (ADR-118).

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

from collections.abc import Iterable

__all__ = (
    "array_index",
    "escape_token",
    "is_array_index_token",
    "pointer_from_tokens",
    "pointer_tokens",
    "unescape_token",
)


def escape_token(token: str) -> str:
    """Encode one reference token: ``~`` becomes ``~0``, then ``/`` becomes ``~1``."""

    return token.replace("~", "~0").replace("/", "~1")


def unescape_token(token: str) -> str:
    """Decode one reference token: ``~1`` becomes ``/``, then ``~0`` becomes ``~``."""

    return token.replace("~1", "/").replace("~0", "~")


def pointer_from_tokens(tokens: Iterable[str]) -> str:
    """Join reference tokens into a pointer; no tokens give the whole-document pointer ``""``."""

    return "".join("/" + escape_token(token) for token in tokens)


def pointer_tokens(pointer: str) -> tuple[str, ...]:
    """Split a pointer into decoded reference tokens; text before the first ``/`` is ignored."""

    return tuple(unescape_token(token) for token in pointer.split("/")[1:])


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
