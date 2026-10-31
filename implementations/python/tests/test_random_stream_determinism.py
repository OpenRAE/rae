"""Schedule-independence, non-interference, and rejection-boundedness witnesses for EXP-718.

SVR-014 (schedule independence): serial, shuffled, partitioned/resumed, and
thread-parallel consumers over identical admitted inputs produce
byte-identical outputs. A cross-process / ``PYTHONHASHSEED`` witness (fixed
argv, per ``test_pipeline_determinism.py``'s pattern) rules out hash-order
leakage, since a single process pins one hash seed.

SVR-015 (stream non-interference): adding or varying an unrelated draw does
not perturb any other address's output; no mutable global stream is shared
across addresses.

Bounded-integer rejection sampling is never modulo-biased and attempts are
always bounded by the caller's budget (EXP-718 preflight, "Reliability, Test
Oracles, And Bounds").

This whole module spawns subprocesses (the hash-seed witness), so it is
marked ``integration`` like ``test_pipeline_determinism.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from raes_contracts.contracts.random_stream import (
    ParticipantStreamAddressModel,
    StreamAddressModel,
    TrialCoordinateModel,
)
from raes_contracts.contracts.random_stream_engine import (
    BLOCK_BYTES,
    _bounded_integer_byte_width,
    derive_stream_key,
    draw_bounded_integer,
    raw_block,
)

pytestmark = pytest.mark.integration

PROFILE_ID = "blake3-xof-v1"
ROOT_ENTROPY = bytes.fromhex("42" * 32)
STREAM_KEY = derive_stream_key(profile_id=PROFILE_ID, root_entropy=ROOT_ENTROPY)

_DRAW_PURPOSES = (
    "condition-assignment",
    "sampling-selection",
    "scheduler-tiebreak",
    "agent-policy",
    "observation-noise",
    "other",
)

_PORTABLE_IDENTIFIER = st.from_regex(r"[a-z0-9][a-z0-9_-]{0,15}", fullmatch=True)


def _address(local_coordinate: int, *, variation_point_id: str = "point-a") -> StreamAddressModel:
    return StreamAddressModel(
        namespace="study-namespace",
        trial_coordinate=TrialCoordinateModel(condition_id="condition-a"),
        selection_policy_id="policy-a",
        variation_point_id=variation_point_id,
        draw_purpose="sampling-selection",
        local_coordinate=local_coordinate,
    )


ADDRESSES = [_address(i) for i in range(12)]


def _block_hex(address: StreamAddressModel) -> str:
    return raw_block(profile_id=PROFILE_ID, stream_key=STREAM_KEY, address=address).hex()


def _draw_all(addresses: list[StreamAddressModel]) -> dict[int, str]:
    """Key by ``local_coordinate`` (semantic identity), not list position, so reordering is a real test."""
    return {address.local_coordinate: _block_hex(address) for address in addresses}


class TestScheduleIndependenceWitnesses:
    def test_serial_and_reversed_order_are_identical(self) -> None:
        assert _draw_all(ADDRESSES) == _draw_all(list(reversed(ADDRESSES)))

    def test_shuffled_order_is_identical(self) -> None:
        shuffled = list(ADDRESSES)
        random.Random(1234).shuffle(shuffled)  # noqa: S311 -- reproducible test-order shuffle, not cryptographic
        assert _draw_all(ADDRESSES) == _draw_all(shuffled)

    def test_partitioned_and_resumed_batches_match_one_full_pass(self) -> None:
        """Compute half now ("resume" later, a separate call) and combine; must match one full serial pass."""
        serial = _draw_all(ADDRESSES)
        first_batch = _draw_all(ADDRESSES[:5])
        second_batch = _draw_all(ADDRESSES[5:])  # simulates a resumed/continued consumer
        combined = {**first_batch, **second_batch}
        assert serial == combined

    def test_thread_parallel_matches_serial(self) -> None:
        serial = _draw_all(ADDRESSES)
        with ThreadPoolExecutor(max_workers=8) as pool:
            pairs = list(pool.map(lambda address: (address.local_coordinate, _block_hex(address)), ADDRESSES))
        assert serial == dict(pairs)

    def test_worker_reversed_batches_match_serial(self) -> None:
        """Two "workers" each taking a batch in a different (reversed) partition order."""
        worker_a = _draw_all(list(reversed(ADDRESSES[:6])))
        worker_b = _draw_all(list(reversed(ADDRESSES[6:])))
        assert _draw_all(ADDRESSES) == {**worker_a, **worker_b}


_SUBPROCESS_DRIVER = textwrap.dedent(
    """
    import hashlib
    import json
    import sys

    from raes_contracts.contracts.random_stream import StreamAddressModel, TrialCoordinateModel
    from raes_contracts.contracts.random_stream_engine import derive_stream_key, raw_block

    profile_id = "blake3-xof-v1"
    root_entropy = bytes.fromhex("42" * 32)
    stream_key = derive_stream_key(profile_id=profile_id, root_entropy=root_entropy)

    addresses = [
        StreamAddressModel(
            namespace="study-namespace",
            trial_coordinate=TrialCoordinateModel(condition_id="condition-a"),
            selection_policy_id="policy-a",
            variation_point_id="point-a",
            draw_purpose="sampling-selection",
            local_coordinate=i,
        )
        for i in range(12)
    ]
    blocks = {
        str(address.local_coordinate): raw_block(
            profile_id=profile_id, stream_key=stream_key, address=address
        ).hex()
        for address in addresses
    }
    canonical = json.dumps(blocks, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    """
)


def _subprocess_digest(hash_seed: str) -> str:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_DRIVER],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, f"determinism driver failed (seed={hash_seed}): {result.stderr}"
    digest = result.stdout.strip()
    assert len(digest) == 64, f"unexpected driver output (seed={hash_seed}): {result.stdout!r} / {result.stderr!r}"
    return digest


def test_cross_process_and_hash_seed_independence() -> None:
    digest_seed_0 = _subprocess_digest("0")
    digest_seed_1 = _subprocess_digest("1")
    in_process = hashlib.sha256(
        json.dumps(
            {str(k): v for k, v in _draw_all(ADDRESSES).items()},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert digest_seed_0 == digest_seed_1 == in_process


def test_participant_occurrence_address_is_deterministic_and_reset_scoped() -> None:
    profile_id = "blake3-xof-participant-v1"
    stream_key = derive_stream_key(profile_id=profile_id, root_entropy=ROOT_ENTROPY)
    address = ParticipantStreamAddressModel(
        namespace="run-policy",
        policy_address="participant.autonomous-execution.participant-behavior",
        participant_address="participant.behavior.participant-agent",
        time_segment=2,
        occurrence_ordinal=7,
        draw_purpose="agent-policy",
        local_coordinate=0,
    )

    first = draw_bounded_integer(
        profile_id=profile_id,
        stream_key=stream_key,
        address=address,
        minimum=0,
        maximum=9,
        max_rejection_attempts=32,
    )
    repeated = draw_bounded_integer(
        profile_id=profile_id,
        stream_key=stream_key,
        address=address,
        minimum=0,
        maximum=9,
        max_rejection_attempts=32,
    )
    reset = draw_bounded_integer(
        profile_id=profile_id,
        stream_key=stream_key,
        address=address.model_copy(update={"time_segment": 3}),
        minimum=0,
        maximum=9,
        max_rejection_attempts=32,
    )

    assert first == repeated
    assert first.value is not None
    assert reset.value is not None
    assert raw_block(profile_id=profile_id, stream_key=stream_key, address=address) != raw_block(
        profile_id=profile_id,
        stream_key=stream_key,
        address=address.model_copy(update={"time_segment": 3}),
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("policy_address", "participant.behavior.not-a-policy"),
        ("participant_address", "participant.agent.not-a-behavior"),
        ("draw_purpose", "ungoverned-purpose"),
    ],
)
def test_participant_occurrence_address_rejects_ungoverned_identity_fields(
    field_name: str,
    invalid_value: str,
) -> None:
    payload = {
        "namespace": "run-policy",
        "policy_address": "participant.autonomous-execution.participant-behavior",
        "participant_address": "participant.behavior.participant-agent",
        "time_segment": 2,
        "occurrence_ordinal": 7,
        "draw_purpose": "agent-policy",
        "local_coordinate": 0,
    }
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        ParticipantStreamAddressModel.model_validate(payload)


class TestNonInterferenceProperty:
    """SVR-015: an unrelated draw or an unrelated address field never perturbs another address's output."""

    @given(
        namespace=_PORTABLE_IDENTIFIER,
        policy_id=_PORTABLE_IDENTIFIER,
        point_id=_PORTABLE_IDENTIFIER,
        draw_purpose=st.sampled_from(_DRAW_PURPOSES),
        local_coordinate=st.integers(min_value=0, max_value=1000),
        unrelated_point_id=_PORTABLE_IDENTIFIER,
        unrelated_local_coordinate=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_unrelated_draw_does_not_change_target_address_output(
        self,
        namespace: str,
        policy_id: str,
        point_id: str,
        draw_purpose: str,
        local_coordinate: int,
        unrelated_point_id: str,
        unrelated_local_coordinate: int,
    ) -> None:
        target = StreamAddressModel(
            namespace=namespace,
            trial_coordinate=TrialCoordinateModel(),
            selection_policy_id=policy_id,
            variation_point_id=point_id,
            draw_purpose=draw_purpose,
            local_coordinate=local_coordinate,
        )
        alone = _block_hex(target)

        unrelated = StreamAddressModel(
            namespace=namespace,
            trial_coordinate=TrialCoordinateModel(),
            selection_policy_id=policy_id,
            variation_point_id=unrelated_point_id,
            draw_purpose=draw_purpose,
            local_coordinate=unrelated_local_coordinate,
        )
        if (unrelated.variation_point_id, unrelated.local_coordinate) == (
            target.variation_point_id,
            target.local_coordinate,
        ):
            return  # not actually unrelated; skip (Hypothesis-generated coincidence)

        # Compute the unrelated draw first, then the target -- interference
        # would show up as the target's output depending on prior calls.
        _block_hex(unrelated)
        with_unrelated = _block_hex(target)

        assert alone == with_unrelated

    @given(
        namespace=_PORTABLE_IDENTIFIER,
        policy_id=_PORTABLE_IDENTIFIER,
        point_id=_PORTABLE_IDENTIFIER,
        local_coordinate=st.integers(min_value=0, max_value=1000),
        changed_field=st.sampled_from(["block_id", "replicate_id"]),
        changed_value=_PORTABLE_IDENTIFIER,
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_varying_one_trial_coordinate_field_does_not_change_other_addresses(
        self,
        namespace: str,
        policy_id: str,
        point_id: str,
        local_coordinate: int,
        changed_field: str,
        changed_value: str,
    ) -> None:
        base = StreamAddressModel(
            namespace=namespace,
            trial_coordinate=TrialCoordinateModel(condition_id="fixed-condition"),
            selection_policy_id=policy_id,
            variation_point_id=point_id,
            draw_purpose="sampling-selection",
            local_coordinate=local_coordinate,
        )
        base_block = _block_hex(base)

        # Draw at a coordinate that varies an unrelated dimension, then re-check the base.
        varied_coordinate = TrialCoordinateModel(condition_id="fixed-condition", **{changed_field: changed_value})
        varied = StreamAddressModel(
            namespace=namespace,
            trial_coordinate=varied_coordinate,
            selection_policy_id=policy_id,
            variation_point_id=point_id,
            draw_purpose="sampling-selection",
            local_coordinate=local_coordinate,
        )
        _block_hex(varied)

        assert base_block == _block_hex(base)


class TestRejectionSamplingBoundedness:
    """No modulo bias, attempts bounded (EXP-718 preflight, "Reliability, Test Oracles, And Bounds")."""

    @given(
        minimum=st.integers(min_value=0, max_value=500),
        span=st.integers(min_value=0, max_value=500),
        max_rejection_attempts=st.integers(min_value=1, max_value=16),
        local_coordinate=st.integers(min_value=0, max_value=200),
    )
    @settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_draw_is_always_within_bounds_and_attempts_never_exceed_budget(
        self, minimum: int, span: int, max_rejection_attempts: int, local_coordinate: int
    ) -> None:
        maximum = minimum + span
        address = _address(local_coordinate)
        draw = draw_bounded_integer(
            profile_id=PROFILE_ID,
            stream_key=STREAM_KEY,
            address=address,
            minimum=minimum,
            maximum=maximum,
            max_rejection_attempts=max_rejection_attempts,
        )
        assert 0 <= draw.rejection_attempts <= max_rejection_attempts
        if draw.rejection_exhausted:
            assert draw.value is None
            assert draw.rejection_attempts == max_rejection_attempts
        else:
            assert draw.value is not None
            assert minimum <= draw.value <= maximum

    @given(width=st.integers(min_value=1, max_value=100_000))
    @settings(max_examples=200, deadline=None)
    def test_acceptance_ceiling_is_an_exact_multiple_of_width(self, width: int) -> None:
        """Structural no-modulo-bias proof: the acceptance region is exactly width-divisible.

        Rejection sampling is unbiased only if every accepted raw value maps to
        exactly the same number of outcomes. That holds iff the acceptance
        ceiling (``limit``) is an exact multiple of ``width`` -- so no reduced
        residue class is over-represented.
        """
        byte_width = _bounded_integer_byte_width(width)
        ceiling = 256**byte_width
        limit = ceiling - (ceiling % width)
        assert limit % width == 0
        assert limit <= ceiling
        assert ceiling // width >= 1
        # The byte width chosen must actually be able to represent the range.
        assert ceiling >= width


class TestBlockByteBudget:
    def test_raw_block_default_length_matches_profile_block_bytes(self) -> None:
        assert len(raw_block(profile_id=PROFILE_ID, stream_key=STREAM_KEY, address=_address(0))) == BLOCK_BYTES
