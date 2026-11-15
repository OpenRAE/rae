"""ACT-623 episode policies govern an applied plan, including autonomous clock resets."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_episode_binding import ParticipantEpisodeRuntimeBinding
from test_dsl_437_benign_participant_execution import _autonomous_manifest, _NativeParticipantRuntime, _scenario_yaml
from test_issue_309_episode_runtime_binding import implementation


def _governed_source(control_actions: list[str]) -> str:
    payload = yaml.safe_load(_scenario_yaml())
    payload["behavior_specifications"]["participant-behavior"]["episode_policy"] = {
        "profile": "participant-episode-policy/v1",
        "reset_policy": {
            "control_actions": control_actions,
            "participant_memory_scope": "persistent_across_episodes",
            "evidence_requirement_refs": ["objective-truth-evidence"],
        },
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _selection(participant_address: str, index: int):
    admitted = implementation(name=f"autonomous-{index}")
    return replace(
        admitted,
        selection=admitted.selection.model_copy(update={"participant_address": participant_address}),
    )


def _governed_run(control_actions: list[str]):
    scenario = parse_sdl(_governed_source(control_actions))
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(compile_runtime_model(scenario)),
        participant_runtime=_NativeParticipantRuntime(),
    )
    with RuntimeManager(target) as planner:
        plan = planner.plan(scenario)
    assert plan.is_valid, [(diagnostic.code, diagnostic.message) for diagnostic in plan.diagnostics]
    governed = sorted(
        address
        for policy in plan.model.participant_episode_policies.values()
        for address in policy.participant_addresses
    )
    selections = tuple(_selection(address, index) for index, address in enumerate(governed))
    binding = ParticipantEpisodeRuntimeBinding(model=plan.model, implementations=selections)
    policy = next(
        spec.autonomous_execution for spec in plan.model.behavior_specifications.values() if spec.autonomous_execution
    )
    return target, plan, binding, policy.clock_address


def test_a_governed_plan_applies_only_under_its_exact_installed_binding():
    target, plan, binding, _ = _governed_run(["reset"])

    with RuntimeManager(target) as unbound:
        refused = unbound.apply(plan)
    assert not refused.success
    assert any(
        diagnostic.code == "runtime.participant-episode-binding-unavailable" for diagnostic in refused.diagnostics
    )

    with RuntimeManager(target, participant_episode=binding) as bound:
        applied = bound.apply(plan)
    assert applied.success, applied.diagnostics


def test_a_clock_reset_cannot_reset_an_episode_that_its_policy_does_not_admit():
    target, plan, binding, clock = _governed_run(["restart"])
    calls = []
    reset = target.time_runtime.reset_with_participants

    def observed_reset(*args):
        calls.append(args)
        return reset(*args)

    target.time_runtime.reset_with_participants = observed_reset
    with RuntimeManager(target, participant_episode=binding) as manager:
        assert manager.apply(plan).success
        before = manager.snapshot

        result = manager.reset_time(clock)

        assert not result.success
        assert [diagnostic.code for diagnostic in result.diagnostics] == ["runtime.participant-episode-reset-refused"]
        assert not calls
        assert manager.snapshot == before


@pytest.mark.parametrize("control_actions", [["reset"], ["reset", "restart"]])
def test_a_clock_reset_that_the_policy_admits_keeps_governed_history(control_actions):
    target, plan, binding, clock = _governed_run(control_actions)
    with RuntimeManager(target, participant_episode=binding) as manager:
        assert manager.apply(plan).success

        result = manager.reset_time(clock)

        assert result.success, result.diagnostics
        binding.require_snapshot(manager.snapshot)
