"""Pinned private measures using the incumbent quantity and accounting modes."""

from __future__ import annotations

from .canonical import canonical_json_digest
from .domain_profiles import (
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingModel,
    DomainProfileCoordinateModel,
    DomainProfileOperation,
    DomainProfileResolutionContextModel,
    DomainProfileSemanticContractModel,
    admit_domain_profile_bindings,
    resolve_domain_profile_definition,
)

RESOURCE_MEASURE_SEMANTICS = DomainProfileSemanticContractModel(
    authority="https://openrae.org/profiles",
    contract_id="participant-resource-measure",
    revision="1",
    digest=canonical_json_digest(
        {
            "contract": "participant-resource-measure/v1",
            "value": "unit, existing accounting mode, exact meter and existing reset mode",
            "effect": (
                "existing integer budget/pool reservation, measured settlement, generation and evidence enforcement"
            ),
        }
    ),
)
_POLICY = DomainProfileAdmissionPolicyModel(
    required_operations=(DomainProfileOperation.EXECUTION, DomainProfileOperation.TYPED_REPORT)
)


def resource_measure_supported(
    kind: object,
    *,
    unit: str,
    accounting_mode: str,
    meter_profile_ref: str,
    reset: str,
    context: DomainProfileResolutionContextModel | None,
) -> bool:
    """Admit exact quantity semantics; a coordinate alone never authorizes use."""

    if not isinstance(kind, DomainProfileCoordinateModel):
        return True
    resolved = resolve_domain_profile_definition(kind, context) if context is not None else None
    if resolved is None or not resolved.resolved or resolved.definition.semantic_contract != RESOURCE_MEASURE_SEMANTICS:
        return False
    binding = DomainProfileBindingModel(
        binding_id="measure",
        coordinate=kind,
        owner={
            "owning_contract_id": "participant-resource-budget-policy-v1",
            "canonical_address": "#/quantity",
            "concept_family": "resource-accounting",
            "lifecycle_phase": "execution",
            "context": "participant-resource-measure",
            "use": "constraint",
        },
        value={
            "unit": unit,
            "accounting_mode": accounting_mode,
            "meter_profile_ref": meter_profile_ref,
            "reset": reset,
        },
        provenance={"basis": "author-supplied", "source_ref": "urn:openrae:resource-budget"},
    )
    return admit_domain_profile_bindings((binding,), context, policy=_POLICY).admitted


def require_resource_pool_profiles(capabilities: object) -> None:
    """Check that every extension pool has at least one supported reset mode."""

    for pool in capabilities.configured_pools:
        if not isinstance(pool.resource_kind, DomainProfileCoordinateModel):
            continue
        if not any(
            resource_measure_supported(
                pool.resource_kind,
                unit=pool.unit,
                accounting_mode=pool.accounting_mode,
                meter_profile_ref=pool.meter_profile_ref,
                reset=reset,
                context=capabilities.domain_profile_context,
            )
            for reset in capabilities.supported_reset_modes
        ):
            raise ValueError("Resource pool lacks independently supported typed profile semantics")
