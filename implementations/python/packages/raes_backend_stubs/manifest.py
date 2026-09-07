"""Pure stub backend manifest declaration (issue #609).

This module holds the stub backend's :class:`BackendManifest` factory and its
supporting constants, separated from ``stubs.py`` so callers that only need the
capability *declaration* -- authoring/inspection surfaces such as the
``raes processor plan`` CLI and the MCP dry-run planning tools -- can import the
manifest without dragging the live stub runtime components (and their
``raes_runtime`` dependency) into the process. It imports only the
capability/contract declaration layers; nothing here touches ``raes_runtime``.

``stubs.py`` re-exports :func:`create_stub_manifest` and the ``REFERENCE_*``
constants as the package's public surface.
"""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

from raes_backend_protocols.capabilities import (
    CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_ROLE_SCOPE,
    TIME_CAPABILITY_REQUIRED_CONTRACTS,
    BackendCapabilitySet,
    BackendManifest,
    CleanupCapabilities,
    EvaluatorCapabilities,
    ObservationCapabilities,
    OrchestratorCapabilities,
    ParticipantFeatureSupport,
    ParticipantRuntimeCapabilities,
    ProvisionerCapabilities,
    TimeCapabilities,
    WorkflowFeature,
    WorkflowStatePredicateFeature,
)
from raes_contracts.apparatus import (
    ConceptBinding,
    RealizationObservationCapability,
    RealizationSupportDeclaration,
)
from raes_contracts.corpus import REALIZATION_ENVELOPES, corpus_family_root
from raes_contracts.manifest_authority import BACKEND_SUPPORTED_CONTRACT_IDS
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.vocabulary import (
    ParticipantFeatureSupportLevel,
    RealizationSupportMode,
    RealizationVerificationScope,
)

REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS = frozenset(BACKEND_SUPPORTED_CONTRACT_IDS) - {
    "experiment-binding-descriptors-v1",
    "realization-envelope-v1",
}
REFERENCE_PARTICIPANT_ROLES = frozenset(
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_ROLE_SCOPE]
)
REFERENCE_PARTICIPANT_BEHAVIOR_FEATURES = (
    frozenset(PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE])
    - {"autonomous_execution"}
    - PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES
)
REFERENCE_PARTICIPANT_INTERACTION_FEATURES = frozenset(
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE]
)

_PARTICIPANT_CONTRACT_VERSIONS = frozenset(
    {
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
        "participant-lifecycle-event-v1",
        "participant-observation-envelope-v1",
        "participant-shared-state-record-v1",
        "participant-joint-action-record-v1",
        "participant-time-management-context-v1",
        "participant-outcome-report-v1",
    }
)
_OBSERVATION_CONTRACT_VERSIONS = frozenset(
    {
        "experiment-capture-spec-v1",
        "experiment-evidence-record-v1",
        "experiment-derived-measure-v1",
        "experiment-run-v1",
    }
)
_TIME_DEDICATED_CONTRACT_VERSIONS = frozenset({"time-model-v1", "time-runtime-state-v1", "realized-time-model-v1"})


def _current_backend_version() -> str:
    try:
        return distribution_version("raes")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def _stub_supported_contract_versions(
    *,
    with_participant_runtime: bool,
    with_observation: bool,
    with_time: bool,
    with_realization_envelope: bool,
) -> frozenset[str]:
    versions = set(REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS)
    if with_realization_envelope:
        versions.add("realization-envelope-v1")
    if not with_participant_runtime:
        versions -= _PARTICIPANT_CONTRACT_VERSIONS
    if not with_observation:
        versions -= _OBSERVATION_CONTRACT_VERSIONS - {"experiment-run-v1"}
    if not with_time:
        versions -= _TIME_DEDICATED_CONTRACT_VERSIONS
    return frozenset(versions)


def _stub_concept_bindings(
    *,
    with_participant_runtime: bool,
    with_observation: bool,
    with_time: bool,
) -> tuple[ConceptBinding, ...]:
    bindings = (
        ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),
        ConceptBinding(scope="capabilities.provisioner.supported_os_families", family="assets"),
        ConceptBinding(scope="capabilities.provisioner.supported_node_architectures", family="assets"),
        ConceptBinding(scope="capabilities.provisioner.supported_content_types", family="tools-and-artifacts"),
        ConceptBinding(scope="capabilities.provisioner.supported_account_features", family="identities"),
        ConceptBinding(scope="capabilities.provisioner.supported_domain_profiles", family="identities"),
        ConceptBinding(
            scope="capabilities.provisioner.supported_service_materialization_profiles",
            family="tools-and-artifacts",
        ),
        ConceptBinding(scope="capabilities.orchestrator.supported_sections", family="actions-and-events"),
        ConceptBinding(scope="capabilities.evaluator.supported_sections", family="observables"),
    )
    if with_participant_runtime:
        bindings += (
            ConceptBinding(scope="capabilities.participant_runtime.supported_participant_roles", family="identities"),
            ConceptBinding(
                scope="capabilities.participant_runtime.supported_behavior_features", family="actions-and-events"
            ),
            ConceptBinding(
                scope="capabilities.participant_runtime.supported_interaction_features", family="relationships"
            ),
        )
    if with_observation:
        bindings += (
            ConceptBinding(scope="capabilities.observation.supported_capture_kinds", family="provenance-and-evidence"),
            ConceptBinding(scope="capabilities.observation.supported_channel_kinds", family="apparatus-declarations"),
            ConceptBinding(scope="capabilities.observation.supported_sealing_modes", family="provenance-and-evidence"),
        )
    if with_time:
        bindings += (
            ConceptBinding(scope="capabilities.time.supported_domain_kinds", family="time-and-apparatus"),
            ConceptBinding(scope="capabilities.time.supported_authority_kinds", family="time-and-apparatus"),
            ConceptBinding(scope="capabilities.time.supported_advancement_modes", family="time-and-apparatus"),
            ConceptBinding(scope="capabilities.time.supported_synchronization_modes", family="time-and-apparatus"),
            ConceptBinding(scope="capabilities.time.supported_constraint_kinds", family="time-and-apparatus"),
        )
    return bindings


def load_stub_realization_envelope() -> BackendRealizationEnvelopeModel:
    """Load the governed in-process emulation apparatus used by the stub."""

    path = corpus_family_root(REALIZATION_ENVELOPES) / "reference-emulation" / "in-process-v1.json"
    return BackendRealizationEnvelopeModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _stub_realization_support(
    envelope: BackendRealizationEnvelopeModel | None,
) -> tuple[RealizationSupportDeclaration, ...]:
    supported_constraint_kinds = {
        "node-type",
        "os-family",
        "node-architecture",
        "content-type",
        "account-feature",
        "workflow-feature",
        "workflow-state-predicate",
    }
    observation_capabilities = {}
    if envelope is not None:
        supported_constraint_kinds.add("compute-substrate")
        substrate_claim = next(claim for claim in envelope.concerns if claim.concern.value == "compute-substrate")
        observation_capabilities["compute-substrate"] = RealizationObservationCapability(
            verification_scope=RealizationVerificationScope.PRESENCE,
            observation_strength=substrate_claim.observation_strength,
        )
    return (
        RealizationSupportDeclaration(
            domain="runtime-realization",
            support_mode=RealizationSupportMode.CONSTRAINED,
            supported_constraint_kinds=frozenset(supported_constraint_kinds),
            supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
            disclosure_kinds=frozenset({"backend-manifest-v2", "runtime-snapshot-v1", "operation-status-v1"}),
            observation_capabilities=observation_capabilities,
        ),
    )


def _stub_provisioner() -> ProvisionerCapabilities:
    return ProvisionerCapabilities(
        name="stub-provisioner",
        supported_node_types=frozenset({"compute", "switch"}),
        supported_os_families=frozenset({"linux", "windows", "macos", "freebsd", "other"}),
        supported_node_architectures=frozenset({"x86_64", "aarch64"}),
        supported_content_types=frozenset({"file", "dataset", "directory"}),
        supported_account_features=frozenset({"groups", "mail", "spn", "shell", "home", "disabled", "auth_method"}),
        supported_domain_profiles=frozenset({"active_directory"}),
        max_total_nodes=None,
        supports_acls=True,
        supports_accounts=True,
        supports_generated_artifacts=True,
        supported_generated_artifact_kinds=frozenset({"certificate_bundle", "rendered_config", "ssh_key_bundle"}),
        supported_generated_artifact_delivery_modes=frozenset({"mount", "environment", "env_file"}),
        supports_persistent_volumes=True,
    )


def _stub_orchestrator() -> OrchestratorCapabilities:
    return OrchestratorCapabilities(
        name="stub-orchestrator",
        supported_sections=frozenset({"injects", "events", "scripts", "stories", "workflows"}),
        supports_workflows=True,
        supports_assertion_refs=True,
        supports_inject_bindings=True,
        supported_workflow_features=frozenset(
            {
                WorkflowFeature.DECISION,
                WorkflowFeature.SWITCH,
                WorkflowFeature.CALL,
                WorkflowFeature.PARALLEL_BARRIER,
                WorkflowFeature.RETRY,
                WorkflowFeature.FAILURE_TRANSITIONS,
                WorkflowFeature.CANCELLATION,
                WorkflowFeature.TIMEOUTS,
                WorkflowFeature.COMPENSATION,
            }
        ),
        supported_workflow_state_predicates=frozenset(
            {
                WorkflowStatePredicateFeature.OUTCOME_MATCHING,
                WorkflowStatePredicateFeature.ATTEMPT_COUNTS,
            }
        ),
    )


def _stub_evaluator() -> EvaluatorCapabilities:
    return EvaluatorCapabilities(
        name="stub-evaluator",
        supported_sections=frozenset({"conditions", "propositions", "assertions", "objectives"}),
        supports_scoring=True,
        supports_objectives=True,
        supported_predicate_families=frozenset({"presence", "boolean", "string", "number"}),
        supported_quantifiers=frozenset({"all", "any", "at_least"}),
        supported_truth_outcomes=frozenset({"true", "false", "unknown", "unsupported"}),
        supported_evidence_channels=frozenset({"log", "api_response", "file_artifact"}),
        supported_time_domains=frozenset({"scenario_time"}),
        preserves_binding_provenance=True,
    )


def _stub_participant_runtime() -> ParticipantRuntimeCapabilities:
    return ParticipantRuntimeCapabilities(
        name="stub-participant-runtime",
        supported_participant_roles=REFERENCE_PARTICIPANT_ROLES,
        supported_behavior_features=REFERENCE_PARTICIPANT_BEHAVIOR_FEATURES,
        supported_interaction_features=REFERENCE_PARTICIPANT_INTERACTION_FEATURES,
        feature_support=tuple(
            ParticipantFeatureSupport(
                feature=feature,
                support_level=ParticipantFeatureSupportLevel.UNSUPPORTED,
                limitation_refs=(f"limitation:{feature}:not-realized",),
                disclosure_refs=(f"disclosure:{feature}:unsupported",),
            )
            for feature in sorted(PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES)
        ),
    )


def _stub_observation() -> ObservationCapabilities:
    return ObservationCapabilities(
        name="stub-observation",
        supported_capture_kinds=frozenset({"artifact", "log", "observation", "packet-capture", "telemetry", "trace"}),
        supported_channel_kinds=frozenset(
            {
                "backend-log",
                "evaluation-history",
                "file-artifact",
                "packet-capture",
                "participant-observation",
                "runtime-snapshot",
                "workflow-history",
            }
        ),
        supported_evidence_contracts=frozenset(_OBSERVATION_CONTRACT_VERSIONS),
        supported_media_types=frozenset({"application/json", "text/plain"}),
        supported_sealing_modes=frozenset({"digest", "immutable-store"}),
        supports_redaction=True,
        supports_loss_disclosure=True,
        supports_chain_of_custody=False,
    )


def _stub_cleanup() -> CleanupCapabilities:
    return CleanupCapabilities(
        name="stub-cleanup",
        supported_contract_versions=CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
        supported_action_kinds=frozenset({"destroy", "reset", "restore", "compensate", "verify"}),
        supported_verification_methods=frozenset({"probe", "receipt"}),
        supports_reusable_state=True,
        supports_residual_state_disclosure=True,
    )


def _stub_time(*, supports_coordinated_participant_reset: bool) -> TimeCapabilities:
    return TimeCapabilities(
        name="stub-time-runtime",
        supported_contract_versions=TIME_CAPABILITY_REQUIRED_CONTRACTS,
        supported_domain_kinds=frozenset({"wall_clock", "monotonic", "simulated", "logical", "external"}),
        supported_authority_kinds=frozenset({"runtime", "backend", "system", "external"}),
        supported_advancement_modes=frozenset({"real_time", "dilated", "stepped", "event_driven", "externally_paced"}),
        supported_synchronization_modes=frozenset({"none", "authority", "barrier", "conservative"}),
        supported_mapping_kinds=frozenset({"identity", "affine_rational"}),
        supported_constraint_kinds=frozenset({"precedence", "duration", "window", "deadline", "cadence"}),
        supported_reset_behaviors=frozenset({"unsupported", "new_segment_zero", "new_segment_preserve_value"}),
        supported_replay_behaviors=frozenset({"unsupported", "restart_from_anchor", "restore_recorded_advances"}),
        supports_pause=True,
        supports_jump=True,
        supports_exact_rational_mappings=True,
        supports_append_only_history=True,
        supports_run_provenance=True,
        supports_coordinated_participant_reset=supports_coordinated_participant_reset,
    )


def _stub_capabilities(
    *,
    with_participant_runtime: bool,
    with_observation: bool,
    with_time: bool,
) -> BackendCapabilitySet:
    return BackendCapabilitySet(
        provisioner=_stub_provisioner(),
        orchestrator=_stub_orchestrator(),
        evaluator=_stub_evaluator(),
        participant_runtime=_stub_participant_runtime() if with_participant_runtime else None,
        observation=(_stub_observation() if with_observation else None),
        cleanup=_stub_cleanup(),
        time=(_stub_time(supports_coordinated_participant_reset=with_participant_runtime) if with_time else None),
    )


def create_stub_manifest(
    *,
    with_participant_runtime: bool = True,
    with_observation: bool = True,
    with_time: bool = False,
    with_realization_envelope: bool = False,
    **config,
) -> BackendManifest:
    """Return the fully capable stub manifest.

    ``with_participant_runtime=False`` omits the participant runtime
    capability block so legacy tests that construct targets with only
    provisioner/orchestrator/evaluator components still satisfy
    ``registry.target-shape-mismatch`` validation. Production callers
    should leave this at its default.
    """

    del config
    realization_envelope = load_stub_realization_envelope() if with_realization_envelope else None
    return BackendManifest(
        name="stub",
        version=_current_backend_version(),
        supported_contract_versions=_stub_supported_contract_versions(
            with_participant_runtime=with_participant_runtime,
            with_observation=with_observation,
            with_time=with_time,
            with_realization_envelope=with_realization_envelope,
        ),
        compatible_processors=frozenset({"raes-reference-processor"}),
        concept_bindings=_stub_concept_bindings(
            with_participant_runtime=with_participant_runtime,
            with_observation=with_observation,
            with_time=with_time,
        ),
        realization_support=_stub_realization_support(realization_envelope),
        capabilities=_stub_capabilities(
            with_participant_runtime=with_participant_runtime,
            with_observation=with_observation,
            with_time=with_time,
        ),
        realization_envelope=realization_envelope,
    )
