"""Canonical-vector conformance tests for published EXP-718 BLAKE3 profiles.

Every vector under ``contracts/fixtures/random-stream-vectors/``
was computed independently of ``raes_contracts.contracts.random_stream_engine`` (a
one-off script that calls the ``blake3`` library directly -- see the EXP-718
implementation notes); these tests run the same inputs through the public
reference engine API and assert the outputs match, so the vector tests do not
just test the engine against itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from raes_contracts.contracts.random_stream import (
    PublicSeedModel,
    RandomStreamVectorModel,
    StreamAddressModel,
)
from raes_contracts.contracts.random_stream_engine import (
    canonical_stream_address_bytes,
    decode_public_seed,
    derive_stream_key,
    draw_bounded_integer,
    raw_block,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VECTORS_ROOT = REPO_ROOT / "contracts" / "fixtures" / "random-stream-vectors"


def _load_vectors() -> list[RandomStreamVectorModel]:
    vectors = []
    for path in sorted(VECTORS_ROOT.glob("*/*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        vectors.append(RandomStreamVectorModel.model_validate(payload))
    return vectors


VECTORS = _load_vectors()


def test_vector_corpus_is_non_empty() -> None:
    assert len(VECTORS) >= 7
    assert any(vector.profile_id == "blake3-xof-participant-v1" for vector in VECTORS)


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v.vector_id)
def test_seed_decoding_matches(vector: RandomStreamVectorModel) -> None:
    decoded = decode_public_seed(vector.root_entropy)
    assert decoded.hex() == vector.root_entropy.value


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v.vector_id)
def test_stream_key_derivation_matches(vector: RandomStreamVectorModel) -> None:
    root_entropy = decode_public_seed(vector.root_entropy)
    key = derive_stream_key(profile_id=vector.profile_id, root_entropy=root_entropy)
    assert key.hex() == vector.stream_key_hex


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v.vector_id)
def test_address_canonical_bytes_match(vector: RandomStreamVectorModel) -> None:
    address_bytes = canonical_stream_address_bytes(vector.address)
    assert address_bytes.hex() == vector.address_canonical_bytes_hex


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v.vector_id)
def test_raw_block_matches(vector: RandomStreamVectorModel) -> None:
    root_entropy = decode_public_seed(vector.root_entropy)
    key = derive_stream_key(profile_id=vector.profile_id, root_entropy=root_entropy)
    block = raw_block(profile_id=vector.profile_id, stream_key=key, address=vector.address)
    assert block.hex() == vector.raw_block_hex


@pytest.mark.parametrize("vector", [v for v in VECTORS if v.transform is not None], ids=lambda v: v.vector_id)
def test_bounded_integer_transform_matches(vector: RandomStreamVectorModel) -> None:
    transform = vector.transform
    assert transform is not None
    root_entropy = decode_public_seed(vector.root_entropy)
    key = derive_stream_key(profile_id=vector.profile_id, root_entropy=root_entropy)
    draw = draw_bounded_integer(
        profile_id=vector.profile_id,
        stream_key=key,
        address=vector.address,
        minimum=transform.minimum,
        maximum=transform.maximum,
        max_rejection_attempts=transform.max_rejection_attempts,
    )
    assert draw.rejection_attempts == transform.expected_rejection_attempts
    assert draw.rejection_exhausted == transform.expected_rejection_exhausted
    if transform.expected_rejection_exhausted:
        assert draw.value is None
    else:
        assert transform.outcome is not None
        assert str(draw.value) == transform.outcome.value


def test_zero_heavy_vector_present() -> None:
    assert any("zero" in vector.vector_id for vector in VECTORS)


def test_boundary_single_value_vector_present() -> None:
    boundary = next(v for v in VECTORS if v.vector_id == "bounded-integer-boundary-single-value")
    assert boundary.transform is not None
    assert boundary.transform.minimum == boundary.transform.maximum


def test_exhaustion_vector_present() -> None:
    exhausted = next(v for v in VECTORS if v.vector_id == "bounded-integer-exhaustion")
    assert exhausted.transform is not None
    assert exhausted.transform.expected_rejection_exhausted is True
    assert exhausted.transform.outcome is None


def test_rejection_then_accept_vector_present() -> None:
    rejected_then_accepted = next(v for v in VECTORS if v.vector_id == "bounded-integer-rejection-then-accept")
    assert rejected_then_accepted.transform is not None
    assert rejected_then_accepted.transform.expected_rejection_attempts >= 1
    assert rejected_then_accepted.transform.expected_rejection_exhausted is False


class TestUnsupportedAndMalformedInputsFailClosed:
    def test_derive_stream_key_rejects_unsupported_profile(self) -> None:
        root_entropy = bytes(32)
        with pytest.raises(ValueError, match="unsupported"):
            derive_stream_key(profile_id="not-a-real-profile-v1", root_entropy=root_entropy)

    def test_derive_stream_key_rejects_wrong_length_entropy(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            derive_stream_key(profile_id="blake3-xof-v1", root_entropy=b"\x00" * 10)

    def test_raw_block_rejects_unsupported_profile(self) -> None:
        address = StreamAddressModel.model_validate(
            {
                "namespace": "n",
                "trial_coordinate": {},
                "selection_policy_id": "p",
                "variation_point_id": "v",
                "draw_purpose": "other",
                "local_coordinate": 0,
            }
        )
        stream_key = bytes(32)
        with pytest.raises(ValueError, match="unsupported"):
            raw_block(profile_id="not-a-real-profile-v1", stream_key=stream_key, address=address)

    def test_draw_bounded_integer_rejects_maximum_below_minimum(self) -> None:
        address = StreamAddressModel.model_validate(
            {
                "namespace": "n",
                "trial_coordinate": {},
                "selection_policy_id": "p",
                "variation_point_id": "v",
                "draw_purpose": "other",
                "local_coordinate": 0,
            }
        )
        stream_key = bytes(32)
        with pytest.raises(ValueError, match="maximum"):
            draw_bounded_integer(
                profile_id="blake3-xof-v1",
                stream_key=stream_key,
                address=address,
                minimum=10,
                maximum=1,
                max_rejection_attempts=4,
            )

    def test_decode_public_seed_rejects_wrong_encoding(self) -> None:
        bad_seed = PublicSeedModel.model_construct(kind="public-seed", encoding="hex-fixed-width", value="00" * 32)
        bad_seed.encoding = "not-a-real-encoding"
        with pytest.raises(ValueError, match="encoding"):
            decode_public_seed(bad_seed)
