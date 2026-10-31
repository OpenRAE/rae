"""Named sorted JSON text variants keep the exact json.dumps bytes (issue #1710, ADR-118)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from raes_contracts.json_serialization import (
    sorted_json_digest,
    sorted_json_text,
    sorted_json_text_finite,
    sorted_json_text_unicode,
    sorted_json_text_unicode_finite,
)

_COMPACT = (",", ":")
_CORPUS = (
    {"b": 1, "a": "é", "c": [1.5, None, True]},
    {"nested": {"z": {"y": " ", "x": "\U0001f600"}}, "n": -0.0},
    ["ordered", {"k": 10**30}, 'tab\tquote"slash\\'],
    {"emoji": "\ud83d", "unicode": "日本"},
    {},
    [],
    "plain",
    12345678901234567890,
)


@pytest.mark.parametrize("value", _CORPUS)
def test_each_variant_is_the_exact_incumbent_json_dumps_call(value):
    assert sorted_json_text(value) == json.dumps(value, sort_keys=True, separators=_COMPACT)
    assert sorted_json_text(value) == json.dumps(value, sort_keys=True, separators=_COMPACT, ensure_ascii=True)
    assert sorted_json_text_finite(value) == json.dumps(value, sort_keys=True, separators=_COMPACT, allow_nan=False)
    assert sorted_json_text_unicode(value) == json.dumps(value, sort_keys=True, separators=_COMPACT, ensure_ascii=False)
    assert sorted_json_text_unicode_finite(value) == json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=_COMPACT
    )


def test_ascii_text_escapes_non_ascii_and_sorts_keys():
    assert sorted_json_text({"b": 1, "a": "é"}) == '{"a":"\\u00e9","b":1}'


def test_unicode_text_keeps_non_ascii_characters():
    assert sorted_json_text_unicode({"b": 1, "a": "é"}) == '{"a":"é","b":1}'


def test_only_the_finite_variants_refuse_nan_and_infinity():
    assert sorted_json_text(float("nan")) == "NaN"
    assert sorted_json_text_unicode(float("-inf")) == "-Infinity"
    infinite = {"x": float("inf")}
    for encode in (sorted_json_text_finite, sorted_json_text_unicode_finite):
        with pytest.raises(ValueError, match="Out of range float values are not JSON compliant"):
            encode(infinite)


def test_conversion_callback_is_explicit():
    amount = {"amount": Decimal("1.5")}
    with pytest.raises(TypeError, match="not JSON serializable"):
        sorted_json_text(amount)
    assert sorted_json_text(amount, default=str) == '{"amount":"1.5"}'
    instant = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert sorted_json_digest({"at": instant}, default=str) == (
        "sha256:" + hashlib.sha256(b'{"at":"2024-01-02 03:04:05+00:00"}').hexdigest()
    )
    assert sorted_json_text_unicode_finite({"v": Decimal("2")}, default=float) == '{"v":2.0}'


def test_digest_hashes_the_utf8_bytes_of_the_ascii_text():
    payload = {"b": [1, 2], "a": "é"}
    expected = "sha256:" + hashlib.sha256(b'{"a":"\\u00e9","b":[1,2]}').hexdigest()
    assert sorted_json_digest(payload) == expected
    assert sorted_json_digest(payload) == "sha256:" + hashlib.sha256(sorted_json_text(payload).encode()).hexdigest()
