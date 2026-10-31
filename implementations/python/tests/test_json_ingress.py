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


# Decoder and encoding failures caused by the input are ingress refusals (ADR-116, issue #1678).
@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("[" + "7" * 5000 + "]", "integer-too-long"),
        (b"[-" + b"7" * 5000 + b"]", "integer-too-long"),
        ('["\ud800"]', "invalid-json"),
    ],
)
def test_parse_bounded_json_refuses_input_that_the_decoder_cannot_convert(source: str | bytes, code: str) -> None:
    with pytest.raises(StrictJsonIngressError) as caught:
        parse_bounded_json(source, max_bytes=1_000_000, root="array")

    assert caught.value.code == code


def test_integer_at_the_digit_limit_remains_a_number() -> None:
    import sys

    digits = sys.get_int_max_str_digits()
    assert parse_bounded_json(("[" + "7" * digits + "]").encode(), max_bytes=10_000, root="array") == [
        int("7" * digits)
    ]


def test_parse_bounded_json_refuses_nesting_that_the_decoder_cannot_build(monkeypatch: pytest.MonkeyPatch) -> None:
    import json.decoder

    # The C decoder stops deep input at a depth that depends on the stack size of the host.
    # This test simulates a host whose decoder stops at the fixture depth.
    raw_decode = json.decoder.JSONDecoder.raw_decode

    def limited_raw_decode(self: json.decoder.JSONDecoder, text: str, idx: int = 0) -> tuple[object, int]:
        if "[" * 50_000 in text:
            raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")
        return raw_decode(self, text, idx)

    monkeypatch.setattr(json.decoder.JSONDecoder, "raw_decode", limited_raw_decode)
    with pytest.raises(StrictJsonIngressError) as caught:
        parse_bounded_json("[" * 100_000 + "]" * 100_000, max_bytes=1_000_000, root="array")

    assert caught.value.code == "input-too-deep"
