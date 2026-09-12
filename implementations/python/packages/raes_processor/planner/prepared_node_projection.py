"""Safe selected-node constraints shared by preparation, delivery and storage."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from pydantic_core import to_jsonable_python
from raes_contracts.canonical import jsonable_fallback
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationNormalizationMetadata,
    RealizationOrigin,
    RealizationRelationStatus,
    evaluate_realization_constraint,
    normalize_realization_literal,
    validate_realization_value,
)
from raes_contracts.runtime_state import RuntimeSnapshot

from ..semantics.realization_concerns import realization_concern_descriptors

_PROFILE = "raes/prepared-portable-node/v1"


def prepared_node_payload_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Use incumbent concern sanitizers; no backend-selected secret becomes authority."""

    if not validate_realization_value(payload, python_carriers=True).conformant:
        raise ValueError("prepared node exceeds its recursive projection bounds")
    projected = deepcopy(payload)
    for descriptor in realization_concern_descriptors():
        current = projected
        for token in descriptor.payload_path[:-1]:
            current = current.get(token) if isinstance(current, dict) else None
        leaf = descriptor.payload_path[-1]
        if isinstance(current, dict) and leaf in current:
            current[leaf] = descriptor.sanitize_observation(current[leaf], recursive=True)
    return to_jsonable_python(projected, fallback=jsonable_fallback)


def _origin_children(value: object) -> Iterable[tuple[object, object]]:
    """Yield the indexed children one projected carrier exposes."""

    if isinstance(value, dict):
        return value.items()
    return enumerate(value) if isinstance(value, list) else ()


def _backend_origins(value: object, path: str = "") -> dict[str, RealizationOrigin]:
    origins = {path: RealizationOrigin.BACKEND}
    for key, child in _origin_children(value):
        token = str(key).replace("~", "~0").replace("/", "~1")
        origins.update(_backend_origins(child, f"{path}/{token}"))
    return origins


def prepared_node_document(payload: Mapping[str, Any]) -> object:
    selected = prepared_node_payload_projection(payload)
    built = normalize_realization_literal(
        selected,
        semantic_profile=_PROFILE,
        default_closure=RealizationClosure(posture="closed", universe="portable-node-value", profile=_PROFILE),
        metadata=RealizationNormalizationMetadata(
            origins=_backend_origins(selected),
        ),
    )
    if built.status is not RealizationRelationStatus.CONFORMANT:
        raise ValueError("prepared node cannot be represented by a bounded recursive completion")
    return built.document


def prepared_additional_node_operations(selected: ProvisioningPlan) -> tuple[ProvisionOp, ...]:
    authority = selected.preparation.node_collection if selected.preparation is not None else None
    if authority is None:
        return ()
    authored_addresses = authority.authored_addresses
    return tuple(
        operation
        for operation in selected.operations
        if operation.address not in authored_addresses
        and operation.resource_type in {"node", "network"}
        and operation.action is not ChangeAction.DELETE
    )


def prepared_node_delivery_violation(selected: ProvisioningPlan, snapshot: RuntimeSnapshot) -> str | None:
    for operation in prepared_additional_node_operations(selected):
        entry = snapshot.entries.get(operation.address)
        if (
            entry is None
            or not evaluate_realization_constraint(
                prepared_node_document(operation.payload),
                prepared_node_payload_projection(entry.payload),
            ).conformant
        ):
            return "Backend did not deliver its admitted portable node completion."
    return None


def sanitize_prepared_node_snapshot(selected: ProvisioningPlan, snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    entries = dict(snapshot.entries)
    for operation in prepared_additional_node_operations(selected):
        entry = entries.get(operation.address)
        if entry is not None:
            entries[operation.address] = replace(entry, payload=prepared_node_payload_projection(entry.payload))
    return snapshot.with_entries(entries)
