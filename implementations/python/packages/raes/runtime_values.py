"""Shared parsing helpers for SDL runtime configuration models."""

import ipaddress
import re
from collections.abc import Iterable
from enum import Enum
from typing import Any

from ._base import (
    is_variable_ref,
    parse_bool_or_var,
    parse_enum_or_var,
)
from ._identifiers import require_portable_identifier

_BYTE_UNITS = {
    "b": 1,
    "kb": 1_000,
    "kib": 1_024,
    "mb": 1_000_000,
    "mib": 1_048_576,
    "gb": 1_000_000_000,
    "gib": 1_073_741_824,
    "tb": 1_000_000_000_000,
    "tib": 1_099_511_627_776,
}

_RAM_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(" + "|".join(_BYTE_UNITS) + r")\s*$",
    re.IGNORECASE,
)
_RAM_MIN_BYTES_ERROR = "RAM must be >= 1 byte"
_WINDOWS_NAMED_PIPE_PREFIXES = ("\\\\.\\pipe\\", "\\\\?\\pipe\\")

# Identifier-shape tokens used to identify names that may benefit from advisory
# sensitivity defaults. They are not a validation rule: SDL values are scenario
# realization facts unless the author explicitly classifies them as withheld.
# The string-concatenation / ``noqa: S105`` markers silence bandit without
# dressing each line up as actual credential material.
SECRET_NAME_TOKENS: tuple[str, ...] = (
    "access_key",
    "access_token",  # noqa: S105
    "api_key",
    "auth_key",
    "authd.pass",
    "client_key",
    "client_secret",  # noqa: S105
    "clientsecret",
    "conninfo",
    "credential",
    "credentials",
    "enrollment_key",
    "hmac",
    "keyfile",
    "keytab",
    "krbprincipalkey",
    "passphrase",
    "passwd",
    "pass" + "word",
    "pg_hba",
    "private_key",
    "privatekey",
    "pwd",
    "refresh_token",  # noqa: S105
    "rndc.key",
    "sasl_passwd",
    "sasl_password",  # noqa: S105
    "sec" + "ret",
    "shared_key",
    "ssh_" + "key",
    "supplementalcredentials",
    "token",
    "tsig",
    "update_key",
)
# Whole alphanumeric parts that can conservatively mark compound names as
# credential-like for advisory consumers. Reference, metadata, and public-key
# context exclusions below keep this from labeling key fingerprints, key-file
# paths, or scalar key facts as credential material.
SECRET_NAME_PARTS: frozenset[str] = frozenset({"key"})
SECRET_NAME_REFERENCE_PARTS: frozenset[str] = frozenset(
    {
        "file",
        "filepath",
        "filename",
        "fingerprint",
        "path",
    }
)
SECRET_NAME_METADATA_PARTS: frozenset[str] = frozenset(
    {
        "bits",
        "bytes",
        "count",
        "len",
        "length",
        "size",
    }
)
PUBLIC_KEY_CONTEXT_PARTS: frozenset[str] = frozenset({"gpg", "pgp", "public"})


def _name_parts(normalized_name: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[^a-z0-9]+", normalized_name) if part)


def _names_secret_reference_or_metadata(normalized_name: str, parts: tuple[str, ...]) -> bool:
    if not parts:
        return False
    if parts[-1] in SECRET_NAME_REFERENCE_PARTS | SECRET_NAME_METADATA_PARTS:
        return True
    return normalized_name.endswith("keyfile")


def _names_public_key_context(parts: tuple[str, ...]) -> bool:
    return len(parts) >= 2 and parts[-1] == "key" and parts[-2] in PUBLIC_KEY_CONTEXT_PARTS


def name_indicates_secret(name: str) -> bool:
    """Return whether a setting name looks credential-bearing.

    This helper is advisory. It does not impose raw-value omission: SDL runtime
    values are scenario content unless their explicit classification says they
    are withheld.
    """
    lowered = name.lower().replace("-", "_")
    parts = _name_parts(lowered)
    if _names_secret_reference_or_metadata(lowered, parts) or _names_public_key_context(parts):
        return False
    if any(token in lowered for token in SECRET_NAME_TOKENS):
        return True
    return bool(frozenset(parts) & SECRET_NAME_PARTS)


def _has_raw_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    return bool(value)


def _classification_label(value: object) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _classification_in(value: object, candidates: Iterable[object]) -> bool:
    if is_variable_ref(value):
        return False
    value_label = _classification_label(value)
    return any(value == candidate or value_label == _classification_label(candidate) for candidate in candidates)


def enforce_observed_value_redaction(
    *,
    owner_label: str,
    value: object,
    classification: object,
    redacted_classifications: tuple[object, ...],
    raw_value_label: str = "raw value",
    redacted_raw_message: str | None = None,
) -> None:
    """Validate explicit redaction classifications for runtime observed values.

    SDL runtime values are scenario-realization facts. A name that resembles a
    secret does not by itself force omission; only an explicit redacted or
    operator-secret classification withholds raw data. Family models still own
    their ids, scopes, refs, provenance enums, and closed lattices.
    """
    has_raw = _has_raw_value(value)
    if has_raw and _classification_in(classification, redacted_classifications):
        if redacted_raw_message:
            raise ValueError(redacted_raw_message)
        raise ValueError(
            f"{owner_label} classified '{_classification_label(classification)}' must omit its {raw_value_label}"
        )


def require_symbol(value: str, *, field_name: str) -> str:
    """Validate a stable, symbol-defining identifier (no ``${var}`` placeholder).

    Symbol-defining ids are reference targets, so they must be concrete: empty
    values and ``${var}`` placeholders are rejected.
    """
    return require_portable_identifier(value, field_name=field_name)


def absolute_path_or_var(value: str, *, field_name: str) -> str:
    if is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value.startswith("/"):
        raise ValueError(f"{field_name} must be an absolute path")
    return value


def ip_address_or_var(value: str, *, field_name: str) -> str:
    """Validate an IPv4/IPv6 address, allowing empty and ``${var}`` values."""
    if not value or is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    try:
        ipaddress.ip_address(value)
    except ValueError as e:
        raise ValueError(f"{field_name} must be a valid IP address") from e
    return value


def is_windows_named_pipe(value: str) -> bool:
    return isinstance(value, str) and value.lower().startswith(_WINDOWS_NAMED_PIPE_PREFIXES)


def control_interface_path_or_var(value: str, *, field_name: str) -> str:
    if is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if value.startswith("/") or is_windows_named_pipe(value):
        return value
    raise ValueError(f"{field_name} must be an absolute path or Windows named pipe")


def parse_runtime_enum_or_var(value: Any, enum_cls: type[Enum], *, field_name: str):
    if value is None or isinstance(value, enum_cls) or is_variable_ref(value):
        return value
    try:
        parsed = parse_enum_or_var(value, enum_cls, field_name=field_name)
    except ValueError:
        parsed = _parse_runtime_extension(value, enum_cls, field_name=field_name)
    return parsed


def _parse_runtime_extension(value: Any, enum_cls: type[Enum], *, field_name: str):
    """Admit a private identity only through the field's governed vocabulary."""
    # The contracts facade also exposes SDL-shaped DTOs. Resolve its catalog
    # after model construction, as the incumbent account vocabulary does.
    from raes_contracts.controlled_vocabularies import (
        controlled_vocabulary_id_for_scope,
        validate_controlled_vocabulary_value,
    )

    vocabulary = controlled_vocabulary_id_for_scope(f"sdl.definitions.{enum_cls.__name__}")
    if vocabulary is None:
        return parse_enum_or_var(value, enum_cls, field_name=field_name)
    if isinstance(value, str):
        try:
            validate_controlled_vocabulary_value(vocabulary, value)
        except ValueError:
            pass
        else:
            return value
    # Catalog exceptions contain rejected inputs; they must not escape through
    # the SDL diagnostics surface. Private identity is never normalized away.
    raise ValueError(f"{field_name} must be one of the known terms, a governed x-<owner>:<term> identity, or ${{var}}")


def parse_runtime_enum_identity(value: object, enum_cls: type[Enum], *, field_name: str) -> str:
    """Validate a concrete vocabulary-domain member and retain exact identity."""
    parsed = parse_runtime_enum_or_var(value, enum_cls, field_name=field_name)
    token = getattr(parsed, "value", parsed)
    if not isinstance(token, str) or is_variable_ref(token):
        raise ValueError(f"{field_name} requires a concrete vocabulary identity")
    return token


def parse_optional_bool_or_var(value: Any, *, field_name: str) -> bool | str | None:
    return parse_bool_or_var(value, field_name=field_name) if value is not None else value


def coerce_string_list(value: Any):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return value


def require_non_empty(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def validate_absolute_paths(values: list[str], *, field_name: str) -> list[str]:
    return [absolute_path_or_var(value, field_name=field_name) for value in values]


def reject_duplicates(
    values: Iterable[object],
    *,
    label: str,
    container_label: str,
    duplicate_template: str = "Duplicate {label} '{value}' in {container_label}",
    skip_empty: bool = True,
) -> None:
    """Raise on the first repeated value in ``values``.

    Most runtime child-id checks ignore optional empty refs, while a few service
    namespaces validate all values. ``skip_empty`` keeps that policy explicit at
    each call site.
    """
    seen: set[object] = set()
    for value in values:
        if skip_empty and (value is None or value == ""):
            continue
        if value in seen:
            raise ValueError(duplicate_template.format(label=label, value=value, container_label=container_label))
        seen.add(value)


def parse_ram(value: str | int) -> int | str:
    """Parse a human-readable RAM string to bytes.

    Accepts bare integers (treated as bytes) or strings like
    ``"4 GiB"``, ``"2048 MiB"``, ``"512mb"``.
    """
    if is_variable_ref(value):
        return value
    if isinstance(value, bool):
        raise ValueError("RAM must be a positive integer or human-readable size")
    if isinstance(value, int):
        if value < 1:
            raise ValueError(_RAM_MIN_BYTES_ERROR)
        return value
    value_str = str(value).strip()
    if value_str.isdigit():
        parsed = int(value_str)
        if parsed < 1:
            raise ValueError(_RAM_MIN_BYTES_ERROR)
        return parsed
    match = _RAM_PATTERN.match(value_str)
    if not match:
        raise ValueError(f"Invalid RAM value: {value_str!r}. Use a number with a unit (e.g., '4 GiB', '2048 MiB').")
    amount = float(match.group(1))
    unit = match.group(2).lower()
    parsed = int(amount * _BYTE_UNITS[unit])
    if parsed < 1:
        raise ValueError(_RAM_MIN_BYTES_ERROR)
    return parsed
