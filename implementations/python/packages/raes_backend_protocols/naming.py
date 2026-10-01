"""Deterministic provider-name derivation from compiler-owned addresses."""

from __future__ import annotations

import hashlib
import re

from raes_contracts.addressing import require_compiled_address

_UNSAFE_PROVIDER_NAME = re.compile(r"[^a-z0-9_.-]+", re.ASCII)
_DIGEST_LENGTH = 12


def provider_resource_name(
    address: str,
    *,
    prefix: str = "",
    namespace: str = "",
    maximum_length: int = 63,
) -> str:
    """Return a bounded readable name whose suffix commits to *address*.

    ``namespace`` binds the name to one run so concurrent runs realizing the
    same address never contend for a single native resource name. It commits
    through the digest rather than the readable head, so the address stays
    legible and the bound stays the same. The empty default reproduces the
    un-namespaced name exactly.
    """

    require_compiled_address(address)
    if isinstance(maximum_length, bool) or not isinstance(maximum_length, int) or maximum_length < 16:
        raise ValueError("provider resource name maximum_length must be an integer >= 16")
    if not isinstance(namespace, str):
        raise TypeError("provider resource name namespace must be a string")
    # NUL cannot appear in either component, so the join is unambiguous and one
    # namespace/address pair can never be spelled as another.
    committed = address if not namespace else f"{namespace}\0{address}"
    digest = hashlib.sha256(committed.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    readable = _UNSAFE_PROVIDER_NAME.sub("-", address.lower()).strip("-._") or "resource"
    safe_prefix = _UNSAFE_PROVIDER_NAME.sub("-", prefix.lower()).strip("-._")
    if safe_prefix:
        readable = f"{safe_prefix}-{readable}"
    suffix = f"-{digest}"
    readable_budget = maximum_length - len(suffix)
    head = readable[:readable_budget].rstrip("-._") or "resource"[:readable_budget]
    return f"{head}{suffix}"


__all__ = ["provider_resource_name"]
