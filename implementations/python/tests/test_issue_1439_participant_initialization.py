"""Autonomous initialization must respect participant effect authority."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from raes.parser import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager
from test_dsl_437_benign_participant_execution import (
    _autonomous_manifest,
    _NativeParticipantRuntime,
    _scenario_yaml,
)


class _RecordingParticipantRuntime(_NativeParticipantRuntime):
    predecessor: RuntimeSnapshot

    def initialize(self, request, snapshot):
        self.predecessor = deepcopy(snapshot)
        return super().initialize(request, snapshot)


class _WritesSnapshotArgument(_RecordingParticipantRuntime):
    def initialize(self, request, snapshot):
        predecessor = deepcopy(snapshot)
        snapshot.metadata["written_by_initialize"] = True
        result = super().initialize(request, snapshot)
        self.predecessor = predecessor
        return result


class _ErasesAcceptedEntries(_RecordingParticipantRuntime):
    def initialize(self, request, snapshot):
        result = super().initialize(request, snapshot)
        return replace(result, snapshot=result.snapshot.with_entries({}), details={"rejected_candidate": True})


def _apply_with_runtime(runtime: _RecordingParticipantRuntime) -> tuple[RuntimeManager, ApplyResult]:
    scenario = parse_sdl(_scenario_yaml())
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(compile_runtime_model(scenario)),
        participant_runtime=runtime,
    )
    manager = RuntimeManager(target)
    return manager, manager.apply(manager.plan(scenario))


@pytest.mark.parametrize("runtime_type", [_WritesSnapshotArgument, _ErasesAcceptedEntries])
def test_autonomous_initialize_rejects_unauthorized_state_changes(runtime_type) -> None:
    runtime = runtime_type()

    manager, result = _apply_with_runtime(runtime)

    assert not result.success
    assert any(diagnostic.code == "runtime.backend-contract-invalid" for diagnostic in result.diagnostics)
    assert runtime.predecessor.entries
    assert result.snapshot == runtime.predecessor
    assert manager.snapshot == runtime.predecessor
    assert "written_by_initialize" not in manager.snapshot.metadata
    assert "rejected_candidate" not in result.details
    assert not runtime.native_actions
    assert not manager.participant_clock_driver_status()["active"]


def test_autonomous_initialize_accepts_honest_participant_effects() -> None:
    runtime = _RecordingParticipantRuntime()

    manager, result = _apply_with_runtime(runtime)

    assert result.success
    assert result.snapshot == manager.snapshot
    assert runtime.predecessor.entries
    for address, entry in runtime.predecessor.entries.items():
        assert manager.snapshot.entries[address] == entry
    assert manager.snapshot.participant_episode_results
    assert manager.snapshot.participant_episode_history
    assert manager.snapshot.participant_autonomous_execution_states
    assert len(runtime.native_actions) == 1
