"""ACT-614 temporal admission."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml
from implementations.python.tests._act_614_temporal_fixtures import (
    _bound_deadline_payload,
    _temporal_target,
    _TemporalEvidenceRuntime,
)
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    _activity_policy_yaml,
    _autonomous_manifest,
    _NativeParticipantRuntime,
    _scenario_yaml,
)
from implementations.python.tests.test_issue_898_participant_execution_control import _service_state
from raes.parser import parse_sdl
from raes_backend_protocols.capabilities import ParticipantRuntimeCapabilities
from raes_backend_protocols.capability_admission import participant_autonomous_execution_capability_gaps
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_v2_model
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance.profiles import BackendCapabilityProfile
from raes_conformance.conformance.target_probes import _target_adapter_cases
from raes_contracts.contracts.participant_execution import ParticipantExecutionControlRequestModel
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager


def test_empty_participant_feature_sets_are_valid_declarations() -> None:
    capability = ParticipantRuntimeCapabilities(name="limited")
    assert capability.supported_behavior_features == frozenset()
    from raes_contracts.contracts.manifests import ParticipantRuntimeCapabilitiesModel

    wire = ParticipantRuntimeCapabilitiesModel(
        name="limited",
        supported_participant_roles=[],
        supported_behavior_features=[],
        supported_interaction_features=[],
    )
    assert wire.supported_behavior_features == []


def test_serial_backend_needs_neither_concurrency_nor_native_execution_control() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    manifest = _autonomous_manifest(model, with_realization_envelope=False)
    capability = replace(
        manifest.participant_runtime,
        supports_execution_control=False,
        supported_execution_control_actions=frozenset(),
        supports_bounded_concurrency=False,
        max_concurrent_actions=1,
        max_autonomous_retries_per_occurrence=0,
    )
    manifest = replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=capability))
    manifest = backend_manifest_from_v2_model(backend_manifest_v2_model(manifest))
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    assert participant_autonomous_execution_capability_gaps(manifest, [policy], model.time_model) == ()


def test_activity_admission_requires_only_authored_features() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    authored = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    authored["timing"] = {"minimum_ticks": 10, "maximum_ticks": 10}
    authored["max_burst_size"] = 1
    candidate = authored["action_candidates"]["portal_login"]
    candidate.update(max_retries=0, retryable_failure_classes=[], cooldown_ticks=0)
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload)))
    manifest = _autonomous_manifest(model)
    capability = replace(
        manifest.participant_runtime,
        supported_autonomous_activity_features=frozenset(
            {"work-windows", "weighted-selection", "occurrence-provenance"}
        ),
    )
    limited = replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=capability))
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    assert participant_autonomous_execution_capability_gaps(limited, [policy], model.time_model) == ()
    # A richer request remains valid SDL and fails only this pairing's admission.
    candidate["cooldown_ticks"] = 10
    richer = compile_runtime_model(parse_sdl(yaml.safe_dump(payload)))
    richer_policy = next(iter(richer.behavior_specifications.values())).autonomous_execution
    gaps = participant_autonomous_execution_capability_gaps(limited, [richer_policy], richer.time_model)
    assert any("cooldowns" in gap for gap in gaps)
    assert participant_autonomous_execution_capability_gaps(manifest, [richer_policy], richer.time_model) == ()


def test_execution_control_rejects_unclaimed_operation_before_calling_backend() -> None:
    class RecordingRuntime(_NativeParticipantRuntime):
        controls = []

        def control_execution(self, request, snapshot):
            self.controls.append(request.action)
            return super().control_execution(request, snapshot)

    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    manifest = _autonomous_manifest(model)
    capability = replace(manifest.participant_runtime, supported_execution_control_actions=frozenset({"start"}))
    manifest = replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=capability))
    runtime = RecordingRuntime()
    target = replace(create_stub_target(), manifest=manifest, participant_runtime=runtime)
    scope = "participant.autonomous-execution.green-activity"
    snapshot = RuntimeSnapshot(participant_execution_services={scope: _service_state().model_dump(mode="json")})
    control_plane = RuntimeControlPlane(target, initial_snapshot=snapshot)
    try:
        control_plane.control_participant_execution(
            ParticipantExecutionControlRequestModel(execution_scope_ref=scope, action="pause", expected_generation=0)
        )
        assert runtime.controls == []
        assert control_plane.snapshot.participant_execution_services == snapshot.participant_execution_services
    finally:
        control_plane.close()


def test_conformance_probes_serial_execution_without_unclaimed_controls() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    manifest = _autonomous_manifest(model)
    capability = replace(
        manifest.participant_runtime,
        supports_execution_control=False,
        supported_execution_control_actions=frozenset(),
        supports_bounded_concurrency=False,
        max_concurrent_actions=1,
        max_autonomous_participants=1,
    )
    manifest = replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=capability))
    target = replace(create_stub_target(), manifest=manifest, participant_runtime=_NativeParticipantRuntime())
    cases = _target_adapter_cases(target, BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE)
    execution_cases = [case for case in cases if case.name.startswith("participant-execution-")]
    assert [case.name for case in execution_cases] == ["participant-execution-bounded-native-actions"]
    assert all(case.passed for case in execution_cases)
    assert execution_cases[0].accounted_operations == ("admit-action",)


@pytest.mark.parametrize("action", ["start", "pause", "resume", "drain", "reset", "teardown"])
def test_conformance_can_probe_one_claimed_control_without_requiring_the_others(action: str) -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    manifest = _autonomous_manifest(model)
    capability = replace(manifest.participant_runtime, supported_execution_control_actions=frozenset({action}))
    manifest = replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=capability))
    target = replace(create_stub_target(), manifest=manifest, participant_runtime=_NativeParticipantRuntime())
    cases = _target_adapter_cases(target, BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE)
    control_cases = [
        case
        for case in cases
        if case.name.startswith("participant-execution-")
        and case.name != "participant-execution-bounded-native-actions"
    ]
    assert {case.name for case in control_cases} == {f"participant-execution-{action}"}
    assert all(case.passed for case in control_cases), control_cases


def test_unbound_deadline_is_not_admitted_as_an_enforced_guarantee() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["temporal_constraints"]["finish-by-five"] = {
        "constraint_kind": "deadline",
        "clock_ref": "scenario-clock",
        "subject_refs": ["participant-agent"],
        "end": {"tick": 5},
        "description": "No action may finish after tick five.",
    }
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"][
        "temporal_constraint_refs"
    ].append("finish-by-five")
    scenario = parse_sdl(yaml.safe_dump(payload))
    model = compile_runtime_model(scenario)
    runtime = _NativeParticipantRuntime()
    target = replace(create_stub_target(), manifest=_autonomous_manifest(model), participant_runtime=runtime)
    manager = RuntimeManager(target)
    plan = manager.plan(scenario)
    assert any("deadline" in diagnostic.message and diagnostic.is_error for diagnostic in plan.diagnostics)
    result = manager.apply(plan)
    assert not result.success
    assert runtime.native_actions == []


def test_temporal_admission_requires_one_offer_for_the_exact_combination() -> None:
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(_bound_deadline_payload())))
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    manifest = _autonomous_manifest(model, with_realization_envelope=False)
    capability = manifest.participant_runtime
    offer = replace(
        capability.execution_bindings[0], temporal_contract_digests=(policy.temporal_bindings[0].contract_digest,)
    )
    sufficient = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities, participant_runtime=replace(capability, execution_bindings=(offer,))
        ),
    )
    restored = backend_manifest_from_v2_model(backend_manifest_v2_model(sufficient))
    assert participant_autonomous_execution_capability_gaps(restored, [policy], model.time_model) == ()
    wrong = replace(offer, temporal_contract_digests=("sha256:" + "0" * 64,))
    insufficient = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities, participant_runtime=replace(capability, execution_bindings=(wrong,))
        ),
    )
    assert any(
        "temporal" in gap
        for gap in participant_autonomous_execution_capability_gaps(insufficient, [policy], model.time_model)
    )


def test_reference_runtime_rejects_bound_manual_policy_without_invalidating_sdl() -> None:
    payload = _bound_deadline_payload()
    scenario, target = _temporal_target(payload)
    payload["behavior_specifications"]["participant-behavior"].pop("autonomous_execution")
    scenario = parse_sdl(yaml.safe_dump(payload))
    manager = RuntimeManager(target)
    plan = manager.plan(scenario)
    assert any(d.code == "runtime.participant-temporal-driver-unsupported" for d in plan.diagnostics)
    result = manager.apply(plan)
    assert not result.success
    assert sum(d.code == "runtime.participant-temporal-driver-unsupported" for d in result.diagnostics) == 1
    assert target.participant_runtime.native_actions == []


@pytest.mark.parametrize("claims", ["sufficient", "no-temporal", "no-participant"])
def test_manual_ingress_cannot_bypass_bound_temporal_execution(claims: str) -> None:
    class RecordingRuntime(_TemporalEvidenceRuntime):
        def bind_autonomous_action(self, *args, **kwargs):
            self.last_request = super().bind_autonomous_action(*args, **kwargs)
            return self.last_request

    runtime = RecordingRuntime()
    scenario, target = _temporal_target(_bound_deadline_payload(), runtime)
    manager = RuntimeManager(target)
    plan = manager.plan(scenario)
    result = manager.apply(plan)
    assert result.success
    request = replace(runtime.last_request, temporal_contexts=())
    native_calls = len(runtime.native_actions)
    if claims != "sufficient":
        capability = target.manifest.participant_runtime
        capability = (
            None
            if claims == "no-participant"
            else replace(
                capability,
                execution_bindings=tuple(
                    replace(offer, temporal_contract_digests=()) for offer in capability.execution_bindings
                ),
            )
        )
        target = replace(
            target,
            participant_runtime=runtime if capability is not None else None,
            manifest=replace(
                target.manifest,
                capabilities=replace(
                    target.manifest.capabilities,
                    participant_runtime=capability,
                    time=replace(target.manifest.time, supports_coordinated_participant_reset=False),
                ),
            ),
        )
    control = RuntimeControlPlane(target, initial_snapshot=result.snapshot)
    try:
        participant = plan.model.participant_behaviors[request.participant_address]
        receipt = control.admit_participant_action(participant, request)
        assert not receipt.accepted
        assert len(runtime.native_actions) == native_calls
    finally:
        control.close()


@pytest.mark.parametrize("evidence", [False, True])
def test_temporal_conformance_executes_claimed_guarantee(evidence: bool) -> None:
    from raes_conformance.conformance.participant_temporal_probes import participant_temporal_scenario_case

    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime() if evidence else None)
    case = participant_temporal_scenario_case(target, scenario)
    assert case.passed is evidence
    assert target.participant_runtime.native_actions
    assert bool(case.evidence_refs) is evidence


def test_temporal_conformance_checks_admission_before_native_execution() -> None:
    from raes_conformance.conformance.participant_temporal_probes import participant_temporal_scenario_case

    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime())
    model = compile_runtime_model(scenario)
    target = replace(target, manifest=_autonomous_manifest(model))
    case = participant_temporal_scenario_case(target, scenario)
    assert not case.passed
    assert target.participant_runtime.native_actions == []


@pytest.mark.parametrize("validation_error", [False, True])
def test_temporal_conformance_does_not_disclose_rejected_input(monkeypatch, validation_error: bool) -> None:
    from raes_conformance.conformance import participant_temporal_probes as probes
    from raes_contracts.contracts.participant_temporal import ParticipantTemporalAssessmentModel

    marker = "private-payload-must-not-appear"

    def reject(_snapshot):
        if validation_error:
            ParticipantTemporalAssessmentModel.model_validate({"status": marker})
        raise ValueError(marker)

    monkeypatch.setattr(probes, "require_participant_temporal_history", reject)
    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime())
    case = probes.participant_temporal_scenario_case(target, scenario)
    assert not case.passed
    assert case.diagnostics
    assert marker not in repr(case)


def test_admission_does_not_union_incompatible_temporal_offers() -> None:
    from copy import deepcopy

    payload = _bound_deadline_payload()
    action = payload["action_contracts"]["probe-customer-portal-login"]
    second = deepcopy(action["temporal_contracts"][0])
    second.update(temporal_id="start", event_points=["start", "deadline"])
    second["shared_time_binding"]["event_point"] = "start"
    action["temporal_contracts"].append(second)
    action["backend_timing_disclosures"][0]["affected_temporal_ids"].append("start")
    scenario, target = _temporal_target(payload)
    model = compile_runtime_model(scenario)
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    capability = target.manifest.participant_runtime
    offer = capability.execution_bindings[0]
    assert len(offer.temporal_contract_digests) == 2
    split = tuple(
        replace(offer, binding_id=f"offer.{index}", temporal_contract_digests=(digest,))
        for index, digest in enumerate(offer.temporal_contract_digests)
    )
    manifest = replace(
        target.manifest,
        capabilities=replace(
            target.manifest.capabilities, participant_runtime=replace(capability, execution_bindings=split)
        ),
    )
    assert participant_autonomous_execution_capability_gaps(target.manifest, [policy], model.time_model) == ()
    assert any(
        "temporal" in gap
        for gap in participant_autonomous_execution_capability_gaps(manifest, [policy], model.time_model)
    )
