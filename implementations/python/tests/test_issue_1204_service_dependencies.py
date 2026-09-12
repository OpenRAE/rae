"""Value isolation must not clone injected stateful backend services."""

from dataclasses import dataclass, replace

from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager
from test_dsl_437_benign_participant_execution import _autonomous_manifest, _NativeParticipantRuntime, _scenario_yaml


def test_coordinated_reset_keeps_a_dataclass_service_dependency_by_identity():
    @dataclass(init=False)
    class NativeService(_NativeParticipantRuntime):
        def __deepcopy__(self, memo):
            raise TypeError("A stateful native service must not be cloned.")

    scenario = parse_sdl(_scenario_yaml())
    model = compile_runtime_model(scenario)
    participant = NativeService()
    target = replace(create_stub_target(), manifest=_autonomous_manifest(model), participant_runtime=participant)
    received = []
    reset = target.time_runtime.reset_with_participants

    def checked_reset(clock, replay, service, requests, snapshot):
        assert service is participant
        received.append(service)
        return reset(clock, replay, service, requests, snapshot)

    target.time_runtime.reset_with_participants = checked_reset
    manager = RuntimeManager(target)
    applied = manager.apply(manager.plan(scenario))
    assert applied.success, applied.diagnostics
    policy = next(
        spec.autonomous_execution for spec in model.behavior_specifications.values() if spec.autonomous_execution
    )
    result = manager.reset_time(policy.clock_address)
    assert result.success, result.diagnostics
    assert received == [participant]
