"""Content-addressed parity records and reproducible reference identity."""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


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
            self.command.replace(" ", "-"),
            digest(self.name.encode()) + ".json",
        )


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encode(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def case_document(case: Case, result: Mapping[str, object]) -> dict[str, object]:
    """Return the JSON document that records one case and its result."""

    return {
        "name": case.name,
        "surface": case.surface,
        "command": case.command,
        "args": list(case.args),
        "files": {name: digest(content) for name, content in sorted(case.files.items())},
        "result": dict(result),
    }


def reference_identity(repo: Path) -> dict[str, str | None]:
    """Bind the source, dependency lock, recorder and relevant runtime tables."""
    sources = [
        *sorted((repo / "implementations/python/packages").rglob("*.py")),
        repo / "implementations/python/uv.lock",
    ]
    identity = b"".join(
        source.relative_to(repo).as_posix().encode() + b"\0" + bytes.fromhex(digest(source.read_bytes()))
        for source in sources
    )
    recorder = b"".join(
        (repo / "tools" / name).read_bytes()
        for name in (
            "parity_corpus.py",
            "parity_primitives.py",
            "parity_records.py",
        )
    )
    return {
        "source_sha256": digest(identity),
        "recorder_sha256": digest(recorder),
        "python": sys.implementation.cache_tag,
        "unicode": unicodedata.unidata_version,
    }
