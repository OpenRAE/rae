"""Pure symbol/reference-rewriting primitives shared by the rewrite passes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .._base import VARIABLE_TOKEN_RE, is_variable_ref
from .._errors import SDLValidationError
from .._identifiers import QualifiedName
from .._reference_targetability import purpose_for_domain
from ..variation import COLLECTION_TARGET_SPECS, REFERENCE_TARGET_SPECS, TIMING_TARGET_SPECS

_REFERENCE_TARGET_SPECS_BY_VALUE = {slot.value: spec for slot, spec in REFERENCE_TARGET_SPECS.items()}
_COLLECTION_TARGET_SPECS_BY_VALUE = {slot.value: spec for slot, spec in COLLECTION_TARGET_SPECS.items()}
_TIMING_TARGET_SPECS_BY_VALUE = {slot.value: spec for slot, spec in TIMING_TARGET_SPECS.items()}


def _prefix(namespace: str, name: str) -> str:
    return QualifiedName.parse(name).prefixed(namespace).render() if namespace else QualifiedName.parse(name).render()


def _private_prefix(namespace: str, name: str) -> str:
    return QualifiedName.parse(name).prefixed(namespace, private=True).render()


def _maybe_rename(name: str, name_map: Mapping[str, str]) -> str:
    if not name or is_variable_ref(name):
        return name
    return name_map.get(name, name)


def _rewrite_section_ref(name: str, section: str, name_map: Mapping[str, str]) -> str:
    """Rewrite a bare or explicitly section-qualified reference."""

    if not name or is_variable_ref(name):
        return name
    prefix = f"{section}."
    if name.startswith(prefix):
        local_name = name.removeprefix(prefix)
        return f"{prefix}{name_map.get(local_name, local_name)}"
    return name_map.get(name, name)


def _rewrite_node_or_service_ref(name: str, node_map: Mapping[str, str]) -> str:
    """Rewrite a node ref while preserving an optional named-service suffix."""

    if not name or is_variable_ref(name):
        return name
    for local_name, qualified_name in sorted(node_map.items(), key=lambda item: len(item[0]), reverse=True):
        service_prefix = f"nodes.{local_name}.services."
        if name.startswith(service_prefix):
            return f"nodes.{qualified_name}.services.{name.removeprefix(service_prefix)}"
    return _rewrite_section_ref(name, "nodes", node_map)


def _rewrite_stateful_dependency_ref(
    reference: str,
    symbols: dict[str, dict[str, str] | set[str]],
    *,
    owner: str,
) -> str:
    """Rewrite through the resource section that owns the dependency."""

    matching_sections: list[str] = []
    for section in ("generated_artifacts", "persistent_volumes"):
        section_map = symbols[section]
        if not isinstance(section_map, Mapping):
            continue
        if reference.startswith(f"{section}."):
            return _rewrite_section_ref(reference, section, section_map)
        if reference in section_map:
            matching_sections.append(section)

    if len(matching_sections) > 1:
        choices = ", ".join(f"{section}.{reference}" for section in matching_sections)
        raise SDLValidationError([f"{owner} dependency reference {reference!r} is ambiguous; use one of: {choices}"])
    if matching_sections:
        section = matching_sections[0]
        section_map = symbols[section]
        assert isinstance(section_map, Mapping)
        return _rewrite_section_ref(reference, section, section_map)
    return reference


def _rewrite_variation_reference(
    reference: str,
    section: str,
    symbols: dict[str, dict[str, str] | set[str]],
) -> str:
    named = purpose_for_domain(section) is not None
    return _maybe_rename(reference, symbols["named"] if named else symbols[section])


def _variation_slot(target: dict[str, Any]) -> str:
    raw_slot = target.get("slot", "")
    return str(getattr(raw_slot, "value", raw_slot))


def _variation_target_section(kind: object, slot: str) -> str | None:
    spec: tuple[str, str] | None = None
    if kind in {"governed-reference", "alternative"}:
        spec = _REFERENCE_TARGET_SPECS_BY_VALUE.get(slot)
    elif kind in {"subset", "order"}:
        spec = _COLLECTION_TARGET_SPECS_BY_VALUE.get(slot)
    return spec[1] if spec is not None else None


def _rewrite_variable_tokens(value: object, variables: Mapping[str, str]) -> object:
    """Namespace preserved authoring-variable tokens in imported content."""

    rewritten: object
    if isinstance(value, str):
        rewritten = VARIABLE_TOKEN_RE.sub(
            lambda match: "${" + variables.get(match.group(1), match.group(1)) + "}",
            value,
        )
    elif isinstance(value, dict):
        rewritten = {key: _rewrite_variable_tokens(item, variables) for key, item in value.items()}
    elif isinstance(value, list):
        rewritten = [_rewrite_variable_tokens(item, variables) for item in value]
    elif isinstance(value, tuple):
        rewritten = tuple(_rewrite_variable_tokens(item, variables) for item in value)
    else:
        rewritten = value
    return rewritten
