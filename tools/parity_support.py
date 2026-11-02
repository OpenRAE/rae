"""Shared case format and deterministic JSON for the parity recorder (#1778)."""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from types import ModuleType
from unittest.mock import patch

ARGUMENTS_FILE = "arguments.json"
PAYLOAD_FILE = "payload.json"
REQUEST_FILE = "request.json"
SHA256_PREFIX = "sha256:"
MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class Case:
    """One invocation of a surface command with its input files."""

    surface: str
    command: str
    name: str
    args: tuple[str, ...]
    files: Mapping[str, bytes]

    @property
    def path(self) -> Path:
        """Return the case file path relative to the corpus directory."""

        return Path(
            "cases",
            self.surface,
            self.command.replace(" ", "-").replace("/", "-").replace("{", "").replace("}", ""),
            digest(self.name.encode()) + ".json",
        )


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encode(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def fixed_clock() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def machine_schema(value: object) -> object:
    """Drop schema prose while preserving property names and authored defaults."""
    if isinstance(value, list):
        return [machine_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    named_maps = {"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"}
    for key, item in value.items():
        if key in {"description", "title", "summary"}:
            continue
        if key in named_maps and isinstance(item, dict):
            result[key] = {name: machine_schema(schema) for name, schema in item.items()}
        elif key in {"default", "const", "enum"}:
            result[key] = item
        else:
            result[key] = machine_schema(item)
    return result


def machine_payload(value: object, *, diagnostic: bool = False) -> object:
    """Remove free diagnostic wording without removing authored payload values."""
    if isinstance(value, list):
        return [machine_payload(item, diagnostic=diagnostic) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: item
        if key == "payload"
        else machine_payload(item, diagnostic=key in {"diagnostics", "source_diagnostics", "advisories"})
        for key, item in value.items()
        if not (diagnostic and key in {"message", "detail", "msg"})
    }


def json_output(text: str) -> object:
    try:
        return machine_payload(json.loads(text))
    except ValueError:
        return None


def runtime_aliases(value: object) -> Iterator[tuple[ModuleType, str]]:
    """Find aliases in the product modules, including modules imported lazily."""
    modules = (
        module
        for name, module in tuple(sys.modules.items())
        if module is not None and name.startswith(("raes", "raes_"))
    )
    for module in modules:
        for attribute, candidate in tuple(vars(module).items()):
            if candidate is value:
                yield module, attribute


@contextmanager
def deterministic_ids(seed: str) -> Iterator[None]:
    """Control generated UUIDs only during an isolated reference recording."""
    original = uuid.uuid4
    serial = 0
    lock = Lock()

    def next_uuid() -> uuid.UUID:
        nonlocal serial
        with lock:
            serial += 1
            identity = digest(f"{seed}/{serial}".encode())[:32]
        return uuid.UUID(hex=identity, version=4)

    with ExitStack() as patches:
        for module, attribute in runtime_aliases(original):
            patches.enter_context(patch.object(module, attribute, next_uuid))
        patches.enter_context(patch.object(uuid, "uuid4", next_uuid))
        try:
            yield
        finally:
            # Lazy imports can retain a patched function after its context ends.
            for module, attribute in runtime_aliases(next_uuid):
                setattr(module, attribute, original)
