"""Authority sets for processor, backend, and participant implementation declarations."""

from __future__ import annotations

from collections.abc import Iterable

PROCESSOR_SUPPORTED_SDL_VERSION_IDS = ("sdl-authoring-input-v1",)

# These are the published processor-facing and live-control-plane contracts a
# processor may honestly claim to support. Concept-authority catalogs, semantic
# profiles, backend manifests, and authoring-side request artifacts are
# separate authority surfaces and do not belong in this declaration field.
PROCESSOR_SUPPORTED_CONTRACT_IDS = (
    "processor-manifest-v2",
    "experiment-binding-descriptors-v1",
    "provisioning-plan-v1",
    "orchestration-plan-v1",
    "evaluation-plan-v1",
    "workflow-cancellation-request-v1",
    "operation-receipt-v1",
    "operation-status-v1",
    "runtime-snapshot-v1",
    "workflow-result-envelope-v1",
    "workflow-history-event-stream-v1",
    "evaluation-result-envelope-v1",
    "proposition-truth-result-v1",
    "evaluation-history-event-stream-v1",
    "participant-episode-state-envelope-v1",
    "participant-episode-history-event-stream-v1",
    "participant-behavior-history-event-stream-v1",
    "participant-resource-budget-policy-v1",
    "time-model-v1",
)

# These are the published backend-facing and live-control-plane contracts a
# backend may honestly claim to support. Concept-authority catalogs, semantic
# profiles, processor manifests, and authoring-side request artifacts are
# separate authority surfaces and do not belong in this declaration field.
BACKEND_SUPPORTED_CONTRACT_IDS = (
    "plan-realization-profiles-v1",
    "backend-realization-preparation-v1",
    "backend-manifest-v2",
    "artifact-requirement-v1",
    "experiment-binding-descriptors-v1",
    "realization-envelope-v1",
    "provisioning-plan-v1",
    "orchestration-plan-v1",
    "evaluation-plan-v1",
    "operation-receipt-v1",
    "operation-status-v1",
    "runtime-snapshot-v1",
    "workflow-result-envelope-v1",
    "workflow-history-event-stream-v1",
    "evaluation-result-envelope-v1",
    "proposition-truth-result-v1",
    "evaluation-history-event-stream-v1",
    "participant-episode-state-envelope-v1",
    "participant-episode-history-event-stream-v1",
    "participant-behavior-history-event-stream-v1",
    "participant-execution-binding-v1",
    "participant-execution-control-v1",
    "participant-execution-service-state-v1",
    "participant-resource-budget-policy-v1",
    "participant-resource-pool-capacity-v1",
    "participant-resource-budget-state-v1",
    "participant-resource-budget-event-v1",
    "participant-control-occurrence-v1",
    "participant-crossing-occurrence-v1",
    "participant-flow-control-relation-v1",
    "participant-lifecycle-event-v1",
    "participant-observation-envelope-v1",
    "participant-shared-state-record-v1",
    "participant-joint-action-record-v1",
    "participant-time-management-context-v1",
    "participant-outcome-report-v1",
    "experiment-capture-spec-v1",
    "experiment-evidence-record-v1",
    "experiment-derived-measure-v1",
    "experiment-run-v1",
    "trial-cleanup-plan-v1",
    "trial-cleanup-receipt-v1",
    "time-model-v1",
    "time-runtime-state-v1",
    "realized-time-model-v1",
)

PARTICIPANT_RUNTIME_ROLE_SCOPE = "capabilities.participant_runtime.supported_participant_roles"
PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE = "capabilities.participant_runtime.supported_behavior_features"
PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE = "capabilities.participant_runtime.supported_interaction_features"

PARTICIPANT_RUNTIME_POLICY_FEATURES = frozenset(
    {
        "participant_declassification",
        "participant_directed_inject_delivery",
        "participant_egress_projection",
        "participant_ingress_admission",
        "participant_intervention",
        "participant_transformation",
    }
)

# Issue #1004 adversarial-control apparatus/backend declaration terms. These are
# evidence-required (a positive claim carries conformance evidence, below-exact
# carries disclosure + limitation, bounded carries constraints) but, like
# participant_predicate_opacity, they are NOT runtime policy features: #1003 /
# RUN-319 own final-sink enforcement and the reference backend's auto-emitted
# policy declarations. A declaration is never proof of realization, isolation,
# monitor independence, non-collusion, flow propagation, or sink enforcement.
PARTICIPANT_ADVERSARIAL_CONTROL_FEATURES = frozenset(
    {
        "participant_boundary_flow_resolution",
        "participant_final_sink_mediation",
        "participant_quarantined_processing",
        "participant_processing_role_trust",
        "participant_monitor_topology",
    }
)

PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES = frozenset(
    {
        *PARTICIPANT_RUNTIME_POLICY_FEATURES,
        "participant_predicate_opacity",
        *PARTICIPANT_ADVERSARIAL_CONTROL_FEATURES,
    }
)

_PARTICIPANT_EPISODE_CONTRACTS = frozenset(
    {
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "runtime-snapshot-v1",
    }
)
_PARTICIPANT_BEHAVIOR_CONTRACTS = frozenset(
    {
        "participant-behavior-history-event-stream-v1",
        "runtime-snapshot-v1",
    }
)
_PARTICIPANT_INTERACTION_CONTRACTS = frozenset(
    {
        "participant-behavior-history-event-stream-v1",
        "participant-shared-state-record-v1",
        "participant-joint-action-record-v1",
        "participant-time-management-context-v1",
        "runtime-snapshot-v1",
    }
)
_PARTICIPANT_AUTONOMOUS_EXECUTION_CONTRACTS = frozenset(
    {
        *_PARTICIPANT_INTERACTION_CONTRACTS,
        "participant-execution-binding-v1",
        "participant-execution-control-v1",
        "participant-execution-service-state-v1",
        "operation-receipt-v1",
        "operation-status-v1",
    }
)
_PARTICIPANT_OPACITY_CONTRACTS = frozenset(
    {
        "operation-receipt-v1",
        "operation-status-v1",
        "runtime-snapshot-v1",
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
        "participant-observation-envelope-v1",
    }
)

PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS = {
    PARTICIPANT_RUNTIME_ROLE_SCOPE: {
        "blue": _PARTICIPANT_EPISODE_CONTRACTS,
        "green": _PARTICIPANT_EPISODE_CONTRACTS,
        "red": _PARTICIPANT_EPISODE_CONTRACTS,
        "white": _PARTICIPANT_EPISODE_CONTRACTS,
    },
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE: {
        "action_contracts": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "autonomous_execution": _PARTICIPANT_AUTONOMOUS_EXECUTION_CONTRACTS,
        "attribution_support": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "behavior_history": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "effects": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "failure_classes": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "observation_boundaries": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "outcome_interpretation": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "participant_predicate_opacity": _PARTICIPANT_OPACITY_CONTRACTS,
        "participant_declassification": frozenset({"participant-crossing-occurrence-v1"}),
        "participant_directed_inject_delivery": frozenset(
            {"orchestration-plan-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_egress_projection": frozenset(
            {"participant-observation-envelope-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_ingress_admission": frozenset(
            {"participant-control-occurrence-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_intervention": frozenset(
            {"participant-control-occurrence-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_transformation": frozenset({"participant-crossing-occurrence-v1"}),
        # Issue #1004 adversarial-control apparatus/backend declarations. Each
        # term requires the backend-facing published contract that OWNS its
        # claimed realization, not merely a generic occurrence carrier: the
        # SEM-233 flow-control relation (resolved by the RUN-319 runtime at the
        # final sink) for flow/sink/quarantine terms, the ACT-617/API-409
        # control occurrence for processing-role trust, and the ASR-536
        # experiment evidence record for monitor topology. The authored
        # boundary-flow-policy profile stays out of backend support lists.
        "participant_boundary_flow_resolution": frozenset(
            {"participant-flow-control-relation-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_final_sink_mediation": frozenset(
            {"participant-flow-control-relation-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_quarantined_processing": frozenset(
            {"participant-flow-control-relation-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_processing_role_trust": frozenset(
            {"participant-control-occurrence-v1", "participant-crossing-occurrence-v1"}
        ),
        "participant_monitor_topology": frozenset({"experiment-evidence-record-v1"}),
        "preconditions": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "state_transitions": _PARTICIPANT_BEHAVIOR_CONTRACTS,
        "temporal_contracts": _PARTICIPANT_BEHAVIOR_CONTRACTS,
    },
    PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE: {
        "contention": _PARTICIPANT_INTERACTION_CONTRACTS,
        "coordination": _PARTICIPANT_INTERACTION_CONTRACTS,
        "interference": _PARTICIPANT_INTERACTION_CONTRACTS,
        "shared_state_change": _PARTICIPANT_INTERACTION_CONTRACTS,
    },
}

PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS = (
    "participant-implementation-manifest-v1",
    "participant-implementation-provenance-v1",
    "experiment-binding-descriptors-v1",
    "participant-configuration-result-v1",
    "participant-episode-state-envelope-v1",
    "participant-episode-history-event-stream-v1",
    "participant-behavior-history-event-stream-v1",
    "participant-decision-surface-v2",
)


def validate_processor_supported_sdl_versions(values: Iterable[str]) -> None:
    _validate_allowed_values(
        "supported_sdl_versions",
        values,
        PROCESSOR_SUPPORTED_SDL_VERSION_IDS,
        "published SDL authoring contract ids",
    )


def validate_processor_supported_contract_versions(values: Iterable[str]) -> None:
    _validate_allowed_values(
        "supported_contract_versions",
        values,
        PROCESSOR_SUPPORTED_CONTRACT_IDS,
        "published processor/runtime contract ids",
    )


def validate_backend_supported_contract_versions(values: Iterable[str]) -> None:
    _validate_allowed_values(
        "supported_contract_versions",
        values,
        BACKEND_SUPPORTED_CONTRACT_IDS,
        "published backend/runtime contract ids",
    )


def validate_participant_implementation_supported_contract_versions(values: Iterable[str]) -> None:
    _validate_allowed_values(
        "supported_contract_versions",
        values,
        PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS,
        "published participant implementation contract ids",
    )


def validate_participant_supported_contract_versions(values: Iterable[str]) -> None:
    _validate_allowed_values(
        "supported_participant_contracts",
        values,
        PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS,
        "published participant implementation contract ids",
    )


def _validate_allowed_values(
    field_name: str,
    values: Iterable[str],
    allowed_values: tuple[str, ...],
    allowed_label: str,
) -> None:
    materialized = list(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{field_name} must not contain duplicates")

    allowed = frozenset(allowed_values)
    unknown = sorted(set(materialized) - allowed)
    if unknown:
        declared = ", ".join(unknown)
        raise ValueError(f"{field_name} include values outside the {allowed_label}: {declared}")
