"""Retain authenticated full SDL context for negotiated materialization results."""

from raes import canonical_instantiated_sdl_bytes, canonical_instantiated_sdl_digest
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.materialization import MATERIALIZATION_ATTESTATION_CONTRACT, MaterializationSource
from raes_contracts.planning import PlanScope

from ..models import RuntimeModel


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
    try:
        if instance is None or scope is None or scope.run_id is None:
            raise ValueError("missing source or run")
        return MaterializationSource(
            snapshot=canonical_instantiated_sdl_bytes(instance).decode("utf-8"),
            authored_digest=instance.instantiation_provenance.authored_digest.value,
            instantiated_digest=canonical_instantiated_sdl_digest(instance).value,
            run_id=scope.run_id,
        ), diagnostics
    except (TypeError, ValueError):
        diagnostics.append(
            Diagnostic(
                code="materialization.source-context-required",
                domain="materialization",
                address="materialization.source",
                message="Materialization reporting requires the admitted full source and a safe run identity.",
            )
        )
        return None, diagnostics
