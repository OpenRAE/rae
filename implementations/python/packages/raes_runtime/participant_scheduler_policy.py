"""Canonical autonomous participant policy identity."""

import hashlib
import json
from dataclasses import asdict

from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime


def _policy_digest(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
) -> str:
    clock = next(item for item in time_model.clocks if item.address == policy.clock_address)
    progression = next(
        item for item in time_model.progression_policies if item.address == policy.progression_policy_address
    )
    domain = next(item for item in time_model.domains if item.address == clock.time_domain_address)
    constraints = sorted(
        (asdict(item) for item in time_model.constraints if item.address in policy.temporal_constraint_addresses),
        key=lambda item: str(item["address"]),
    )
    payload = {
        "address": policy.address,
        "participant_addresses": policy.participant_addresses,
        "participant_implementation_ref": policy.participant_implementation_ref,
        "clock_address": policy.clock_address,
        "progression_policy_address": policy.progression_policy_address,
        "temporal_constraint_addresses": policy.temporal_constraint_addresses,
        "action_contract_addresses": policy.action_contract_addresses,
        "target_addresses": policy.target_addresses,
        "execution_bindings": tuple(asdict(binding) for binding in policy.execution_bindings),
        "observation_boundary_address": policy.observation_boundary_address,
        "selection_strategy": policy.selection_strategy,
        "max_action_attempts": policy.max_action_attempts,
        "max_in_flight": policy.max_in_flight,
        "failure_policy": policy.failure_policy,
        "evaluation_authority_mode": policy.evaluation_authority_mode,
        "objective_refs": policy.objective_refs,
        "proof_producer_refs": policy.proof_producer_refs,
        "score_authority_refs": policy.score_authority_refs,
        "receipt_authority_refs": policy.receipt_authority_refs,
        "resolved_clock": asdict(clock),
        "resolved_time_domain": asdict(domain),
        "resolved_progression_policy": asdict(progression),
        "resolved_temporal_constraints": constraints,
    }
    if policy.temporal_bindings:
        payload["temporal_bindings"] = [binding.model_dump(mode="json") for binding in policy.temporal_bindings]
        payload["observation_boundary_evidence_refs"] = policy.observation_boundary_evidence_refs
    if policy.profile in {
        "participant-autonomous-execution/v2",
        "participant-autonomous-execution/v3",
    }:
        payload.update(
            {
                "profile": policy.profile,
                "work_window_addresses": policy.work_window_addresses,
                "pause_window_addresses": policy.pause_window_addresses,
                "stochastic_control_ref": policy.stochastic_control_ref,
                "timing_minimum_ticks": policy.timing_minimum_ticks,
                "timing_maximum_ticks": policy.timing_maximum_ticks,
                "outside_window_disposition": policy.outside_window_disposition,
                "empty_eligible_disposition": policy.empty_eligible_disposition,
                "action_candidate_ids": policy.action_candidate_ids,
                "action_candidate_weights": policy.action_candidate_weights,
                "action_candidate_dependencies": policy.action_candidate_dependencies,
                "action_candidate_retry_failure_classes": (policy.action_candidate_retry_failure_classes),
                "action_candidate_max_retries": policy.action_candidate_max_retries,
                "action_candidate_cooldown_ticks": policy.action_candidate_cooldown_ticks,
                "max_occurrences": policy.max_occurrences,
                "max_burst_size": policy.max_burst_size,
            }
        )
    if policy.profile == "participant-autonomous-execution/v3":
        payload.update(
            {
                "resource_owners": tuple(asdict(owner) for owner in policy.resource_owners),
                "resource_demands": tuple(asdict(demand) for demand in policy.resource_demands),
                "resource_fairness": asdict(policy.resource_fairness),
            }
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
