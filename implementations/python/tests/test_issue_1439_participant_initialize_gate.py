"""Autonomous participant initialization passes the backend result gate (issue #1439).

The control plane already invokes ``participant_runtime.initialize`` through the
backend result gate with the participant's effect authority. The autonomous
scheduler now does the same, so an episode initialization can neither write the
snapshot it is shown nor drop accepted resources from the apply's state.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager
from test_dsl_437_benign_participant_execution import _autonomous_manifest, _NativeParticipantRuntime, _scenario_yaml

_MARK = "written_by_initialize"


class _WritesItsSnapshotArgument(_NativeParticipantRuntime):
    def initialize(self, request, snapshot):
        snapshot.metadata[_MARK] = True
        return super().initialize(request, snapshot)


class _DropsAcceptedEntries(_NativeParticipantRuntime):
    def initialize(self, request, snapshot):
        result = super().initialize(request, snapshot)
        return replace(result, snapshot=result.snapshot.with_entries({}))


def _apply(participant_runtime):
    scenario = parse_sdl(_scenario_yaml())
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(compile_runtime_model(scenario)),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target)
    return manager, manager.apply(manager.plan(scenario))


def test_honest_episode_initialization_is_admitted():
    manager, result = _apply(_NativeParticipantRuntime())

    assert result.success, [diagnostic.message for diagnostic in result.diagnostics]
    assert manager.snapshot.participant_episode_results


@pytest.mark.parametrize(
    "runtime_class",
    [_WritesItsSnapshotArgument, _DropsAcceptedEntries],
    ids=["writes-snapshot-argument", "drops-accepted-entries"],
)
def test_episode_initialization_cannot_change_state_outside_its_participant(runtime_class):
    honest, _ = _apply(_NativeParticipantRuntime())
    manager, result = _apply(runtime_class())

    assert result.success is False
    assert "runtime.backend-contract-invalid" in {diagnostic.code for diagnostic in result.diagnostics}
    assert _MARK not in manager.snapshot.metadata
    assert manager.snapshot.participant_episode_results == {}
    assert _provisioned(manager) == _provisioned(honest) != set()


def _provisioned(manager) -> set[str]:
    return {address for address in manager.snapshot.entries if address.startswith("provision.")}
