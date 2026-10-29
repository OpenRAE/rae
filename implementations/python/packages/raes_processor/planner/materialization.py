"""Retain authenticated full SDL context for negotiated materialization results."""

from dataclasses import replace

from pydantic import ValidationError
from raes import canonical_instantiated_sdl_bytes, canonical_instantiated_sdl_digest
from raes.scenario import InstantiatedScenario
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.materialization import MATERIALIZATION_ATTESTATION_CONTRACT, MaterializationSource
from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, PlanScope, ProvisioningPlan

from ..models import RuntimeModel


def attach_materialization_sources[DomainPlan: (ProvisioningPlan, OrchestrationPlan, EvaluationPlan)](
    plans: tuple[DomainPlan, ...], model: RuntimeModel, manifest: BackendManifest, scope: PlanScope | None
) -> tuple[tuple[DomainPlan, ...], list[Diagnostic]]:
    source, diagnostics = planned_materialization_source(model, manifest, scope)
    scope_required = (
        model.realization_instance is not None and model.realization_instance.augmentation_scope is not None
    )
    return (
        tuple(
            replace(
                domain_plan,
                purpose="inspection" if model.materialization_description is not None else domain_plan.purpose,
                materialization_source=source,
                augmentation_scope_required=scope_required,
                diagnostics=[*domain_plan.diagnostics, *diagnostics],
            )
            for domain_plan in plans
        ),
        diagnostics,
    )


def planned_materialization_source(
    model: RuntimeModel,
    manifest: BackendManifest,
    scope: PlanScope | None,
) -> tuple[MaterializationSource | None, list[Diagnostic]]:
    """Bind descriptive output to its original input, never reconstruct from resources."""
    instance = model.realization_instance
    required = instance is not None and instance.augmentation_scope is not None
    diagnostics = []
    if required and not {AUGMENTATION_SCOPE_CONTRACT, MATERIALIZATION_ATTESTATION_CONTRACT}.issubset(
        manifest.supported_contract_versions
    ):
        diagnostics.append(
            Diagnostic(
                code="augmentation.scope-unsupported",
                domain="augmentation",
                address="/augmentation_scope",
                message=(
                    "Explicit augmentation permission requires negotiated scope enforcement "
                    "and materialization reporting."
                ),
            )
        )
    if (
        MATERIALIZATION_ATTESTATION_CONTRACT not in manifest.supported_contract_versions and not required
    ) or model.materialization_description is not None:
        return None, diagnostics
    source = _build_materialization_source(
        instance, scope, RUNTIME_DESCENDANTS_CONTRACT in manifest.supported_contract_versions
    )
    if source is None:
        diagnostics.append(
            Diagnostic(
                code="materialization.source-context-required",
                domain="materialization",
                address="materialization.source",
                message="Materialization reporting requires the admitted full source and a safe run identity.",
            )
        )
    return source, diagnostics


def _build_materialization_source(
    instance: InstantiatedScenario | None, scope: PlanScope | None, descendants: bool
) -> MaterializationSource | None:
    """Return ``None`` when the admitted full source or a safe run identity is unavailable."""

    if instance is None or scope is None or scope.run_id is None:
        return None
    if descendants and not scope.target_name:
        # Runtime inventory reporting requires the selected target scope.
        return None
    snapshot = canonical_instantiated_sdl_bytes(instance).decode("utf-8")
    authored_digest = instance.instantiation_provenance.authored_digest.value
    instantiated_digest = canonical_instantiated_sdl_digest(instance).value
    try:
        return MaterializationSource(
            snapshot=snapshot,
            authored_digest=authored_digest,
            instantiated_digest=instantiated_digest,
            run_id=scope.run_id,
            target_scope=f"target:{scope.target_name}" if descendants else None,
        )
    except ValidationError:
        # The source contract refuses an unsafe run identity or target scope.
        return None
