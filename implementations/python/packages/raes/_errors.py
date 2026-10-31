"""SDL error types.

Provides structured error reporting for parsing and semantic validation.
SDLValidationError collects all issues from a validation pass rather
than failing on the first error.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from raes_contracts.errors import InvalidInputError


class SDLError(InvalidInputError):
    """Base exception for all SDL operations: authored SDL is not valid input."""


@dataclass(frozen=True)
class SDLSourcePosition:
    """One-based source position."""

    line: int
    column: int

    def as_dict(self) -> dict[str, int]:
        return {"line": self.line, "column": self.column}


@dataclass(frozen=True)
class SDLSourceRange:
    """Half-open source range for one authored token."""

    start: SDLSourcePosition
    end: SDLSourcePosition

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {"start": self.start.as_dict(), "end": self.end.as_dict()}


@dataclass(frozen=True)
class SDLParseDiagnostic:
    """Structured diagnostic produced before SDL model construction."""

    code: str
    message: str
    pointer: str
    primary_range: SDLSourceRange
    authored_keys: tuple[str, str] | None = None
    related_range: SDLSourceRange | None = None
    related_message: str | None = None
    stage: str = "parse"
    severity: str = "error"
    source: str | None = None
    original_pointer: str | None = None
    canonical_address: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": self.stage,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.pointer,
            "range": self.primary_range.as_dict(),
        }
        if self.source is not None:
            payload["source"] = self.source
        if self.original_pointer is not None:
            payload["original_path"] = self.original_pointer
        if self.canonical_address is not None:
            payload["canonical_address"] = self.canonical_address
        if self.authored_keys is not None:
            payload["authored_keys"] = list(self.authored_keys)
        if self.related_range is not None:
            payload["related"] = [
                {
                    "message": self.related_message or "Related authored key.",
                    "range": self.related_range.as_dict(),
                }
            ]
        return payload


class SDLParseError(SDLError):
    """YAML parsing or structural validation failed.

    Attributes:
        path: The file that failed to parse (if applicable).
        details: Detailed error message.
    """

    def __init__(
        self,
        message: str,
        path: Path | None = None,
        *,
        diagnostics: Iterable[SDLParseDiagnostic] = (),
    ) -> None:
        self.path = path
        self.details = message
        self.diagnostics = tuple(diagnostics)
        prefix = f"{path}: " if path else ""
        super().__init__(f"{prefix}{message}")


@dataclass(frozen=True)
class SDLValidationFinding:
    """One semantic validation error and the data that a handler needs (ADR-116 rule E7).

    ``owner`` is the ``(section, name)`` pair of the declaration that the message names first.
    ``section.name`` is the canonical address of that declaration, also for a nested declaration.
    ``pointer`` is the JSON pointer of the authored location, when the validator records it.
    """

    message: str
    owner: tuple[str, str] | None = None
    pointer: str | None = None


class SDLValidationError(SDLError):
    """Semantic validation failed.

    Collects all errors found during a validation pass rather than
    failing on the first one.

    Attributes:
        errors: List of individual error descriptions.
        findings: One finding for each error, in the same order. A plain
            message gives a finding without owner or pointer.
        path: The file that failed validation (if applicable).
    """

    def __init__(self, errors: Sequence[str | SDLValidationFinding], path: Path | None = None) -> None:
        self.findings = tuple(
            error if isinstance(error, SDLValidationFinding) else SDLValidationFinding(error) for error in errors
        )
        self.errors = [finding.message for finding in self.findings]
        self.path = path
        self.diagnostics: tuple[SDLParseDiagnostic | None, ...] = ()
        prefix = f"{path}: " if path else ""
        count = len(self.errors)
        summary = f"{count} validation error{'s' if count != 1 else ''}"
        detail = "\n  ".join(self.errors)
        super().__init__(f"{prefix}{summary}:\n  {detail}")


class SDLInstantiationError(SDLError):
    """Scenario instantiation failed.

    Raised when a parsed scenario cannot be converted into a fully concrete
    instantiated scenario because parameter binding, default application, or
    post-substitution validation failed.
    """

    def __init__(self, errors: list[str], path: Path | None = None) -> None:
        self.errors = errors
        self.path = path
        prefix = f"{path}: " if path else ""
        count = len(errors)
        summary = f"{count} instantiation error{'s' if count != 1 else ''}"
        detail = "\n  ".join(errors)
        super().__init__(f"{prefix}{summary}:\n  {detail}")


class SDLSelectionError(SDLError):
    """A selection, or a selection policy, does not fit the admitted scenario family."""
