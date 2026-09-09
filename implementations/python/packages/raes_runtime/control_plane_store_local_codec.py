"""Canonical payload and transaction primitives for the local store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Commit all local-store changes together or roll them all back."""

    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def encode_payload(payload: dict[str, Any]) -> tuple[str, str]:
    """Encode one canonical durable object with its integrity digest."""

    content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return content, hashlib.sha256(content.encode("utf-8")).hexdigest()


def decode_payload(content: str, expected_digest: str, *, kind: str) -> dict[str, Any]:
    """Validate and decode one canonical durable object."""

    actual_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if actual_digest != expected_digest:
        raise ValueError(f"{kind} failed its durable integrity check")
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError(f"{kind} payload must be an object")
    return payload


__all__ = ("decode_payload", "encode_payload", "transaction")
