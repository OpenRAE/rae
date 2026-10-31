"""Caller-supplied SDL source bytes for one consumer parse (ADR-119).

This module owns lexical path confinement for immutable SDL source sets. The
OCI module cache and the consumer parse use the same confinement rule. The
module calls no filesystem, environment, network or process function: each
document has the virtual path ``/<logical path>`` and every path operation is
lexical.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from ._errors import SDLImportError, SDLImportErrorCode

_VIRTUAL_ROOT = Path("/")
_ESCAPE_MESSAGE = "Local import path escapes base directory."


def normalize_bundle_path(base_relative: str, relative: str) -> str:
    """Join one authored relative path to a base directory without leaving the bundle.

    ``base_relative`` is ``"."`` for the bundle root. The result is a canonical
    POSIX path relative to the bundle root.
    """

    normalized = relative.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    invalid_reference = (
        not normalized
        or "\x00" in normalized
        or candidate.is_absolute()
        or (candidate.parts and len(candidate.parts[0]) == 2 and candidate.parts[0][1] == ":")
    )
    if invalid_reference:
        raise SDLImportError(SDLImportErrorCode.PATH_INVALID, _ESCAPE_MESSAGE)
    parts = [] if base_relative == "." else list(PurePosixPath(base_relative).parts)
    for part in candidate.parts:
        if part != "..":
            parts.append(part)
        elif parts:
            parts.pop()
        else:
            raise SDLImportError(SDLImportErrorCode.PATH_INVALID, _ESCAPE_MESSAGE)
    if not parts:
        raise SDLImportError(SDLImportErrorCode.PATH_INVALID, _ESCAPE_MESSAGE)
    return PurePosixPath(*parts).as_posix()


def _canonical_relative(path: str) -> bool:
    parts = path.split("/")
    return (
        bool(path)
        and "\x00" not in path
        and "\\" not in path
        and ":" not in parts[0]
        and all(part not in {"", ".", ".."} for part in parts)
    )


@dataclass(frozen=True)
class SuppliedSources:
    """An immutable copy of the bytes that one consumer parse may read.

    Keys are canonical POSIX paths relative to the source root. Use
    :meth:`capture` to build an instance from a caller mapping.
    """

    documents: Mapping[str, bytes]

    @classmethod
    def capture(cls, sources: Mapping[str, bytes]) -> SuppliedSources:
        """Copy each caller value one time, so later caller changes have no effect."""

        captured: dict[str, bytes] = {}
        for key in sources:
            value = sources[key]
            if not isinstance(key, str) or not isinstance(value, bytes | bytearray | memoryview):
                raise TypeError("SDL sources must map str paths to bytes")
            if not _canonical_relative(key):
                raise SDLImportError(
                    SDLImportErrorCode.PATH_INVALID, "A supplied source path is not a canonical relative path."
                )
            captured[key] = bytes(value)
        return cls(MappingProxyType(captured))

    def root(self, logical: str) -> tuple[Path, bytes]:
        """Return the virtual path and bytes of the root document."""

        if not _canonical_relative(logical):
            raise SDLImportError(SDLImportErrorCode.PATH_INVALID, "The root path is not a canonical relative path.")
        return self._document(logical)

    def resolve(self, *, base_dir: Path, relative: str) -> tuple[Path, bytes]:
        """Return the virtual path and bytes of one import target below ``base_dir``."""

        target = normalize_bundle_path(self._logical(base_dir) or ".", relative)
        return self._document(target)

    def companion(self, directory: Path, name: str) -> bytes | None:
        """Return the bytes of the file ``name`` in ``directory``, such as its lock, when supplied."""

        base = self._logical(directory)
        return self.documents.get(f"{base}/{name}" if base else name)

    @staticmethod
    def relative_identity(target: Path, base_dir: Path) -> str:
        """Return the checkout-independent POSIX path of ``target`` relative to ``base_dir``."""

        # Both virtual paths are absolute, so relpath never reads the current directory.
        return posixpath.relpath(target.as_posix(), base_dir.as_posix())

    def _document(self, logical: str) -> tuple[Path, bytes]:
        data = self.documents.get(logical)
        if data is None:
            raise SDLImportError(SDLImportErrorCode.SOURCE_MISSING, "A supplied source is not in the source set.")
        return _VIRTUAL_ROOT.joinpath(*logical.split("/")), data

    @staticmethod
    def _logical(path: Path) -> str:
        relative = path.as_posix().removeprefix("/")
        if path.as_posix()[:1] != "/" or (relative and not _canonical_relative(relative)):
            raise SDLImportError(SDLImportErrorCode.PATH_INVALID, _ESCAPE_MESSAGE)
        return relative
