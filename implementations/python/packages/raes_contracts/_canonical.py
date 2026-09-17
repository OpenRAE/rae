"""Dependency-neutral RFC 8785 (JCS) + SHA-256 canonical digest helpers.

Extracted so every closed contract shares one canonicalizer instead of minting
its own trial-plan or evidence serializer. ``canonical_contract_digest`` (in
:mod:`raes_contracts.satisfiability`) and the admitted trial-plan integrity
chain both route through here, keeping RFC 8785 canonicalization and the
``sha256:`` digest prefix identical across contracts.
"""

from __future__ import annotations

import hashlib

import rfc8785

#: A JSON value produced by ``model_dump(mode="json")`` — the only input these
#: canonicalizers accept.
JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_json_bytes(payload: JsonValue) -> bytes:
    """Return the RFC 8785 (JCS) canonical byte encoding of a JSON-able payload."""

    return rfc8785.dumps(payload)


def canonical_json_digest(payload: JsonValue) -> str:
    """Return the ``sha256:``-prefixed JCS SHA-256 digest of a JSON-able payload.

    The payload must already be JSON-compatible (e.g. ``model_dump(mode="json")``).
    """

    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


#: Prefix marking a carrier that is outside the modelled realization value space.
UNSERIALIZABLE_CARRIER_PREFIX = "urn:openrae:unserializable-carrier:"


def jsonable_fallback(value: object) -> str:
    """Render an unmodelled carrier as a stable, type-qualified marker.

    ``pydantic_core.to_jsonable_python`` raises on any carrier it has no schema
    for. Realization projections are comparison-only and must not crash on input
    that has drifted outside the modelled value space, so an unknown carrier is
    rendered as a marker instead. The marker is derived from the carrier's type
    alone, which keeps it identical across processes and runs — ``repr`` would
    embed object addresses and break digest stability — and the ``urn:`` prefix
    keeps it distinguishable from any modelled string value.
    """

    carrier = type(value)
    return f"{UNSERIALIZABLE_CARRIER_PREFIX}{carrier.__module__}.{carrier.__qualname__}"
