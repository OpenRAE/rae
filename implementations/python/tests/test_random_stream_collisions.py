"""Collision-detection tests for the EXP-718 batch-draw operation.

"One bounded operation" is a single ``draw_bounded_integer_batch`` call:
within that call, duplicate semantic coordinates and duplicate canonical
address bytes among the materialized addresses are detected and reported as
one deterministic ``Diagnostic``, with no partial result (per the EXP-718
preflight's "Canonical Inputs, Addresses, And Collision Handling" section and
the acceptance-criteria collision test).
"""

from __future__ import annotations

from raes_contracts.contracts.random_stream import StreamAddressModel
from raes_contracts.contracts.random_stream_engine import (
    BoundedIntegerDrawRequest,
    draw_bounded_integer_batch,
)
from raes_contracts.diagnostics import Severity

PROFILE_ID = "blake3-xof-v1"
STREAM_KEY = bytes(range(32))


def _address(local_coordinate: int, *, variation_point_id: str = "point-a") -> StreamAddressModel:
    return StreamAddressModel.model_validate(
        {
            "namespace": "study-namespace",
            "trial_coordinate": {"condition_id": "condition-a"},
            "selection_policy_id": "policy-a",
            "variation_point_id": variation_point_id,
            "draw_purpose": "sampling-selection",
            "local_coordinate": local_coordinate,
        }
    )


def _request(local_coordinate: int, **kwargs: object) -> BoundedIntegerDrawRequest:
    return BoundedIntegerDrawRequest(
        address=_address(local_coordinate, **kwargs),
        minimum=0,
        maximum=9,
        max_rejection_attempts=32,
    )


class TestNoCollision:
    def test_distinct_addresses_all_succeed(self) -> None:
        requests = [_request(0), _request(1), _request(2)]
        result = draw_bounded_integer_batch(profile_id=PROFILE_ID, stream_key=STREAM_KEY, requests=requests)
        assert result.diagnostic is None
        assert result.draws is not None
        assert len(result.draws) == 3


class TestCollisionDetection:
    def test_duplicate_local_coordinate_and_point_is_a_collision(self) -> None:
        requests = [_request(0), _request(0)]
        result = draw_bounded_integer_batch(profile_id=PROFILE_ID, stream_key=STREAM_KEY, requests=requests)
        assert result.draws is None
        assert result.diagnostic is not None
        assert result.diagnostic.severity == Severity.ERROR
        assert result.diagnostic.domain == "random-stream"

    def test_collision_yields_no_partial_result(self) -> None:
        """A collision anywhere in the batch means NO draws are returned, not the non-colliding subset."""
        requests = [_request(0), _request(1), _request(1)]
        result = draw_bounded_integer_batch(profile_id=PROFILE_ID, stream_key=STREAM_KEY, requests=requests)
        assert result.draws is None
        assert result.diagnostic is not None

    def test_collision_diagnostic_is_bounded_and_safe(self) -> None:
        """The diagnostic never renders raw block bytes, the stream key, or an unbounded domain dump."""
        requests = [_request(0), _request(0)]
        result = draw_bounded_integer_batch(profile_id=PROFILE_ID, stream_key=STREAM_KEY, requests=requests)
        assert result.diagnostic is not None
        message = result.diagnostic.message
        assert len(message) <= 512
        assert STREAM_KEY.hex() not in message

    def test_collision_is_deterministic_across_repeated_calls(self) -> None:
        requests = [_request(0), _request(0)]
        first = draw_bounded_integer_batch(profile_id=PROFILE_ID, stream_key=STREAM_KEY, requests=requests)
        second = draw_bounded_integer_batch(profile_id=PROFILE_ID, stream_key=STREAM_KEY, requests=requests)
        assert first.diagnostic is not None
        assert second.diagnostic is not None
        assert first.diagnostic == second.diagnostic

    def test_same_semantic_coordinate_different_variation_point_is_not_a_collision(self) -> None:
        """Distinguishing dimensions (variation_point_id) genuinely differ, so this is not a collision."""
        requests = [_request(0, variation_point_id="point-a"), _request(0, variation_point_id="point-b")]
        result = draw_bounded_integer_batch(profile_id=PROFILE_ID, stream_key=STREAM_KEY, requests=requests)
        assert result.diagnostic is None
        assert result.draws is not None
        assert len(result.draws) == 2
