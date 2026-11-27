"""SHA-256 digests of exact bytes and their renderings (ADR-118).

This module is the one owner of SHA-256 construction in the packages. Callers
choose the input bytes, the framing and any domain prefix; this module only
hashes the bytes. Persisted records and evidence contain these digests, so a
rendering never changes.

This module uses only the standard library.
"""

from __future__ import annotations

import hashlib
from collections.abc import Buffer
from typing import Final, Protocol

__all__ = (
    "SHA256_DIGEST_PATTERN",
    "SHA256_PREFIX",
    "Sha256Hasher",
    "sha256_bytes",
    "sha256_digest",
    "sha256_hasher",
    "sha256_hex",
)

#: Algorithm label of a prefixed digest such as ``sha256:<64 lowercase hex digits>``.
SHA256_PREFIX: Final = "sha256:"
SHA256_DIGEST_PATTERN: Final = r"^sha256:[a-f0-9]{64}$"


class Sha256Hasher(Protocol):
    """An incremental SHA-256 object for bounded read loops."""

    def update(self, data: Buffer, /) -> None: ...

    def digest(self) -> bytes: ...

    def hexdigest(self) -> str: ...


def sha256_hasher() -> Sha256Hasher:
    """Return a new, empty incremental SHA-256 object."""

    return hashlib.sha256()


def sha256_bytes(data: Buffer) -> bytes:
    """Return the 32-byte SHA-256 digest of ``data``."""

    return hashlib.sha256(data).digest()


def sha256_hex(data: Buffer) -> str:
    """Return the lowercase hexadecimal SHA-256 digest of ``data``."""

    return hashlib.sha256(data).hexdigest()


def sha256_digest(data: Buffer) -> str:
    """Return the ``sha256:``-prefixed lowercase hexadecimal digest of ``data``."""

    return SHA256_PREFIX + sha256_hex(data)
