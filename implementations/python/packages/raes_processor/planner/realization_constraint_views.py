"""Read the existing addressed constraints at the portable plan boundary."""

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot

from ..semantics.realization import (
    CompiledRealizationRequirement,
    realization_envelope_diagnostics,
    realization_support_diagnostics,
)
from ..semantics.realization_runtime_evaluation import evaluate_registered_realization


def planned_constraint_requirements(plan: ProvisioningPlan) -> tuple[CompiledRealizationRequirement, ...]:
    """Recover constraints without a compiler model or invented observation floor."""

    return tuple(
        CompiledRealizationRequirement(
            address=item.address,
            field_path=item.field_path,
            domain="runtime-realization",
            requirement_kind=item.concern,
            explicitness=ExplicitnessClass(item.posture),
            provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
            governing_scope=item.governing_scope,
            value_domain=item.value_domain,
            constraint_provenance=item.provenance,
        )
        for item in plan.realization_constraints
    )


def planned_constraint_disclosure(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> tuple[list[Diagnostic], tuple[RealizationProvenanceEntry, ...]]:
    diagnostics, provenance = [], []
    for requirement in planned_constraint_requirements(plan):
        diagnostic, entry = evaluate_registered_realization(requirement, plan, snapshot, manifest=manifest)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        if entry is not None:
            provenance.append(entry)
    return diagnostics, tuple(provenance)


def planned_constraint_admission(plan: ProvisioningPlan, manifest: BackendManifest) -> list[Diagnostic]:
    requirements = planned_constraint_requirements(plan)
    return [
        *realization_support_diagnostics(requirements, manifest),
        *realization_envelope_diagnostics(requirements, manifest),
    ]
