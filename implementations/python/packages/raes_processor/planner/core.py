"""Top-level planning pipeline that reconciles a runtime model against a snapshot."""

from dataclasses import replace
from typing import cast

from raes.realization_envelope import member
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.capability_admission import (
    participant_autonomous_execution_capability_gaps,
    participant_feature_support_gaps,
    time_model_capability_gaps,
)
from raes_backend_protocols.domain_topology import domain_topology_plan_diagnostics
from raes_backend_protocols.service_materialization import service_materialization_plan_diagnostics
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain

from ..capture_admission import capture_admission_diagnostics
from ..compiler.realization_deferred_constraints import resolve_pending_recursive_constraints
from ..compiler.time_model import time_model_contract_model
from ..models import CompiledRealizationRequirement, ExecutionPlan, RuntimeModel, RuntimeSnapshot
from ..semantics.realization import (
    ApparatusRealizationDefaultResolver,
    artifact_requirement_diagnostics,
    materialize_realization_requirements,
    realization_envelope_diagnostics,
    realization_support_diagnostics,
    resolve_apparatus_realization_defaults,
)
from .manifest_validation import _validate_manifest
from .operations import (
    _build_evaluation_plan,
    _build_operations,
    _build_orchestration_plan,
    _build_provisioning_plan,
)
from .ordering import _ordering_cycle_diagnostics
from .realization_authority import materialize_realization_authority
from .realization_collections import planned_node_collection, retain_open_collection_nodes
from .realization_preparation import preparation_authority, preparation_member_diagnostics
from .realization_profiles import profile_resources
from .resources import _collect_resources


def _time_model_diagnostics(model: RuntimeModel, manifest: BackendManifest) -> list[Diagnostic]:
    declaration = time_model_contract_model(model.time_model)
    if declaration is None:
        return []
    return [
        Diagnostic(
            code="time.unsupported-capability",
            domain="time",
            address="time.model",
            message=gap,
        )
        for gap in time_model_capability_gaps(manifest, declaration)
    ]


def _participant_execution_diagnostics(
    model: RuntimeModel,
    manifest: BackendManifest,
) -> list[Diagnostic]:
    specifications = tuple(model.behavior_specifications.values())
    autonomous_specifications = tuple(
        specification for specification in specifications if specification.autonomous_execution is not None
    )
    policies = tuple(specification.autonomous_execution for specification in autonomous_specifications)
    diagnostics = [
        Diagnostic(
            code="participant.autonomous-execution-unsupported",
            domain="participant",
            address="participant.autonomous-execution",
            message=gap,
        )
        for gap in participant_autonomous_execution_capability_gaps(manifest, policies, model.time_model)
    ]
    for specification in specifications:
        for gap in participant_feature_support_gaps(
            manifest,
            specification.backend_feature_support_refs,
        ):
            diagnostics.append(
                Diagnostic(
                    code="participant.feature-support-insufficient",
                    domain="participant",
                    address=specification.address,
                    message=gap,
                )
            )
    return diagnostics


def _observation_owner(
    evaluation: object,
    orchestration: object,
) -> RuntimeDomain:
    """Choose the last actionable backend phase as the single observation owner."""

    if orchestration.actionable_operations:
        return RuntimeDomain.ORCHESTRATION
    if evaluation.actionable_operations:
        return RuntimeDomain.EVALUATION
    return RuntimeDomain.PROVISIONING


def _resolved_realization(
    model: RuntimeModel,
    manifest: BackendManifest,
    apparatus_realization_default: ApparatusRealizationDefaultResolver | None,
) -> tuple[RuntimeModel, tuple[CompiledRealizationRequirement, ...], tuple[object, ...], list[Diagnostic]]:
    """Resolve apparatus defaults, lower deferred constraints, and materialize authority."""

    apparatus_decisions = resolve_apparatus_realization_defaults(
        model.realization_requirements,
        manifest,
        apparatus_default=apparatus_realization_default,
    )
    model = resolve_pending_recursive_constraints(model, apparatus_decisions)
    effective_requirements = materialize_realization_requirements(
        model.realization_requirements,
        manifest,
        apparatus_decisions=apparatus_decisions,
    )
    resolved_authority, authority_diagnostics = materialize_realization_authority(
        model,
        manifest,
        apparatus_decisions=apparatus_decisions,
    )
    return (
        replace(model, realization_requirements=effective_requirements),
        effective_requirements,
        resolved_authority,
        authority_diagnostics,
    )


def _envelope_diagnostics(
    effective_model: RuntimeModel,
    manifest: BackendManifest,
    effective_requirements: tuple[CompiledRealizationRequirement, ...],
    *,
    preparation: object | None,
) -> list[Diagnostic]:
    """Project envelope membership, keeping only statically decidable failures."""

    envelope = manifest.realization_envelope
    instance = effective_model.realization_instance
    diagnostics = (
        list(member(instance, envelope.expression).diagnostics) if envelope is not None and instance is not None else []
    )
    if preparation is None:
        return diagnostics
    return preparation_member_diagnostics(diagnostics, effective_requirements)


def _admission_diagnostics(
    effective_model: RuntimeModel,
    manifest: BackendManifest,
    effective_requirements: tuple[CompiledRealizationRequirement, ...],
    *,
    artifact_availability: ArtifactAvailabilityContext | None,
    preparation: object | None,
) -> list[Diagnostic]:
    """Collect every static admission failure before any operation is planned."""

    return [
        *effective_model.diagnostics,
        *_validate_manifest(effective_model, manifest),
        *_time_model_diagnostics(effective_model, manifest),
        *_participant_execution_diagnostics(effective_model, manifest),
        *capture_admission_diagnostics(effective_model.capture_demands, manifest.observation),
        *realization_support_diagnostics(effective_requirements, manifest),
        *realization_envelope_diagnostics(
            effective_requirements,
            manifest,
            preparation=preparation is not None,
        ),
        *artifact_requirement_diagnostics(
            effective_requirements,
            manifest,
            availability=artifact_availability,
        ),
        *_envelope_diagnostics(
            effective_model,
            manifest,
            effective_requirements,
            preparation=preparation,
        ),
    ]


def plan(
    model: RuntimeModel,
    manifest: BackendManifest,
    snapshot: RuntimeSnapshot | None = None,
    *,
    target_name: str | None = None,
    apparatus_realization_default: ApparatusRealizationDefaultResolver | None = None,
    artifact_availability: ArtifactAvailabilityContext | None = None,
    profile_context: DomainProfileResolutionContextModel | None = None,
) -> ExecutionPlan:
    """Reconcile a compiled runtime model against the current snapshot."""

    snapshot = snapshot or RuntimeSnapshot()
    effective_model, effective_requirements, resolved_authority, authority_diagnostics = _resolved_realization(
        model, manifest, apparatus_realization_default
    )
    resources = _collect_resources(effective_model)
    resources, profile_diagnostics = profile_resources(effective_model, resources, manifest, snapshot, profile_context)
    preparation = preparation_authority(manifest)
    diagnostics = [
        *profile_diagnostics,
        *_admission_diagnostics(
            effective_model,
            manifest,
            effective_requirements,
            artifact_availability=artifact_availability,
            preparation=preparation,
        ),
        *authority_diagnostics,
        *_ordering_cycle_diagnostics(resources),
    ]
    actions, deleted_entries = _build_operations(
        resources,
        snapshot,
        effective_requirements,
    )

    provisioning = _build_provisioning_plan(
        resources,
        actions,
        deleted_entries,
        manifest,
        effective_requirements,
        resolved_authority,
        effective_model.observation_demands,
    )
    if preparation is not None:
        try:
            preparation = preparation.model_copy(
                update={"node_collection": planned_node_collection(effective_model, provisioning)}
            )
        except (TypeError, ValueError):
            diagnostics.append(
                Diagnostic(
                    code="realization.invalid-node-collection",
                    domain="provisioning",
                    address="nodes",
                    message="Portable node membership cannot be represented by a bounded collection authority.",
                )
            )
    provisioning = retain_open_collection_nodes(
        cast(
            "ProvisioningPlan",
            replace(provisioning, preparation=preparation, profile_authority=model.profile_authority),
        )
    )
    materialization_diagnostics = service_materialization_plan_diagnostics(
        provisioning,
        manifest.provisioner,
        manifest.realization_envelope,
        manifest.realization_support,
    )
    diagnostics.extend(materialization_diagnostics)
    provisioning.diagnostics.extend(materialization_diagnostics)
    topology_diagnostics = domain_topology_plan_diagnostics(
        provisioning,
        snapshot=snapshot,
        supported_domain_profiles=manifest.provisioner.supported_domain_profiles,
    )
    diagnostics.extend(topology_diagnostics)
    provisioning.diagnostics.extend(topology_diagnostics)
    orchestration = _build_orchestration_plan(resources, actions, deleted_entries, effective_model.observation_demands)
    evaluation = _build_evaluation_plan(resources, actions, deleted_entries, effective_model.observation_demands)

    return ExecutionPlan(
        target_name=target_name,
        manifest=manifest,
        base_snapshot=snapshot,
        scenario_name=model.scenario_name,
        model=effective_model,
        provisioning=provisioning,
        orchestration=orchestration,
        evaluation=evaluation,
        observation_owner=_observation_owner(evaluation, orchestration),
        diagnostics=diagnostics,
        artifact_availability=artifact_availability or ArtifactAvailabilityContext(),
    )
