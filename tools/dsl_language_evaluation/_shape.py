"""Shape, id, and locator primitives for the DSL evaluation checker."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from tools.dsl_language_evaluation._keys import (
    _HISTORICAL_PACKAGE_MOVES,
    _ID_RE,
    _SENSITIVE_QUERY_KEYS,
)
from tools.policy.common import PolicyFailure, safe_repo_path


def _failure(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _resolve_repository_artifact(repo_root: Path, artifact_path: str) -> Path | None:
    """Resolve an immutable evidence locator through the Python package moves."""

    resolved_path = artifact_path
    for historical_prefix, current_prefix in _HISTORICAL_PACKAGE_MOVES:
        if artifact_path == historical_prefix or artifact_path.startswith(f"{historical_prefix}/"):
            resolved_path = f"{current_prefix}{artifact_path[len(historical_prefix) :]}"
            break
    return safe_repo_path(repo_root, resolved_path)


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
    limit: int,
    failures: list[PolicyFailure],
    *,
    rule_id: str,
    label: str,
    path: str,
) -> list[object]:
    if not isinstance(value, list):
        failures.append(_failure(rule_id, f"{label} must be a list", path))
        return []
    if len(value) > limit:
        failures.append(_failure(rule_id, f"{label} exceeds the {limit}-entry limit", path))
        return []
    return value


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _bounded_text(value: object, *, maximum: int = 6000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _string_list(value: object, *, non_empty: bool = False) -> list[str] | None:
    if not isinstance(value, list) or (non_empty and not value):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return value


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
    duplicates: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        value = record.get(field)
        if not _valid_id(value):
            failures.append(_failure(rule_id, f"{label} has invalid {field} {value!r}", path))
            continue
        if value in result:
            duplicates.add(value)
        result.add(value)
    if duplicates:
        failures.append(_failure(rule_id, f"duplicate {label} ids: {sorted(duplicates)}", path))
    return result


def _validate_https_locator(locator: object, failures: list[PolicyFailure], source_id: object) -> None:
    if not isinstance(locator, str):
        failures.append(_failure("dsl-evaluation-source-locator", f"{source_id}: locator must be text"))
        return
    try:
        parsed = urlsplit(locator)
    except ValueError:
        # urlsplit refuses a malformed authority, such as an unclosed IPv6 bracket.
        failures.append(_failure("dsl-evaluation-source-locator", f"{source_id}: locator must be absolute HTTPS"))
        return
    if parsed.scheme != "https" or not parsed.netloc:
        failures.append(
            _failure(
                "dsl-evaluation-source-locator",
                f"{source_id}: locator must be absolute HTTPS",
            )
        )
    if parsed.username is not None or parsed.password is not None:
        failures.append(
            _failure(
                "dsl-evaluation-source-secret",
                f"{source_id}: locator contains URI userinfo",
            )
        )
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    sensitive = sorted(query_keys & _SENSITIVE_QUERY_KEYS)
    if sensitive:
        failures.append(
            _failure(
                "dsl-evaluation-source-secret",
                f"{source_id}: locator contains secret-bearing query keys {sensitive}",
            )
        )


def _protocol_records_by_id(
    protocol: Mapping[str, object],
    field: str,
    id_field: str,
) -> dict[str, Mapping[str, object]]:
    records = protocol.get(field, [])
    if not isinstance(records, list):
        return {}
    return {
        record[id_field]: record
        for record in records
        if isinstance(record, Mapping) and isinstance(record.get(id_field), str)
    }
