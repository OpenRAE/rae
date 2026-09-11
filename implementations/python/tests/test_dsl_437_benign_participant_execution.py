"""DSL-437 benign participant autonomous execution semantics and runtime."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from implementations.python.tests.participant_execution_test_backend import (
    NativeParticipantExecutionController,
)
from raes._errors import SDLValidationError
from raes.parser import parse_sdl
from raes.participant_behavior import ParticipantFailureClass
from raes.participant_execution import ParticipantAutonomousExecutionPolicyV2
from raes_backend_protocols.capabilities import (
    ObservationCaptureOffer,
    ParticipantExecutionBinding,
    ParticipantFeatureSupport,
)
from raes_backend_protocols.capability_admission import participant_autonomous_execution_capability_gaps
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_v2_model
from raes_backend_protocols.participant_runtime_base import BaseParticipantRuntime
from raes_backend_stubs.manifest import create_stub_manifest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import (
    ExperimentStochasticControlModel,
    ParticipantActionResultModel,
    ParticipantAutonomousExecutionStateModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    RuntimeSnapshotEnvelopeModel,
)
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.contracts.participant_resource_budgets import ParticipantResourceMeasurementModel
from raes_contracts.contracts.random_stream import (
    GovernedEntropyRefModel,
    PublicSeedModel,
    RandomStreamControlBindingModel,
    RandomStreamProfileReferenceModel,
)
from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
    ParticipantNativeActionExecution,
)
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_processor.compiler import compile_runtime_model
from raes_processor.compiler.time_model import time_model_contract_model
from raes_processor.planner import plan
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_activity import (
    activity_tick_is_eligible,
    next_activity_timing,
    resolve_participant_activity_controls,
    select_activity_candidate,
)
from raes_runtime.participant_clock_driver import ParticipantClockDriver
from raes_runtime.participant_scheduler import ParticipantScheduler
from raes_runtime.time_coordinator import ReferenceTimeRuntime, TimeCoordinator

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = REPO_ROOT / "examples" / "scenarios" / "enterprise-participant-evidence-loop.sdl.yaml"
IMPLEMENTATION_REF = "participant-implementation-manifests.green-worker.v1"
SCENARIO_CLOCK_ADDRESS = "time.clock.scenario-clock"
SCENARIO_CLOCK_STEP_TICKS = 10


def _advance_stepped_clock_to_tick(manager: RuntimeManager, target_tick: int) -> ApplyResult:
    current_tick = manager.read_time_state().clocks[SCENARIO_CLOCK_ADDRESS].coordinate.tick
    assert target_tick > current_tick
    assert (target_tick - current_tick) % SCENARIO_CLOCK_STEP_TICKS == 0
    while current_tick < target_tick:
        advanced = manager.advance_time(SCENARIO_CLOCK_ADDRESS, ticks=SCENARIO_CLOCK_STEP_TICKS)
        assert advanced.success
        current_tick += SCENARIO_CLOCK_STEP_TICKS
    return advanced


def _scenario_yaml(*, role: str = "green") -> str:
    payload = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for node in payload["nodes"].values():
        node.pop("os", None)
        node.pop("os_distribution", None)
        node.pop("os_version", None)
    payload["entities"]["enterprise-participant"]["role"] = role
    payload["objectives"] = {}
    payload["workflows"] = {}
    payload["outcome_interpretation_rules"] = {}
    specification = payload["behavior_specifications"]["participant-behavior"]
    specification["participant_role_refs"] = [role]
    specification["outcome_interpretation_rule_refs"] = []
    specification["authority_scope_refs"] = []
    specification["behavior_mode"] = "autonomous"
    specification["backend_feature_support_refs"] = [
        "action_contracts",
        "autonomous_execution",
        "behavior_history",
        "observation_boundaries",
        "temporal_contracts",
    ]
    specification["autonomous_execution"] = {
        "participant_implementation_ref": IMPLEMENTATION_REF,
        "clock_ref": "scenario-clock",
        "progression_policy_ref": "scenario-progression",
        "temporal_constraint_refs": ["green-cadence"],
        "action_order": ["probe-customer-portal-login"],
        "observation_boundary_ref": "participant-view",
        "selection_strategy": "ordered_cycle",
        "max_action_attempts": 2,
        "max_in_flight": 1,
        "failure_policy": "stop",
        "evaluation_authority": {"mode": "none"},
    }
    payload["time_domains"] = {
        "scenario": {
            "kind": "simulated",
            "tick_period_seconds": {"numerator": 1, "denominator": 1},
            "epoch": "scenario_start",
            "visibility": "participant_visible",
            "description": "Exact shared scenario time for benign participant actions.",
        }
    }
    payload["clocks"] = {
        "scenario-clock": {
            "time_domain_ref": "scenario",
            "authority_kind": "runtime",
            "authority_ref": "runtime.time-coordinator",
            "monotonicity": "non_decreasing",
            "supports_pause": True,
            "supports_reset": True,
            "description": "Authoritative shared scenario clock.",
        }
    }
    payload["time_progression_policies"] = {
        "scenario-progression": {
            "clock_ref": "scenario-clock",
            "advancement_mode": "stepped",
            "synchronization_mode": "barrier",
            "step_ticks": 10,
            "reset_behavior": "new_segment_zero",
            "replay_behavior": "restore_recorded_advances",
            "description": "Deterministic stepped progression.",
        }
    }
    payload["temporal_constraints"] = {
        "green-cadence": {
            "constraint_kind": "cadence",
            "clock_ref": "scenario-clock",
            "subject_refs": ["nodes.customer-portal"],
            "start": {"tick": 0},
            "cadence_ticks": 10,
            "description": "One benign participant action every ten ticks.",
        }
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _activity_policy_yaml() -> str:
    payload = yaml.safe_load(_scenario_yaml())
    payload["temporal_constraints"].update(
        {
            "work-window": {
                "constraint_kind": "window",
                "clock_ref": "scenario-clock",
                "subject_refs": ["participant-agent"],
                "start": {"tick": 0},
                "end": {"tick": 100},
                "description": "Participant work availability.",
            },
            "pause-window": {
                "constraint_kind": "window",
                "clock_ref": "scenario-clock",
                "subject_refs": ["participant-agent"],
                "start": {"tick": 40},
                "end": {"tick": 50},
                "description": "Participant pause interval.",
            },
        }
    )
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"] = {
        "profile": "participant-autonomous-execution/v2",
        "participant_implementation_ref": IMPLEMENTATION_REF,
        "clock_ref": "scenario-clock",
        "progression_policy_ref": "scenario-progression",
        "work_window_refs": ["work-window"],
        "pause_window_refs": ["pause-window"],
        "observation_boundary_ref": "participant-view",
        "stochastic_control_ref": "green-activity-policy",
        "selection_strategy": "weighted",
        "timing": {"minimum_ticks": 10, "maximum_ticks": 30},
        "outside_window_disposition": "next_opening",
        "empty_eligible_disposition": "complete",
        "action_candidates": {
            "portal_login": {
                "action_ref": "probe-customer-portal-login",
                "weight": 3,
                "depends_on": [],
                "retryable_failure_classes": ["target_unavailable", "timeout"],
                "max_retries": 2,
                "cooldown_ticks": 20,
            }
        },
        "max_occurrences": 8,
        "max_action_attempts": 24,
        "max_burst_size": 2,
        "max_in_flight": 1,
        "failure_policy": "continue",
        "evaluation_authority": {"mode": "none"},
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _implementation_manifest() -> ParticipantImplementationManifestModel:
    return ParticipantImplementationManifestModel.model_validate(
        {
            "schema_version": "participant-implementation-manifest/v1",
            "identity": {"name": "green-worker", "version": "1.0.0"},
            "implementation_kind": "agent",
            "supported_contract_versions": [
                "participant-implementation-manifest-v1",
                "participant-implementation-provenance-v1",
                "participant-episode-state-envelope-v1",
                "participant-episode-history-event-stream-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "compatibility": {"participant_runtimes": ["test-runtime"]},
            "concept_bindings": [
                {"scope": "implementation_kind", "family": "apparatus-declarations"},
                {
                    "scope": "capabilities.supported_participant_contracts",
                    "family": "apparatus-declarations",
                },
                {
                    "scope": "capabilities.supported_decision_surface_modes",
                    "family": "apparatus-declarations",
                },
                {
                    "scope": "capabilities.tool_affordance_expectations",
                    "family": "tools-and-artifacts",
                },
                {
                    "scope": "capabilities.exposure_policy_kinds",
                    "family": "provenance-and-evidence",
                },
            ],
            "capabilities": {
                "supported_participant_contracts": [
                    "participant-episode-state-envelope-v1",
                    "participant-episode-history-event-stream-v1",
                    "participant-behavior-history-event-stream-v1",
                ],
                "supported_decision_surface_modes": ["autonomous"],
                "tool_affordance_expectations": ["http-api"],
                "exposure_policy_kinds": ["observation-stream"],
            },
        }
    )


def _activity_control() -> ExperimentStochasticControlModel:
    return ExperimentStochasticControlModel(
        control_id="green-activity-policy",
        role="agent-policy",
        executable_binding=RandomStreamControlBindingModel(
            profile_ref=RandomStreamProfileReferenceModel(
                ref_id="blake3-xof-participant-v1",
                ref_kind="profile",
                ref_version="1",
            ),
            namespace="green-activity",
            root_entropy=PublicSeedModel(
                kind="public-seed",
                encoding="hex-fixed-width",
                value="42" * 32,
            ),
        ),
    )


def _selection(participant_address: str) -> ParticipantImplementationSelectionModel:
    return ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": participant_address,
            "implementation_identity": {"name": "green-worker", "version": "1.0.0"},
            "manifest_ref": IMPLEMENTATION_REF,
            "manifest_digest": "sha256:" + "1" * 64,
            "selected_decision_surface_mode": "autonomous",
            "participant_contract_versions": [
                "participant-episode-state-envelope-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "exposure_policy": {
                "policy_id": "green-worker-policy",
                "policy_version": "1.0.0",
                "policy_digest": "sha256:" + "2" * 64,
                "exposure_policy_kinds": ["observation-stream"],
                "disclosed_refs": ["content.task-brief"],
                "withheld_refs": ["content.evaluator-notes"],
                "tool_affordance_refs": [],
                "visibility_scope_refs": ["participants.green.visible"],
            },
        }
    )


class _NativeParticipantRuntime(BaseParticipantRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.native_actions: list[str] = []
        self._execution_controller = NativeParticipantExecutionController()

    def control_execution(self, request, snapshot):
        return self._execution_controller.control(request, snapshot)

    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        self._execution_controller.begin_action()
        try:
            self.native_actions.append(request.action_instance_id)
            metadata = dict(snapshot.metadata)
            metadata["last_native_action"] = request.action_instance_id
            return ParticipantNativeActionExecution(
                apply_result=ApplyResult(
                    success=True,
                    snapshot=snapshot.with_entries(dict(snapshot.entries), metadata=metadata),
                    changed_addresses=["native.service.customer-portal"],
                ),
                action_result=ParticipantActionResultModel(
                    status="succeeded",
                    participant_address=request.participant_address,
                    episode_id=episode_id,
                    action_instance_id=request.action_instance_id,
                    action_contract_address=request.action_contract_address,
                    observation_point=request.temporal_contexts[0].observation_point,
                    observations=["customer portal responded"],
                    resource_measurements=[
                        ParticipantResourceMeasurementModel(
                            budget_state_ref=requirement.budget_state_ref,
                            operation_id=request.action_instance_id,
                            execution_generation=request.execution_generation or 0,
                            resource_kind=requirement.resource_kind,
                            unit=requirement.unit,
                            meter_profile_ref=requirement.meter_profile_ref,
                            measured=requirement.reserved,
                            evidence_refs=(f"evidence:{request.action_instance_id}:{requirement.budget_state_ref}",),
                        )
                        for requirement in request.resource_measurement_requirements
                    ],
                    evidence_refs=[],
                ),
            )
        finally:
            self._execution_controller.finish_action()

    def bind_autonomous_action(
        self,
        participant_address: str,
        action_contract_address: str,
        observation_boundary_address: str,
        participant_implementation_ref: str,
        action_instance_id: str,
        temporal_contexts: tuple[object, ...],
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionAdmissionRequest:
        del participant_implementation_ref, snapshot
        return ParticipantActionAdmissionRequest(
            participant_address=participant_address,
            action_contract_address=action_contract_address,
            observation_boundary_address=observation_boundary_address,
            action_instance_id=action_instance_id,
            implementation_manifest=_implementation_manifest(),
            implementation_selection=_selection(participant_address),
            temporal_contexts=temporal_contexts,
        )


class _FailedParticipantRuntime(_NativeParticipantRuntime):
    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        assert execution.action_result is not None
        return replace(
            execution,
            action_result=execution.action_result.model_copy(
                update={
                    "status": "failed",
                    "failure_class": ParticipantFailureClass.TARGET_UNAVAILABLE,
                }
            ),
        )


class _MissingOutcomeRuntime(_NativeParticipantRuntime):
    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        return replace(execution, action_result=None)


class _ContradictoryTimeRuntime(_NativeParticipantRuntime):
    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        assert execution.action_result is not None
        return replace(
            execution,
            action_result=execution.action_result.model_copy(
                update={"observation_point": "time.clock.scenario-clock@segment=9,tick=999"}
            ),
        )


class _ResetFailParticipantRuntime(_NativeParticipantRuntime):
    def reset(self, request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        del request
        return ApplyResult(success=False, snapshot=snapshot)


class _SecondResetFailParticipantRuntime(_NativeParticipantRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.reset_calls = 0

    def reset(
        self,
        request: ParticipantEpisodeResetRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        self.reset_calls += 1
        if self.reset_calls == 2:
            return ApplyResult(success=False, snapshot=snapshot)
        return super().reset(request, snapshot)


class _NoBatchResetParticipantRuntime(_NativeParticipantRuntime):
    reset_many = None


class _PlainApplyParticipantRuntime(_NativeParticipantRuntime):
    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        result = super().admit_action(request, snapshot)
        return ApplyResult(
            success=result.success,
            snapshot=result.snapshot,
            diagnostics=result.diagnostics,
            changed_addresses=result.changed_addresses,
        )


class _NonResultParticipantRuntime(_NativeParticipantRuntime):
    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> object:
        del request, snapshot
        return object()


class _DirectContradictoryParticipantRuntime(_NativeParticipantRuntime):
    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        episode = snapshot.participant_episode_results[request.participant_address]
        mutated = snapshot.with_entries(
            dict(snapshot.entries),
            metadata={**snapshot.metadata, "direct_native_mutation": True},
        )
        return ParticipantActionApplyResult(
            success=True,
            snapshot=mutated,
            changed_addresses=[request.participant_address],
            action_result=ParticipantActionResultModel(
                status="succeeded",
                participant_address=request.participant_address,
                episode_id=episode["episode_id"],
                action_instance_id=request.action_instance_id,
                action_contract_address=request.action_contract_address,
                observation_point="time.clock.other@segment=0,tick=0",
            ),
        )


class _StaleHistoryParticipantRuntime(_NativeParticipantRuntime):
    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        result = super().admit_action(request, snapshot)
        return replace(
            result,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries),
                participant_behavior_history={
                    address: list(events) for address, events in snapshot.participant_behavior_history.items()
                },
            ),
        )


class _IncompleteHistoryParticipantRuntime(_NativeParticipantRuntime):
    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        result = super().admit_action(request, snapshot)
        history = {address: list(events) for address, events in result.snapshot.participant_behavior_history.items()}
        history[request.participant_address] = history[request.participant_address][:-1]
        return replace(
            result,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries),
                participant_behavior_history=history,
            ),
        )


class _WrongProvenanceParticipantRuntime(_NativeParticipantRuntime):
    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        result = super().admit_action(request, snapshot)
        history = {address: list(events) for address, events in result.snapshot.participant_behavior_history.items()}
        attempted = dict(history[request.participant_address][0])
        attempted["actor_provenance"] = "participant-implementation:wrong@9.9.9"
        history[request.participant_address][0] = attempted
        return replace(
            result,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries),
                participant_behavior_history=history,
            ),
        )


class _BlockingReadTimeRuntime(ReferenceTimeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.block_reads = False
        self.read_entered = threading.Event()
        self.read_release = threading.Event()

    def state(self, snapshot: RuntimeSnapshot) -> TimeRuntimeStateModel:
        if self.block_reads:
            self.read_entered.set()
            self.read_release.wait(timeout=1.0)
        return super().state(snapshot)


def _compiled() -> tuple[object, object]:
    runtime_model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    specification = runtime_model.behavior_specifications["participant.behavior-specification.participant-behavior"]
    assert specification.autonomous_execution is not None
    return runtime_model, specification.autonomous_execution


def _autonomous_manifest(
    runtime_model: object,
    *,
    with_realization_envelope: bool = True,
) -> object:
    policies = tuple(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    base_manifest = create_stub_manifest(
        with_time=True,
        with_realization_envelope=with_realization_envelope,
    )
    assert base_manifest.participant_runtime is not None
    assert base_manifest.observation is not None
    capture_offers = tuple(
        ObservationCaptureOffer(
            offer_id=f"test-{demand.demand_id}",
            offer_version="1.0.0",
            output_contract=demand.output_contract or "experiment-evidence-record-v1",
            field_selectors=demand.field_selectors or ("",),
            artifact_roles=frozenset(demand.artifact_roles or ("observation",)),
            media_types=frozenset(demand.media_types or ("application/json",)),
            capture_kind=demand.capture_kind or "observation",
            source_classes=frozenset(demand.source_classes or ("sdl-evidence-requirement",)),
            source_refs=frozenset(demand.source_refs),
            scopes=frozenset(demand.scopes or ("run",)),
            channel_kinds=frozenset(demand.channel_kinds),
            channel_refs=frozenset(demand.channel_refs),
            window_kinds=frozenset(demand.window_kinds or ("run",)),
            integrity_modes=frozenset(demand.integrity_modes or ("checksum",)),
            sensitivity=demand.sensitivity or "internal",
            availability="available",
            fidelity="complete",
            disclosure=demand.disclosure,
            retention_policy_refs=frozenset(demand.retention_policy_refs),
            export_policy=demand.export_policy,
            redaction_policy=demand.redaction_policy,
        )
        for demand in runtime_model.capture_demands
    )
    return replace(
        base_manifest,
        capabilities=replace(
            base_manifest.capabilities,
            observation=replace(base_manifest.observation, capture_offers=capture_offers),
            participant_runtime=replace(
                base_manifest.participant_runtime,
                supported_behavior_features=(
                    base_manifest.participant_runtime.supported_behavior_features | {"autonomous_execution"}
                ),
                supports_autonomous_execution=True,
                supported_autonomous_selection_strategies=frozenset(policy.selection_strategy for policy in policies),
                supported_autonomous_action_contracts=frozenset(
                    address for policy in policies for address in policy.action_contract_addresses
                ),
                supported_autonomous_observation_boundaries=frozenset(
                    policy.observation_boundary_address for policy in policies
                ),
                supported_autonomous_target_addresses=frozenset(
                    address for policy in policies for address in policy.target_addresses
                ),
                supported_autonomous_policy_profiles=frozenset(policy.profile for policy in policies),
                supported_autonomous_activity_features=frozenset(
                    {
                        "work-windows",
                        "timing-variation",
                        "weighted-selection",
                        "dependencies",
                        "bounded-retries",
                        "cooldowns",
                        "limited-bursts",
                        "occurrence-provenance",
                    }
                    if any(policy.profile == "participant-autonomous-execution/v2" for policy in policies)
                    else ()
                ),
                supported_autonomous_random_stream_profiles=frozenset(
                    {"blake3-xof-participant-v1"}
                    if any(policy.profile == "participant-autonomous-execution/v2" for policy in policies)
                    else ()
                ),
                max_autonomous_participants=8,
                max_autonomous_action_attempts=max(policy.max_action_attempts for policy in policies),
                max_autonomous_in_flight=max(policy.max_in_flight for policy in policies),
                max_autonomous_occurrences=max(
                    (policy.max_occurrences or policy.max_action_attempts for policy in policies),
                    default=1,
                ),
                max_autonomous_retries_per_occurrence=max(
                    (max(policy.action_candidate_max_retries, default=0) for policy in policies),
                    default=0,
                )
                or 1,
                max_autonomous_burst_size=max((policy.max_burst_size for policy in policies), default=1),
                execution_bindings=tuple(
                    ParticipantExecutionBinding(
                        binding_id=(f"{policy.address}.binding.{binding.action_contract_address.rsplit('.', 1)[-1]}"),
                        action_contract_address=binding.action_contract_address,
                        target_addresses=binding.target_addresses,
                        participant_implementation_ref=(binding.participant_implementation_ref),
                        constraint_refs=policy.temporal_constraint_addresses,
                        evidence_refs=(f"evidence:{policy.address}:native-execution",),
                        max_action_attempts=binding.max_action_attempts,
                        max_in_flight=binding.max_in_flight,
                        timeout_seconds=30,
                        max_retries=max(
                            policy.action_candidate_max_retries,
                            default=0,
                        ),
                    )
                    for policy in policies
                    for binding in policy.execution_bindings
                ),
                supports_execution_control=True,
                supported_execution_control_actions=frozenset(
                    {"start", "pause", "resume", "drain", "reset", "teardown"}
                ),
                supports_bounded_concurrency=True,
                max_execution_services=8,
                max_concurrent_actions=8,
            ),
        ),
    )


def test_autonomous_execution_compiles_existing_participant_and_shared_time_refs() -> None:
    runtime_model, policy = _compiled()

    assert policy.participant_addresses == ("participant.behavior.participant-agent",)
    assert policy.action_contract_addresses == ("participant.action-contract.probe-customer-portal-login",)
    assert policy.clock_address == "time.clock.scenario-clock"
    assert policy.progression_policy_address == "time.policy.scenario-progression"
    assert policy.temporal_constraint_addresses == ("time.constraint.green-cadence",)
    assert "provision.node.customer-portal.service.http" in policy.target_addresses
    assert runtime_model.time_model.constraints[0].cadence_ticks == 10
    action = runtime_model.action_contracts["participant.action-contract.probe-customer-portal-login"]
    assert action.interaction_classes == ("shared_state_change",)
    assert action.shared_state_refs == ("nodes.customer-portal.services.http",)
    assert action.commutative_interaction_targets == ("nodes.customer-portal.services.http",)
    assert action.merge_rule_refs == ()


def test_activity_policy_v2_compiles_weighted_candidates_and_shared_time_windows() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_activity_policy_yaml()))
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution

    assert policy is not None
    assert policy.profile == "participant-autonomous-execution/v2"
    assert policy.selection_strategy == "weighted"
    assert policy.work_window_addresses == ("time.constraint.work-window",)
    assert policy.pause_window_addresses == ("time.constraint.pause-window",)
    assert policy.stochastic_control_ref == "green-activity-policy"
    assert policy.timing_minimum_ticks == 10
    assert policy.timing_maximum_ticks == 30
    assert policy.action_candidate_ids == ("portal_login",)
    assert policy.action_candidate_weights == (3,)
    assert policy.action_contract_addresses == ("participant.action-contract.probe-customer-portal-login",)
    assert policy.max_occurrences == 8
    assert policy.max_burst_size == 2


def test_activity_policy_v2_compiles_section_qualified_window_refs_to_canonical_addresses() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    policy["work_window_refs"] = ["temporal_constraints.work-window"]
    policy["pause_window_refs"] = ["temporal_constraints.pause-window"]

    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))
    compiled = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution

    assert compiled is not None
    assert compiled.work_window_addresses == ("time.constraint.work-window",)
    assert compiled.pause_window_addresses == ("time.constraint.pause-window",)
    assert set(compiled.temporal_constraint_addresses) == {
        "time.constraint.work-window",
        "time.constraint.pause-window",
    }


def test_activity_policy_v2_rejects_dependency_cycles() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    policy["action_candidates"]["portal_login"]["depends_on"] = ["second_action"]
    policy["action_candidates"]["second_action"] = {
        **policy["action_candidates"]["portal_login"],
        "depends_on": ["portal_login"],
    }

    with pytest.raises(ValueError, match="dependency graph must be acyclic"):
        ParticipantAutonomousExecutionPolicyV2.model_validate(policy)


def test_activity_policy_v2_rejects_non_window_availability_constraint() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["work_window_refs"] = [
        "green-cadence"
    ]
    rendered = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="work and pause refs must resolve to window constraints"):
        parse_sdl(rendered)


def test_activity_policy_v2_rejects_timing_bounds_unreachable_by_stepped_progression() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["timing"]["minimum_ticks"] = 15
    rendered = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="activity timing bounds are unreachable by stepped progression"):
        parse_sdl(rendered)


def test_activity_policy_v2_rejects_window_for_unrelated_subject() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["temporal_constraints"]["work-window"]["subject_refs"] = ["nodes.customer-portal"]
    rendered = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="must name the behavior specification or every governed participant"):
        parse_sdl(rendered)


def test_non_evaluated_autonomous_participant_must_be_green() -> None:
    scenario_yaml = _scenario_yaml(role="red")

    with pytest.raises(SDLValidationError, match="must have the green role"):
        parse_sdl(scenario_yaml)


def test_non_evaluated_autonomous_participant_cannot_widen_evaluation_authority() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["behavior_specifications"]["participant-behavior"]["authority_scope_refs"] = [
        "nodes.customer-portal.services.http"
    ]
    scenario_yaml = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="cannot carry outcome-interpretation or authority-scope refs"):
        parse_sdl(scenario_yaml)


def test_autonomous_execution_requires_exactly_one_shared_clock_cadence() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["temporal_constraints"]["second-cadence"] = {
        **payload["temporal_constraints"]["green-cadence"],
        "cadence_ticks": 20,
    }
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"][
        "temporal_constraint_refs"
    ].append("second-cadence")
    scenario_yaml = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="requires exactly one cadence constraint"):
        parse_sdl(scenario_yaml)


def test_autonomous_participant_has_exactly_one_scheduler_owner() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["behavior_specifications"]["second-participant-behavior"] = {
        **payload["behavior_specifications"]["participant-behavior"],
    }
    scenario_yaml = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="already controlled by behavior specification"):
        parse_sdl(scenario_yaml)


def test_backend_admission_enforces_finite_autonomous_execution_limits() -> None:
    runtime_model, _ = _compiled()
    policies = tuple(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    manifest = _autonomous_manifest(runtime_model, with_realization_envelope=False)
    assert participant_autonomous_execution_capability_gaps(manifest, policies) == ()

    assert manifest.participant_runtime is not None
    constrained = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            participant_runtime=replace(
                manifest.participant_runtime,
                max_autonomous_action_attempts=1,
            ),
        ),
    )
    gaps = participant_autonomous_execution_capability_gaps(constrained, policies)
    assert len(gaps) == 1

    assert constrained.time is not None
    no_transaction = replace(
        constrained,
        capabilities=replace(
            constrained.capabilities,
            time=replace(
                constrained.time,
                supports_coordinated_participant_reset=False,
            ),
        ),
    )
    gaps = participant_autonomous_execution_capability_gaps(
        no_transaction,
        policies,
        runtime_model.time_model,
    )
    assert "autonomous clock reset requires coordinated participant reset support" in gaps
    assert "action attempts" in gaps[0]


def test_backend_admission_requires_exact_v2_activity_and_random_profile_support() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_activity_policy_yaml()))
    policies = tuple(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    manifest = _autonomous_manifest(runtime_model, with_realization_envelope=False)

    assert participant_autonomous_execution_capability_gaps(manifest, policies, runtime_model.time_model) == ()
    restored = backend_manifest_from_v2_model(backend_manifest_v2_model(manifest))
    assert participant_autonomous_execution_capability_gaps(restored, policies, runtime_model.time_model) == ()
    assert manifest.participant_runtime is not None
    unsupported = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            participant_runtime=replace(
                manifest.participant_runtime,
                supported_autonomous_random_stream_profiles=frozenset({"blake3-xof-v1"}),
            ),
        ),
    )

    gaps = participant_autonomous_execution_capability_gaps(unsupported, policies, runtime_model.time_model)
    assert "unsupported autonomous random-stream profiles: blake3-xof-participant-v1" in gaps
    missing_dependency_support = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            participant_runtime=replace(
                manifest.participant_runtime,
                supported_autonomous_activity_features=(
                    manifest.participant_runtime.supported_autonomous_activity_features - {"dependencies"}
                ),
            ),
        ),
    )
    gaps = participant_autonomous_execution_capability_gaps(
        missing_dependency_support,
        policies,
        runtime_model.time_model,
    )
    assert "unsupported autonomous activity features: dependencies" in gaps


def test_planner_enforces_required_participant_features_and_exact_targets() -> None:
    runtime_model, _ = _compiled()
    manifest = _autonomous_manifest(runtime_model)
    assert manifest.participant_runtime is not None
    unsupported_target = "provision.node.unsupported.service.http"
    unsupported_bindings = tuple(
        replace(binding, target_addresses=(unsupported_target,))
        for binding in manifest.participant_runtime.execution_bindings
    )
    unsupported = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            participant_runtime=replace(
                manifest.participant_runtime,
                supported_behavior_features=frozenset({"autonomous_execution"}),
                supported_autonomous_target_addresses=frozenset({unsupported_target}),
                execution_bindings=unsupported_bindings,
            ),
        ),
    )

    execution_plan = plan(runtime_model, unsupported)

    messages = [diagnostic.message for diagnostic in execution_plan.diagnostics]
    assert any("participant feature 'action_contracts'" in message for message in messages)
    assert any("unsupported autonomous target addresses" in message for message in messages)


def test_planner_fails_closed_for_policy_features_outside_autonomous_execution() -> None:
    runtime_model, _ = _compiled()
    address = "participant.behavior-specification.participant-behavior"
    specification = replace(
        runtime_model.behavior_specifications[address],
        autonomous_execution=None,
        backend_feature_support_refs=("participant_ingress_admission",),
    )
    runtime_model = replace(
        runtime_model,
        behavior_specifications={**runtime_model.behavior_specifications, address: specification},
    )

    execution_plan = plan(runtime_model, create_stub_manifest(with_time=True))

    assert any(
        diagnostic.code == "participant.feature-support-insufficient"
        and diagnostic.address == address
        and "explicitly unsupported" in diagnostic.message
        for diagnostic in execution_plan.diagnostics
    )


def test_planner_accepts_evidence_backed_exact_policy_feature_support() -> None:
    runtime_model, _ = _compiled()
    address = "participant.behavior-specification.participant-behavior"
    feature = "participant_ingress_admission"
    specification = replace(
        runtime_model.behavior_specifications[address],
        autonomous_execution=None,
        backend_feature_support_refs=(feature,),
    )
    runtime_model = replace(
        runtime_model,
        behavior_specifications={**runtime_model.behavior_specifications, address: specification},
    )
    manifest = create_stub_manifest(with_time=True)
    assert manifest.participant_runtime is not None
    declaration = ParticipantFeatureSupport(
        feature=feature,
        support_level=ParticipantFeatureSupportLevel.EXACT,
        evidence_refs=("conformance:participant-ingress-admission:case-1",),
    )
    manifest = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            participant_runtime=replace(
                manifest.participant_runtime,
                supported_behavior_features=manifest.participant_runtime.supported_behavior_features | {feature},
                feature_support=(declaration,),
            ),
        ),
    )

    execution_plan = plan(runtime_model, manifest)

    assert not any(
        diagnostic.code == "participant.feature-support-insufficient" and diagnostic.address == address
        for diagnostic in execution_plan.diagnostics
    )


def test_runtime_manager_drives_due_actions_from_shared_clock_controls() -> None:
    scenario = parse_sdl(_scenario_yaml())
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success
    assert len(participant_runtime.native_actions) == 1
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    skipped = manager.advance_time(policy.clock_address, ticks=20)
    assert not skipped.success
    assert skipped.diagnostics[0].code == "runtime.participant-autonomous-cadence-skipped"
    assert manager.read_time_state().clocks[policy.clock_address].coordinate.tick == 0
    paused = manager.pause_time(policy.clock_address)
    assert paused.success
    assert any(
        address.endswith(".state.participant.behavior.participant-agent") for address in paused.changed_addresses
    )
    resumed = manager.resume_time(policy.clock_address)
    assert resumed.success
    advanced = manager.advance_time(policy.clock_address, ticks=10)
    assert advanced.success
    assert len(participant_runtime.native_actions) == 2
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(advanced.snapshot.participant_autonomous_execution_states.values()))
    )
    assert state.lifecycle_state == "completed"
    reset = manager.reset_time(policy.clock_address)
    assert reset.success
    assert len(participant_runtime.native_actions) == 2
    reset_state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(reset.snapshot.participant_autonomous_execution_states.values()))
    )
    assert (reset_state.time_segment, reset_state.attempted_actions, reset_state.next_tick) == (1, 0, 0)
    due = manager.run_due_participant_actions()
    assert due.success
    assert len(participant_runtime.native_actions) == 3


def test_runtime_manager_executes_v2_activity_from_admitted_random_control() -> None:
    scenario = parse_sdl(_activity_policy_yaml())
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])

    applied = manager.apply(manager.plan(scenario))

    assert applied.success
    assert participant_runtime.native_actions == []
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )
    assert 10 <= state.next_tick <= 30
    due = _advance_stepped_clock_to_tick(manager, state.next_tick)
    assert due.success
    assert len(participant_runtime.native_actions) == 1
    advanced = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(due.snapshot.participant_autonomous_execution_states.values()))
    )
    assert advanced.occurrence_ordinal == 1
    assert advanced.last_candidate_id == "portal_login"
    assert advanced.random_control_id == "green-activity-policy"
    assert advanced.random_profile_id == "blake3-xof-participant-v1"
    history = due.snapshot.participant_behavior_history[advanced.participant_address]
    assert len(history) == 3
    provenances = [event["activity_provenance"] for event in history]
    assert all(provenance is not None for provenance in provenances)
    assert {provenance["occurrence_id"] for provenance in provenances} == {
        (
            "participant.autonomous-execution.participant-behavior:"
            "participant.behavior.participant-agent:segment=0:occurrence=0"
        )
    }
    assert all(provenance["candidate_id"] == "portal_login" for provenance in provenances)
    assert all(
        provenance["random_address"]["time_segment"] == 0 and provenance["random_address"]["occurrence_ordinal"] == 0
        for provenance in provenances
    )


def test_runtime_manager_bounds_v2_retries_and_preserves_occurrence_causality() -> None:
    scenario = parse_sdl(_activity_policy_yaml())
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _FailedParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(scenario))
    initial = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )

    due = _advance_stepped_clock_to_tick(manager, initial.next_tick)

    assert due.success
    assert participant_runtime.native_actions == [
        (
            "participant.autonomous-execution.participant-behavior:"
            "participant.behavior.participant-agent:"
            f"episode={initial.episode_id}:segment=0:occurrence=0:retry=0"
        ),
        (
            "participant.autonomous-execution.participant-behavior:"
            "participant.behavior.participant-agent:"
            f"episode={initial.episode_id}:segment=0:occurrence=0:retry=1"
        ),
        (
            "participant.autonomous-execution.participant-behavior:"
            "participant.behavior.participant-agent:"
            f"episode={initial.episode_id}:segment=0:occurrence=0:retry=2"
        ),
    ]
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(due.snapshot.participant_autonomous_execution_states.values()))
    )
    assert (state.occurrence_ordinal, state.current_retry) == (1, 0)
    assert (state.attempted_actions, state.failed_actions) == (3, 3)
    history = due.snapshot.participant_behavior_history[state.participant_address]
    attempted = [event for event in history if event["event_type"] == "action_attempted"]
    assert [event["activity_provenance"]["timing_disposition"] for event in attempted] == [
        initial.next_timing_disposition,
        "retry",
        "retry",
    ]
    assert attempted[1]["activity_provenance"]["predecessor_attempt_id"] == participant_runtime.native_actions[0]
    assert attempted[2]["activity_provenance"]["predecessor_attempt_id"] == participant_runtime.native_actions[1]


def test_runtime_manager_global_attempt_bound_stops_v2_retry_chain() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    policy.update(max_occurrences=2, max_action_attempts=2, max_burst_size=1)
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _FailedParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(scenario))
    initial = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )

    due = _advance_stepped_clock_to_tick(manager, initial.next_tick)

    assert due.success
    assert len(participant_runtime.native_actions) == 2
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(due.snapshot.participant_autonomous_execution_states.values()))
    )
    assert state.lifecycle_state == "completed"
    assert (state.occurrence_ordinal, state.attempted_actions, state.failed_actions) == (1, 2, 2)


def test_runtime_manager_normalizes_v2_timing_to_half_open_work_availability() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["temporal_constraints"]["work-window"]["start"] = {"tick": 20, "microstep": 1}
    timing = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["timing"]
    timing.update(minimum_ticks=10, maximum_ticks=10)
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=_NativeParticipantRuntime(),
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])

    applied = manager.apply(manager.plan(scenario))

    assert applied.success
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    assert state.next_tick == 30
    assert state.next_timing_disposition == "next_opening"
    assert not activity_tick_is_eligible(policy, runtime_model.time_model, 20)
    assert not activity_tick_is_eligible(policy, runtime_model.time_model, 40)
    assert activity_tick_is_eligible(policy, runtime_model.time_model, 50)
    assert not activity_tick_is_eligible(policy, runtime_model.time_model, 100)


def test_v2_weighted_selection_honors_each_cumulative_weight_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    authored_policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    authored_policy["action_candidates"]["follow_up"] = {
        **authored_policy["action_candidates"]["portal_login"],
        "weight": 2,
    }
    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution
    assert policy is not None
    control = resolve_participant_activity_controls([_activity_control()])["green-activity-policy"]
    first_weight = policy.action_candidate_weights[0]
    total_weight = sum(policy.action_candidate_weights)

    for drawn_value, expected_index in (
        (0, 0),
        (first_weight - 1, 0),
        (first_weight, 1),
        (total_weight - 1, 1),
    ):
        monkeypatch.setattr(
            "raes_runtime.participant_activity.draw_activity_integer",
            lambda drawn_value=drawn_value, **_kwargs: drawn_value,
        )
        selected = select_activity_candidate(
            policy=policy,
            participant_address=policy.participant_addresses[0],
            time_segment=0,
            occurrence_ordinal=0,
            control=control,
            eligible_indices=(0, 1),
        )
        assert selected == expected_index


def test_v2_timing_search_advances_across_disjoint_work_windows() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["temporal_constraints"]["work-window"]["end"] = {"tick": 20}
    payload["temporal_constraints"]["second-work-window"] = {
        **payload["temporal_constraints"]["work-window"],
        "start": {"tick": 50},
        "end": {"tick": 100},
    }
    authored_policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    authored_policy["work_window_refs"] = ["work-window", "second-work-window"]
    authored_policy["pause_window_refs"] = []
    authored_policy["timing"] = {"minimum_ticks": 30, "maximum_ticks": 30}
    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution
    assert policy is not None
    control = resolve_participant_activity_controls([_activity_control()])["green-activity-policy"]

    timing = next_activity_timing(
        policy=policy,
        time_model=runtime_model.time_model,
        participant_address=policy.participant_addresses[0],
        time_segment=0,
        occurrence_ordinal=0,
        current_tick=0,
        control=control,
    )

    assert timing.tick == 50
    assert timing.disposition == "next_opening"


def test_runtime_manager_waits_when_every_v2_candidate_is_cooling_down() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    authored_policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    authored_policy["empty_eligible_disposition"] = "wait"
    authored_policy["timing"] = {"minimum_ticks": 10, "maximum_ticks": 10}
    authored_policy["max_occurrences"] = 2
    authored_policy["max_burst_size"] = 2
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(scenario))
    initial = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )
    assert initial.burst_size == 2

    due = _advance_stepped_clock_to_tick(manager, initial.next_tick)

    assert due.success
    assert len(participant_runtime.native_actions) == 1
    waiting = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(due.snapshot.participant_autonomous_execution_states.values()))
    )
    assert waiting.lifecycle_state == "running"
    assert waiting.occurrence_ordinal == 1
    assert waiting.attempted_actions == 1
    assert waiting.next_tick == initial.next_tick + 10


def test_runtime_manager_skips_v2_timing_outside_work_windows() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["temporal_constraints"]["work-window"]["end"] = {"tick": 20}
    payload["temporal_constraints"]["second-work-window"] = {
        **payload["temporal_constraints"]["work-window"],
        "start": {"tick": 50},
        "end": {"tick": 100},
    }
    authored_policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    authored_policy["work_window_refs"] = ["work-window", "second-work-window"]
    authored_policy["pause_window_refs"] = []
    authored_policy["timing"] = {"minimum_ticks": 30, "maximum_ticks": 30}
    authored_policy["outside_window_disposition"] = "skip"
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])

    applied = manager.apply(manager.plan(scenario))

    assert applied.success
    assert participant_runtime.native_actions == []
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )
    assert state.lifecycle_state == "completed"
    assert state.next_tick == 0
    assert state.next_timing_disposition == "drawn"


def test_runtime_manager_enforces_v2_dependencies_cooldowns_and_limited_burst() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    policy["action_candidates"]["follow_up"] = {
        **policy["action_candidates"]["portal_login"],
        "weight": 1,
        "depends_on": ["portal_login"],
    }
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(scenario))
    initial = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )
    assert initial.burst_size == 2

    due = _advance_stepped_clock_to_tick(manager, initial.next_tick)

    assert due.success
    assert len(participant_runtime.native_actions) == 2
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(due.snapshot.participant_autonomous_execution_states.values()))
    )
    assert state.occurrence_ordinal == 2
    assert state.completed_candidate_ids == ["portal_login", "follow_up"]
    assert state.candidate_cooldown_until == {
        "portal_login": initial.next_tick + 20,
        "follow_up": initial.next_tick + 20,
    }
    attempted = [
        event
        for event in due.snapshot.participant_behavior_history[state.participant_address]
        if event["event_type"] == "action_attempted"
    ]
    assert attempted[1]["activity_provenance"]["candidate_id"] == "follow_up"
    assert attempted[1]["activity_provenance"]["dependency_candidate_ids"] == ["portal_login"]
    assert attempted[1]["activity_provenance"]["timing_disposition"] == "burst"


def test_runtime_manager_resets_v2_continuation_and_random_generation() -> None:
    scenario = parse_sdl(_activity_policy_yaml())
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(scenario))
    initial = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    )
    first_due = _advance_stepped_clock_to_tick(manager, initial.next_tick)
    assert first_due.success
    first_attempts = [
        event["activity_provenance"]
        for event in first_due.snapshot.participant_behavior_history[initial.participant_address]
        if event["event_type"] == "action_attempted"
    ]
    first_attempt_ids = {provenance["attempt_id"] for provenance in first_attempts}

    reset = manager.reset_time("time.clock.scenario-clock")

    assert reset.success
    reset_state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(reset.snapshot.participant_autonomous_execution_states.values()))
    )
    assert reset_state.time_segment == 1
    assert reset_state.occurrence_ordinal == 0
    assert reset_state.current_retry == 0
    assert reset_state.completed_candidate_ids == []
    assert reset_state.candidate_cooldown_until == {}
    second_due = _advance_stepped_clock_to_tick(manager, reset_state.next_tick)
    assert second_due.success
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(second_due.snapshot.participant_autonomous_execution_states.values()))
    )
    attempted = [
        event
        for event in second_due.snapshot.participant_behavior_history[state.participant_address]
        if event["event_type"] == "action_attempted"
    ]
    assert [event["activity_provenance"] for event in attempted[: len(first_attempts)]] == first_attempts
    second_attempt_ids = {event["activity_provenance"]["attempt_id"] for event in attempted[len(first_attempts) :]}
    assert first_attempt_ids.isdisjoint(second_attempt_ids)
    latest = attempted[-1]["activity_provenance"]
    assert f"episode={reset_state.episode_id}" in latest["attempt_id"]
    assert "segment=1" in latest["attempt_id"]
    assert latest["occurrence_id"].endswith("segment=1:occurrence=0")
    assert latest["random_address"]["time_segment"] == 1
    assert latest["random_address"]["occurrence_ordinal"] == 0


def test_runtime_manager_rejects_v2_activity_without_admitted_random_control() -> None:
    scenario = parse_sdl(_activity_policy_yaml())
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )

    manager = RuntimeManager(target)
    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any("stochastic control" in diagnostic.message for diagnostic in applied.diagnostics)


def test_runtime_manager_fails_closed_for_unresolved_governed_activity_entropy() -> None:
    control = _activity_control()
    assert control.executable_binding is not None
    governed = control.model_copy(
        update={
            "executable_binding": control.executable_binding.model_copy(
                update={
                    "root_entropy": GovernedEntropyRefModel(
                        kind="governed-reference",
                        reference_id="participant-activity-seed",
                        reference_version="1",
                    )
                }
            )
        }
    )

    target = create_stub_target()
    with pytest.raises(ValueError, match="governed entropy without a resolver"):
        RuntimeManager(target, stochastic_controls=[governed])


def test_runtime_manager_rolls_back_clock_when_participant_reset_fails() -> None:
    scenario = parse_sdl(_scenario_yaml())
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _ResetFailParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target)
    applied = manager.apply(manager.plan(scenario))
    predecessor = applied.snapshot
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )

    reset = manager.reset_time(policy.clock_address)

    assert not reset.success
    assert reset.snapshot == predecessor
    assert manager.snapshot == predecessor
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(manager.snapshot.participant_autonomous_execution_states.values()))
    )
    assert state.time_segment == 0
    assert manager.read_time_state().clocks[policy.clock_address].coordinate.segment == 0


def test_reference_batch_reset_restores_base_state_when_second_participant_reset_fails() -> None:
    runtime_model, policy = _compiled()
    declaration = time_model_contract_model(runtime_model.time_model)
    assert declaration is not None
    participant_runtime = _NativeParticipantRuntime()
    time_runtime = ReferenceTimeRuntime()
    snapshot = time_runtime.initialize(declaration, RuntimeSnapshot()).snapshot
    participant_address = "participant.behavior.participant-agent"
    snapshot = participant_runtime.initialize(
        ParticipantEpisodeInitializeRequest(participant_address=participant_address),
        snapshot,
    ).snapshot
    predecessor_results = participant_runtime.results()
    predecessor_history = participant_runtime.history()
    requests = (
        ParticipantEpisodeResetRequest(participant_address=participant_address),
        ParticipantEpisodeResetRequest(participant_address="participant.behavior.missing"),
    )

    reset = time_runtime.reset_with_participants(
        policy.clock_address,
        False,
        participant_runtime,
        requests,
        snapshot,
    )

    assert not reset.success
    assert reset.snapshot == snapshot
    assert participant_runtime.results() == predecessor_results
    assert participant_runtime.history() == predecessor_history


def test_base_batch_reset_refuses_subclass_native_reset_without_atomic_override() -> None:
    participant_runtime = _SecondResetFailParticipantRuntime()
    address = "participant.behavior.participant-agent"
    snapshot = participant_runtime.initialize(
        ParticipantEpisodeInitializeRequest(participant_address=address),
        RuntimeSnapshot(),
    ).snapshot

    result = participant_runtime.reset_many(
        (ParticipantEpisodeResetRequest(participant_address=address),),
        snapshot,
    )

    assert not result.success
    assert result.snapshot == snapshot
    assert participant_runtime.reset_calls == 0
    assert "must implement their own atomic reset_many" in result.diagnostics[0].message


def test_runtime_target_rejects_autonomous_claim_without_native_binding_method() -> None:
    runtime_model, _ = _compiled()
    target = create_stub_target()
    manifest = _autonomous_manifest(runtime_model)

    with pytest.raises(ValueError, match="bind_autonomous_action"):
        replace(target, manifest=manifest)


def test_runtime_target_rejects_coordinated_reset_claim_without_batch_reset_method() -> None:
    runtime_model, _ = _compiled()
    target = create_stub_target()
    manifest = _autonomous_manifest(runtime_model)
    participant_runtime = _NoBatchResetParticipantRuntime()

    with pytest.raises(ValueError, match="reset_many"):
        replace(
            target,
            manifest=manifest,
            participant_runtime=participant_runtime,
        )


def test_scheduler_executes_native_actions_and_persists_shared_time_readback() -> None:
    runtime_model, policy = _compiled()
    scheduler = ParticipantScheduler()
    participant_runtime = _NativeParticipantRuntime()
    coordinator = TimeCoordinator(runtime_model.time_model)
    snapshot = coordinator.initialize()

    initialized = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        snapshot,
    )
    assert initialized.success
    first = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        initialized.snapshot,
    )
    assert first.success
    assert participant_runtime.native_actions == [
        "participant.autonomous-execution.participant-behavior:participant.behavior.participant-agent:0"
    ]
    assert first.snapshot.metadata["last_native_action"] == participant_runtime.native_actions[0]

    state_key = "participant.autonomous-execution.participant-behavior.state.participant.behavior.participant-agent"
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        first.snapshot.participant_autonomous_execution_states[state_key]
    )
    assert (state.attempted_actions, state.succeeded_actions, state.next_tick) == (1, 1, 10)
    assert state.time_segment == 0
    assert state.policy_digest == "sha256:2fb5d1cbbde0d3c7554fac379e1f58fd39f6b74c98b0267f28fcd7b9a4cca9d8"
    events = first.snapshot.participant_behavior_history[state.participant_address]
    assert [event["event_type"] for event in events] == [
        "action_attempted",
        "state_transition_recorded",
        "observation_emitted",
    ]
    assert all(
        event["temporal_contexts"][0]["temporal_contract_id"] == "time.constraint.green-cadence" for event in events
    )
    assert all("segment=0,tick=0" in event["temporal_contexts"][0]["observation_point"] for event in events)

    reapplied = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        first.snapshot,
    )
    preserved = ParticipantAutonomousExecutionStateModel.model_validate(
        reapplied.snapshot.participant_autonomous_execution_states[state_key]
    )
    assert preserved.attempted_actions == 1

    paused = scheduler.set_clock_lifecycle(reapplied.snapshot, policy.clock_address, "paused").snapshot
    paused_state = ParticipantAutonomousExecutionStateModel.model_validate(
        paused.participant_autonomous_execution_states[state_key]
    )
    assert paused_state.lifecycle_state == "paused"
    paused_service = ParticipantExecutionServiceStateModel.model_validate(
        paused.participant_execution_services[policy.address]
    )
    assert paused_service.observed_lifecycle == "paused"
    assert paused_service.accepting_new_work is False
    paused_due = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        paused,
    )
    assert paused_due.success
    assert len(participant_runtime.native_actions) == 1
    resumed = scheduler.set_clock_lifecycle(paused, policy.clock_address, "running").snapshot

    advanced = coordinator.advance(resumed, policy.clock_address, ticks=10)
    second = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        advanced,
    )
    completed = ParticipantAutonomousExecutionStateModel.model_validate(
        second.snapshot.participant_autonomous_execution_states[state_key]
    )
    assert completed.lifecycle_state == "completed"
    assert completed.attempted_actions == 2

    reset_time = coordinator.reset(second.snapshot, policy.clock_address)
    reset = scheduler.reset_clock(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        reset_time,
        policy.clock_address,
    )
    reset_state = ParticipantAutonomousExecutionStateModel.model_validate(
        reset.snapshot.participant_autonomous_execution_states[state_key]
    )
    assert (reset_state.lifecycle_state, reset_state.attempted_actions, reset_state.next_tick) == (
        "running",
        0,
        0,
    )
    assert reset.snapshot.participant_episode_results[state.participant_address]["sequence_number"] == 1


def test_scheduler_rejects_reapplication_after_material_policy_change() -> None:
    runtime_model, policy = _compiled()
    scheduler = ParticipantScheduler()
    participant_runtime = _NativeParticipantRuntime()
    snapshot = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    ).snapshot

    changed = scheduler.initialize(
        [replace(policy, max_action_attempts=policy.max_action_attempts + 1)],
        runtime_model.time_model,
        participant_runtime,
        snapshot,
    )

    assert not changed.success
    assert changed.diagnostics[0].code == "runtime.participant-autonomous-state-conflict"


def test_scheduler_rejects_v2_continuation_after_material_policy_change() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_activity_policy_yaml()))
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution
    assert policy is not None
    scheduler = ParticipantScheduler()
    controls = resolve_participant_activity_controls([_activity_control()])
    initialized = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        _NativeParticipantRuntime(),
        TimeCoordinator(runtime_model.time_model).initialize(),
        controls,
    )
    assert initialized.success

    changed = scheduler.initialize(
        [replace(policy, timing_maximum_ticks=policy.timing_maximum_ticks + 10)],
        runtime_model.time_model,
        _NativeParticipantRuntime(),
        initialized.snapshot,
        controls,
    )

    assert not changed.success
    assert changed.diagnostics[0].code == "runtime.participant-autonomous-state-conflict"


def test_scheduler_rejects_reapplication_after_referenced_cadence_change() -> None:
    runtime_model, policy = _compiled()
    scheduler = ParticipantScheduler()
    participant_runtime = _NativeParticipantRuntime()
    snapshot = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    ).snapshot
    changed_constraint = replace(runtime_model.time_model.constraints[0], cadence_ticks=20)
    changed_time_model = replace(runtime_model.time_model, constraints=(changed_constraint,))

    changed = scheduler.initialize(
        [policy],
        changed_time_model,
        participant_runtime,
        snapshot,
    )

    assert not changed.success
    assert changed.diagnostics[0].code == "runtime.participant-autonomous-state-conflict"


def test_scheduler_counts_native_action_outcome_not_control_plane_success() -> None:
    runtime_model, policy = _compiled()
    scheduler = ParticipantScheduler()
    participant_runtime = _FailedParticipantRuntime()
    initialized = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    )

    result = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        initialized.snapshot,
    )

    assert not result.success
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(result.snapshot.participant_autonomous_execution_states.values()))
    )
    assert (state.lifecycle_state, state.succeeded_actions, state.failed_actions) == ("failed", 0, 1)
    observation = result.snapshot.participant_behavior_history[state.participant_address][-1]
    assert observation["action_result"]["status"] == "failed"


@pytest.mark.parametrize("runtime_type", [_MissingOutcomeRuntime, _ContradictoryTimeRuntime])
def test_scheduler_rejects_invalid_native_outcome_before_committing_history_or_snapshot(
    runtime_type: type[_NativeParticipantRuntime],
) -> None:
    runtime_model, policy = _compiled()
    scheduler = ParticipantScheduler()
    participant_runtime = runtime_type()
    initialized = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    )

    result = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        initialized.snapshot,
    )

    assert not result.success
    assert "last_native_action" not in result.snapshot.metadata
    assert result.snapshot.participant_behavior_history == {}
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(result.snapshot.participant_autonomous_execution_states.values()))
    )
    assert (state.lifecycle_state, state.attempted_actions, state.failed_actions) == ("failed", 1, 1)
    repeated = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        result.snapshot,
    )
    assert repeated.success
    assert len(participant_runtime.native_actions) == 1


@pytest.mark.parametrize(
    "runtime_type",
    [
        _PlainApplyParticipantRuntime,
        _NonResultParticipantRuntime,
        _DirectContradictoryParticipantRuntime,
        _StaleHistoryParticipantRuntime,
        _IncompleteHistoryParticipantRuntime,
        _WrongProvenanceParticipantRuntime,
    ],
)
def test_scheduler_fails_closed_for_nonconforming_direct_runtime(
    runtime_type: type[_NativeParticipantRuntime],
) -> None:
    runtime_model, policy = _compiled()
    scheduler = ParticipantScheduler()
    participant_runtime = runtime_type()
    initialized = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    )

    result = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        initialized.snapshot,
    )

    assert not result.success
    assert result.diagnostics[-1].code == "runtime.participant-autonomous-action-protocol-invalid"
    assert "direct_native_mutation" not in result.snapshot.metadata
    assert result.snapshot.participant_behavior_history == {}


def test_semantics_rejects_unreachable_stepped_cadence() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 5
    scenario_yaml = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="cadence points are unreachable"):
        parse_sdl(scenario_yaml)


def test_semantics_rejects_externally_paced_autonomous_clock_without_driver() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "externally_paced"
    progression.pop("step_ticks")
    scenario_yaml = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="has no portable runtime transition driver"):
        parse_sdl(scenario_yaml)


def test_semantics_rejects_negative_autonomous_cadence_start() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["temporal_constraints"]["green-cadence"]["start"]["tick"] = -10
    scenario_yaml = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="cadence points are unreachable"):
        parse_sdl(scenario_yaml)


def test_semantics_rejects_backend_authority_for_wall_paced_autonomous_clock() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["clocks"]["scenario-clock"]["authority_kind"] = "backend"
    payload["clocks"]["scenario-clock"]["authority_ref"] = "backend.clock"
    scenario_yaml = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(SDLValidationError, match="must use runtime authority"):
        parse_sdl(scenario_yaml)


def test_runtime_manager_automatically_drives_wall_paced_participant_clock() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 100}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target)

    applied = manager.apply(manager.plan(scenario))
    deadline = time.monotonic() + 1.0
    while len(participant_runtime.native_actions) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert applied.success
    assert len(participant_runtime.native_actions) == 2
    assert manager.participant_clock_driver_status()["active"] is True
    manager.destroy()
    assert manager.participant_clock_driver_status()["active"] is False


def test_wall_driver_cannot_advance_during_time_state_readback() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 20}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    time_runtime = _BlockingReadTimeRuntime()
    manager = RuntimeManager(
        replace(
            create_stub_target(),
            manifest=_autonomous_manifest(runtime_model),
            participant_runtime=_NativeParticipantRuntime(),
            time_runtime=time_runtime,
        )
    )
    assert manager.apply(manager.plan(scenario)).success
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    time_runtime.block_reads = True
    outcome: list[TimeRuntimeStateModel | Exception] = []

    def read_state() -> None:
        try:
            outcome.append(manager.read_time_state())
        except Exception as exc:
            outcome.append(exc)

    reader = threading.Thread(target=read_state)
    reader.start()
    assert time_runtime.read_entered.wait(timeout=1.0)
    predecessor = manager.snapshot
    assert predecessor.time_model_state is not None
    predecessor_coordinate = predecessor.time_model_state.clocks[policy.clock_address].coordinate
    time.sleep(0.1)

    assert manager.snapshot == predecessor
    time_runtime.read_release.set()
    reader.join(timeout=1.0)
    assert not reader.is_alive()
    assert len(outcome) == 1
    assert not isinstance(outcome[0], Exception)
    state = outcome[0]
    assert isinstance(state, TimeRuntimeStateModel)
    assert state.clocks[policy.clock_address].coordinate == predecessor_coordinate
    assert manager.destroy().success


def test_wall_driver_recomputes_after_pause_and_resume() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 5}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    manager = RuntimeManager(
        replace(
            create_stub_target(),
            manifest=_autonomous_manifest(runtime_model),
            participant_runtime=participant_runtime,
        )
    )
    assert manager.apply(manager.plan(scenario)).success
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )

    assert manager.pause_time(policy.clock_address).success
    time.sleep(0.25)
    assert manager.read_time_state().clocks[policy.clock_address].coordinate.tick == 0
    assert manager.resume_time(policy.clock_address).success
    deadline = time.monotonic() + 1.0
    while len(participant_runtime.native_actions) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert len(participant_runtime.native_actions) == 2
    assert manager.participant_clock_driver_status()["failure"] is None
    assert manager.destroy().success


def test_wall_driver_discards_transition_stale_after_manual_advance() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 5}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    manager = RuntimeManager(
        replace(
            create_stub_target(),
            manifest=_autonomous_manifest(runtime_model),
            participant_runtime=participant_runtime,
        )
    )
    assert manager.apply(manager.plan(scenario)).success
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )

    assert manager.advance_time(policy.clock_address, ticks=1).success
    time.sleep(0.25)

    assert manager.read_time_state().clocks[policy.clock_address].coordinate.tick == 1
    assert len(participant_runtime.native_actions) == 2
    assert manager.destroy().success


def test_wall_driver_stop_keeps_live_thread_owned_until_it_exits() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 100}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    participant_runtime = _NativeParticipantRuntime()
    scheduler = ParticipantScheduler()
    snapshot = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    ).snapshot
    snapshot = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        snapshot,
    ).snapshot
    entered = threading.Event()
    release = threading.Event()

    def blocking_advance(_clock_address: str, _ticks: int) -> ApplyResult:
        entered.set()
        release.wait(timeout=1.0)
        return ApplyResult(success=True, snapshot=snapshot)

    driver = ParticipantClockDriver(
        [policy],
        runtime_model.time_model,
        snapshot=lambda: snapshot,
        advance=blocking_advance,
        service_due=lambda: ApplyResult(success=True, snapshot=snapshot),
        lock=threading.RLock(),
    )
    driver.start()
    assert entered.wait(timeout=1.0)

    assert driver.stop(timeout=0.01) is False
    assert driver.active
    release.set()
    assert driver.stop(timeout=1.0) is True
    assert not driver.active


def test_wall_driver_records_an_unexpected_runtime_exception() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 100}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    participant_runtime = _NativeParticipantRuntime()
    scheduler = ParticipantScheduler()
    snapshot = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    ).snapshot
    snapshot = scheduler.run_due(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        snapshot,
    ).snapshot

    def failing_advance(_clock_address: str, _ticks: int) -> ApplyResult:
        raise RuntimeError("clock backend failed")

    driver = ParticipantClockDriver(
        [policy],
        runtime_model.time_model,
        snapshot=lambda: snapshot,
        advance=failing_advance,
        service_due=lambda: ApplyResult(success=True, snapshot=snapshot),
        lock=threading.RLock(),
    )
    driver.start()
    deadline = time.monotonic() + 1.0
    while driver.failure is None and time.monotonic() < deadline:
        time.sleep(0.01)

    assert driver.failure is not None
    assert driver.failure.diagnostics[0].code == "runtime.participant-clock-driver-failed"
    execution_state = ParticipantExecutionServiceStateModel.model_validate(
        driver.failure.snapshot.participant_execution_services[policy.address]
    )
    assert execution_state.health == "degraded"
    assert execution_state.readiness == "not_ready"
    assert execution_state.accepting_new_work is False
    assert execution_state.pacing_deviation_refs
    assert driver.stop()


def test_runtime_manager_refuses_destroy_while_clock_driver_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = RuntimeManager(create_stub_target())
    monkeypatch.setattr(manager, "_stop_participant_clock_driver", lambda: False)

    result = manager.destroy()

    assert not result.success
    assert result.diagnostics[0].code == "runtime.participant-clock-driver-stop-timeout"


def test_preserve_value_reset_selects_reachable_cadence() -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_progression_policies"]["scenario-progression"]["reset_behavior"] = "new_segment_preserve_value"
    scenario = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    manager = RuntimeManager(
        replace(
            create_stub_target(),
            manifest=_autonomous_manifest(runtime_model),
            participant_runtime=participant_runtime,
        )
    )
    assert manager.apply(manager.plan(scenario)).success
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    assert manager.advance_time(policy.clock_address, ticks=10).success

    reset = manager.reset_time(policy.clock_address)

    assert reset.success
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(reset.snapshot.participant_autonomous_execution_states.values()))
    )
    assert (state.time_segment, state.next_tick, state.attempted_actions) == (1, 10, 0)
    assert manager.run_due_participant_actions().success


def test_runtime_snapshot_rejects_misaddressed_autonomous_execution_state() -> None:
    state = ParticipantAutonomousExecutionStateModel(
        policy_address="participant.autonomous-execution.green-users",
        policy_digest="sha256:" + "0" * 64,
        participant_address="participant.behavior.green-user",
        episode_id="participant.behavior.green-user-autonomous-0",
        participant_implementation_ref=IMPLEMENTATION_REF,
        clock_address="time.clock.scenario-clock",
        time_segment=0,
        lifecycle_state="running",
        next_tick=0,
        next_action_index=0,
        attempted_actions=0,
        succeeded_actions=0,
        failed_actions=0,
    )

    with pytest.raises(ValueError, match="map key must equal"):
        RuntimeSnapshotEnvelopeModel(
            participant_autonomous_execution_states={"participant.autonomous-execution.wrong": state}
        )


def test_scheduler_rejects_an_unselected_participant_implementation() -> None:
    runtime_model, policy = _compiled()
    scheduler = ParticipantScheduler()
    participant_runtime = _NativeParticipantRuntime()
    snapshot = scheduler.initialize(
        [policy],
        runtime_model.time_model,
        participant_runtime,
        TimeCoordinator(runtime_model.time_model).initialize(),
    ).snapshot

    class WrongBindingRuntime(_NativeParticipantRuntime):
        def bind_autonomous_action(
            self,
            participant_address: str,
            action_contract_address: str,
            observation_boundary_address: str,
            participant_implementation_ref: str,
            action_instance_id: str,
            temporal_contexts: tuple[object, ...],
            snapshot: RuntimeSnapshot,
        ) -> ParticipantActionAdmissionRequest:
            request = super().bind_autonomous_action(
                participant_address,
                action_contract_address,
                observation_boundary_address,
                participant_implementation_ref,
                action_instance_id,
                temporal_contexts,
                snapshot,
            )
            return replace(
                request,
                implementation_selection=request.implementation_selection.model_copy(
                    update={"manifest_ref": "participant-implementation-manifests.other.v1"}
                ),
            )

    participant_runtime = WrongBindingRuntime()
    with pytest.raises(ValueError, match="does not match the autonomous execution policy"):
        scheduler.run_due(
            [policy],
            runtime_model.time_model,
            participant_runtime,
            snapshot,
        )
    assert participant_runtime.native_actions == []
