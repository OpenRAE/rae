"""Workflow timeout reconciliation edge cases for the runtime control plane."""

from __future__ import annotations

from datetime import datetime

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import ConflictError, InvalidInputError
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.workflow import WorkflowExecutionState, WorkflowStatus
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_timeouts import (
    INVALID_RECONCILIATION_CLOCK,
    INVALID_TIMEOUT_CONFIGURATION,
    INVALID_WORKFLOW_STATE,
    INVALID_WORKFLOW_TIMESTAMP,
    NON_MONOTONIC_WORKFLOW_CLOCK,
    TIMED_OUT_REASON,
    workflow_timeout_update,
)
from raes_runtime.control_plane_workflows import parse_timestamp

_WORKFLOW_ADDRESS = "orchestration.workflow.response"


def _workflow_entry_with_timeout(timeout_seconds: int) -> SnapshotEntry:
    return SnapshotEntry(
        address=_WORKFLOW_ADDRESS,
        domain=RuntimeDomain.ORCHESTRATION,
        resource_type="workflow",
        payload={"execution_contract": {"timeout_seconds": timeout_seconds}},
    )


def _workflow_entry(timeout_seconds: int = 1) -> SnapshotEntry:
    return SnapshotEntry(
        address=_WORKFLOW_ADDRESS,
        domain=RuntimeDomain.ORCHESTRATION,
        resource_type="workflow",
        payload={"execution_contract": {"timeout_seconds": timeout_seconds}},
    )


def _running_result(started_at: str, updated_at: str | None = None) -> dict[str, object]:
    """Build a persisted RUNNING workflow payload with ``started_at`` as recorded.

    The payload is edited after construction because the model rejects values it
    considers unusable, while reconciliation reads snapshots back through
    ``WorkflowExecutionState.from_payload`` and must cope with whatever the store
    actually holds.
    """

    payload = WorkflowExecutionState(
        workflow_status=WorkflowStatus.RUNNING,
        run_id="run-1",
        started_at="2000-01-01T00:00:00Z",
        updated_at="2000-01-01T00:00:00Z",
    ).to_payload()
    payload["started_at"] = started_at
    payload["updated_at"] = updated_at if updated_at is not None else started_at
    return payload


def _reconcile(
    started_at: str,
    submitted_at: str,
    *,
    updated_at: str | None = None,
    timeout_seconds: object = 1,
    history: dict[str, list[dict[str, object]]] | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]] | None:
    entry = SnapshotEntry(
        address=_WORKFLOW_ADDRESS,
        domain=RuntimeDomain.ORCHESTRATION,
        resource_type="workflow",
        payload={"execution_contract": {"timeout_seconds": timeout_seconds}},
    )
    return workflow_timeout_update(
        RuntimeSnapshot(),
        _WORKFLOW_ADDRESS,
        entry,
        {_WORKFLOW_ADDRESS: _running_result(started_at, updated_at)},
        history if history is not None else {},
        submitted_at,
    )


def test_expired_workflow_is_timed_out():
    update = _reconcile("2000-01-01T00:00:00Z", "2000-01-01T00:01:00Z")

    assert update is not None
    assert update[0]["workflow_status"] == WorkflowStatus.TIMED_OUT.value
    assert update[0]["terminal_reason"] == TIMED_OUT_REASON


def test_workflow_inside_its_deadline_is_left_running():
    assert _reconcile("2000-01-01T00:00:00Z", "2000-01-01T00:00:00Z") is None


def test_workflow_without_a_persisted_result_is_not_timed_out() -> None:
    assert (
        workflow_timeout_update(
            RuntimeSnapshot(),
            _WORKFLOW_ADDRESS,
            _workflow_entry(),
            {},
            {},
            "2000-01-01T00:00:01Z",
        )
        is None
    )


def test_workflow_without_a_declared_timeout_is_not_timed_out() -> None:
    entry = _workflow_entry()
    object.__setattr__(entry, "payload", {"execution_contract": {}})

    assert (
        workflow_timeout_update(
            RuntimeSnapshot(),
            _WORKFLOW_ADDRESS,
            entry,
            {_WORKFLOW_ADDRESS: _running_result("2000-01-01T00:00:00Z")},
            {},
            "2000-01-01T00:00:01Z",
        )
        is None
    )


def test_workflow_at_its_exact_deadline_is_timed_out():
    update = _reconcile("2000-01-01T00:00:00Z", "2000-01-01T00:00:01Z")

    assert update is not None
    assert update[0]["terminal_reason"] == TIMED_OUT_REASON


def test_workflow_with_future_started_at_is_rejected_without_mutation():
    history: dict[str, list[dict[str, object]]] = {}

    with pytest.raises(ConflictError, match=NON_MONOTONIC_WORKFLOW_CLOCK):
        _reconcile("2000-01-01T00:00:01Z", "2000-01-01T00:00:00Z", history=history)

    assert history == {}


def test_workflow_elapsed_time_normalizes_timezone_offsets():
    update = _reconcile("2000-01-01T01:00:00+01:00", "2000-01-01T00:00:01Z")

    assert update is not None
    assert update[0]["terminal_reason"] == TIMED_OUT_REASON


@pytest.mark.parametrize("started_at", ["None", "not-a-timestamp", "2000-13-45T99:99:99Z"])
def test_workflow_with_unparseable_started_at_fails_without_synthesizing_timeout(started_at: str):
    history: dict[str, list[dict[str, object]]] = {}

    with pytest.raises(ConflictError, match=INVALID_WORKFLOW_TIMESTAMP):
        _reconcile(started_at, "2000-01-01T00:01:00Z", history=history)

    assert history == {}


@pytest.mark.parametrize(
    ("started_at", "updated_at"),
    [
        ("2000-01-01", "2000-01-01T00:00:00Z"),
        ("2000-01-01T00:00:00Z", "2000-01-01"),
    ],
)
def test_workflow_timestamps_require_explicit_offsets(started_at: str, updated_at: str):
    with pytest.raises(ConflictError, match=INVALID_WORKFLOW_TIMESTAMP):
        _reconcile(
            started_at,
            "2000-01-02T00:00:00Z",
            updated_at=updated_at,
        )


def test_reconciliation_clock_cannot_precede_latest_persisted_update():
    history: dict[str, list[dict[str, object]]] = {}

    with pytest.raises(ConflictError, match=NON_MONOTONIC_WORKFLOW_CLOCK):
        _reconcile(
            "2000-01-01T00:00:00Z",
            "2000-01-01T00:00:02Z",
            updated_at="2000-01-01T00:00:03Z",
            history=history,
        )

    assert history == {}


def test_updated_at_cannot_precede_started_at():
    with pytest.raises(ConflictError, match=INVALID_WORKFLOW_TIMESTAMP):
        _reconcile(
            "2000-01-01T00:00:01Z",
            "2000-01-01T00:00:02Z",
            updated_at="2000-01-01T00:00:00Z",
        )


def test_enormous_timeout_reports_not_timed_out_instead_of_overflowing():
    """`timeout_seconds` has no declared upper bound, so it must not overflow.

    Folding a very large timeout into a float timestamp or a timedelta raises
    `OverflowError`, which would abort the whole reconciliation pass and surface
    as a 500 from the HTTP adapter.
    """
    update = workflow_timeout_update(
        RuntimeSnapshot(),
        _WORKFLOW_ADDRESS,
        _workflow_entry_with_timeout(10**400),
        {_WORKFLOW_ADDRESS: _running_result("2000-01-01T00:00:00Z")},
        {},
        "2030-01-01T00:00:00Z",
    )

    assert update is None


def test_large_elapsed_span_does_not_round_up_to_an_early_timeout():
    """One microsecond below an integer deadline must remain below it.

    ``timedelta.total_seconds()`` rounds this span to
    ``315537897600.0`` even though its exact whole-second component is one
    second smaller.
    """

    update = workflow_timeout_update(
        RuntimeSnapshot(),
        _WORKFLOW_ADDRESS,
        _workflow_entry_with_timeout(315_537_897_600),
        {_WORKFLOW_ADDRESS: _running_result("0001-01-01T00:00:00Z")},
        {},
        "9999-12-31T23:59:59.999999Z",
    )

    assert update is None


def test_unparseable_reconciliation_clock_is_raised_not_swallowed():
    """A bad caller-supplied ``now`` governs every workflow, so it must surface.

    Reported as ``InvalidInputError``; the HTTP adapter maps that to 409 rather than
    silently disabling timeouts for the whole pass.
    """
    with pytest.raises(InvalidInputError, match=INVALID_RECONCILIATION_CLOCK):
        _reconcile("2000-01-01T00:00:00Z", "not-a-timestamp")


def test_naive_reconciliation_clock_is_rejected():
    with pytest.raises(InvalidInputError, match=INVALID_RECONCILIATION_CLOCK):
        _reconcile("2000-01-01T00:00:00Z", "2000-01-01T00:00:01")


def test_explicit_naive_reconciliation_clock_is_rejected_before_state_mutation() -> None:
    history: dict[str, list[dict[str, object]]] = {}
    snapshot = RuntimeSnapshot()
    entry = _workflow_entry()
    workflow_states = {_WORKFLOW_ADDRESS: _running_result("2000-01-01T00:00:00Z")}
    reconciliation_clock = datetime(2000, 1, 1, 0, 0, 1)

    with pytest.raises(InvalidInputError, match=INVALID_RECONCILIATION_CLOCK):
        workflow_timeout_update(
            snapshot,
            _WORKFLOW_ADDRESS,
            entry,
            workflow_states,
            history,
            "2000-01-01T00:00:01Z",
            reconciliation_clock=reconciliation_clock,
        )

    assert history == {}


@pytest.mark.parametrize("persisted", [[], {"workflow_status": "running"}])
def test_malformed_persisted_workflow_state_fails_closed(persisted: object) -> None:
    snapshot = RuntimeSnapshot()
    entry = _workflow_entry()
    workflow_states: dict[str, dict[str, object]] = {
        _WORKFLOW_ADDRESS: persisted,  # type: ignore[dict-item]
    }

    with pytest.raises(ConflictError, match=INVALID_WORKFLOW_STATE):
        workflow_timeout_update(
            snapshot,
            _WORKFLOW_ADDRESS,
            entry,
            workflow_states,
            {},
            "2000-01-01T00:00:01Z",
        )


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ([], INVALID_TIMEOUT_CONFIGURATION),
        ({"execution_contract": None}, None),
        ({"execution_contract": []}, INVALID_TIMEOUT_CONFIGURATION),
    ],
)
def test_persisted_workflow_timeout_shape_is_validated(
    payload: object,
    expected_error: str | None,
) -> None:
    entry = _workflow_entry()
    object.__setattr__(entry, "payload", payload)

    if expected_error is None:
        assert (
            workflow_timeout_update(
                RuntimeSnapshot(),
                _WORKFLOW_ADDRESS,
                entry,
                {_WORKFLOW_ADDRESS: _running_result("2000-01-01T00:00:00Z")},
                {},
                "2000-01-01T00:00:01Z",
            )
            is None
        )
    else:
        snapshot = RuntimeSnapshot()
        workflow_states = {_WORKFLOW_ADDRESS: _running_result("2000-01-01T00:00:00Z")}

        with pytest.raises(ConflictError, match=expected_error):
            workflow_timeout_update(
                snapshot,
                _WORKFLOW_ADDRESS,
                entry,
                workflow_states,
                {},
                "2000-01-01T00:00:01Z",
            )


@pytest.mark.parametrize("raw", ["", None])
def test_timestamp_parser_rejects_empty_and_non_string_inputs(raw: object) -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        parse_timestamp(raw)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout_seconds", [-1, 0, True, 1.5, "1", "bogus"])
def test_invalid_timeout_configuration_fails_closed(timeout_seconds: object):
    history: dict[str, list[dict[str, object]]] = {}

    with pytest.raises(ConflictError, match=INVALID_TIMEOUT_CONFIGURATION):
        _reconcile(
            "2000-01-01T00:00:00Z",
            "2000-01-01T00:01:00Z",
            timeout_seconds=timeout_seconds,
            history=history,
        )

    assert history == {}


def test_terminal_timeout_reconciliation_is_idempotent():
    history: dict[str, list[dict[str, object]]] = {}
    first = _reconcile(
        "2000-01-01T00:00:00Z",
        "2000-01-01T00:00:01Z",
        history=history,
    )
    assert first is not None
    before = list(first[1])

    repeated = workflow_timeout_update(
        RuntimeSnapshot(),
        _WORKFLOW_ADDRESS,
        _workflow_entry(),
        {_WORKFLOW_ADDRESS: first[0]},
        {_WORKFLOW_ADDRESS: list(first[1])},
        "2000-01-01T00:00:02Z",
    )

    assert repeated is None
    assert first[1] == before


def test_invalid_clock_is_rejected_even_when_control_plane_has_no_workflows():
    control_plane = RuntimeControlPlane(create_stub_target())
    before = control_plane._snapshot

    with pytest.raises(InvalidInputError, match=INVALID_RECONCILIATION_CLOCK):
        control_plane.reconcile_workflow_timeouts(now="not-a-timestamp")

    assert control_plane._snapshot == before


def test_invalid_state_timestamp_cannot_trigger_timeout_compensation():
    entry = SnapshotEntry(
        address=_WORKFLOW_ADDRESS,
        domain=RuntimeDomain.ORCHESTRATION,
        resource_type="workflow",
        payload={
            "execution_contract": {
                "start_step": "run",
                "timeout_seconds": 1,
                "compensation_mode": "automatic",
                "compensation_triggers": ["timed_out"],
                "compensation_targets": {"run": "orchestration.workflow.rollback"},
            }
        },
    )
    original_history = [
        {
            "event_type": "step_completed",
            "timestamp": "2000-01-01T00:00:00Z",
            "step_name": "run",
            "branch_name": None,
            "join_step": None,
            "outcome": "succeeded",
            "details": {},
        }
    ]
    history = {_WORKFLOW_ADDRESS: list(original_history)}
    snapshot = RuntimeSnapshot(entries={_WORKFLOW_ADDRESS: entry})
    workflow_states = {_WORKFLOW_ADDRESS: _running_result("2100-01-01T00:00:00Z")}

    with pytest.raises(ConflictError, match=NON_MONOTONIC_WORKFLOW_CLOCK):
        workflow_timeout_update(
            snapshot,
            _WORKFLOW_ADDRESS,
            entry,
            workflow_states,
            history,
            "2000-01-01T00:00:00Z",
        )

    assert history == {_WORKFLOW_ADDRESS: original_history}
