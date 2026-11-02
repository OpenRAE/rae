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


def _file_identity(repo: Path, sources: list[Path]) -> str:
    identity = hashlib.sha256()
    for source in sorted(sources):
        identity.update(source.relative_to(repo).as_posix().encode() + b"\0")
        identity.update(hashlib.sha256(source.read_bytes()).digest())
    return identity.hexdigest()


def reference_identity(repo: Path) -> dict[str, str]:
    """Bind source, dependency locks, all recorder modules and runtime tables."""
    project = repo / "implementations/python"
    return {
        "source_sha256": _file_identity(repo, list((project / "packages").rglob("*.py"))),
        "environment_sha256": _file_identity(repo, [project / "pyproject.toml", project / "uv.lock"]),
        "recorder_sha256": _file_identity(repo, list((repo / "tools").glob("parity*.py"))),
        "python": sys.implementation.cache_tag or "unknown",
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "unicode": unicodedata.unidata_version,
    }
