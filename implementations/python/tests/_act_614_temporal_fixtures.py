"""ACT-614 temporal fixtures."""

from __future__ import annotations

from dataclasses import replace

import yaml
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    _autonomous_manifest,
    _NativeParticipantRuntime,
    _scenario_yaml,
)
from raes.parser import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model


def _bound_deadline_payload(event: str = "end") -> dict:
    payload = yaml.safe_load(_scenario_yaml())
    payload["temporal_constraints"]["finish-by-five"] = {
        "constraint_kind": "deadline",
        "clock_ref": "scenario-clock",
        "subject_refs": ["action_contracts.probe-customer-portal-login"],
        "end": {"tick": 5},
        "description": "The selected action event must occur no later than tick five.",
    }
    action = payload["action_contracts"]["probe-customer-portal-login"]
    action["temporal_contracts"] = [
        {
            "temporal_id": "finish",
            "temporal_kind": "deadline",
            "time_domain": "simulation_time",
            "clock_authority": "scenario-clock",
            "event_points": [event, "deadline"],
            "description": "Bounded action deadline.",
            "duration_ref": "finish-by-five",
            "reset_boundary": "fresh-segment",
            "replay_boundary": "fresh-evidence",
            "ordering_basis": "shared-superdense-time",
            "backend_disclosure_refs": ["timing"],
            "shared_time_binding": {
                "profile": "participant-shared-time/v1",
                "clock_ref": "scenario-clock",
                "constraint_ref": "finish-by-five",
                "event_point": event,
                "evidence_mode": "event",
            },
        }
    ]
    action["backend_timing_disclosures"] = [
        {
            "disclosure_id": "timing",
            "disclosure_kind": "synchronization",
            "support_mode": "exact",
            "description": "Admission requires exact bound-event evidence from the selected backend.",
            "affected_temporal_ids": ["finish"],
        }
    ]
    return payload


def _temporal_target(payload: dict, runtime=None):
    scenario = parse_sdl(yaml.safe_dump(payload))
    model = compile_runtime_model(scenario)
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    if policy.profile == "participant-autonomous-execution/v3":
        from implementations.python.tests.test_issue_899_participant_resource_budgets import _governed_manifest

        manifest = _governed_manifest()
    else:
        manifest = _autonomous_manifest(model)
    capability = manifest.participant_runtime
    offers = tuple(
        replace(
            offer,
            temporal_contract_digests=tuple(
                binding.contract_digest
                for binding in policy.temporal_bindings
                if binding.action_contract_address == offer.action_contract_address
            ),
        )
        for offer in capability.execution_bindings
    )
    manifest = replace(
        manifest,
        capabilities=replace(manifest.capabilities, participant_runtime=replace(capability, execution_bindings=offers)),
    )
    runtime = runtime or _NativeParticipantRuntime()
    return scenario, replace(create_stub_target(), manifest=manifest, participant_runtime=runtime)


class _TemporalEvidenceRuntime(_NativeParticipantRuntime):
    def __init__(self, *, mutation: str | None = None):
        super().__init__()
        self.mutation = mutation
        self.previous_evidence = None

    def bind_autonomous_action(self, *args):
        request = super().bind_autonomous_action(*args)
        return replace(request, observation_boundary_evidence_refs=("content.participant-observation",))

    def admit_actions_concurrently(self, requests, snapshot, max_in_flight):
        assert len(requests) <= max_in_flight
        return tuple(self.admit_action(request, snapshot) for request in requests)

    def _model_action(self, request, snapshot, *, episode_id):
        from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel

        native = super()._model_action(request, snapshot, episode_id=episode_id)
        evidence = []
        for context in request.temporal_contexts:
            scope = context.shared_time
            if scope is None or scope.binding.temporal_kind != "deadline":
                continue
            coordinate = scope.submitted_at.model_dump()
            payload = {
                "context": scope.model_dump(mode="json"),
                "observation_boundary_address": request.observation_boundary_address,
                "event_point": scope.binding.event_point,
                "coordinate": coordinate,
                "evidence_refs": ["content.participant-observation"],
            }
            if self.mutation == "future":
                coordinate["tick"] += 10
            elif self.mutation == "event":
                payload["event_point"] = "start"
            elif self.mutation == "boundary":
                payload["observation_boundary_address"] = "participant.observation-boundary.other"
            elif self.mutation in {"episode_id", "action_instance_id"}:
                payload["context"][self.mutation] = "another"
            elif self.mutation == "execution_generation":
                payload["context"][self.mutation] += 1
            elif self.mutation == "segment":
                coordinate["segment"] += 1
            evidence.append(ParticipantTemporalEvidenceModel.model_validate(payload))
        if self.mutation == "reused" and self.previous_evidence is not None:
            evidence = self.previous_evidence
        self.previous_evidence = evidence
        return replace(
            native,
            apply_result=replace(native.apply_result, snapshot=snapshot),
            action_result=native.action_result.model_copy(update={"temporal_evidence": evidence}),
        )


def _bound_dwell_payload() -> dict:
    payload = _bound_deadline_payload("start")
    # The condition must be visible before dispatch, not revealed by the action.
    payload["observation_boundaries"]["participant-view"] = {
        "projection_basis": "Declared target condition and evidence.",
        "observable_refs": ["nodes.customer-portal.services.http"],
        "evidence_refs": ["content.participant-observation"],
        "redaction_policy": "No backend-private data.",
        "latency_profile": "continuous condition coverage",
        "observer_effects": ["Observation may create service logs"],
        "realized_view_disclosure": "Only declared condition and evidence.",
    }
    payload["temporal_constraints"].pop("finish-by-five")
    payload["temporal_constraints"]["hold-window"] = {
        "constraint_kind": "window",
        "clock_ref": "scenario-clock",
        "subject_refs": ["action_contracts.probe-customer-portal-login"],
        "start": {"tick": 0},
        "end": {"tick": 10},
        "description": "The condition must hold throughout [0, 10) before dispatch.",
    }
    payload["temporal_constraints"]["green-cadence"]["start"] = {"tick": 10}
    temporal = payload["action_contracts"]["probe-customer-portal-login"]["temporal_contracts"][0]
    temporal.update(
        temporal_kind="dwell", event_points=["start", "end"], window_ref="hold-window", duration_ref="hold-window"
    )
    temporal["shared_time_binding"].update(
        constraint_ref="hold-window",
        evidence_mode="continuous",
        condition_precondition_id="portal-present",
        observation_boundary_ref="participant-view",
    )
    return payload


class _DwellEvidenceRuntime(_TemporalEvidenceRuntime):
    def bind_autonomous_action(self, *args):
        from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel

        request = super().bind_autonomous_action(*args)
        proofs = []
        for context in request.temporal_contexts:
            scope = context.shared_time
            if scope is None or scope.binding.temporal_kind != "dwell":
                continue
            if self.mutation == "missing":
                continue
            coverage = [{"start": {"tick": 0}, "end": {"tick": 10}, "condition_holds": True}]
            if self.mutation == "gap":
                coverage = [
                    {"start": {"tick": 0}, "end": {"tick": 4}, "condition_holds": True},
                    {"start": {"tick": 6}, "end": {"tick": 10}, "condition_holds": True},
                ]
            elif self.mutation == "false":
                coverage[0]["condition_holds"] = False
            elif self.mutation == "endpoints":
                coverage = [
                    {"start": {"tick": tick}, "end": {"tick": tick}, "condition_holds": True} for tick in (0, 10)
                ]
            proof = {
                "context": scope.model_dump(mode="json"),
                "observation_boundary_address": request.observation_boundary_address,
                "evidence_mode": "sampled" if self.mutation == "endpoints" else "continuous",
                "condition_precondition_id": "portal-present",
                "coverage": coverage,
                "evidence_refs": ["content.participant-observation"],
            }
            if self.mutation == "wrong_condition":
                proof["condition_precondition_id"] = "participant-authorized"
            proofs.append(ParticipantTemporalEvidenceModel.model_validate(proof))
        return replace(request, temporal_evidence=tuple(proofs))


def _activity_temporal_payload(source) -> dict:
    payload = yaml.safe_load(source())
    bound = _bound_deadline_payload()
    payload["action_contracts"] = bound["action_contracts"]
    payload["temporal_constraints"]["finish-by-five"] = bound["temporal_constraints"]["finish-by-five"]
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["failure_policy"] = "stop"
    return payload
