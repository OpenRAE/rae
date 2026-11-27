"""Structured edit primitives for SDL language-service helpers.

An edit request comes from outside the program, so a refused edit raises
``InvalidInputError`` (ADR-116). A refusal message is a fixed reason. The
caller already has its pointer, and a pointer token is unbounded caller text.
"""

from __future__ import annotations

from collections.abc import MutableMapping, MutableSequence
from typing import Any

from raes_contracts.errors import InvalidInputError
from raes_contracts.json_pointer import array_index, is_array_index_token

_MISSING_SEGMENT = "missing path segment"
_NOT_A_CONTAINER = "path segment does not address a mapping or list"


def apply_edit(
    data: Any,
    *,
    operation: str,
    tokens: list[str],
    value: Any,
) -> Any:
    """Apply a JSON-pointer addressed edit to loaded YAML data."""
    if not tokens:
        if operation != "set":
            raise InvalidInputError("root pointer supports only the set operation")
        return value

    operation = operation.strip().lower()
    if operation not in {"set", "delete", "append"}:
        raise InvalidInputError("operation must be one of: set, delete, append")

    parent = _resolve_parent(data, tokens, create_missing=operation == "set")
    final = tokens[-1]
    if operation == "set":
        _assign_child(parent, final, value)
    elif operation == "delete":
        _delete_child(parent, final)
    elif operation == "append":
        target = _resolve_child(parent, final)
        if not isinstance(target, list):
            raise InvalidInputError("append target is not a list")
        target.append(value)
    return data


def _resolve_parent(data: Any, tokens: list[str], *, create_missing: bool) -> Any:
    current = data
    for index, token in enumerate(tokens[:-1]):
        next_token = tokens[index + 1]
        current = _resolve_path_segment(
            current,
            token,
            next_token=next_token,
            create_missing=create_missing,
        )
    return current


def _resolve_path_segment(
    current: Any,
    token: str,
    *,
    next_token: str,
    create_missing: bool,
) -> Any:
    if isinstance(current, MutableMapping):
        return _resolve_mapping_segment(
            current,
            token,
            next_token=next_token,
            create_missing=create_missing,
        )
    if isinstance(current, MutableSequence):
        return current[_list_index(current, token)]
    raise InvalidInputError(_NOT_A_CONTAINER)


def _resolve_mapping_segment(
    current: MutableMapping[str, Any],
    token: str,
    *,
    next_token: str,
    create_missing: bool,
) -> Any:
    if token not in current:
        if not create_missing:
            raise InvalidInputError(_MISSING_SEGMENT)
        current[token] = [] if is_array_index_token(next_token) else {}
    return current[token]


def _resolve_child(parent: Any, token: str) -> Any:
    if isinstance(parent, MutableMapping):
        if token not in parent:
            raise InvalidInputError(_MISSING_SEGMENT)
        return parent[token]
    if isinstance(parent, MutableSequence):
        return parent[_list_index(parent, token)]
    raise InvalidInputError(_NOT_A_CONTAINER)


def _assign_child(parent: Any, segment: str, value: Any) -> None:
    if isinstance(parent, MutableMapping):
        parent[segment] = value
        return
    if isinstance(parent, MutableSequence):
        if segment == "-":
            parent.append(value)
            return
        parent[_list_index(parent, segment)] = value
        return
    raise InvalidInputError(_NOT_A_CONTAINER)


def _delete_child(parent: Any, segment: str) -> None:
    if isinstance(parent, MutableMapping):
        if segment not in parent:
            raise InvalidInputError(_MISSING_SEGMENT)
        del parent[segment]
        return
    if isinstance(parent, MutableSequence):
        del parent[_list_index(parent, segment)]
        return
    raise InvalidInputError(_NOT_A_CONTAINER)


def _list_index(values: MutableSequence[Any], token: str) -> int:
    if not is_array_index_token(token):
        raise InvalidInputError("list path segment is not a canonical array index")
    index = array_index(token, len(values))
    if index is None:
        raise InvalidInputError("list index is out of range")
    return index
