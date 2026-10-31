"""Canonical dispatch ordering for admitted ``trial-coordinate-v1`` entries.

This is the single owning post-serialization order helper for admitted trial
coordinates (SVR-014 schedule independence, SVR-031 scheduler opacity). Both the
processor scheduling policy and the contract-layer receipt validator reuse it so
a recorded dispatch ordinal can be verified against the one canonical order
rather than trusted as a free-form claim. It lives in the contract layer because
the canonical order of an admitted coordinate set is a property of the sealed
plan contract, not of any particular scheduler.
"""

from __future__ import annotations

from typing import Final

from .random_stream import TrialCoordinateModel

#: Width of the zero-padded ordinal in a ``trial-coordinate-v1`` replicate id.
REPLICATE_ID_WIDTH: Final = 6

#: Identity of the single owning canonical coordinate order policy.
CANONICAL_ORDER_POLICY_ID: Final = "trial-coordinate-canonical-v1"


def replicate_ordinal(replicate_id_value: str) -> int:
    """Decode the one-based ordinal from a ``trial-coordinate-v1`` replicate id."""

    suffix = replicate_id_value.removeprefix("replicate-")
    if suffix == replicate_id_value or len(suffix) != REPLICATE_ID_WIDTH or not suffix.isdigit():
        raise ValueError("replicate id is not a trial-coordinate-v1 identifier")
    return int(suffix)


def canonical_coordinate_sort_key(coordinate: TrialCoordinateModel) -> tuple[str, int]:
    """Return the stable ``trial-coordinate-canonical-v1`` dispatch order key.

    Simple allocations order by numeric replicate ordinal; structured
    allocations order by portable ``condition_id`` then numeric replicate
    ordinal. ``block_id`` is deliberately not an ordering dimension of this
    policy: the ``trial-coordinate-v1`` compiler profile populates only
    ``condition_id`` and ``replicate_id`` (spec README), so ordering by block
    would certify a policy other than the published one. A future policy that
    orders by block requires a new canonical-order identifier. Absent dimensions
    sort first. Order never comes from list position, plan-entry map iteration,
    ``plan_entry_id``, queue insertion, worker availability, completion order, or
    a random UUID.
    """

    condition = coordinate.condition_id or ""
    replicate = replicate_ordinal(coordinate.replicate_id) if coordinate.replicate_id is not None else 0
    return (condition, replicate)


__all__ = [
    "CANONICAL_ORDER_POLICY_ID",
    "REPLICATE_ID_WIDTH",
    "canonical_coordinate_sort_key",
    "replicate_ordinal",
]
