"""Shared shape, digest, and JSON-pointer primitives for coverage validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Container, Hashable, Iterable, Mapping, Sequence
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from raes_contracts.errors import InvalidInputError
from raes_contracts.json_pointer import array_index

from tools.policy.common import PolicyFailure
from tools.specification_coverage._keys import (
    _ID_RE,
    _MAX_CATALOG_ITEMS,
    _SENSITIVE_QUERY_KEYS,
)


def _failure(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


# Authored JSON can put a list or an object where an identifier is expected. Such a value
# has no hash, so these helpers treat it as an unknown value instead of a crash.
def _hashable(value: object) -> bool:
    """Return whether an authored value can be a set member or a mapping key."""
    return isinstance(value, Hashable)


def _member(value: object, collection: Container[object]) -> bool:
    """Return whether an authored value is in a set or a mapping; an unhashable value never is."""
    return isinstance(value, Hashable) and value in collection


def _members(value: object) -> Iterable[object]:
    """Return the members of an authored container; a scalar has no members."""
    return value if isinstance(value, Iterable) else ()


def _exact_keys(
    value: object,
    expected: set[str],
    failures: list[PolicyFailure],
    *,
    rule_id: str,
    label: str,
    path: str,
) -> bool:
    if not isinstance(value, dict):
        failures.append(_failure(rule_id, f"{label} must be an object", path))
        return False
    actual = set(value)
    if actual != expected:
        failures.append(
            _failure(
                rule_id,
                f"{label} fields must exactly match {sorted(expected)}; got {sorted(actual)}",
                path,
            )
        )
        return False
    return True


def _bounded_list(
    value: object,
    failures: list[PolicyFailure],
    *,
    rule_id: str,
    label: str,
    path: str,
    maximum: int = _MAX_CATALOG_ITEMS,
) -> list[object]:
    if not isinstance(value, list):
        failures.append(_failure(rule_id, f"{label} must be a list", path))
        return []
    if len(value) > maximum:
        failures.append(_failure(rule_id, f"{label} exceeds {maximum} entries", path))
        return []
    return value


def _bounded_text(value: object, *, maximum: int = 6000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _record_ids(
    records: Sequence[object],
    field: str,
    failures: list[PolicyFailure],
    *,
    rule_id: str,
    label: str,
    path: str,
) -> set[str]:
    result: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        value = record.get(field)
        if not _valid_id(value):
            failures.append(_failure(rule_id, f"{label}[{index}].{field} is invalid", path))
        elif value in result:
            failures.append(_failure(rule_id, f"duplicate {label} id {value!r}", path))
        else:
            result.add(value)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_python_tree(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(candidate for candidate in path.rglob("*.py") if candidate.is_file())
    if not files:
        raise InvalidInputError(f"implementation surface {path} contains no Python files")
    for candidate in files:
        if candidate.is_symlink():
            raise InvalidInputError(f"implementation surface contains symlink {candidate}")
        relative = candidate.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with candidate.open("rb") as handle:
            for block in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def _json_sha256(value: object) -> str | None:
    """Return the digest of the canonical JSON text, or None when the text has no UTF-8 form."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError:
        # An unpaired surrogate from a JSON escape has no UTF-8 form, so no digest can bind the value.
        return None
    return hashlib.sha256(encoded).hexdigest()


def _validate_https_locator(locator: object) -> bool:
    if not isinstance(locator, str) or len(locator) > 2048:
        return False
    try:
        parsed = urlsplit(locator)
    except ValueError:
        # urlsplit() refuses a malformed authority, such as an unclosed IPv6 bracket.
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and not any(key.lower() in _SENSITIVE_QUERY_KEYS for key, _ in parse_qsl(parsed.query))
    )


_POINTER_MISS = object()


def _pointer_step(current: object, segment: str) -> object:
    if isinstance(current, Mapping):
        return current.get(segment, _POINTER_MISS)
    if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
        index = array_index(segment, len(current))
        return current[index] if index is not None else _POINTER_MISS
    return _POINTER_MISS


def _json_pointer_get(payload: object, pointer: object) -> tuple[bool, object | None]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return False, None
    current: object = payload
    for raw_segment in pointer[1:].split("/"):
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        current = _pointer_step(current, segment)
        if current is _POINTER_MISS:
            return False, None
    return True, current
