"""Shared aggregate bounds for portable runtime snapshots and preparation."""

from .realization_structure import RealizationConstraintLimits

# One admitted materialization document: source snapshot, submitted report or prospective augmentation content.
# It stays below the 8 MiB SDL parser input limit, so a rendered report keeps room to expand and still parse.
MATERIALIZATION_MAX_BYTES = 4 * 1048576

RUNTIME_SNAPSHOT_VALUE_LIMITS = RealizationConstraintLimits(
    max_nodes=65536,
    max_operations=4 * 65536,
    max_members=16384,
    max_scalar_bytes=1048576,
    max_total_scalar_bytes=8 * 1048576,
    max_document_scalar_bytes=MATERIALIZATION_MAX_BYTES,
)

# Planner-produced operation plans and their compiled realization authority. Only the node and operation budgets
# are larger: a released full-size scenario carries about 74,000 authority nodes. Other carriers keep the limits above.
PLAN_VALUE_LIMITS = RealizationConstraintLimits(
    max_nodes=262144,
    max_operations=4 * 262144,
    max_members=16384,
    max_scalar_bytes=1048576,
    max_total_scalar_bytes=8 * 1048576,
    max_document_scalar_bytes=MATERIALIZATION_MAX_BYTES,
)
