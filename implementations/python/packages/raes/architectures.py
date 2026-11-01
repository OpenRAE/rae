"""Governed target-node CPU architecture vocabulary (issue #674).

The single source of truth for the SDL target-node CPU architecture requirement:
its canonical enumeration, authoring aliases, governed-extension form, the
field-aware normalizer shared by ``Node.architecture`` and
``RuntimePackage.architecture``, and the deterministic compatibility primitive.

Semantics (see ``docs/decisions/issue-674-target-node-cpu-architecture-preflight.md``):

- Canonical tokens are deliberately small: ``x86_64`` and ``aarch64``. Authoring
  aliases (``amd64``/``x64``/``x86-64`` and ``arm64``) normalize to them.
- Normalization is case-insensitive and applies the shared hyphen-to-underscore
  rule before alias resolution; canonical serialization emits the canonical token.
- Unknown unqualified strings fail closed. A custom architecture is admitted only
  in the governed-extension form ``x-<owner>:<term>`` (canonical lowercase), which
  compares by exact token with no implicit aliases.
- Absence (``None`` / unset) means no authored architecture requirement; it never
  implies the host, runner, image, or package architecture.

Keeping this vocabulary in one module — rather than duplicating alias maps in the
model, planner, backend, and envelope layers — is the ADR-012 portable-vocabulary
discipline and the anti-duplication guardrail from the preflight note.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import WithJsonSchema
from raes_contracts.variable_references import VARIABLE_TOKEN_PATTERN, is_variable_ref, normalize_enum_value


class NodeArchitecture(str, Enum):
    """Canonical target-node CPU architecture vocabulary.

    Governed-extension vocabulary (DSL-139): the closed canonical set below is
    kept deliberately small; a custom architecture uses the governed
    ``x-<owner>:<term>`` extension form rather than a catch-all sentinel, so
    neither ``unknown`` nor ``other`` is carried (absence already expresses "no
    target architecture requirement"). Kept in parity with the
    ``provisioner-node-architectures`` controlled vocabulary.
    """

    X86_64 = "x86_64"
    AARCH64 = "aarch64"


# Governed-extension form ``x-<owner>:<term>`` shared with the concept-authority
# controlled-vocabulary ``provisioner-node-architectures`` extension pattern.
ARCHITECTURE_EXTENSION_PATTERN = r"^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$"
_ARCHITECTURE_EXTENSION_RE = re.compile(ARCHITECTURE_EXTENSION_PATTERN)

# Authoring aliases as written before hyphen-to-underscore normalization; the raw
# spellings a document may carry for a non-canonical string branch.
_ARCHITECTURE_AUTHORING_ALIASES = ("amd64", "x64", "x86-64", "arm64")
_ARCHITECTURE_EXTENSION_BODY = r"x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*"

# JSON Schema (ADR-009 normative contract) constraints so the published schema
# encodes the governed vocabulary directly instead of leaving an unrestricted
# string branch: a schema-only consumer accepts a canonical value, a governed
# alias, a governed ``x-<owner>:<term>`` extension, or a whole-field ``${var}``
# reference, and nothing else. Runtime enforcement stays in
# :func:`normalize_architecture`; these annotations only shape the schema.
_ARCHITECTURE_NON_CANONICAL_STRING_SCHEMA = {
    "type": "string",
    "pattern": (
        "^(?:"
        + "|".join(_ARCHITECTURE_AUTHORING_ALIASES)
        + "|"
        + _ARCHITECTURE_EXTENSION_BODY
        + "|"
        + VARIABLE_TOKEN_PATTERN
        + ")$"
    ),
}
_PACKAGE_ARCHITECTURE_STRING_SCHEMA = {
    "type": "string",
    "pattern": (
        "^(?:"
        + "|".join(member.value for member in NodeArchitecture)
        + "|"
        + "|".join(_ARCHITECTURE_AUTHORING_ALIASES)
        + "|"
        + _ARCHITECTURE_EXTENSION_BODY
        + "|"
        + VARIABLE_TOKEN_PATTERN
        + ")?$"
    ),
}

# ``Node.architecture`` carries the canonical values through the ``NodeArchitecture``
# enum branch; this annotated string branch admits only governed non-canonical
# spellings. ``RuntimePackage.architecture`` is a bare string whose empty value
# means "not architecture-constrained", so its branch also admits the canonical
# tokens and the empty string.
AuthoredNodeArchitectureString = Annotated[str, WithJsonSchema(_ARCHITECTURE_NON_CANONICAL_STRING_SCHEMA)]
PackageArchitectureString = Annotated[str, WithJsonSchema(_PACKAGE_ARCHITECTURE_STRING_SCHEMA)]

# Authoring aliases keyed on the hyphen-normalized lowercase spelling. Canonical
# members are not listed here; they resolve directly against ``NodeArchitecture``.
ARCHITECTURE_ALIASES: dict[str, str] = {
    "amd64": NodeArchitecture.X86_64.value,
    "x64": NodeArchitecture.X86_64.value,
    "arm64": NodeArchitecture.AARCH64.value,
}

_ALLOWED_MESSAGE = (
    "architecture must be one of: "
    + ", ".join(member.value for member in NodeArchitecture)
    + ", a governed x-<owner>:<term> extension, or a ${var} placeholder"
)


def is_architecture_extension(value: str) -> bool:
    """Return whether ``value`` is a governed ``x-<owner>:<term>`` extension token."""

    return _ARCHITECTURE_EXTENSION_RE.fullmatch(value) is not None


def normalize_architecture(value: object) -> object:
    """Normalize a target/package architecture value, allowing ``${var}`` refs.

    Returns ``None`` unchanged, a ``${var}`` placeholder unchanged, a
    :class:`NodeArchitecture` member for canonical values and aliases, and the
    canonical lowercase token for a governed ``x-<owner>:<term>`` extension.
    Unknown unqualified strings fail closed with a stable message.
    """

    if value is None or isinstance(value, NodeArchitecture) or is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError("architecture must be a string")

    lowered = value.lower()
    if is_architecture_extension(lowered):
        return lowered

    normalized = normalize_enum_value(lowered)
    canonical = ARCHITECTURE_ALIASES.get(normalized, normalized)
    try:
        return NodeArchitecture(canonical)
    except ValueError as exc:
        raise ValueError(_ALLOWED_MESSAGE) from exc


def _canonical_token(value: object) -> str | None:
    """Return the comparable canonical token for a normalized architecture value."""

    if isinstance(value, NodeArchitecture):
        return value.value
    if isinstance(value, str) and value != "":
        return value
    return None


def architectures_compatible(node_architecture: object, package_architecture: object) -> bool:
    """Return whether a normalized node/package architecture pair is compatible.

    Both arguments must already be normalized (a :class:`NodeArchitecture`, a
    governed extension token, or empty/``None``). Compatibility is exact canonical
    equality; empty package architecture is architecture-independent and always
    compatible. The absent-node / present-package fail-closed rule is enforced by
    the semantic validator, not here.
    """

    package_token = _canonical_token(package_architecture)
    if package_token is None:
        return True
    node_token = _canonical_token(node_architecture)
    if node_token is None:
        return False
    return node_token == package_token


__all__ = [
    "ARCHITECTURE_ALIASES",
    "ARCHITECTURE_EXTENSION_PATTERN",
    "AuthoredNodeArchitectureString",
    "NodeArchitecture",
    "PackageArchitectureString",
    "architectures_compatible",
    "is_architecture_extension",
    "normalize_architecture",
]
