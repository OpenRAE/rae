"""Incremental hashers for the checksum algorithms of artifact references.

Artifact contracts admit SHA-256, SHA-384, SHA-512 and BLAKE3 checksums.
``hashlib`` provides the SHA-2 family; the ``blake3`` package provides BLAKE3.
Each validator that recomputes an artifact checksum uses this one constructor.
"""

from __future__ import annotations

import hashlib
from collections.abc import Buffer
from typing import Protocol

from blake3 import blake3


class ChecksumHasher(Protocol):
    """An incremental hash object for bounded read loops."""

    def update(self, data: Buffer, /) -> object: ...

    def hexdigest(self) -> str: ...


def checksum_hasher(algorithm: str) -> ChecksumHasher:
    """Return a new, empty hasher for ``algorithm``.

    Raise ``ValueError`` for an algorithm that neither ``blake3`` nor ``hashlib`` provides.
    """

    if algorithm == "blake3":
        return blake3()
    return hashlib.new(algorithm)


__all__ = ["ChecksumHasher", "checksum_hasher"]
