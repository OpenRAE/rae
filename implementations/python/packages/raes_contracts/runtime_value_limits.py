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

# Full SDL source and report admission needs a document budget, independent of runtime snapshots.
# Keep scalar and depth limits unchanged; cap recursive document work explicitly.
MATERIALIZATION_VALUE_LIMITS = RUNTIME_SNAPSHOT_VALUE_LIMITS.model_copy(
    update={"max_nodes": 262144, "max_operations": 4 * 262144, "max_members": 65536}
)

# Planner-produced plans carry the document and its compiled authority under a separate aggregate budget.
PLAN_VALUE_LIMITS = RealizationConstraintLimits(
    max_nodes=524288,
    max_operations=4 * 524288,
    max_members=16384,
    max_scalar_bytes=1048576,
    max_total_scalar_bytes=16 * 1048576,
    max_document_scalar_bytes=MATERIALIZATION_MAX_BYTES,
)

# Recursive authority includes scopes, origins and keyed identities in addition to the projected inventory.
# This fixed process-owned profile is shared by compilation, binding, preparation and delivery evaluation.
PLAN_AUTHORITY_LIMITS = RealizationConstraintLimits(
    max_nodes=65536,
    max_operations=1048576,
    max_members=65536,
    max_identity_checks=65536,
    max_scalar_bytes=1048576,
    max_total_scalar_bytes=8 * 1048576,
)
