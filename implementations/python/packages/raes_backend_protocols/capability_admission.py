"""Admission checks that bind backend capabilities to portable contracts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

from .capabilities import (
    OBSERVATION_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_ROLE_SCOPE,
)
from .participant_feature_admission import (
    participant_feature_support_gaps,
    resolve_participant_feature_support,
)
from .participant_resource_admission import (
    ResourceGovernedPolicy,
    participant_resource_budget_gaps,
)

if TYPE_CHECKING:
    from raes_contracts.contracts.time_model import TimeModelDeclarationModel
    from raes_contracts.contracts.trial_cleanup import TrialCleanupPlanModel

    from .backend_manifest import BackendManifest
    from .capabilities import ParticipantRuntimeCapabilities, TimeCapabilities


class AutonomousExecutionPolicy(ResourceGovernedPolicy, Protocol):
    profile: str
    participant_addresses: tuple[str, ...]
    action_contract_addresses: tuple[str, ...]
    target_addresses: tuple[str, ...]
    observation_boundary_address: str
    max_action_attempts: int
    max_in_flight: int
    selection_strategy: str
    action_candidate_max_retries: tuple[int, ...]
    max_occurrences: int
    max_burst_size: int
    execution_bindings: tuple[object, ...]
    timing_minimum_ticks: int
    timing_maximum_ticks: int
    action_candidate_dependencies: tuple[tuple[str, ...], ...]
    action_candidate_cooldown_ticks: tuple[int, ...]


_V2_RANDOM_STREAM_PROFILE = "blake3-xof-participant-v1"


def _required_activity_features(policy: AutonomousExecutionPolicy) -> set[str]:
    """Derive required support from the request, not a richest-profile bundle."""

    features = {"work-windows", "weighted-selection", "occurrence-provenance"}
    if policy.timing_minimum_ticks != policy.timing_maximum_ticks:
        features.add("timing-variation")
    if any(policy.action_candidate_dependencies):
        features.add("dependencies")
    if any(policy.action_candidate_max_retries):
        features.add("bounded-retries")
    if any(policy.action_candidate_cooldown_ticks):
        features.add("cooldowns")
    if policy.max_burst_size > 1:
        features.add("limited-bursts")
    return features


def participant_runtime_capability_contract_gaps(manifest: BackendManifest) -> tuple[str, ...]:
    """Return missing contract surfaces for declared standard API-405 claims."""

    participant_runtime = manifest.participant_runtime
    if participant_runtime is None:
        return ()

    declared_terms = {
        PARTICIPANT_RUNTIME_ROLE_SCOPE: participant_runtime.supported_participant_roles,
        PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE: participant_runtime.supported_behavior_features,
        PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE: participant_runtime.supported_interaction_features,
    }
    gaps: list[str] = []
    for scope, terms in declared_terms.items():
        required_by_term = PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[scope]
        for term in sorted(terms):
            required_contracts = required_by_term.get(term)
            if required_contracts is None:
                continue
            missing = sorted(required_contracts - manifest.supported_contract_versions)
            if missing:
                gaps.append(f"{scope}.{term} missing required contracts: {', '.join(missing)}")
    return tuple(gaps)


def _autonomous_limit_gaps(
    capability: ParticipantRuntimeCapabilities,
    policies: tuple[AutonomousExecutionPolicy, ...],
) -> list[str]:
    gaps: list[str] = []
    participant_count = len({participant for policy in policies for participant in policy.participant_addresses})
    limits = (
        ("participants", participant_count, capability.max_autonomous_participants),
        (
            "action attempts",
            max(policy.max_action_attempts for policy in policies),
            capability.max_autonomous_action_attempts,
        ),
        (
            "in-flight actions",
            max(policy.max_in_flight for policy in policies),
            capability.max_autonomous_in_flight,
        ),
        (
            "occurrences",
            max((policy.max_occurrences or policy.max_action_attempts) for policy in policies),
            capability.max_autonomous_occurrences,
        ),
        (
            "retries per occurrence",
            max(max(policy.action_candidate_max_retries, default=0) for policy in policies),
            capability.max_autonomous_retries_per_occurrence,
        ),
        (
            "burst size",
            max(policy.max_burst_size for policy in policies),
            capability.max_autonomous_burst_size,
        ),
    )
    for label, required, supported in limits:
        if supported is None or required > supported:
            gaps.append(f"autonomous {label} require {required}, backend limit is {supported}")
    required_concurrency = max(policy.max_in_flight for policy in policies)
    if required_concurrency > 1 and not capability.supports_bounded_concurrency:
        gaps.append("autonomous in-flight actions require bounded concurrency support")
    if capability.max_concurrent_actions is None or required_concurrency > capability.max_concurrent_actions:
        gaps.append(
            f"autonomous in-flight actions require {required_concurrency}, backend concurrent-action "
            f"limit is {capability.max_concurrent_actions}"
        )
    return gaps


def _unsupported_autonomous_value_gaps(
    capability: ParticipantRuntimeCapabilities,
    policies: tuple[AutonomousExecutionPolicy, ...],
) -> list[str]:
    requirements = (
        (
            "selection strategies",
            {policy.selection_strategy for policy in policies},
            capability.supported_autonomous_selection_strategies,
        ),
        (
            "action contracts",
            {address for policy in policies for address in policy.action_contract_addresses},
            capability.supported_autonomous_action_contracts,
        ),
        (
            "observation boundaries",
            {policy.observation_boundary_address for policy in policies},
            capability.supported_autonomous_observation_boundaries,
        ),
        (
            "target addresses",
            {address for policy in policies for address in policy.target_addresses},
            capability.supported_autonomous_target_addresses,
        ),
        (
            "policy profiles",
            {policy.profile for policy in policies},
            capability.supported_autonomous_policy_profiles,
        ),
    )
    gaps = [
        f"unsupported autonomous {label}: {', '.join(unsupported)}"
        for label, required, supported in requirements
        if (unsupported := sorted(required - supported))
    ]
    activity_policies = tuple(
        policy
        for policy in policies
        if policy.profile in {"participant-autonomous-execution/v2", "participant-autonomous-execution/v3"}
    )
    if activity_policies:
        required_features = set().union(*(_required_activity_features(policy) for policy in activity_policies))
        missing_features = sorted(required_features - capability.supported_autonomous_activity_features)
        if missing_features:
            gaps.append(f"unsupported autonomous activity features: {', '.join(missing_features)}")
        if _V2_RANDOM_STREAM_PROFILE not in capability.supported_autonomous_random_stream_profiles:
            gaps.append(f"unsupported autonomous random-stream profiles: {_V2_RANDOM_STREAM_PROFILE}")
    return gaps


def _autonomous_execution_binding_gaps(
    capability: ParticipantRuntimeCapabilities,
    policies: tuple[AutonomousExecutionPolicy, ...],
) -> list[str]:
    gaps: list[str] = []
    declared = tuple(capability.execution_bindings)
    for policy in policies:
        for required in policy.execution_bindings:
            required_digests = {
                binding.contract_digest
                for binding in getattr(policy, "temporal_bindings", ())
                if binding.action_contract_address == required.action_contract_address
            }
            matching = [binding for binding in declared if _binding_identity_matches(binding, required)]
            exact = [binding for binding in matching if _binding_capacity_matches(binding, required, required_digests)]
            if exact:
                continue
            required_targets = ", ".join(required.target_addresses)
            gaps.append(
                "unsupported autonomous execution binding or temporal guarantee for "
                f"{required.action_contract_address} targets: {required_targets}"
            )
    return gaps


def _binding_identity_matches(binding: object, required: object) -> bool:
    return (
        binding.action_contract_address == required.action_contract_address
        and binding.participant_implementation_ref == required.participant_implementation_ref
    )


def _binding_capacity_matches(binding: object, required: object, required_digests: set[str]) -> bool:
    return (
        set(binding.target_addresses) == set(required.target_addresses)
        and binding.max_action_attempts >= required.max_action_attempts
        and binding.max_in_flight >= required.max_in_flight
        and required_digests.issubset(binding.temporal_contract_digests)
    )


def _requires_coordinated_reset(
    policies: tuple[AutonomousExecutionPolicy, ...],
    time_model: object,
) -> bool:
    progression_by_address = {
        progression.address: progression for progression in getattr(time_model, "progression_policies", ())
    }
    return any(
        progression_by_address[policy.progression_policy_address].reset_behavior != "unsupported"
        or progression_by_address[policy.progression_policy_address].replay_behavior != "unsupported"
        for policy in policies
        if policy.progression_policy_address in progression_by_address
    )


def _autonomous_reset_gaps(
    manifest: BackendManifest,
    policies: tuple[AutonomousExecutionPolicy, ...],
    time_model: object | None,
) -> list[str]:
    if time_model is None or not _requires_coordinated_reset(policies, time_model):
        return []
    time_capability = manifest.time
    if time_capability is not None and time_capability.supports_coordinated_participant_reset:
        return []
    return ["autonomous clock reset requires coordinated participant reset support"]


def _autonomous_temporal_binding_gaps(
    policies: tuple[AutonomousExecutionPolicy, ...],
    time_model: object | None,
) -> list[str]:
    """A constraint-kind claim cannot substitute for an action/event binding."""

    constraints = {constraint.address: constraint for constraint in getattr(time_model, "constraints", ())}
    gaps: list[str] = []
    for policy in policies:
        bindings = getattr(policy, "temporal_bindings", ())
        bound_constraints = {binding.constraint_address for binding in bindings}
        if policy.profile != "participant-autonomous-execution/v1":
            continue
        for address in policy.temporal_constraint_addresses:
            constraint = constraints.get(address)
            if constraint is not None and constraint.kind != "cadence" and address not in bound_constraints:
                gaps.append(
                    f"autonomous {constraint.kind} constraint {address} requires an explicit action temporal binding"
                )
    return gaps


def participant_autonomous_execution_capability_gaps(
    manifest: BackendManifest,
    policies: Iterable[AutonomousExecutionPolicy],
    time_model: object | None = None,
) -> tuple[str, ...]:
    """Return fail-closed backend gaps for compiled autonomous participants."""

    normalized_policies = tuple(policies)
    gaps: list[str] = []
    capability = manifest.participant_runtime
    if normalized_policies and (capability is None or not capability.supports_autonomous_execution):
        gaps.append("backend does not declare autonomous participant execution")
    elif normalized_policies and capability is not None:
        gaps.extend(_autonomous_limit_gaps(capability, normalized_policies))
        gaps.extend(_unsupported_autonomous_value_gaps(capability, normalized_policies))
        gaps.extend(
            _autonomous_execution_binding_gaps(
                capability,
                normalized_policies,
            )
        )
        gaps.extend(participant_resource_budget_gaps(manifest, capability, normalized_policies))
        gaps.extend(_autonomous_reset_gaps(manifest, normalized_policies, time_model))
        gaps.extend(_autonomous_temporal_binding_gaps(normalized_policies, time_model))
    return tuple(gaps)


def observation_capability_contract_gaps(manifest: BackendManifest) -> tuple[str, ...]:
    """Return missing contract surfaces for declared EXP-715 observation claims."""

    observation = manifest.observation
    if observation is None:
        return ()

    required_contracts = set(observation.supported_evidence_contracts) | set(OBSERVATION_CAPABILITY_REQUIRED_CONTRACTS)
    missing = sorted(required_contracts - manifest.supported_contract_versions)
    gaps: list[str] = []
    if missing:
        gaps.append(f"capabilities.observation missing required contracts: {', '.join(missing)}")
    return tuple(gaps)


def time_capability_contract_gaps(manifest: BackendManifest) -> tuple[str, ...]:
    """Return missing contract surfaces for a declared API-421 capability."""

    from .capabilities import TIME_CAPABILITY_REQUIRED_CONTRACTS

    if manifest.time is None:
        return ()
    missing = sorted(TIME_CAPABILITY_REQUIRED_CONTRACTS - manifest.supported_contract_versions)
    return () if not missing else (f"capabilities.time missing required contracts: {', '.join(missing)}",)


def _unsupported_time_terms(
    label: str,
    required: set[str],
    supported: frozenset[str],
) -> list[str]:
    missing = sorted(required - supported)
    return [] if not missing else [f"unsupported time {label}: {', '.join(missing)}"]


def _time_capacity_gaps(
    capability: TimeCapabilities,
    declaration: TimeModelDeclarationModel,
) -> list[str]:
    gaps: list[str] = []
    if capability.max_time_domains is not None and len(declaration.domains) > capability.max_time_domains:
        gaps.append(
            f"time model requires {len(declaration.domains)} domains; backend limit is {capability.max_time_domains}"
        )
    if capability.max_clocks is not None and len(declaration.clocks) > capability.max_clocks:
        gaps.append(f"time model requires {len(declaration.clocks)} clocks; backend limit is {capability.max_clocks}")
    return gaps


def _time_control_gaps(
    capability: TimeCapabilities,
    declaration: TimeModelDeclarationModel,
) -> list[str]:
    requirements = (
        (
            any(clock.supports_pause for clock in declaration.clocks.values()),
            capability.supports_pause,
            "pause control",
        ),
        (any(clock.supports_jump for clock in declaration.clocks.values()), capability.supports_jump, "jump control"),
        (bool(declaration.mappings), capability.supports_exact_rational_mappings, "exact rational mappings"),
        (True, capability.supports_append_only_history, "append-only clock transition history"),
        (True, capability.supports_run_provenance, "realized run provenance"),
    )
    return [f"time model requires {label}" for required, supported, label in requirements if required and not supported]


def time_model_capability_gaps(
    manifest: BackendManifest,
    declaration: TimeModelDeclarationModel,
) -> tuple[str, ...]:
    """Return fail-closed admission gaps for one portable time declaration."""

    capability = manifest.time
    if capability is None:
        return ("backend does not declare time capabilities",)

    gaps: list[str] = [*time_capability_contract_gaps(manifest)]
    term_sources = (
        ("domain kinds", declaration.domains.values(), "kind", capability.supported_domain_kinds),
        ("authority kinds", declaration.clocks.values(), "authority_kind", capability.supported_authority_kinds),
        (
            "advancement modes",
            declaration.progression_policies.values(),
            "advancement_mode",
            capability.supported_advancement_modes,
        ),
        (
            "synchronization modes",
            declaration.progression_policies.values(),
            "synchronization_mode",
            capability.supported_synchronization_modes,
        ),
        ("mapping kinds", declaration.mappings.values(), "mapping_kind", capability.supported_mapping_kinds),
        (
            "constraint kinds",
            declaration.temporal_constraints.values(),
            "kind",
            capability.supported_constraint_kinds,
        ),
        (
            "reset behaviors",
            declaration.progression_policies.values(),
            "reset_behavior",
            capability.supported_reset_behaviors,
        ),
        (
            "replay behaviors",
            declaration.progression_policies.values(),
            "replay_behavior",
            capability.supported_replay_behaviors,
        ),
    )
    for label, values, attribute, supported in term_sources:
        gaps.extend(_unsupported_time_terms(label, {getattr(value, attribute) for value in values}, supported))
    gaps.extend(_time_capacity_gaps(capability, declaration))
    gaps.extend(_time_control_gaps(capability, declaration))
    return tuple(gaps)


def require_time_model_capability(
    manifest: BackendManifest,
    declaration: TimeModelDeclarationModel,
) -> None:
    """Fail admission when a backend cannot honor the portable time model."""

    gaps = time_model_capability_gaps(manifest, declaration)
    if gaps:
        raise ValueError("; ".join(gaps))


def _required_cleanup_actions(plan: TrialCleanupPlanModel) -> set[str]:
    return {
        obligation.action_kind
        for obligation in plan.cleanup_obligations.values()
        if obligation.requirement == "required"
    }


def _required_cleanup_probe_methods(plan: TrialCleanupPlanModel) -> set[str]:
    probe_refs = set(plan.clean_state.verification_probe_refs)
    probe_refs.update(
        probe_ref
        for obligation in plan.cleanup_obligations.values()
        if obligation.requirement == "required"
        for probe_ref in obligation.verification_probe_refs
    )
    return {probe_ref.partition(":")[0] for probe_ref in probe_refs}


def _require_supported_cleanup_values(label: str, required: set[str], supported: frozenset[str]) -> None:
    unsupported = sorted(required - supported)
    if unsupported:
        raise ValueError(f"unsupported cleanup {label}: {', '.join(unsupported)}")


def require_cleanup_plan_capability(manifest: BackendManifest, plan: TrialCleanupPlanModel) -> None:
    """Fail admission when a backend cannot satisfy a portable cleanup plan."""

    cleanup = manifest.cleanup
    if cleanup is None:
        raise ValueError("backend does not declare cleanup capabilities")

    _require_supported_cleanup_values("action kinds", _required_cleanup_actions(plan), cleanup.supported_action_kinds)
    _require_supported_cleanup_values(
        "verification methods", _required_cleanup_probe_methods(plan), cleanup.supported_verification_methods
    )

    if plan.clean_state.mode == "declared-reusable" and not cleanup.supports_reusable_state:
        raise ValueError("backend does not support declared reusable state")
    required_cleanup = any(obligation.requirement == "required" for obligation in plan.cleanup_obligations.values())
    if required_cleanup and not cleanup.supports_residual_state_disclosure:
        raise ValueError("required cleanup needs backend residual-state disclosure")


__all__ = [
    "participant_feature_support_gaps",
    "resolve_participant_feature_support",
]
