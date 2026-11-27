"""Durable run progress uses the incumbent phase execution and operation ledger."""

from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import PlanScope
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from test_runtime_manager import _full_scenario


def test_durable_run_restores_participant_clock_bindings(tmp_path):
    from dataclasses import replace

    from raes import parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from test_dsl_437_benign_participant_execution import (
        _autonomous_manifest,
        _NativeParticipantRuntime,
        _scenario_yaml,
    )

    scenario = parse_sdl(_scenario_yaml())
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(compile_runtime_model(scenario)),
        participant_runtime=_NativeParticipantRuntime(),
    )
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:clock") as runtime:
        plan = runtime.plan(scenario, run_scope=PlanScope(run_id="clock"))
        for _ in range(3):
            assert runtime.advance_plan(plan, execution_id="clock").state == "progress"
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:clock") as runtime:
        for _ in range(10):
            progress = runtime.advance_plan(plan, execution_id="clock")
            if progress.state != "progress":
                break
        assert progress.state == "succeeded"
        assert runtime._participant_clock_driver is not None
        assert runtime._participant_execution_policies
        assert runtime.read_time_state() == runtime.snapshot.time_model_state


def test_run_progress_survives_restart_without_repeating_completed_effects(tmp_path):
    target = create_stub_target()
    calls = []
    apply = target.provisioner.apply

    def record(plan, snapshot):
        calls.append("provision")
        return apply(plan, snapshot)

    target.provisioner.apply = record
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:one") as runtime:
        plan = runtime.plan(_full_scenario(), run_scope=PlanScope(run_id="one"))
        progress = runtime.advance_plan(plan, execution_id="apply-one")
        assert progress.state == "progress"
        assert calls == ["provision"]
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:one") as runtime:
        for _ in range(10):
            progress = runtime.advance_plan(plan, execution_id="apply-one")
            if progress.state != "progress":
                break
        assert progress.state == "succeeded"
        assert runtime.snapshot.entries
        assert runtime.advance_plan(plan, execution_id="apply-one") == progress
        assert calls == ["provision"]
        assert runtime.destroy().success


def test_failed_module_finalization_cannot_become_success_on_redelivery(monkeypatch):
    from raes_contracts.runtime_state import ApplyResult

    with RuntimeControlPlane(create_stub_target()) as run:
        plan = run.plan(_full_scenario())
        calls = []

        def fail(state):
            calls.append("failed")
            state.failure = ApplyResult(False, run.snapshot)

        monkeypatch.setattr(run, "_finalize_participant_driver_apply", fail)
        for _ in range(10):
            progress = run.advance_plan(plan, execution_id="driver-failure")
            if progress.state != "progress":
                break
        assert progress.state == "failed"
        assert run.advance_plan(plan, execution_id="driver-failure").state == "failed"
        assert calls == ["failed"]
