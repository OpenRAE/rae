"""Language-service helpers for SDL authoring tools.

The functions in this module are deliberately editor-agnostic.  They expose
completion, reference lookup, formatting, diagnostics, and structured edits as
plain JSON-like dictionaries so MCP tools, CLIs, and future LSP adapters can
share one implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from raes_contracts.errors import InvalidInputError
from raes_contracts.json_pointer import pointer_tokens

from ._base import is_variable_ref
from ._composition_budget import CompositionTraversal
from ._declarations import DeclarationIndex, preferred_spelling
from ._errors import SDLParseError, SDLValidationError
from ._language_context import (
    SECTION_FIELDS,
    DocumentContext,
    PurposeResolver,
    document_context,
    endpoint_purposes,
    load_completion_data,
    reference_context,
)
from ._language_diagnostics import diagnostic as _diagnostic
from ._language_diagnostics import invalid as _invalid
from ._language_diagnostics import parse_error as _parse_error
from ._language_edit import apply_edit
from ._language_metadata import (
    RELATIONSHIP_ENDPOINT_DOMAIN,
    SECTION_FIELD_COMPLETIONS,
    VARIATION_SLOT_TARGETS,
    reference_completion_target,
)
from ._language_references import find_references
from ._language_relationship_candidates import filter_relationship_candidates
from ._language_structural_variation import inventory_reference_candidates, inventory_reference_scope
from ._reference_targetability import ReferencePurpose, purposes_for_domain, reference_domain
from ._relationship_endpoint_policy import relationship_endpoint_purposes
from ._source_profile import DEFAULT_PARSER_LIMITS
from .agents import Agent
from .formatting import format_sdl_source
from .parser import _load_normalized_data, parse_sdl
from .participant_behavior_specification import ParticipantBehaviorSpecification
from .scenario import Scenario, ScenarioContent

_MAX_INPUT_BYTES = 64 * 1024
_SUCCESS_COMPLETION_TARGETS = {"conditions": "conditions"}
# Participant-relationship refinements that validation keeps within what endpoints hold:
# field -> (endpoint fields, participant field, purpose of that participant field).
_ENDPOINT_BOUNDED_REFINEMENTS = {
    "scope_refs": (("source", "target"), "operating_scope", ReferencePurpose.OPERATING_SCOPE),
    "authority_basis_refs": (("source",), "authority_anchors", ReferencePurpose.AUTHORITY_ANCHOR),
}
_TOP_LEVEL_KEYS = tuple(Scenario.model_fields)


def language_completions(
    sdl_content: str,
    *,
    cursor_path: str = "",
    prefix: str = "",
    path: Path | None = None,
) -> dict[str, Any]:
    """Return completion items for a JSON-pointer-like SDL location.

    With *path*, local imports resolve first, as in ``parse_sdl_file()``, so imported
    declarations are offered under their namespaces; registry imports are not fetched.
    """
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    data, error = load_completion_data(sdl_content)
    if error is not None:
        return error
    document = document_context(data, path)
    data = document.data

    pointer = _split_pointer_or_empty(cursor_path)
    reference_pointer = pointer[:-1] if pointer and pointer[-1].isdecimal() else pointer
    target_section = _completion_target_section(reference_pointer, data)
    if target_section is not None:
        items = _reference_completion_items(
            data,
            target_section,
            pointer=reference_pointer,
            scenario=document.scenario,
            declaration_index=document.declaration_index,
            resolver=document.resolver,
        )
        items = filter_relationship_candidates(
            items, pointer, data, document.scenario, document.partial_scenario, document.resolver
        )
        items = _inventory_completion_items(document, reference_pointer, items)
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


def _inventory_completion_items(
    document: DocumentContext, pointer: list[str], items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    scope = inventory_reference_scope(document.data, pointer)
    if scope is None:
        return items
    candidates = inventory_reference_candidates(document.scenario or document.partial_scenario, scope)
    return [_reference_item(address, address) for address in sorted(candidates)]


def language_references(sdl_content: str, symbol: str, *, path: Path | None = None) -> dict[str, Any]:
    """Return definition and occurrence locations for an SDL symbol.

    With *path*, local imports resolve first, so a root value is an occurrence of an
    imported declaration when it resolves to exactly that declaration.
    """
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    document = reference_context(sdl_content, path)
    return find_references(
        sdl_content,
        symbol,
        section_fields=SECTION_FIELDS,
        declaration_index=None if document is None else document.declaration_index,
        resolver=None if document is None else document.resolver,
        endpoint_purposes={} if document is None else endpoint_purposes(document.data),
    )


def language_format(sdl_content: str, *, path: Path | None = None) -> dict[str, Any]:
    """Migrate recognized legacy spellings and return canonical SDL YAML."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        result = format_sdl_source(sdl_content, path=path, _traversal=_local_traversal(path))
    except SDLParseError as exc:
        return _parse_error(exc)

    formatted = result.content
    diagnostics = [item.as_dict() for item in result.diagnostics]
    diagnostics.extend(language_diagnostics(formatted, path=path)["diagnostics"])
    status = "formatted" if not diagnostics else "formatted_with_diagnostics"
    return {"status": status, "content": formatted, "diagnostics": diagnostics}


def language_diagnostics(
    sdl_content: str,
    *,
    semantic_validation: bool = True,
    path: Path | None = None,
) -> dict[str, Any]:
    """Parse SDL and return structured diagnostics instead of prose.

    With *path*, local imports compose as in ``parse_sdl_file()``; a registry import
    is refused instead of fetched.
    """
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        parse_sdl(
            sdl_content,
            path=path,
            skip_semantic_validation=not semantic_validation,
            _traversal=_local_traversal(path),
        )
    except SDLParseError as exc:
        return _parse_error(exc)
    except SDLValidationError as exc:
        return {
            "status": "invalid",
            "stage": "semantic_validation",
            "diagnostics": [
                exc.diagnostics[index].as_dict()
                if index < len(exc.diagnostics) and exc.diagnostics[index] is not None
                else _diagnostic("semantic_validation", "sdl.semantic", message)
                for index, message in enumerate(exc.errors)
            ],
        }

    return {"status": "valid", "stage": "semantic_validation" if semantic_validation else "parse", "diagnostics": []}


def apply_structured_edit(
    sdl_content: str,
    *,
    operation: str,
    pointer: str,
    value: Any = None,
    path: Path | None = None,
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
    except InvalidInputError as exc:
        return _invalid("edit", "sdl.edit", str(exc))

    content = yaml.safe_dump(
        edited,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
    )
    diagnostics = language_diagnostics(content, path=path)["diagnostics"]
    status = "edited" if not diagnostics else "edited_with_diagnostics"
    return {"status": status, "content": content, "diagnostics": diagnostics}


def _completion_target_section(pointer: list[str], data: dict[str, Any]) -> str | None:
    if len(pointer) < 3:
        return None
    if inventory_reference_scope(data, pointer) is not None:
        return "targetable"
    target = reference_completion_target(pointer, pointer[-1])
    if target == RELATIONSHIP_ENDPOINT_DOMAIN and len(pointer) == 3:
        target = reference_domain(relationship_endpoint_purposes(_entry(data, "relationships", pointer[1]), pointer[2]))
    elif pointer[0] == "variation_points" and pointer[-1] in VARIATION_SLOT_TARGETS:
        target = VARIATION_SLOT_TARGETS[pointer[-1]].get(_variation_slot(data, pointer[1]), target)
    elif target is None and len(pointer) >= 4 and pointer[-2] == "success":
        target = _SUCCESS_COMPLETION_TARGETS.get(pointer[-1])
    return target


def _entry(data: dict[str, Any], section: str, name: str) -> dict[str, Any]:
    entries = data.get(section)
    entry = entries.get(name) if isinstance(entries, dict) else None
    return entry if isinstance(entry, dict) else {}


def _variation_slot(data: dict[str, Any], name: str) -> str:
    """Return the authored target slot of a variation point, even in an incomplete document."""

    target = _entry(data, "variation_points", name).get("target")
    slot = target.get("slot") if isinstance(target, dict) else None
    return slot if isinstance(slot, str) else ""


def _reference_item(label: str, detail: str) -> dict[str, str]:
    return {"label": label, "kind": "reference", "detail": detail, "insert_text": label}


def _sorted_items(items: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(items, key=lambda item: (item["detail"], item["label"]))


def _reference_completion_items(
    data: dict[str, Any],
    target_section: str,
    *,
    pointer: list[str],
    scenario: ScenarioContent | None,
    declaration_index: DeclarationIndex | None,
    resolver: PurposeResolver,
) -> list[dict[str, str]]:
    purposes = purposes_for_domain(target_section)
    if purposes is not None:
        return _purpose_completion_items(purposes, pointer=pointer, scenario=scenario, resolver=resolver)
    if target_section == "workflow_steps":
        return _workflow_step_completion_items(data)
    section_data = data.get(target_section)
    names = section_data if isinstance(section_data, dict) else {}
    return _sorted_items(
        _reference_item(str(name), f"{target_section}.{name}")
        for name in names
        if declaration_index is None or declaration_index.declaration_for(f"{target_section}.{name}") is not None
    )


def _purpose_completion_items(
    purposes: tuple[ReferencePurpose, ...],
    *,
    pointer: list[str],
    scenario: ScenarioContent | None,
    resolver: PurposeResolver,
) -> list[dict[str, str]]:
    """Offer one spelling per eligible declaration that the field's resolver maps to exactly that declaration.

    A declaration must be eligible for every purpose in *purposes*. An incomplete
    document resolves through its partial index, so a bare label is offered only
    when no other indexed declaration in the purposes' resolution domain shares it.
    Operating scopes resolve only in a structurally valid document.
    """

    if purposes == (ReferencePurpose.OPERATING_SCOPE,):
        aliases = resolver.operating_scope
        addresses = {address for candidates in aliases.values() for address in candidates}
        offered = [(preferred_spelling(aliases, address), address) for address in addresses]
    else:
        offered = [
            (spelling, declaration.address) for spelling, declaration in resolver.index.reference_completions(purposes)
        ]
    held = (
        _controller_state_held(pointer, scenario, resolver)
        if pointer[0] == "behavior_specifications"
        else _endpoint_held(pointer, scenario, resolver)
    )
    return _sorted_items(
        _reference_item(spelling, address) for spelling, address in offered if held is None or address in held
    )


def _endpoint_held(pointer: list[str], scenario: ScenarioContent | None, resolver: PurposeResolver) -> set[str] | None:
    """Return what a participant-relationship refinement may name, as validation requires, or None if unbounded.

    An endpoint that does not resolve to one participant, or whose own field is
    still parameterized, bounds nothing, as in validation.
    """

    bound = _ENDPOINT_BOUNDED_REFINEMENTS.get(pointer[-1]) if pointer[0] == "relationships" else None
    if bound is None or scenario is None:
        return None
    relationship = scenario.relationships.get(pointer[1])
    if relationship is None or relationship.participant is None:
        return None
    endpoint_fields, participant_field, purpose = bound
    held: set[str] | None = None
    for endpoint_field in endpoint_fields:
        refs = _endpoint_refs(scenario, resolver, getattr(relationship, endpoint_field), participant_field)
        if refs is None or any(is_variable_ref(ref) for ref in refs):
            continue
        own = {address for ref in refs for address in resolver.resolve(ref, purpose)}
        held = own if held is None else held & own
    return held


def _endpoint_refs(scenario: ScenarioContent, resolver: PurposeResolver, endpoint: str, field: str) -> list[str] | None:
    """Return a participant endpoint's own *field* refs, or None when it names no single participant."""

    candidates = resolver.resolve(endpoint, ReferencePurpose.PARTICIPANT_ENDPOINT)
    declaration = resolver.index.declaration_for(next(iter(candidates))) if len(candidates) == 1 else None
    return None if declaration is None else list(getattr(scenario.agents[declaration.model_tokens[1]], field))


def _controller_state_held(
    pointer: list[str], scenario: ScenarioContent | None, resolver: PurposeResolver
) -> set[str] | None:
    """Apply the controller's authority and the owner/controller scope intersection."""

    if scenario is None or len(pointer) != 6 or pointer[2:4] != ["mixed_control", "controller_states"]:
        return None
    owner = scenario.behavior_specifications.get(pointer[1])
    declaration = None if owner is None else owner.mixed_control
    state = None if declaration is None else declaration.controller_states.get(pointer[4])
    if state is None:
        return None
    controller_ref = declaration.participant_ref if state.controller_ref == "self" else state.controller_ref
    controller = scenario.agents.get(controller_ref)
    return None if controller is None else _controller_state_reference_bounds(owner, controller, pointer[-1], resolver)


def _controller_state_reference_bounds(
    owner: ParticipantBehaviorSpecification, controller: Agent, field: str, resolver: PurposeResolver
) -> set[str] | None:
    if field == "authority_basis_refs":
        return {
            address
            for ref in controller.authority_anchors
            for address in resolver.resolve(ref, ReferencePurpose.AUTHORITY_ANCHOR)
        }
    if field == "scope_refs":
        owner_scope = {
            address
            for ref in owner.authority_scope_refs
            for address in resolver.resolve(ref, ReferencePurpose.AUTHORITY_SCOPE)
        }
        controller_scope = {
            address
            for ref in controller.operating_scope
            for address in resolver.resolve(ref, ReferencePurpose.OPERATING_SCOPE)
        }
        return owner_scope & controller_scope
    return None


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
    except InvalidInputError:
        return []


def _split_pointer(pointer: str) -> list[str]:
    if pointer in {"", "/"}:
        return []
    if not pointer.startswith("/"):
        raise InvalidInputError("pointer must be empty or start with '/'")
    return list(pointer_tokens(pointer))


def _local_traversal(path: Path | None) -> CompositionTraversal | None:
    """Start a fresh local-only composition for one path-mode parse; content-only calls compose nothing."""

    return None if path is None else CompositionTraversal.local_root(DEFAULT_PARSER_LIMITS)


def _size_error(*values: str) -> dict[str, Any] | None:
    size = sum(len(value.encode("utf-8", errors="replace")) for value in values)
    if size <= _MAX_INPUT_BYTES:
        return None
    return _invalid("input", "sdl.input_too_large", f"INPUT TOO LARGE - limit is {_MAX_INPUT_BYTES} bytes.")
