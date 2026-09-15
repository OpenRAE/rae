"""Read-only identity metadata for registered runtime inventory collections."""

from ._runtime_service_families import (
    RUNTIME_SERVICE_FAMILIES as _RUNTIME_SERVICE_FAMILIES,
)
from ._runtime_service_families import (
    RuntimeReferenceChild as _RuntimeReferenceChild,
)
from ._runtime_service_families import (
    RuntimeServiceFamily as _RuntimeServiceFamily,
)


def runtime_inventory_collection_identity(family_key: str, pointer: str = "") -> tuple[str, ...]:
    """Return the registered ID for a source-relative collection pointer.

    The empty pointer addresses the family collection. Nested pointers walk
    numeric member indices and registered child collections, for example
    ``/0/nodes/1/plugins``. Unregistered, malformed or non-collection paths
    return no metadata. This lookup does not decide comparison order or closure.
    """

    family = next((item for item in _RUNTIME_SERVICE_FAMILIES if item.key == family_key), None)
    fields: list[str] = []
    if family is not None:
        identity = _collection_identity(family, pointer)
        if identity is not None:
            fields.append(identity)
    return tuple(fields)


def _collection_identity(family: _RuntimeServiceFamily, pointer: str) -> str | None:
    if not pointer:
        return family.id_field
    tokens = pointer[1:].split("/")
    if not pointer.startswith("/") or len(tokens) % 2:
        return None
    return _nested_collection_identity(family.child_refs, tokens)


def _nested_collection_identity(children: tuple[_RuntimeReferenceChild, ...], tokens: list[str]) -> str | None:
    selected = None
    for index, name in zip(tokens[::2], tokens[1::2], strict=True):
        # Registry field names are literal identifiers: escaped names cannot
        # alias an addressable collection in this contract.
        selected = next((child for child in children if child.collection_name == name), None)
        if not _canonical_index(index) or selected is None:
            return None
        children = selected.children
    return selected.id_field if selected is not None else None


def _canonical_index(index: str) -> bool:
    return index.isascii() and index.isdecimal() and (index == "0" or not index.startswith("0"))
