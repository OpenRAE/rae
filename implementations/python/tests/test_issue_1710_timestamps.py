"""One wall-clock read, one UTC text form and four named timestamp parsers (issue #1710, ADR-118)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from raes_contracts.timestamps import (
    EXPLICIT_OFFSET_TIMESTAMP_ERROR,
    WallClock,
    isoformat_z,
    parse_offset_datetime,
    parse_offset_timestamp_utc,
    parse_rfc3339_datetime,
    parse_timestamp_assuming_utc,
    utc_now,
)


def _offset(value: datetime) -> timedelta | None:
    return value.utcoffset()


# --- Wall clock and UTC text --------------------------------------------------------------------------------


def test_utc_now_reads_an_aware_utc_instant_at_each_call():
    before = datetime.now(UTC)
    instant = utc_now()
    after = datetime.now(UTC)
    assert instant.tzinfo is UTC
    assert before <= instant <= after


def test_wall_clock_is_a_callable_that_returns_a_datetime():
    assert WallClock.__value__ == Callable[[], datetime]


def test_isoformat_z_replaces_the_utc_offset_and_keeps_automatic_precision():
    assert isoformat_z(datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)) == "2024-01-02T03:04:05Z"
    assert isoformat_z(datetime(2024, 1, 2, 3, 4, 5, 6, tzinfo=UTC)) == "2024-01-02T03:04:05.000006Z"
    instant = datetime(2031, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)
    assert isoformat_z(instant) == instant.isoformat().replace("+00:00", "Z")


# --- RFC 3339 (contracts) -----------------------------------------------------------------------------------


def test_rfc3339_parser_accepts_the_governed_grammar_and_keeps_the_offset():
    assert parse_rfc3339_datetime("at", "2024-01-01T00:00:00Z") == datetime(2024, 1, 1, tzinfo=UTC)
    assert parse_rfc3339_datetime("at", "2024-01-01t00:00:00z") == datetime(2024, 1, 1, tzinfo=UTC)
    parsed = parse_rfc3339_datetime("at", "2024-01-01T05:30:00.25+05:30")
    assert _offset(parsed) == timedelta(hours=5, minutes=30)
    assert parsed.microsecond == 250000


def test_rfc3339_parser_rolls_a_valid_leap_second_forward():
    assert parse_rfc3339_datetime("at", "2016-12-31T23:59:60Z") == datetime(2017, 1, 1, tzinfo=UTC)
    shifted = parse_rfc3339_datetime("at", "2017-01-01T05:29:60+05:30")
    assert shifted == datetime(2017, 1, 1, tzinfo=UTC)
    assert _offset(shifted) == timedelta(hours=5, minutes=30)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("2015-12-31T23:59:60Z", "decided_at must use a valid RFC 3339 leap-second instant"),
        ("2024-01-01 00:00:00Z", "decided_at must be a valid RFC 3339 date-time"),
        ("2024-02-30T00:00:00Z", "decided_at must be a valid RFC 3339 date-time"),
        ("2024-01-01T00:00:00", "decided_at must be a valid RFC 3339 date-time"),
        ("2024-01-01", "decided_at must be a valid RFC 3339 date-time"),
    ],
)
def test_rfc3339_parser_refusals_name_the_field(value, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        parse_rfc3339_datetime("decided_at", value)


# --- Explicit offset, normalized to UTC (workflow timeouts) -------------------------------------------------


def test_utc_timestamp_parser_requires_an_offset_and_returns_utc():
    parsed = parse_offset_timestamp_utc("2024-01-01T05:00:00+05:00")
    assert parsed == datetime(2024, 1, 1, tzinfo=UTC)
    assert parsed.tzinfo is UTC
    assert parse_offset_timestamp_utc("2024-01-01T00:00:00Z").tzinfo is UTC


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "2024-01-01T00:00:00",
        "2024-01-01",
        "2024-01-01T00:00:00z",
        "not a time",
        "0001-01-01T00:00:00+01:00",
        5,
        None,
    ],
)
def test_utc_timestamp_parser_refuses_with_one_value_free_message(raw):
    assert EXPLICIT_OFFSET_TIMESTAMP_ERROR == "timestamp must be an ISO-8601 value with an explicit UTC offset"
    with pytest.raises(ValueError, match=f"^{EXPLICIT_OFFSET_TIMESTAMP_ERROR}$") as caught:
        parse_offset_timestamp_utc(raw)
    assert caught.value.__cause__ is None


# --- Explicit offset, offset kept (runtime facts) -----------------------------------------------------------


def test_offset_datetime_parser_accepts_lowercase_z_and_keeps_the_offset():
    assert parse_offset_datetime("2024-01-01T00:00:00z") == datetime(2024, 1, 1, tzinfo=UTC)
    parsed = parse_offset_datetime("2024-01-01T05:00:00+05:00", "observed_at")
    assert _offset(parsed) == timedelta(hours=5)


@pytest.mark.parametrize(("value", "field"), [("2024-01-01T00:00:00", "observed_at"), ("x", "expires_at"), (5, None)])
def test_offset_datetime_parser_refusals_name_the_field_and_not_the_value(value, field):
    name = field or "timestamp"
    arguments = (value,) if field is None else (value, field)
    with pytest.raises(ValueError, match=f"^{name} must be an ISO 8601 date-time with an explicit UTC offset$"):
        parse_offset_datetime(*arguments)


# --- Naive values read as UTC (result-contract diagnostics) -------------------------------------------------


def test_assuming_utc_parser_reads_naive_and_date_only_values_as_utc():
    assert parse_timestamp_assuming_utc("2024-01-01T00:00:00") == datetime(2024, 1, 1, tzinfo=UTC)
    assert parse_timestamp_assuming_utc("2024-01-01") == datetime(2024, 1, 1, tzinfo=UTC)
    assert parse_timestamp_assuming_utc("2024-01-01T00:00:00Z") == datetime(2024, 1, 1, tzinfo=UTC)
    assert _offset(parse_timestamp_assuming_utc("2024-01-01T05:00:00+05:00")) == timedelta(hours=5)


def test_assuming_utc_parser_keeps_the_datetime_error():
    with pytest.raises(ValueError, match="^Invalid isoformat string: 'bad'$"):
        parse_timestamp_assuming_utc("bad")
