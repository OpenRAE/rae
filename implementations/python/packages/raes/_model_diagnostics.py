"""Pydantic-error → SDL-diagnostic rendering for the SDL parser.

Converts a Pydantic :class:`ValidationError` into bounded, source-anchored
:class:`SDLParseError` diagnostics. Kept separate from :mod:`raes.parser`
so the parser module stays focused on loading/normalization; ``parser`` re-imports
these helpers so ``from raes.parser import ...`` call sites remain stable.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ._classification_guard import CLASSIFICATION_MIGRATION_CODE
from ._errors import (
    SDLParseDiagnostic,
    SDLParseError,
    SDLSourcePosition,
    SDLSourceRange,
)
from ._module_declarations import ImportDecl

_IMPORT_DECLARATIONS: TypeAdapter[list[ImportDecl]] = TypeAdapter(list[ImportDecl])


def _dedupe_source_diagnostics(
    diagnostics: list[SDLParseDiagnostic],
) -> list[SDLParseDiagnostic]:
    unique: list[SDLParseDiagnostic] = []
    seen: set[tuple[object, ...]] = set()
    for diagnostic in diagnostics:
        start = diagnostic.primary_range.start
        end = diagnostic.primary_range.end
        key = (
            diagnostic.source,
            diagnostic.code,
            diagnostic.pointer,
            start.line,
            start.column,
            end.line,
            end.column,
        )
        if key not in seen:
            seen.add(key)
            unique.append(diagnostic)
    return unique


def _pointer_from_location(location: tuple[object, ...]) -> str:
    tokens = [str(part) for part in location if str(part) != "[key]"]
    return "".join(f"/{token.replace('~', '~0').replace('/', '~1')}" for token in tokens)


def _nearest_source_range(pointer: str, source_ranges: dict[str, SDLSourceRange]) -> SDLSourceRange:
    candidate = pointer
    while candidate:
        source_range = source_ranges.get(candidate)
        if source_range is not None:
            return source_range
        candidate = candidate.rsplit("/", 1)[0]
    source_range = source_ranges.get("")
    if source_range is not None:
        return source_range
    position = SDLSourcePosition(1, 1)
    return SDLSourceRange(start=position, end=position)


_MODEL_DIAGNOSTIC_MESSAGE_MAX_LENGTH = 512


def _bounded_model_message(message: str) -> str:
    """Render validator-owned prose without Pydantic's input or traceback."""

    if message.startswith("Value error, "):
        message = message.removeprefix("Value error, ")
    escaped = "".join(character if character.isprintable() else f"\\u{ord(character):04x}" for character in message)
    if len(escaped) <= _MODEL_DIAGNOSTIC_MESSAGE_MAX_LENGTH:
        return escaped
    return escaped[: _MODEL_DIAGNOSTIC_MESSAGE_MAX_LENGTH - 3] + "..."


def _field_problems(error: ValidationError) -> str:
    """Render each failure as ``field: message`` with bounded prose and no input values."""

    problems: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = _bounded_model_message(str(item.get("msg", "")))
        problems.append(f"{location}: {message}" if location else message)
    return "; ".join(problems)


def _model_parse_error(
    error: ValidationError,
    *,
    path: Path | None,
    source_ranges: dict[str, SDLSourceRange],
    location_prefix: tuple[str, ...] = (),
) -> SDLParseError:
    diagnostics: list[SDLParseDiagnostic] = []
    for item in error.errors():
        pointer = _pointer_from_location((*location_prefix, *item.get("loc", ())))
        raw_message = str(item.get("msg", ""))
        is_identifier = "portable SDL identifier" in raw_message or "qualified SDL identifier" in raw_message
        message = _bounded_model_message(raw_message)
        code = "sdl.identifier.invalid" if is_identifier else "sdl.model.invalid"
        if item.get("type") == CLASSIFICATION_MIGRATION_CODE:
            code = CLASSIFICATION_MIGRATION_CODE
        diagnostics.append(
            SDLParseDiagnostic(
                code=code,
                message=message,
                pointer=pointer,
                primary_range=_nearest_source_range(pointer, source_ranges),
                source=str(path) if path is not None else None,
            )
        )
    diagnostics = _dedupe_source_diagnostics(diagnostics)
    rendered = "; ".join(f"{diagnostic.pointer or '/'}: {diagnostic.message}" for diagnostic in diagnostics[:8])
    if len(diagnostics) > 8:
        rendered += f", and {len(diagnostics) - 8} more"
    return SDLParseError(
        f"SDL model validation failed at {rendered or '/'}",
        path=path,
        diagnostics=diagnostics,
    )


def _import_declarations(
    data: Mapping[str, object],
    *,
    path: Path | None,
    source_ranges: dict[str, SDLSourceRange],
) -> list[ImportDecl]:
    """Validate a document's ``imports`` as its typed field, failing with field diagnostics.

    Pointers and source ranges match what full-document validation reports for
    the same ``imports`` value, so callers that consume only the declarations
    agree with :func:`raes.parser.parse_sdl` (ADR-053 validation order, step 3).
    """

    if "imports" not in data:
        return []
    try:
        return _IMPORT_DECLARATIONS.validate_python(data["imports"])
    except ValidationError as exc:
        raise _model_parse_error(exc, path=path, source_ranges=source_ranges, location_prefix=("imports",)) from exc
