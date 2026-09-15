"""Language-service helpers for SDL authoring tools.

The functions in this module are deliberately editor-agnostic.  They expose
completion, reference lookup, formatting, diagnostics, and structured edits as
plain JSON-like dictionaries so MCP tools, CLIs, and future LSP adapters can
share one implementation.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import ValidationError

from ._declarations import DeclarationIndex, build_declaration_index
from ._errors import SDLParseError, SDLValidationError
from ._language_diagnostics import diagnostic as _diagnostic
from ._language_diagnostics import invalid as _invalid
from ._language_diagnostics import parse_error as _parse_error
from ._language_edit import apply_edit
from ._language_metadata import REFERENCE_COMPLETION_TARGETS, SECTION_FIELD_COMPLETIONS
from ._language_references import find_references
from ._reference_targetability import is_targetable_section
from .formatting import format_sdl_source
from .parser import _load_normalized_data, parse_sdl
from .scenario import Scenario

_MAX_INPUT_BYTES = 64 * 1024
_SCENARIO_METADATA_FIELDS = frozenset(
    {"name", "version", "description", "semantic_revision", "module", "imports", "realization"}
)
_SECTION_FIELDS = tuple(field for field in Scenario.model_fields if field not in _SCENARIO_METADATA_FIELDS)
_TARGETABLE_SECTION_FIELDS = tuple(field for field in _SECTION_FIELDS if is_targetable_section(field))
_TOP_LEVEL_KEYS = tuple(Scenario.model_fields)


def language_completions(
    sdl_content: str,
    *,
    cursor_path: str = "",
    prefix: str = "",
) -> dict[str, Any]:
    """Return completion items for a JSON-pointer-like SDL location."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    data, error = _load_completion_data(sdl_content)
    if error is not None:
        return error
    declaration_index = _declaration_index_from_data(data)

    pointer = _split_pointer_or_empty(cursor_path)
    target_section = _completion_target_section(pointer)
    if target_section is not None:
        items = _reference_completion_items(data, target_section, declaration_index=declaration_index)
        context = f"reference:{target_section}"
    elif len(pointer) == 1 and pointer[0] in SECTION_FIELD_COMPLETIONS:
        section = pointer[0]
        items = [
            {
                "label": field,
                "kind": "field",
                "detail": f"{section} field",
                "insert_text": f"{field}: ",
            }
            for field in SECTION_FIELD_COMPLETIONS[section]
        ]
        context = f"section:{section}"
    elif len(pointer) <= 1:
        existing = set(data) if isinstance(data, dict) else set()
        items = [
            {
                "label": key,
                "kind": "field",
                "detail": "top-level SDL key",
                "insert_text": f"{key}: ",
            }
            for key in _TOP_LEVEL_KEYS
            if key not in existing
        ]
        context = "top-level"
    else:
        section = pointer[0]
        fields = SECTION_FIELD_COMPLETIONS.get(section, ())
        items = [
            {
                "label": field,
                "kind": "field",
                "detail": f"{section} field",
                "insert_text": f"{field}: ",
            }
            for field in fields
        ]
        context = f"section:{section}"

    filtered = _filter_items(items, prefix)
    return {"status": "ok", "context": context, "items": filtered}


def language_references(sdl_content: str, symbol: str) -> dict[str, Any]:
    """Return definition and occurrence locations for an SDL symbol."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    return find_references(
        sdl_content,
        symbol,
        section_fields=_SECTION_FIELDS,
        declaration_index=_try_declaration_index(sdl_content),
    )


def _try_declaration_index(sdl_content: str) -> DeclarationIndex | None:
    """Return the authoritative index for a complete structural document."""

    try:
        data = _load_normalized_data(sdl_content)
    except SDLParseError:
        return None
    return _declaration_index_from_data(data)


def _declaration_index_from_data(data: dict[str, Any]) -> DeclarationIndex | None:
    try:
        scenario = Scenario.model_validate(data)
    except ValidationError:
        return None
    return build_declaration_index(scenario, raise_on_collision=False)


def language_format(sdl_content: str) -> dict[str, Any]:
    """Migrate recognized legacy spellings and return canonical SDL YAML."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        result = format_sdl_source(sdl_content)
    except SDLParseError as exc:
        return _parse_error(exc)

    formatted = result.content
    diagnostics = [item.as_dict() for item in result.diagnostics]
    diagnostics.extend(language_diagnostics(formatted)["diagnostics"])
    status = "formatted" if not diagnostics else "formatted_with_diagnostics"
    return {"status": status, "content": formatted, "diagnostics": diagnostics}


def language_diagnostics(
    sdl_content: str,
    *,
    semantic_validation: bool = True,
) -> dict[str, Any]:
    """Parse SDL and return structured diagnostics instead of prose."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        parse_sdl(
            sdl_content,
            skip_semantic_validation=not semantic_validation,
        )
    except SDLParseError as exc:
        return _parse_error(exc)
    except SDLValidationError as exc:
        return {
            "status": "invalid",
            "stage": "semantic_validation",
            "diagnostics": [
                _diagnostic(
                    "semantic_validation",
                    "sdl.semantic",
                    message,
                )
                for message in exc.errors
            ],
        }

    return {"status": "valid", "stage": "semantic_validation" if semantic_validation else "parse", "diagnostics": []}


def apply_structured_edit(
    sdl_content: str,
    *,
    operation: str,
    pointer: str,
    value: Any = None,
) -> dict[str, Any]:
    """Apply a structured edit addressed by JSON pointer and revalidate."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        data = _load_normalized_data(sdl_content)
    except SDLParseError as exc:
        return _parse_error(exc)

    try:
        tokens = _split_pointer(pointer)
        edited = apply_edit(data, operation=operation, tokens=tokens, value=value)
    except ValueError as exc:
        return _invalid("edit", "sdl.edit", str(exc))

    content = yaml.safe_dump(
        edited,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
    )
    diagnostics = language_diagnostics(content)["diagnostics"]
    status = "edited" if not diagnostics else "edited_with_diagnostics"
    return {"status": status, "content": content, "diagnostics": diagnostics}


def _load_completion_data(sdl_content: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not sdl_content.strip():
        return {}, None
    try:
        return _load_normalized_data(sdl_content), None
    except SDLParseError as exc:
        return {}, _parse_error(exc)


def _completion_target_section(pointer: list[str]) -> str | None:
    if len(pointer) < 3:
        return None
    section = pointer[0]
    field = pointer[-1]
    target = REFERENCE_COMPLETION_TARGETS.get((section, field))
    if target is not None:
        return target
    if len(pointer) >= 4 and pointer[-2] == "success":
        success_targets = {
            "conditions": "conditions",
        }
        return success_targets.get(field)
    return None


def _reference_completion_items(
    data: dict[str, Any],
    target_section: str,
    *,
    declaration_index: DeclarationIndex | None,
) -> list[dict[str, str]]:
    if declaration_index is not None and target_section in {"any", "targetable"}:
        return sorted(
            (
                {
                    "label": spelling,
                    "kind": "reference",
                    "detail": declaration.address,
                    "insert_text": spelling,
                }
                for spelling, declaration in declaration_index.reference_completions(
                    targetable=target_section == "targetable"
                )
            ),
            key=lambda item: (item["detail"], item["label"]),
        )
    if target_section == "any":
        sections = _SECTION_FIELDS
    elif target_section == "targetable":
        sections = _TARGETABLE_SECTION_FIELDS
    elif target_section == "workflow_steps":
        return _workflow_step_completion_items(data)
    else:
        sections = (target_section,)

    items: list[dict[str, str]] = []
    for section in sections:
        section_data = data.get(section)
        if not isinstance(section_data, dict):
            continue
        for name in section_data:
            detail = f"{section}.{name}"
            if declaration_index is not None and declaration_index.declaration_for(detail) is None:
                continue
            items.append(
                {
                    "label": str(name),
                    "kind": "reference",
                    "detail": detail,
                    "insert_text": str(name),
                }
            )
    return sorted(items, key=lambda item: (item["detail"], item["label"]))


def _workflow_step_completion_items(data: dict[str, Any]) -> list[dict[str, str]]:
    workflows = data.get("workflows")
    if not isinstance(workflows, dict):
        return []
    items: list[dict[str, str]] = []
    for workflow_name, workflow in workflows.items():
        if not isinstance(workflow, dict):
            continue
        steps = workflow.get("steps")
        if not isinstance(steps, dict):
            continue
        for step_name in steps:
            label = str(step_name)
            items.append(
                {
                    "label": label,
                    "kind": "reference",
                    "detail": f"workflows.{workflow_name}.steps.{step_name}",
                    "insert_text": label,
                }
            )
    return sorted(items, key=lambda item: item["detail"])


def _filter_items(items: list[dict[str, str]], prefix: str) -> list[dict[str, str]]:
    if not prefix:
        return items
    return [item for item in items if item["label"].startswith(prefix)]


def _split_pointer_or_empty(pointer: str) -> list[str]:
    if not pointer:
        return []
    try:
        return _split_pointer(pointer)
    except ValueError:
        return []


def _split_pointer(pointer: str) -> list[str]:
    if pointer in {"", "/"}:
        return []
    if not pointer.startswith("/"):
        raise ValueError("pointer must be empty or start with '/'")
    return [_unescape_pointer_token(token) for token in pointer.split("/")[1:]]


def _unescape_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _size_error(*values: str) -> dict[str, Any] | None:
    size = sum(len(value.encode("utf-8", errors="replace")) for value in values)
    if size <= _MAX_INPUT_BYTES:
        return None
    return _invalid("input", "sdl.input_too_large", f"INPUT TOO LARGE - limit is {_MAX_INPUT_BYTES} bytes.")
