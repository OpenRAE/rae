"""Wire contract for processor-owned runtime addresses."""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import AfterValidator, WithJsonSchema

COMPILED_ADDRESS_MAX_LENGTH = 2048
_ADDRESS_SEGMENT = r"(?:[a-z0-9][a-z0-9_-]{0,63}|__private)"
COMPILED_ADDRESS_PATTERN = rf"{_ADDRESS_SEGMENT}(?:\.{_ADDRESS_SEGMENT})+"
_COMPILED_ADDRESS_RE = re.compile(COMPILED_ADDRESS_PATTERN, re.ASCII)
COMPILED_ADDRESS_JSON_SCHEMA: dict[str, Any] = {
    "type": "string",
    "minLength": 3,
    "maxLength": COMPILED_ADDRESS_MAX_LENGTH,
    "pattern": rf"^{COMPILED_ADDRESS_PATTERN}$",
    "not": {"pattern": "[^a-z0-9_.-]"},
}
PLAN_ADDRESS_ROOT_BY_DOMAIN = {
    "provisioning": "provision",
    "orchestration": "orchestration",
    "evaluation": "evaluation",
}


def require_compiled_address(value: object, *, field_name: str = "address") -> str:
    if (
        not isinstance(value, str)
        or len(value) > COMPILED_ADDRESS_MAX_LENGTH
        or _COMPILED_ADDRESS_RE.fullmatch(value) is None
    ):
        raise ValueError(f"{field_name} must be a canonical compiled address")
    return value


def _validate_compiled_address(value: str) -> str:
    return require_compiled_address(value)


CompiledAddress = Annotated[
    str,
    AfterValidator(_validate_compiled_address),
    WithJsonSchema(COMPILED_ADDRESS_JSON_SCHEMA),
]


def render_compiled_address(*parts: str) -> str:
    address = ".".join(part for part in parts if part)
    return require_compiled_address(address)


def is_compiler_owned_temporal_subject_address(address: str) -> bool:
    """Return whether a temporal subject is owned by an SDL compiler."""

    parts = address.split(".")
    return address.startswith("sdl.") or (
        len(parts) == 5
        and all(parts)
        and parts[0] == "participant"
        and parts[1] == "behavior-specification"
        and parts[3] == "inject-delivery"
    )


__all__ = [
    "COMPILED_ADDRESS_JSON_SCHEMA",
    "COMPILED_ADDRESS_MAX_LENGTH",
    "CompiledAddress",
    "is_compiler_owned_temporal_subject_address",
    "render_compiled_address",
    "require_compiled_address",
]
