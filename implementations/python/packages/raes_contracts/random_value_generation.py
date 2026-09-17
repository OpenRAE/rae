"""Portable random-value alphabets and reference generation (issue #1276).

The alphabet charsets are the single source of truth shared by the SDL recipe
model (:mod:`raes.random_value`, for entropy accounting) and any backend that
realizes a ``random_value`` generated artifact. Generation itself is a backend
concern; :func:`render_random_value` is the reference implementation and uses a
cryptographically secure generator with unbiased sampling.
"""

from __future__ import annotations

import math
import secrets
from collections.abc import Mapping

# Concrete alphabets keyed by the portable ``NamedAlphabet`` string value.
NAMED_ALPHABET_CHARSETS: dict[str, str] = {
    "hex_lower": "0123456789abcdef",
    "hex_upper": "0123456789ABCDEF",
    "digits": "0123456789",
    "alpha": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "alphanumeric": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "base32": "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",
    "base58": "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz",
}


def recipe_charset(recipe: Mapping[str, object]) -> str:
    """Return the concrete alphabet for a serialized ``random_value`` recipe."""

    named = recipe.get("alphabet")
    if isinstance(named, str):
        try:
            return NAMED_ALPHABET_CHARSETS[named]
        except KeyError as exc:
            raise ValueError(f"unknown random value alphabet {named!r}") from exc
    custom = recipe.get("custom_alphabet")
    if isinstance(custom, str) and custom:
        return custom
    raise ValueError("random value recipe declares neither a named nor a custom alphabet")


def recipe_random_length(recipe: Mapping[str, object]) -> int:
    """Return the random character count for a recipe (length or entropy-derived)."""

    charset = recipe_charset(recipe)
    length = recipe.get("length")
    if isinstance(length, int) and not isinstance(length, bool):
        return length
    entropy_bits = recipe.get("entropy_bits")
    if isinstance(entropy_bits, int) and not isinstance(entropy_bits, bool):
        return math.ceil(entropy_bits / math.log2(len(charset)))
    raise ValueError("random value recipe declares neither a length nor an entropy budget")


def render_random_value(recipe: Mapping[str, object]) -> str:
    """Reference cryptographically-secure realization of a ``random_value`` recipe.

    Draws each character uniformly from the recipe's alphabet with a CSPRNG and
    applies the optional literal ``format`` wrapper. The wrapper contributes no
    entropy.
    """

    charset = recipe_charset(recipe)
    length = recipe_random_length(recipe)
    segment = "".join(secrets.choice(charset) for _ in range(length))
    fmt = recipe.get("format")
    if isinstance(fmt, Mapping):
        prefix = fmt.get("prefix", "")
        suffix = fmt.get("suffix", "")
        return f"{prefix if isinstance(prefix, str) else ''}{segment}{suffix if isinstance(suffix, str) else ''}"
    return segment


__all__ = [
    "NAMED_ALPHABET_CHARSETS",
    "recipe_charset",
    "recipe_random_length",
    "render_random_value",
]
