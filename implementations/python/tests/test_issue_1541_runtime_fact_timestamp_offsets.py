"""Issue #1541: runtime fact timestamps must carry an explicit UTC offset.

A naive or date-only ``requested_at`` used to be admitted and then made binding raise
``TypeError`` when freshness compared it with offset-aware fact timestamps. The same
happened for a fact version whose ``observed_at`` or ``expires_at`` lost its offset
through a validation bypass (``model_copy``) or a post-append mutation.
"""

from __future__ import annotations

import pytest
from raes_contracts.contracts.runtime_facts import RuntimeFactBindingDisposition
from raes_contracts.errors import InvalidInputError
from raes_runtime.runtime_fact_bindings import RuntimeFactActionDisposition, RuntimeFactBindingPlane
from test_runtime_fact_bindings import (
    _admission,
    _capture_dispatch,
    _host_declaration,
    _host_request,
    _host_version,
)

_OFFSET_RULE = "must be an ISO 8601 date-time with an explicit UTC offset"


@pytest.mark.parametrize(
    "requested_at",
    [
        "2026-07-20T03:02:00",
        "2026-07-20",
        "2026-07-20T03:02:00.123456",
        "not-a-timestamp",
        None,
        1.5,
    ],
)
def test_admission_rejects_requested_at_without_an_offset(requested_at: object) -> None:
    request = _host_request()

    with pytest.raises(ValueError, match=f"^requested_at {_OFFSET_RULE}$") as raised:
        _admission(request, requested_at=requested_at)  # type: ignore[arg-type]

    assert str(requested_at) not in str(raised.value)
    assert raised.value.__context__ is None or raised.value.__suppress_context__


@pytest.mark.parametrize(
    ("requested_at", "expected"),
    [
        ("2026-07-20T03:02:00Z", RuntimeFactBindingDisposition.BOUND),
        ("2026-07-20T03:02:00z", RuntimeFactBindingDisposition.BOUND),
        ("2026-07-20T03:02:00+00:00", RuntimeFactBindingDisposition.BOUND),
        ("2026-07-20T03:02:00-00:00", RuntimeFactBindingDisposition.BOUND),
        ("2026-07-20T08:32:00+05:30", RuntimeFactBindingDisposition.BOUND),
        ("2026-07-19T20:02:00-07:00", RuntimeFactBindingDisposition.BOUND),
        ("2026-07-20T08:40:00+05:30", RuntimeFactBindingDisposition.STALE),
    ],
)
def test_offset_qualified_requested_at_binds_with_offset_correct_freshness(
    requested_at: str,
    expected: RuntimeFactBindingDisposition,
) -> None:
    request = _host_request()
    dispatched: dict[str, object] = {}
    plane = RuntimeFactBindingPlane(
        admissions=[_admission(request, requested_at=requested_at)],
        action_dispatcher=_capture_dispatch(dispatched),
    )
    plane.declare(_host_declaration())
    plane.append(_host_version())

    result = plane.bind_action_inputs(request)

    assert result.events[0].disposition is expected
    assert result.accepted is (expected is RuntimeFactBindingDisposition.BOUND)
    if expected is RuntimeFactBindingDisposition.BOUND:
        assert result.action_disposition is RuntimeFactActionDisposition.BOUND
        assert dispatched == {"input.target.host": "10.0.0.23"}
    else:
        assert dispatched == {}


_NAIVE_FACT_TIMESTAMPS = [
    pytest.param("observed_at", "2026-07-20T03:00:00", id="observed_at-naive"),
    pytest.param("observed_at", "2026-07-20", id="observed_at-date"),
    pytest.param("expires_at", "2026-07-20T03:05:00", id="expires_at-naive"),
    pytest.param("expires_at", "2026-07-20", id="expires_at-date"),
]


@pytest.mark.parametrize(("field_name", "value"), _NAIVE_FACT_TIMESTAMPS)
def test_append_rejects_fact_version_timestamp_without_an_offset(field_name: str, value: str) -> None:
    plane = RuntimeFactBindingPlane(admissions=[_admission(_host_request())])
    plane.declare(_host_declaration())
    forged = _host_version().model_copy(update={field_name: value})

    with pytest.raises(InvalidInputError, match=f"^{field_name} {_OFFSET_RULE}$"):
        plane.append(forged)

    assert plane.history("fact.observed-host") == ()


@pytest.mark.parametrize(("field_name", "value"), _NAIVE_FACT_TIMESTAMPS)
def test_binding_raises_value_error_not_type_error_for_mutated_stored_timestamp(
    field_name: str,
    value: str,
) -> None:
    request = _host_request()
    dispatched: dict[str, object] = {}
    plane = RuntimeFactBindingPlane(
        admissions=[_admission(request)],
        action_dispatcher=_capture_dispatch(dispatched),
    )
    plane.declare(_host_declaration())
    version = _host_version()
    plane.append(version)
    setattr(version, field_name, value)

    with pytest.raises(ValueError, match=f"^{field_name} {_OFFSET_RULE}$"):
        plane.bind_action_inputs(request)

    assert dispatched == {}
