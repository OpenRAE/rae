"""Tests for bounded, ambiguity-rejecting portable JSON ingress."""

from __future__ import annotations

import pytest
from raes_contracts.json_ingress import StrictJsonIngressError, parse_bounded_json


def test_parse_bounded_json_accepts_an_explicit_array_root() -> None:
    assert parse_bounded_json(b'[{"event": 1}]', max_bytes=128, root="array") == [{"event": 1}]


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (b'{"member": 1, "member": 2}', "duplicate-member"),
        (b'{"member": NaN}', "non-finite-number"),
        (b'{"member": 1e999}', "non-finite-number"),
        (b'{"member": -1e999}', "non-finite-number"),
        (b"{}", "invalid-root"),
    ],
)
def test_parse_bounded_json_preserves_strict_ingress_failures(source: bytes, code: str) -> None:
    with pytest.raises(StrictJsonIngressError) as caught:
        parse_bounded_json(source, max_bytes=128, root="array")

    assert caught.value.code == code


def test_finite_exponent_remains_a_number() -> None:
    assert parse_bounded_json(b"[1e100]", max_bytes=128, root="array") == [1e100]
