"""One shared SHA-256 implementation and its renderings (issue #1710, ADR-118)."""

from __future__ import annotations

from raes_contracts.digests import SHA256_PREFIX, sha256_bytes, sha256_digest, sha256_hasher, sha256_hex

# FIPS 180-2 test vectors.
_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_prefix_is_the_sha256_algorithm_label():
    assert SHA256_PREFIX == "sha256:"


def test_hex_digest_matches_the_standard_vectors():
    assert sha256_hex(b"") == _EMPTY
    assert sha256_hex(b"abc") == _ABC


def test_prefixed_digest_adds_the_label_to_the_lowercase_hex_text():
    assert sha256_digest(b"abc") == "sha256:" + _ABC


def test_raw_digest_is_the_32_byte_value():
    assert sha256_bytes(b"abc") == bytes.fromhex(_ABC)


def test_renderings_accept_any_bytes_like_value():
    assert sha256_hex(bytearray(b"abc")) == _ABC
    assert sha256_digest(memoryview(b"abc")) == "sha256:" + _ABC


def test_incremental_hasher_equals_the_one_shot_digest():
    hasher = sha256_hasher()
    for chunk in (b"a", b"", b"bc"):
        hasher.update(chunk)
    assert hasher.hexdigest() == _ABC
    assert hasher.digest() == bytes.fromhex(_ABC)


def test_each_hasher_starts_empty():
    first = sha256_hasher()
    first.update(b"abc")
    assert sha256_hasher().hexdigest() == _EMPTY
