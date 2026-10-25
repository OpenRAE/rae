"""Portable SDL identifiers and composition-generated qualified names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import AfterValidator, WithJsonSchema

PORTABLE_IDENTIFIER_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"
PORTABLE_IDENTIFIER_RE = re.compile(PORTABLE_IDENTIFIER_PATTERN, re.ASCII)
PORTABLE_IDENTIFIER_MAX_LENGTH = 64
QUALIFIED_IDENTIFIER_MAX_LENGTH = 2048
PRIVATE_NAMESPACE_SEGMENT = "__private"

# JSON Schema's `$` may match immediately before a final newline. Combining a
# first-character check with an explicit rejection of every character outside
# the alphabet keeps the machine-readable contract independent of that quirk.
PORTABLE_IDENTIFIER_JSON_SCHEMA: dict[str, Any] = {
    "type": "string",
    "minLength": 1,
    "maxLength": PORTABLE_IDENTIFIER_MAX_LENGTH,
    "pattern": "^[a-z0-9]",
    "not": {"pattern": "[^a-z0-9_-]"},
}


def portable_identifier_map_schema(schema: dict[str, Any]) -> None:
    """Keep all key constraints when Pydantic moves the pattern to patternProperties."""

    schema["propertyNames"] = dict(PORTABLE_IDENTIFIER_JSON_SCHEMA)
    schema["additionalProperties"] = False


def is_portable_identifier(value: object) -> bool:
    """Return whether *value* is one exact portable local identifier."""

    return isinstance(value, str) and PORTABLE_IDENTIFIER_RE.fullmatch(value) is not None


def require_portable_identifier(value: object, *, field_name: str) -> str:
    """Return a valid portable identifier or raise a value-only-safe error."""

    if not is_portable_identifier(value):
        raise ValueError(
            f"{field_name} must be a portable SDL identifier: 1-64 lowercase "
            "ASCII letters, digits, hyphens, or underscores, starting with a letter or digit"
        )
    return value


def _validate_portable_identifier(value: str) -> str:
    return require_portable_identifier(value, field_name="value")


def _validate_optional_portable_identifier(value: str) -> str:
    return value if value == "" else require_portable_identifier(value, field_name="value")


PortableIdentifier = Annotated[
    str,
    AfterValidator(_validate_portable_identifier),
    WithJsonSchema(PORTABLE_IDENTIFIER_JSON_SCHEMA),
]
OptionalPortableIdentifier = Annotated[
    str,
    AfterValidator(_validate_optional_portable_identifier),
    WithJsonSchema(
        {
            "anyOf": [
                {"const": ""},
                PORTABLE_IDENTIFIER_JSON_SCHEMA,
            ]
        }
    ),
]


def require_module_identifier(value: object, *, field_name: str = "module.id") -> str:
    """Validate the exact ``publisher/name`` module identity shape."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must use portable 'publisher/name' format")
    parts = value.split("/")
    if len(parts) != 2 or any(not is_portable_identifier(part) for part in parts):
        raise ValueError(f"{field_name} must use portable 'publisher/name' format")
    return value


@dataclass(frozen=True, order=True)
class QualifiedName:
    """A composition-generated namespace path followed by one local symbol."""

    parts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.parts or not is_portable_identifier(self.parts[-1]):
            raise ValueError("qualified SDL name must end with a portable local identifier")
        for part in self.parts[:-1]:
            if part != PRIVATE_NAMESPACE_SEGMENT and not is_portable_identifier(part):
                raise ValueError("qualified SDL namespace contains an invalid segment")
        if len(self.render()) > QUALIFIED_IDENTIFIER_MAX_LENGTH:
            raise ValueError("qualified SDL name exceeds the maximum length")

    @classmethod
    def parse(cls, value: object) -> QualifiedName:
        if not isinstance(value, str):
            raise ValueError("qualified SDL name must be a string")
        return cls(tuple(value.split(".")))

    @classmethod
    def local(cls, value: object) -> QualifiedName:
        return cls((require_portable_identifier(value, field_name="local identifier"),))

    def prefixed(self, namespace: object, *, private: bool = False) -> QualifiedName:
        segment = require_portable_identifier(namespace, field_name="namespace")
        prefix = (segment, PRIVATE_NAMESPACE_SEGMENT) if private else (segment,)
        return QualifiedName((*prefix, *self.parts))

    def render(self) -> str:
        return ".".join(self.parts)


def require_qualified_identifier(value: object, *, field_name: str) -> str:
    """Validate one composition-generated qualified symbol spelling."""

    try:
        return QualifiedName.parse(value).render()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a qualified SDL identifier") from exc


__all__ = [
    "OptionalPortableIdentifier",
    "portable_identifier_map_schema",
    "PORTABLE_IDENTIFIER_JSON_SCHEMA",
    "PORTABLE_IDENTIFIER_MAX_LENGTH",
    "PORTABLE_IDENTIFIER_PATTERN",
    "PRIVATE_NAMESPACE_SEGMENT",
    "QUALIFIED_IDENTIFIER_MAX_LENGTH",
    "PortableIdentifier",
    "QualifiedName",
    "is_portable_identifier",
    "require_module_identifier",
    "require_portable_identifier",
    "require_qualified_identifier",
]
