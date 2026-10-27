"""Exact portable-value costs for immutable history prefixes."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ValueCosts:
    nodes: int = 1
    scalar_bytes: int = 0
    max_scalar_bytes: int = 0
    depth: int = 0
    members: int = 0
    valid: bool = True

    def extend(self, child: ValueCosts, *, key_bytes: int = 0, members: int = 0) -> ValueCosts:
        return ValueCosts(
            self.nodes + child.nodes,
            self.scalar_bytes + child.scalar_bytes + key_bytes,
            max(self.max_scalar_bytes, child.max_scalar_bytes, key_bytes),
            max(self.depth, child.depth + 1),
            max(self.members, child.members, members),
            self.valid and child.valid,
        )


def value_costs(value: object) -> ValueCosts:
    from .immutable_history import EventHistory, HistoryMap

    if isinstance(value, EventHistory):
        return value._costs
    if type(value) in {HistoryMap}:
        cached = getattr(value, "_value_costs", None)
        if cached is not None:
            return cached
    if isinstance(value, (Mapping, list, tuple)):
        result = ValueCosts(members=len(value))
        children = value.items() if isinstance(value, Mapping) else enumerate(value)
        for key, child in children:
            if isinstance(value, Mapping) and not isinstance(key, str):
                return ValueCosts(valid=False)
            key_bytes = len(key.encode("utf-8")) if isinstance(value, Mapping) else 0
            result = result.extend(value_costs(child), key_bytes=key_bytes)
        if type(value) in {HistoryMap}:
            object.__setattr__(value, "_value_costs", result)
        return result
    if isinstance(value, str):
        size = len(value.encode("utf-8"))
    elif type(value) is int:
        size = max(1, (value.bit_length() + 7) // 8)
    elif type(value) in {bool, float, type(None)}:
        size = 8
    else:
        return ValueCosts(valid=False)
    return ValueCosts(
        scalar_bytes=size,
        max_scalar_bytes=size,
        valid=not (isinstance(value, float) and not math.isfinite(value)),
    )


def charge_immutable_history(value: object, depth: int, budget: object) -> bool:
    """Charge an immutable value exactly; fall back to traversal on any failure."""
    from .immutable_history import EventHistory, HistoryMap

    if type(value) not in {EventHistory, HistoryMap}:
        return False
    costs = value_costs(value)
    limits = budget.limits
    if (
        not costs.valid
        or depth + costs.depth > limits.max_depth
        or costs.members > limits.max_members
        or costs.max_scalar_bytes > limits.max_scalar_bytes
        or budget.nodes + costs.nodes > limits.max_nodes
        or budget.operations + costs.nodes > limits.max_operations
        or budget.scalar_bytes + costs.scalar_bytes > limits.max_total_scalar_bytes
    ):
        return False
    budget.nodes += costs.nodes
    budget.operations += costs.nodes
    budget.scalar_bytes += costs.scalar_bytes
    return True
