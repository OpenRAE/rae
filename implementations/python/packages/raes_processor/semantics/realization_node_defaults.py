"""Typed node defaults for comparison without changing supplied concern values."""

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from pydantic import TypeAdapter
from raes.nodes import Node
from raes_contracts.errors import InvalidInputError
from raes_contracts.planning import PlannedResource, ProvisionOp
from raes_contracts.runtime_state import SnapshotEntry

from .realization_concern_observations import typed_runtime_observation_shape
from .realization_concerns import realization_concern_descriptors


def defaulted_node_payload(resource: ProvisionOp, cache: dict[str, object]) -> object:
    """Cache one comparison projection for all closed concerns on a resource."""

    if resource.address not in cache:
        try:
            cache[resource.address] = with_node_defaults(resource).payload
        except InvalidInputError:
            cache[resource.address] = None
    return cache[resource.address]


def with_node_defaults(
    resource: SnapshotEntry | PlannedResource | ProvisionOp,
) -> SnapshotEntry | PlannedResource | ProvisionOp:
    """Restore typed defaults while retaining validated value commitments.

    A payload without a node specification, or one that the node contract refuses, raises ``InvalidInputError``.
    """

    spec = resource.payload.get("spec")
    if not isinstance(spec, Mapping) or not isinstance(spec.get("node"), Mapping):
        raise InvalidInputError("resource payload has no node specification")
    adapter = TypeAdapter(Node)
    try:
        node = adapter.dump_python(typed_runtime_observation_shape(spec["node"], adapter=adapter), mode="json")
    # The shape helper and the node contract refuse a malformed specification with ValueError (E9).
    except ValueError as exc:
        raise InvalidInputError("node specification does not satisfy the node contract") from exc
    for descriptor in realization_concern_descriptors():
        if descriptor.section == "nodes":
            _restore_supplied_concern(spec["node"], node, descriptor.authored_path)
    return cast(
        "SnapshotEntry | PlannedResource | ProvisionOp",
        replace(resource, payload={**resource.payload, "spec": {**spec, "node": node}}),
    )


def _restore_supplied_concern(original: object, normalized: object, path: tuple[str, ...]) -> None:
    for token in path[:-1]:
        original = original.get(token) if isinstance(original, dict) else None
        normalized = normalized.get(token) if isinstance(normalized, dict) else None
    leaf = path[-1]
    if isinstance(original, dict) and isinstance(normalized, dict) and leaf in original:
        normalized[leaf] = original[leaf]
