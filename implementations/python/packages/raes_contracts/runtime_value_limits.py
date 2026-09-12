"""Shared aggregate bounds for portable runtime snapshots and preparation."""

from .realization_structure import RealizationConstraintLimits

RUNTIME_SNAPSHOT_VALUE_LIMITS = RealizationConstraintLimits(
    max_nodes=65536,
    max_operations=4 * 65536,
    max_members=16384,
    max_scalar_bytes=1048576,
    max_total_scalar_bytes=8 * 1048576,
)
