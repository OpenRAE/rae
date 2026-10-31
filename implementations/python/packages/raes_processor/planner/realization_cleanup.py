"""Authority-preserving validation of failed apply cleanup inventory."""

from dataclasses import replace

from raes.explicitness import ExplicitnessClass
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import RuntimeSnapshot

from ..semantics.realization import CompiledRealizationRequirement, realization_disclosure
from ..semantics.realization_runtime_common import MISSING_CONCERN_VALUE
from ..semantics.realization_runtime_evaluation import realized_concern_value
from .realization_authority import (
    plan_realization_requirements,
    realization_authority_diagnostics,
    realization_authority_disclosure,
)


def _cleanup_requirement(
    requirement: CompiledRealizationRequirement, snapshot: RuntimeSnapshot
) -> CompiledRealizationRequirement:
    if (
        requirement.explicitness is ExplicitnessClass.OPEN
        and requirement.structure is None
        and requirement.constraint_document is None
        and realized_concern_value(requirement, snapshot) is MISSING_CONCERN_VALUE
    ):
        return replace(requirement, verification_scope=None, required_observation_strength=None)
    return requirement


def realization_cleanup_diagnostics(
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    *,
    manifest: BackendManifest | None = None,
    requirements: tuple[CompiledRealizationRequirement, ...] = (),
    artifact_availability: ArtifactAvailabilityContext | None = None,
) -> list[Diagnostic]:
    """Validate failed inventory without interpreting omission as a success claim.

    Validate original authority before making a local comparison projection.
    Supplied values retain their verification floors and all semantic checks.
    Cleanup never produces successful realization provenance.
    """

    diagnostics = realization_authority_diagnostics(declared_plan, manifest)
    if diagnostics:
        return diagnostics
    cleanup_views = {
        (item.address, item.requirement_kind): _cleanup_requirement(item, returned_snapshot)
        for item in plan_realization_requirements(declared_plan)
    }
    cleanup_authority = []
    for item in declared_plan.realization_authority:
        view = cleanup_views.get((item.address, item.requirement_kind))
        cleanup_authority.append(
            replace(
                item,
                verification_scope=view.verification_scope,
                required_observation_strength=view.required_observation_strength,
            )
            if view is not None
            else item
        )
    cleanup_plan: ProvisioningPlan = replace(
        declared_plan,
        observation_demands=(),
        realization_authority=tuple(cleanup_authority),
    )
    diagnostics, _ = realization_authority_disclosure(cleanup_plan, returned_snapshot, manifest=manifest)
    supplemental, _ = realization_disclosure(
        tuple(_cleanup_requirement(item, returned_snapshot) for item in requirements),
        cleanup_plan,
        returned_snapshot,
        manifest=manifest,
        artifact_availability=artifact_availability,
    )
    return [*diagnostics, *supplemental]
