"""Read-only identity metadata for registered runtime inventory collections."""

from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES


def runtime_inventory_collection_identity(family_key: str, pointer: str = "") -> tuple[str, ...]:
    """Return the registered ID for a source-relative collection pointer.

    The empty pointer addresses the family collection. Nested pointers walk
    numeric member indices and registered child collections, for example
    ``/0/nodes/1/plugins``. Unregistered, malformed or non-collection paths
    return no metadata. This lookup does not decide comparison order or closure.
    """

    family = next((item for item in RUNTIME_SERVICE_FAMILIES if item.key == family_key), None)
    if family is None:
        return ()
    if not pointer:
        return (family.id_field,)
    if not pointer.startswith("/"):
        return ()
    tokens = pointer[1:].split("/")
    if len(tokens) % 2:
        return ()
    children = family.child_refs
    selected = None
    for index, name in zip(tokens[::2], tokens[1::2], strict=True):
        if not index.isascii() or not index.isdecimal() or (len(index) > 1 and index.startswith("0")):
            return ()
        # Registry field names are literal identifiers: escaped names cannot
        # alias an addressable collection in this contract.
        selected = next((child for child in children if child.collection_name == name), None)
        if selected is None:
            return ()
        children = selected.children
    return (selected.id_field,) if selected is not None else ()
