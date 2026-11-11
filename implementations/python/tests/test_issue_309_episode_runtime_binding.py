"""ACT-623 binds real implementation contracts to ADR-013 lifecycle calls."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from raes.parser import parse_sdl_file
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts.participant_manifests import (
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.errors import ConflictError
from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.participant_episode_binding import (
    EPISODE_CONTRACTS,
    ParticipantEpisodeImplementationBinding,
    ParticipantEpisodeRuntimeBinding,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts/fixtures/sdl/participant-episode-policy-v1/valid/standalone-episode-structure.yaml"
MANIFEST = (
    ROOT
    / "contracts/fixtures/participant-implementation-manifest/participant-implementation-manifest-v1/valid/reference.json"
)
PARTICIPANT = "participant.behavior.replayer"


def episode_model():
    return compile_runtime_model(parse_sdl_file(FIXTURE))


def implementation(kind="agent", mode="autonomous", name="reference-red-agent"):
    payload = json.loads(MANIFEST.read_text())
    payload["implementation_kind"] = kind
    payload["identity"]["name"] = name
    payload["capabilities"]["supported_decision_surface_modes"] = [mode]
    manifest = ParticipantImplementationManifestModel.model_validate(payload)
    selection = ParticipantImplementationSelectionModel(
        participant_address=PARTICIPANT,
        implementation_identity=manifest.identity,
        manifest_ref=f"participant-manifest:{name}",
        manifest_digest=canonical_contract_digest(manifest),
        selected_decision_surface_mode=mode,
        participant_contract_versions=sorted(EPISODE_CONTRACTS),
        exposure_policy={
            "policy_id": "episode-evidence",
            "policy_version": "1.0.0",
            "policy_digest": "sha256:" + "3" * 64,
            "exposure_policy_kinds": ["task-statement"],
            "disclosed_refs": ["scenario.tasks.replay"],
        },
    )
    return ParticipantEpisodeImplementationBinding(manifest=manifest, selection=selection)


def runtime_binding(**implementation_options):
    return ParticipantEpisodeRuntimeBinding(
        model=episode_model(), implementations=(implementation(**implementation_options),)
    )


@pytest.mark.parametrize(
    ("kind", "mode", "name"),
    [
        ("agent", "autonomous", "autonomous-agent"),
        ("human-control-proxy", "human-control-proxy", "human-participant"),
        ("script", "scripted", "scripted-participant"),
        ("policy", "policy-directed", "policy-participant"),
        ("agent", "policy-directed", "rl-participant"),
        ("agent", "autonomous", "llm-participant"),
    ],
)
def test_implementation_kinds_run_the_bound_episode_lifecycle(kind, mode, name):
    binding = runtime_binding(kind=kind, mode=mode, name=name)
    with RuntimeControlPlane(create_stub_target(), participant_episode=binding) as plane:
        initialized = plane.initialize_participant_episode(PARTICIPANT)
        first = plane.snapshot.participant_episode_results[PARTICIPANT]
        reset = plane.reset_participant_episode(PARTICIPANT)
        following = plane.snapshot.participant_episode_results[PARTICIPANT]
        terminal = plane.terminate_participant_episode(
            PARTICIPANT, terminal_reason=ParticipantEpisodeTerminalReason.TIMED_OUT
        )
        assert all(
            plane.get_operation(receipt.operation_id).state.value == "succeeded"
            for receipt in (initialized, reset, terminal)
        )
        assert first["participant_address"] == following["participant_address"] == PARTICIPANT
        assert following["previous_episode_id"] == first["episode_id"]
        assert following["episode_id"] != first["episode_id"]
        assert following["sequence_number"] == first["sequence_number"] + 1


@pytest.mark.parametrize("operation", ["restart", "completed"])
def test_disallowed_episode_operations_never_call_the_backend(operation, monkeypatch):
    binding = runtime_binding()
    target = create_stub_target()
    with RuntimeControlPlane(target, participant_episode=binding) as plane:
        plane.initialize_participant_episode(PARTICIPANT)
        if operation == "restart":
            plane.terminate_participant_episode(PARTICIPANT, terminal_reason=ParticipantEpisodeTerminalReason.TIMED_OUT)
        before = plane.snapshot
        calls = []
        method = "restart" if operation == "restart" else "terminate"
        monkeypatch.setattr(target.participant_runtime, method, lambda *args: calls.append(args))
        receipt = (
            plane.restart_participant_episode(PARTICIPANT)
            if operation == "restart"
            else plane.terminate_participant_episode(
                PARTICIPANT, terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED
            )
        )
        assert plane.get_operation(receipt.operation_id).state.value == "failed"
        assert not calls
        assert plane.snapshot == before


def test_episode_binding_rejects_ambiguous_or_missing_implementation_selections():
    admitted = implementation()
    model = episode_model()
    for selections in [(), (admitted, admitted)]:
        with pytest.raises(ValueError, match="one (implementation|policy)"):
            ParticipantEpisodeRuntimeBinding(model=model, implementations=selections)


def test_episode_binding_rejects_unsupported_contracts_and_forged_manifest_digest():
    admitted = implementation()
    for changes in [
        {"participant_contract_versions": ["participant-decision-surface-v2"]},
        {"manifest_digest": "sha256:" + "0" * 64},
    ]:
        selection = admitted.selection.model_copy(update=changes)
        with pytest.raises(ValueError, match="episode|manifest"):
            ParticipantEpisodeImplementationBinding(manifest=admitted.manifest, selection=selection)


def test_episode_binding_rejects_substituted_compiler_policy():
    model = episode_model()
    address, policy = next(iter(model.participant_episode_policies.items()))
    model.participant_episode_policies[address] = replace(policy, reset_control_actions=("reset", "restart"))
    admitted = implementation()
    with pytest.raises(ValueError, match="original compiler context"):
        ParticipantEpisodeRuntimeBinding(model=model, implementations=(admitted,))


def test_episode_binding_rejects_a_target_without_participant_runtime():
    target = create_stub_target(with_participant_runtime=False)
    binding = runtime_binding()
    with pytest.raises(ValueError, match="installed participant runtime"):
        RuntimeControlPlane(target, participant_episode=binding)


def test_episode_aggregate_requires_its_installed_binding():
    model = episode_model()
    target = create_stub_target()
    with pytest.raises(ValueError, match="installed participant episode binding"):
        RuntimeControlPlane(target, behavior_specifications=model.behavior_specifications)


def test_restored_history_must_agree_with_the_installed_episode_policy():
    with RuntimeControlPlane(create_stub_target()) as unbound:
        unbound.initialize_participant_episode(PARTICIPANT)
        unbound.terminate_participant_episode(PARTICIPANT, terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED)
        snapshot = unbound.snapshot
    target = create_stub_target()
    binding = runtime_binding()
    with pytest.raises(ConflictError, match="recorded participant episodes"):
        RuntimeControlPlane(target, initial_snapshot=snapshot, participant_episode=binding)


def test_planner_authorization_requires_the_exact_installed_episode_model():
    from raes_processor.reference import run_reference_processor

    target = create_stub_target()
    source = """name: host-free-episodes
entities:
  blue: {role: blue}
agents:
  replayer: {affiliations: [blue]}
propositions:
  ready:
    description: The participant is ready for its next episode.
    subjects: [agents.replayer]
    basis: declared_state
    predicate:
      kind: boolean
      property: ready
      semantic_ref: urn:raes:observable:ready
      expected: true
assertions:
  ready: {proposition: ready, role: precondition}
behavior_specifications:
  replay:
    semantic_version: 1.0.0
    participant_refs: [replayer]
    episode_policy:
      profile: participant-episode-policy/v1
      initialization: {assertion_refs: [ready]}
"""
    plan = run_reference_processor(source, target.manifest).execution_plan
    assert plan.is_valid, [(diagnostic.code, diagnostic.message) for diagnostic in plan.diagnostics]
    assert not plan.model.realization_instance.nodes
    binding = ParticipantEpisodeRuntimeBinding(model=plan.model, implementations=(implementation(),))
    with RuntimeControlPlane(target) as unbound, pytest.raises(ConflictError, match="exact installed runtime binding"):
        unbound.register_planner_produced_plan(plan)
    with RuntimeControlPlane(target, participant_episode=binding) as bound:
        assert bound.register_planner_produced_plan(plan)
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.manager_plan_admission import runtime_plan_precondition_diagnostics

    diagnostics = runtime_plan_precondition_diagnostics(plan, target, RuntimeSnapshot())
    assert any(diagnostic.code == "runtime.participant-episode-binding-unavailable" for diagnostic in diagnostics)


@pytest.mark.parametrize("field", ["participant_address", "selected_decision_surface_mode"])
def test_episode_implementation_selection_cannot_substitute_participant_or_mode(field):
    admitted = implementation()
    changes = {field: "participant.behavior.other" if field == "participant_address" else "scripted"}
    selection = admitted.selection.model_copy(update=changes)
    if field == "selected_decision_surface_mode":
        with pytest.raises(ValueError, match="manifest"):
            ParticipantEpisodeImplementationBinding(manifest=admitted.manifest, selection=selection)
    else:
        other = ParticipantEpisodeImplementationBinding(manifest=admitted.manifest, selection=selection)
        model = episode_model()
        with pytest.raises(ValueError, match="one policy and one implementation"):
            ParticipantEpisodeRuntimeBinding(model=model, implementations=(other,))


def test_episode_binding_rejects_missing_original_compiler_context():
    model = replace(episode_model(), realization_instance=None)
    admitted = implementation()
    with pytest.raises(TypeError, match="retained compiler context"):
        ParticipantEpisodeRuntimeBinding(model=model, implementations=(admitted,))


@pytest.mark.parametrize("field", ["participant_runtimes", "backends"])
def test_episode_implementation_must_be_compatible_with_its_target(field):
    admitted = implementation()
    payload = admitted.manifest.model_dump(mode="json")
    payload["compatibility"][field] = ["other-runtime"]
    manifest = ParticipantImplementationManifestModel.model_validate(payload)
    selection = admitted.selection.model_copy(update={"manifest_digest": canonical_contract_digest(manifest)})
    implementation_binding = ParticipantEpisodeImplementationBinding(manifest=manifest, selection=selection)
    binding = ParticipantEpisodeRuntimeBinding(model=episode_model(), implementations=(implementation_binding,))
    target = create_stub_target()
    with pytest.raises(ValueError, match="selected (participant runtime|backend)"):
        RuntimeControlPlane(target, participant_episode=binding)


def test_installed_episode_context_is_detached_from_caller_mutations():
    binding = runtime_binding()
    model = binding.model
    admitted = binding.implementations[0]
    installed = ParticipantEpisodeRuntimeBinding(model=model, implementations=(admitted,))
    model.participant_episode_policies.clear()
    admitted.selection.participant_contract_versions.clear()
    assert installed.model.participant_episode_policies
    assert set(installed.implementations[0].selection.participant_contract_versions) == EPISODE_CONTRACTS


def test_authored_episode_policy_stays_in_the_semantic_fingerprint(tmp_path):
    from tools.check_formal_semantic_validation import replay_case

    source = FIXTURE.read_text()
    fixture = tmp_path / "episode.yaml"
    fixture.write_text(source)
    case = {"case_id": "episode-policy-control", "fixture_path": "episode.yaml", "replay_mode": "compile-stability"}
    original = replay_case(tmp_path, case)
    fixture.write_text(source.replace("control_actions: [reset]", "control_actions: [reset, restart]"))
    changed = replay_case(tmp_path, case)
    assert original["actual_outcome"] == changed["actual_outcome"] == "stable"
    assert original["result_digest"] != changed["result_digest"]
