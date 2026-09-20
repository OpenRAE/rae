"""Issue #1016 reference mixed-runtime coordination boundaries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from participant_crossing_fixtures import (
    ACTION,
    CONTROLLER,
    PARTICIPANT,
    admission_request,
    behavior,
    evidence,
    identity,
)
from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope
from raes_backend_stubs.stubs import StubParticipantRuntime, create_stub_components, create_stub_target
from raes_contracts.contracts import BackendManifestV2Model, seal_mixed_composition_profile
from raes_contracts.contracts.mixed_runtime import (
    MixedCompositionRuntimeEventModel,
    MixedCompositionRuntimeStateModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionApplyResult
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import (
    InMemoryControlPlaneStore,
    _snapshot_from_payload,
    _snapshot_payload,
)
from raes_runtime.mixed_runtime import (
    MixedPhaseTransitionEvaluation,
    MixedRuntimeBinding,
    MixedRuntimeComponent,
)
from raes_runtime.mixed_runtime_dispatch import mixed_recovery_target
from raes_runtime.mixed_runtime_state import runtime_state
from raes_runtime.participant_result_contracts import participant_runtime_history_transition_diagnostics
from raes_runtime.registry import RuntimeTarget
from sem233_flow_sink_fixtures import permit_resolver
from test_issue_1014_mixed_composition_contracts import _alternative_profile, _staged_profile
from test_issue_1015_mixed_staged_trial_admission import _mixed_request

pytestmark = pytest.mark.control_plane_conformance


def _initial_composition_snapshot() -> RuntimeSnapshot:
    event = MixedCompositionRuntimeEventModel(
        event_id="composition:run-one:initial",
        event_kind="phase-activated",
        run_id="run-one",
        plan_id="plan-one",
        plan_entry_id="entry-one",
        profile_id="profile-one",
        profile_digest=f"sha256:{'a' * 64}",
        phase_id="phase-one",
        phase_revision=0,
        active_component_ids=["sim", "emu"],
        active_allocation_ids=["participant", "action"],
        active_edge_ids=["sim-to-emu"],
        disposition="committed",
        order_ref="order:initial",
        evidence_refs=["evidence:admission"],
    )
    state = MixedCompositionRuntimeStateModel(
        run_id=event.run_id,
        plan_id=event.plan_id,
        plan_entry_id=event.plan_entry_id,
        profile_id=event.profile_id,
        profile_digest=event.profile_digest,
        phase_id=event.phase_id,
        phase_revision=event.phase_revision,
        active_component_ids=event.active_component_ids,
        active_allocation_ids=event.active_allocation_ids,
        active_edge_ids=event.active_edge_ids,
        history_head=event.event_id,
    )
    return RuntimeSnapshot(
        mixed_composition_states={event.run_id: state.model_dump(mode="json")},
        mixed_composition_history={event.run_id: [event.model_dump(mode="json")]},
    )


def test_mixed_phase_state_round_trips_without_losing_history() -> None:
    snapshot = _initial_composition_snapshot()

    restored = _snapshot_from_payload(_snapshot_payload(snapshot))

    assert restored.mixed_composition_states == snapshot.mixed_composition_states
    assert restored.mixed_composition_history == snapshot.mixed_composition_history
    assert restored.with_entries({}).mixed_composition_history == snapshot.mixed_composition_history


def test_mixed_phase_history_cannot_be_retracted() -> None:
    snapshot = _initial_composition_snapshot()
    rewritten = snapshot.with_entries({}, mixed_composition_states={}, mixed_composition_history={})

    assert any(
        "append-only" in diagnostic.message
        for diagnostic in participant_runtime_history_transition_diagnostics(snapshot, rewritten)
    )


def test_action_coordination_fact_requires_exact_dispatch_identity() -> None:
    initial = _initial_composition_snapshot().mixed_composition_history["run-one"][0]

    with pytest.raises(ValueError, match="exact allocation"):
        MixedCompositionRuntimeEventModel(
            **{
                **initial,
                "event_id": "composition:run-one:decision",
                "event_kind": "decision",
                "predecessor_event_id": initial["event_id"],
                "disposition": "permitted",
            }
        )


def test_runtime_state_rejects_membership_outside_the_admitted_phase() -> None:
    binding, run_id, _ = _admitted_binding(_runtime_profile)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    state = {**plane.snapshot.mixed_composition_states[run_id], "active_component_ids": ["emu"]}
    event = {**plane.snapshot.mixed_composition_history[run_id][0], "active_component_ids": ["emu"]}
    tampered = plane.snapshot.with_entries(
        dict(plane.snapshot.entries),
        mixed_composition_states={run_id: state},
        mixed_composition_history={run_id: [event]},
    )

    with pytest.raises(ValueError, match="admitted phase"):
        runtime_state(binding, tampered)


class _CountingParticipantRuntime(StubParticipantRuntime):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.admission_count = 0
        self.initialize_count = 0
        self.fail = fail
        self.action_started: Event | None = None
        self.action_release: Event | None = None

    def initialize(self, request, snapshot):
        self.initialize_count += 1
        return super().initialize(request, snapshot)

    def admit_action(self, request, snapshot):
        self.admission_count += 1
        if self.action_started is not None:
            self.action_started.set()
        if self.action_release is not None:
            assert self.action_release.wait(timeout=5)
        if self.fail:
            return ParticipantActionApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    Diagnostic(
                        code="runtime.test-provider-rejected",
                        domain="participant",
                        address=request.participant_address,
                        message="Synthetic provider rejection.",
                    )
                ],
            )
        return super().admit_action(request, snapshot)


class _FailingSecondCompositionCommitStore(InMemoryControlPlaneStore):
    def __init__(self, *, fail_on: int = 2) -> None:
        super().__init__()
        self.composition_commits = 0
        self.fail_on = fail_on

    def commit_participant_transition(self, **kwargs):
        self.composition_commits += 1
        if self.composition_commits == self.fail_on:
            raise RuntimeError("injected composition commit failure")
        return super().commit_participant_transition(**kwargs)


def _runtime_profile():
    source = _alternative_profile()
    fields = source.model_dump(mode="python", exclude={"profile_digest"})
    fields["allocations"]["allocation.participant"]["target_address"] = PARTICIPANT
    fields["allocations"]["allocation.action"]["target_address"] = ACTION
    for allocation_id in ("allocation.participant", "allocation.action"):
        fields["allocations"][allocation_id]["controller_ref"] = CONTROLLER
        fields["allocations"][allocation_id]["action_authority_ref"] = "authority:red-team"
    return seal_mixed_composition_profile(**fields)


def _runtime_staged_profile():
    source = _staged_profile()
    fields = source.model_dump(mode="python", exclude={"profile_digest"})
    fields["allocations"]["allocation.participant"]["target_address"] = PARTICIPANT
    fields["allocations"]["allocation.action"]["target_address"] = ACTION
    for allocation_id in ("allocation.participant", "allocation.action"):
        fields["allocations"][allocation_id]["controller_ref"] = CONTROLLER
        fields["allocations"][allocation_id]["action_authority_ref"] = "authority:red-team"
    return seal_mixed_composition_profile(**fields)


def _runtime_mixed_profile():
    from test_issue_1014_mixed_composition_contracts import _profile

    source = _profile()
    fields = source.model_dump(mode="python", exclude={"profile_digest"})
    fields["allocations"]["allocation.participant"]["target_address"] = PARTICIPANT
    fields["allocations"]["allocation.action"]["target_address"] = ACTION
    fields["allocations"]["allocation.action"]["provider_component_id"] = "emu"
    for allocation_id in ("allocation.participant", "allocation.action"):
        fields["allocations"][allocation_id]["controller_ref"] = CONTROLLER
        fields["allocations"][allocation_id]["action_authority_ref"] = "authority:red-team"
    return seal_mixed_composition_profile(**fields)


def _runtime_unsupported_profile():
    source = _runtime_profile()
    fields = source.model_dump(mode="python", exclude={"profile_digest"})
    fields["allocations"]["allocation.action"]["feature_requirements"] = []
    return seal_mixed_composition_profile(**fields)


def _admitted_binding(
    profile_factory=_alternative_profile,
    transition_evaluator=None,
    failing_component: str | None = None,
) -> tuple[MixedRuntimeBinding, str, dict[str, _CountingParticipantRuntime]]:
    request = _mixed_request(profile_factory=profile_factory)
    compiled = compile_admitted_trial_plan(request)
    assert compiled.plan is not None
    entry = next(iter(compiled.plan.entries.values()))
    profile = request.mixed_profiles[entry.apparatus.profile_ref.ref_id]
    components = {}
    runtimes = {}
    for component_id, component in profile.components.items():
        manifest_model = next(
            manifest
            for manifest in request.apparatus_manifests.values()
            if isinstance(manifest, BackendManifestV2Model)
            and manifest.identity.name == component.manifest_ref.subject_ref.ref_id
        )
        envelope = request.mixed_realization_envelopes[component.realization_envelope.envelope_id]
        manifest = backend_manifest_from_v2_model_with_envelope(manifest_model, envelope)
        parts = create_stub_components(manifest=manifest)
        runtime = _CountingParticipantRuntime(fail=component_id == failing_component)
        target = RuntimeTarget(
            name=component_id,
            manifest=manifest,
            provisioner=parts.provisioner,
            orchestrator=parts.orchestrator,
            evaluator=parts.evaluator,
            participant_runtime=runtime,
            time_runtime=parts.time_runtime,
            observation_runtime=parts.observation_runtime,
        )
        components[component_id] = MixedRuntimeComponent(
            target=target,
            manifest=manifest_model,
            envelope=envelope,
        )
        runtimes[component_id] = runtime

    def permit_transition(transition, _state, _snapshot):
        return MixedPhaseTransitionEvaluation(
            permitted=True,
            attempts=1,
            order_ref="order:transition:1",
            evidence_refs=tuple(item.evidence_ref for item in transition.evidence_bindings),
            provenance_refs=("provenance:transition-evaluator",),
        )

    evaluator = transition_evaluator or permit_transition
    transition_evaluators = {transition.evaluator_ref: evaluator for transition in profile.transitions.values()}
    return (
        MixedRuntimeBinding(
            plan=compiled.plan,
            plan_entry_id=entry.plan_entry_id,
            profile=profile,
            context=request.mixed_profile_contexts[profile.profile_id],
            components=components,
            transition_evaluators=transition_evaluators,
        ),
        entry.run_id,
        runtimes,
    )


def test_mixed_runtime_activation_commits_the_admitted_initial_phase() -> None:
    binding, run_id, _ = _admitted_binding()
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )

    receipt = plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    assert receipt.accepted
    state = plane.snapshot.mixed_composition_states[run_id]
    assert state["phase_id"] == binding.profile.initial_phase_id
    assert state["profile_digest"] == binding.profile.profile_digest
    assert plane.snapshot.mixed_composition_history[run_id][0]["event_kind"] == "phase-activated"

    replay = plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    assert replay.operation_id == receipt.operation_id
    with pytest.raises(RuntimeError):
        plane.activate_mixed_composition(identity=identity(), idempotency_key="different-activation")
    assert len(plane.snapshot.mixed_composition_history[run_id]) == 1


def test_action_dispatch_commits_exact_provider_cut_before_effect() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_profile)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    initialize = plane.initialize_participant_episode(
        PARTICIPANT,
        episode_id="episode-1",
        idempotency_key="mixed-initialize",
        identity=identity(),
    )
    initialize_replay = plane.initialize_participant_episode(
        PARTICIPANT,
        episode_id="episode-1",
        idempotency_key="mixed-initialize",
        identity=identity(),
    )

    receipt = plane.admit_participant_action(
        behavior(),
        admission_request(),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="mixed-action",
    )

    assert receipt.accepted
    assert initialize_replay.operation_id == initialize.operation_id
    assert mixed_recovery_target(plane, initialize.operation_id) is binding.components["sim"].target
    assert runtimes["sim"].initialize_count == 1
    assert runtimes["sim"].admission_count == 1
    kinds = [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]]
    assert kinds == [
        "phase-activated",
        "lifecycle-decision",
        "lifecycle-attempt",
        "lifecycle-result",
        "decision",
        "attempt",
        "result",
        "delivery",
        "observation",
    ]
    decision = next(
        event for event in plane.snapshot.mixed_composition_history[run_id] if event["event_kind"] == "decision"
    )
    assert decision["allocation_id"] == "allocation.action"
    assert decision["component_id"] == "sim"
    assert decision["crossing_event_ref"]


def test_mixed_action_dispatch_resolves_the_admitted_edge_and_clock_mapping() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_mixed_profile)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    receipt = plane.admit_participant_action(
        behavior(),
        admission_request(),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="mixed-edge-action",
    )

    assert runtimes["sim"].admission_count == 0
    assert runtimes["emu"].admission_count == 1
    decision = next(
        event for event in plane.snapshot.mixed_composition_history[run_id] if event["event_kind"] == "decision"
    )
    assert decision["edge_id"] == "edge.sim-to-emu"
    assert decision["mapping_ref"] == "time.mappings.sim-to-emu"
    assert decision["mapping_loss_refs"] == ["limitation:mapping"]
    assert plane.snapshot.mixed_composition_history[run_id][-1]["event_kind"] == "weakening"
    record = plane._store.load_records()[receipt.operation_id]
    assert mixed_recovery_target(plane, record.receipt.operation_id) is binding.components["emu"].target
    assert mixed_recovery_target(plane, "unknown-operation") is None


def test_backend_rejection_appends_failure_without_delivery() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_profile, failing_component="sim")
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    receipt = plane.admit_participant_action(
        behavior(),
        admission_request(),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="rejected-action",
    )

    assert runtimes["sim"].admission_count == 1
    kinds = [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]]
    assert kinds[-2:] == ["result", "failure"]
    assert "delivery" not in kinds
    status = plane.get_operation(receipt.operation_id, identity=identity())
    assert status is not None and status.state.value == "failed"


def test_failed_decision_commit_invokes_no_component_and_publishes_no_cut() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_profile)
    store = _FailingSecondCompositionCommitStore(fail_on=4)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        store=store,
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    with pytest.raises(RuntimeError, match="composition commit failure"):
        plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="failed-decision-commit",
        )

    assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    assert [event["event_kind"] for event in store.load_snapshot().mixed_composition_history[run_id]] == [
        "phase-activated",
        "lifecycle-decision",
        "lifecycle-attempt",
        "lifecycle-result",
    ]


def test_failed_lifecycle_cut_commit_invokes_no_component() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_profile)
    store = _FailingSecondCompositionCommitStore()
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        store=store,
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    with pytest.raises(RuntimeError, match="composition commit failure"):
        plane.initialize_participant_episode(
            PARTICIPANT,
            episode_id="episode-1",
            identity=identity(),
        )

    assert all(runtime.initialize_count == 0 for runtime in runtimes.values())
    assert [event["event_kind"] for event in store.load_snapshot().mixed_composition_history[run_id]] == [
        "phase-activated"
    ]


def test_unsupported_admitted_capability_invokes_no_component_and_publishes_no_delivery() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_unsupported_profile)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    receipt = plane.admit_participant_action(
        behavior(),
        admission_request(),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="unsupported-action",
    )

    assert receipt.accepted
    assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    assert [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]] == [
        "phase-activated",
        "lifecycle-decision",
        "lifecycle-attempt",
        "lifecycle-result",
    ]
    decision = plane.snapshot.participant_crossing_history[PARTICIPANT][-1]["occurrence"]
    assert decision["disposition"] == "unsupported"
    assert decision["gates"]["backend_support"] == "unsupported"


def test_staged_phase_progression_is_bounded_append_only_and_idempotent() -> None:
    evaluations = []

    def evaluate(transition, state, _snapshot):
        evaluations.append((transition.transition_id, state.phase_revision))
        return MixedPhaseTransitionEvaluation(
            permitted=True,
            attempts=transition.progress_bound,
            order_ref="order:transition:7",
            evidence_refs=tuple(item.evidence_ref for item in transition.evidence_bindings),
            provenance_refs=("provenance:trusted-evaluator",),
        )

    binding, run_id, runtimes = _admitted_binding(_runtime_staged_profile, evaluate)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    receipt = plane.advance_mixed_composition(
        "transition.sim-to-emu",
        identity=identity(),
        idempotency_key="advance-once",
    )

    state = plane.snapshot.mixed_composition_states[run_id]
    assert state["phase_id"] == "phase.emu"
    assert state["phase_revision"] == 1
    assert evaluations == [("transition.sim-to-emu", 0)]
    assert [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]] == [
        "phase-activated",
        "lifecycle-decision",
        "lifecycle-attempt",
        "lifecycle-result",
        "phase-transition",
        "handoff",
    ]
    replay = plane.advance_mixed_composition(
        "transition.sim-to-emu",
        identity=identity(),
        idempotency_key="advance-once",
    )
    assert replay.operation_id == receipt.operation_id
    assert evaluations == [("transition.sim-to-emu", 0)]
    with pytest.raises(RuntimeError):
        plane.advance_mixed_composition(
            "transition.sim-to-emu",
            identity=identity(),
            idempotency_key="stale-transition",
        )
    with pytest.raises(ValueError, match="active .* allocation"):
        plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="inactive-action",
        )
    assert all(runtime.admission_count == 0 for runtime in runtimes.values())


def test_phase_progression_rejects_an_outstanding_mixed_effect() -> None:
    evaluations = []

    def evaluate(transition, state, _snapshot):
        evaluations.append((transition.transition_id, state.phase_revision))
        return MixedPhaseTransitionEvaluation(
            permitted=True,
            attempts=1,
            order_ref="order:blocked-transition",
            evidence_refs=tuple(item.evidence_ref for item in transition.evidence_bindings),
        )

    binding, run_id, runtimes = _admitted_binding(_runtime_staged_profile, evaluate)
    first = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    first.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    first.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
    second = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        store=first._store,
    )
    started = Event()
    release = Event()
    runtimes["sim"].action_started = started
    runtimes["sim"].action_release = release

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            first.admit_participant_action,
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="outstanding-action",
        )
        assert started.wait(timeout=5)
        try:
            with pytest.raises(RuntimeError):
                second.advance_mixed_composition(
                    "transition.sim-to-emu",
                    identity=identity(),
                    idempotency_key="blocked-advance",
                )
            assert evaluations == []
            assert second.snapshot.mixed_composition_states[run_id]["phase_id"] == "phase.sim"
        finally:
            release.set()
        receipt = future.result(timeout=5)

    status = first.get_operation(receipt.operation_id, identity=identity())
    assert status is not None and status.state.value == "succeeded"


def test_transition_evaluator_failure_is_sanitized_and_records_failure_fact() -> None:
    def fail_with_sensitive_detail(*_args):
        raise RuntimeError("private evaluator internals")

    binding, run_id, _ = _admitted_binding(_runtime_staged_profile, fail_with_sensitive_detail)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    receipt = plane.advance_mixed_composition(
        "transition.sim-to-emu",
        identity=identity(),
        idempotency_key="failed-transition",
    )

    state = plane.snapshot.mixed_composition_states[run_id]
    assert state["phase_id"] == "phase.sim"
    assert state["phase_revision"] == 0
    assert plane.snapshot.mixed_composition_history[run_id][-1]["event_kind"] == "failure"
    status = plane.get_operation(receipt.operation_id, identity=identity())
    assert status is not None and status.state.value == "failed"
    assert "private evaluator internals" not in repr(status.diagnostics)


def test_concurrent_phase_progression_commits_one_cas_winner() -> None:
    barrier = Barrier(2)

    def evaluate(transition, _state, _snapshot):
        barrier.wait(timeout=5)
        return MixedPhaseTransitionEvaluation(
            permitted=True,
            attempts=1,
            order_ref="order:concurrent-transition",
            evidence_refs=tuple(item.evidence_ref for item in transition.evidence_bindings),
        )

    binding, run_id, _ = _admitted_binding(_runtime_staged_profile, evaluate)
    first = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    first.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    second = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        store=first._store,
    )

    def advance(plane, key):
        try:
            return plane.advance_mixed_composition(
                "transition.sim-to-emu",
                identity=identity(),
                idempotency_key=key,
            )
        except ValueError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(advance, (first, second), ("advance-a", "advance-b")))

    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    snapshot = first._store.load_snapshot()
    assert snapshot.mixed_composition_states[run_id]["phase_revision"] == 1
    assert [event["event_kind"] for event in snapshot.mixed_composition_history[run_id]].count("phase-transition") == 1
