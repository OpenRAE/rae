"""Owners read the wall clock through an injected callable (issue #1710, ADR-118).

Each test constructs owners with fixed clocks through public constructors and
observes the recorded time. No test patches a module or a private name.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from raes_backend_stubs.manifest import create_stub_manifest
from raes_backend_stubs.stubs import StubOrchestrator, create_stub_components, create_stub_target
from raes_contracts.participant_episode import ParticipantEpisodeInitializeRequest
from raes_contracts.planning import ChangeAction, OrchestrationOp, OrchestrationPlan
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.timestamps import utc_now
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_configuration import ControlPlaneConfiguration
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_maintenance import (
    DestinationConflictPolicy,
    LocalStoreMaintenanceOperation,
    maintain_local_control_plane_store,
)

FIRST = datetime(2031, 2, 3, 4, 5, 6, 789000, tzinfo=UTC)
SECOND = datetime(2032, 7, 8, 9, 10, 11, tzinfo=UTC)


def _fixed(instant: datetime) -> Callable[[], datetime]:
    return lambda: instant


def _audit_times(plane: RuntimeControlPlane) -> list[str]:
    return [event.timestamp for event in plane.audit_log() if event.action == "clock-check"]


def test_configuration_refuses_a_clock_that_is_not_callable():
    with pytest.raises(TypeError, match="^wall_clock must be a callable that returns an aware UTC datetime$"):
        ControlPlaneConfiguration(wall_clock="2031-02-03T04:05:06Z")


def test_the_default_clock_is_the_system_utc_clock():
    plane = RuntimeControlPlane(create_stub_target())
    try:
        assert plane.wall_clock is utc_now
    finally:
        plane.close()


def test_each_control_plane_records_time_from_its_own_clock():
    first = RuntimeControlPlane(create_stub_target(), wall_clock=_fixed(FIRST))
    second = RuntimeControlPlane(create_stub_target(), wall_clock=_fixed(SECOND))
    try:
        for plane in (first, second):
            plane.record_audit(action="clock-check", identity="operator-1710", allowed=True, target="target:stub")
        assert _audit_times(first) == ["2031-02-03T04:05:06.789000Z"]
        assert _audit_times(second) == ["2032-07-08T09:10:11Z"]
    finally:
        first.close()
        second.close()


def test_a_run_inherits_the_clock_of_its_engine():
    clock = _fixed(FIRST)
    plane = RuntimeControlPlane(create_stub_target(), wall_clock=clock)
    try:
        run = plane.open_run(run_scope="run:clock-1710")
        assert run.wall_clock is clock
        run.record_audit(action="clock-check", identity="operator-1710", allowed=True, target="target:stub")
        assert _audit_times(run) == ["2031-02-03T04:05:06.789000Z"]
    finally:
        plane.close()


def test_a_run_cannot_replace_the_clock_of_its_engine():
    clock = _fixed(FIRST)
    plane = RuntimeControlPlane(create_stub_target(), wall_clock=clock)
    try:
        other = _fixed(SECOND)
        with pytest.raises(ValueError, match="^a run cannot replace engine execution configuration$"):
            plane.open_run(run_scope="run:clock-other", wall_clock=other)
        assert plane.open_run(run_scope="run:clock-same", wall_clock=clock).wall_clock is clock
    finally:
        plane.close()


def test_a_scheduler_pass_refuses_an_unknown_keyword():
    from raes_runtime.participant_scheduler import ParticipantScheduler

    snapshot = RuntimeSnapshot()
    with pytest.raises(
        TypeError, match="^ParticipantScheduler.run_due\\(\\) got an unexpected keyword argument 'clock'$"
    ):
        ParticipantScheduler.run_due([], None, None, snapshot, clock=utc_now)


def test_backend_participant_runtime_records_episode_time_from_its_clock():
    components = create_stub_components(manifest=create_stub_manifest(), wall_clock=_fixed(FIRST))
    started = components.participant_runtime.initialize(
        ParticipantEpisodeInitializeRequest(participant_address="participant.red"), RuntimeSnapshot()
    )
    episode = started.snapshot.participant_episode_results["participant.red"]
    assert episode["initialized_at"] == episode["updated_at"] == "2031-02-03T04:05:06.789000Z"


def test_stub_orchestrator_records_workflow_time_from_its_clock():
    plan = OrchestrationPlan(
        operations=[
            OrchestrationOp(
                action=ChangeAction.CREATE, address="orchestration.workflow.w", resource_type="workflow", payload={}
            )
        ]
    )
    result = StubOrchestrator(wall_clock=_fixed(SECOND)).start(plan, RuntimeSnapshot())
    workflow = result.snapshot.orchestration_results["orchestration.workflow.w"]
    assert workflow["started_at"] == workflow["updated_at"] == "2032-07-08T09:10:11Z"


def test_restore_names_the_retained_copy_from_the_maintenance_clock(tmp_path: Path):
    source, backup, restored = tmp_path / "source-store", tmp_path / "backup.sqlite3", tmp_path / "restored-store"
    for path in (source, restored):
        plane = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(path), run_scope="run:ops")
        plane.close()
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.RESTORE,
        store_path=restored,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
        conflict_policy=DestinationConflictPolicy.REPLACE,
        wall_clock=_fixed(FIRST),
    )
    assert [path.name for path in restored.glob("pre-restore-*.sqlite3")] == [
        "pre-restore-20310203040506789000.sqlite3"
    ]
