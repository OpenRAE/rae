"""Execution-service state coordination for the autonomous scheduler."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.contracts.participant_resource_budgets import participant_resource_budget_state_ref
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime


def _payload_digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def execution_service_state(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    *,
    policy_digest: str,
) -> ParticipantExecutionServiceStateModel:
    """Build typed execution-service readback for one admitted policy."""

    clock = next(item for item in time_model.clocks if item.address == policy.clock_address)
    progression = next(
        item for item in time_model.progression_policies if item.address == policy.progression_policy_address
    )
    constraints = tuple(
        asdict(item)
        for item in time_model.constraints
        if item.address
        in {
            *policy.temporal_constraint_addresses,
            *(binding.constraint_address for binding in policy.temporal_bindings),
        }
    )
    return ParticipantExecutionServiceStateModel(
        execution_scope_ref=policy.address,
        policy_address=policy.address,
        desired_lifecycle="running",
        observed_lifecycle="running",
        generation=0,
        observed_generation=0,
        health="healthy",
        readiness="ready",
        accepting_new_work=True,
        draining=False,
        quiescent=True,
        resources_released=False,
        policy_digest=policy_digest,
        binding_digest=_payload_digest(tuple(asdict(binding) for binding in policy.execution_bindings)),
        time_declaration_digest=_payload_digest(
            {
                "clock": asdict(clock),
                "progression": asdict(progression),
                "constraints": constraints,
            }
        ),
        scheduler_state_refs=tuple(
            f"{policy.address}.state.{participant_address}" for participant_address in policy.participant_addresses
        ),
        resource_budget_state_refs=(
            tuple(
                participant_resource_budget_state_ref(policy.address, demand.budget_id)
                for demand in policy.resource_demands
            )
            if policy.profile == "participant-autonomous-execution/v3"
            else ()
        ),
        capacity=policy.max_in_flight,
        reserved=0,
        in_flight=0,
        last_transition_ref=f"operation:{policy.address}:start:generation-0",
        evidence_refs=(f"evidence:{policy.address}:readiness:generation-0",),
    )


def reset_execution_service(
    snapshot: RuntimeSnapshot,
    policy_address: str,
) -> tuple[RuntimeSnapshot, bool]:
    """Advance the service generation after a shared-clock reset."""

    services = dict(snapshot.participant_execution_services)
    payload = services.get(policy_address)
    if payload is None:
        return snapshot, False
    service = ParticipantExecutionServiceStateModel.model_validate(payload)
    generation = service.generation + 1
    evidence_ref = f"evidence:{policy_address}:shared-time-reset:generation-{generation}"
    services[policy_address] = service.model_copy(
        update={
            "desired_lifecycle": "running",
            "observed_lifecycle": "running",
            "generation": generation,
            "observed_generation": generation,
            "readiness": "ready",
            "accepting_new_work": True,
            "draining": False,
            "quiescent": True,
            "reserved": 0,
            "in_flight": 0,
            "last_transition_ref": (f"operation:{policy_address}:shared-time-reset:generation-{generation}"),
            "evidence_refs": tuple(dict.fromkeys([*service.evidence_refs, evidence_ref])),
        }
    ).model_dump(mode="json")
    return (
        snapshot.with_entries(
            dict(snapshot.entries),
            participant_execution_services=services,
        ),
        True,
    )


def set_execution_clock_lifecycle(
    snapshot: RuntimeSnapshot,
    clock_address: str,
    lifecycle_state: str,
) -> ApplyResult:
    """Coordinate shared-clock lifecycle with scheduler and service readback."""

    states = dict(snapshot.participant_autonomous_execution_states)
    services = dict(snapshot.participant_execution_services)
    changed: list[str] = []
    affected_policies: set[str] = set()
    for key, payload in list(states.items()):
        state = ParticipantAutonomousExecutionStateModel.model_validate(payload)
        if state.clock_address == clock_address and state.lifecycle_state not in {"completed", "failed"}:
            states[key] = state.model_copy(update={"lifecycle_state": lifecycle_state}).model_dump(mode="json")
            changed.append(key)
            affected_policies.add(state.policy_address)
    for policy_address in affected_policies:
        service_payload = services.get(policy_address)
        if service_payload is None:
            continue
        service = ParticipantExecutionServiceStateModel.model_validate(service_payload)
        paused = lifecycle_state == "paused"
        evidence_ref = f"evidence:{policy_address}:shared-time-{lifecycle_state}:generation-{service.generation}"
        services[policy_address] = service.model_copy(
            update={
                "desired_lifecycle": lifecycle_state,
                "observed_lifecycle": lifecycle_state,
                "readiness": "not_ready" if paused else "ready",
                "accepting_new_work": not paused,
                "last_transition_ref": (
                    f"operation:{policy_address}:shared-time-{lifecycle_state}:generation-{service.generation}"
                ),
                "evidence_refs": tuple(dict.fromkeys([*service.evidence_refs, evidence_ref])),
            }
        ).model_dump(mode="json")
        changed.append(policy_address)
    return ApplyResult(
        success=True,
        snapshot=snapshot.with_entries(
            dict(snapshot.entries),
            participant_autonomous_execution_states=states,
            participant_execution_services=services,
        ),
        changed_addresses=changed,
    )


__all__ = [
    "execution_service_state",
    "reset_execution_service",
    "set_execution_clock_lifecycle",
]
