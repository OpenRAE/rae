"""Named sorted, compact ``json.dumps`` text variants (ADR-118).

Existing digests, signatures and stored records use these exact bytes. They are
not RFC 8785 bytes: the text escapes or keeps non-ASCII characters, writes
Python float text and sorts keys by code point. Use
:mod:`raes_contracts.canonical` for a new digest. A change from one variant to
another, or to RFC 8785, changes bytes and needs a digest migration.

Each variant sorts keys and uses the compact ``(",", ":")`` separators. The
``finite`` variants refuse NaN and infinities with ``ValueError``; the others
write ``NaN``, ``Infinity`` and ``-Infinity``. The ``unicode`` variants keep
non-ASCII characters; the others escape them. ``default`` is the explicit
``json.dumps`` conversion callback; ``None`` raises ``TypeError`` for a value
that JSON cannot represent.

This module uses only the standard library.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from .digests import sha256_digest

__all__ = (
    "sorted_json_digest",
    "sorted_json_text",
    "sorted_json_text_finite",
    "sorted_json_text_unicode",
    "sorted_json_text_unicode_finite",
)

type JsonConversion = Callable[[object], object]


def _sorted_json(value: object, *, ensure_ascii: bool, allow_nan: bool, default: JsonConversion | None) -> str:
    return json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        allow_nan=allow_nan,
        sort_keys=True,
        separators=(",", ":"),
        default=default,
    )


def sorted_json_text(value: object, *, default: JsonConversion | None = None) -> str:
    """Return sorted, compact ASCII JSON text; NaN and infinities are written as such."""

    return _sorted_json(value, ensure_ascii=True, allow_nan=True, default=default)


def sorted_json_text_finite(value: object, *, default: JsonConversion | None = None) -> str:
    """Return sorted, compact ASCII JSON text; NaN and infinities raise ``ValueError``."""

    return _sorted_json(value, ensure_ascii=True, allow_nan=False, default=default)


def sorted_json_text_unicode(value: object, *, default: JsonConversion | None = None) -> str:
    """Return sorted, compact JSON text that keeps non-ASCII characters; NaN is written as such."""

    return _sorted_json(value, ensure_ascii=False, allow_nan=True, default=default)


def sorted_json_text_unicode_finite(value: object, *, default: JsonConversion | None = None) -> str:
    """Return sorted, compact JSON text that keeps non-ASCII characters; NaN raises ``ValueError``."""

    return _sorted_json(value, ensure_ascii=False, allow_nan=False, default=default)


def sorted_json_digest(value: object, *, default: JsonConversion | None = None) -> str:
    """Return the ``sha256:`` digest of the UTF-8 bytes of :func:`sorted_json_text`."""

    return sha256_digest(sorted_json_text(value, default=default).encode("utf-8"))
