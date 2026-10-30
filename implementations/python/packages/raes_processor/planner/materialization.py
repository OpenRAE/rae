"""Retain authenticated full SDL context for negotiated materialization results."""

from dataclasses import replace

from pydantic import ValidationError
from raes import canonical_instantiated_sdl_bytes, canonical_instantiated_sdl_digest
from raes.scenario import InstantiatedScenario
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.materialization import (
    MATERIALIZATION_ATTESTATION_CONTRACT,
    MATERIALIZATION_LIMIT_ERROR,
    MATERIALIZATION_MAX_BYTES,
    MaterializationSource,
)
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
    source, refusal = _build_materialization_source(
        instance, scope, RUNTIME_DESCENDANTS_CONTRACT in manifest.supported_contract_versions
    )
    if refusal is not None:
        diagnostics.append(_SOURCE_REFUSALS[refusal])
    return source, diagnostics


# Each refusal is value-free: it names the failed condition, never the rejected source or identity.
_SOURCE_REFUSALS = {
    "context": Diagnostic(
        code="materialization.source-context-required",
        domain="materialization",
        address="materialization.source",
        message="Materialization reporting requires the admitted full source and a safe run identity.",
    ),
    "limit": Diagnostic(
        code="materialization.source-limit-exceeded",
        domain="materialization",
        address="materialization.source",
        message=(
            "The admitted full source exceeds the materialization document limit of "
            f"{MATERIALIZATION_MAX_BYTES} bytes or its portable value bounds."
        ),
    ),
    "invalid": Diagnostic(
        code="materialization.source-invalid",
        domain="materialization",
        address="materialization.source",
        message="The admitted full source does not satisfy the materialization source contract.",
    ),
}
_CONTEXT_FIELDS = frozenset({"run_id", "target_scope"})
_LIMIT_ERRORS = frozenset({MATERIALIZATION_LIMIT_ERROR, "string_too_long"})


def _build_materialization_source(
    instance: InstantiatedScenario | None, scope: PlanScope | None, descendants: bool
) -> tuple[MaterializationSource | None, str | None]:
    """Return the sealed source, or the refusal class when it cannot be bound."""

    # Runtime inventory reporting requires the selected target scope.
    if instance is None or scope is None or scope.run_id is None or (descendants and not scope.target_name):
        return None, "context"
    snapshot = canonical_instantiated_sdl_bytes(instance)
    if len(snapshot) > MATERIALIZATION_MAX_BYTES:
        return None, "limit"
    authored_digest = instance.instantiation_provenance.authored_digest.value
    instantiated_digest = canonical_instantiated_sdl_digest(instance).value
    try:
        source = MaterializationSource(
            snapshot=snapshot.decode("utf-8"),
            authored_digest=authored_digest,
            instantiated_digest=instantiated_digest,
            run_id=scope.run_id,
            target_scope=f"target:{scope.target_name}" if descendants else None,
        )
    except ValidationError as exc:
        return None, _source_refusal(exc)
    return source, None


def _source_refusal(exc: ValidationError) -> str:
    """Classify by structured error type and location, never by message text."""
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    if any(error["type"] in _LIMIT_ERRORS for error in errors):
        return "limit"
    # The source contract refuses an unsafe run identity or target scope.
    if all(error["loc"] and error["loc"][0] in _CONTEXT_FIELDS for error in errors):
        return "context"
    return "invalid"
