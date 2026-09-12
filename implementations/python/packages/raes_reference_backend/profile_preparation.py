"""Reference implementation of public portable resource-label profiles.

Labels are typed portable resource state, not guest settings, access grants or
observations. The semantic implementation is installed code; profile documents
and target choices cannot name or load handlers.
"""

from copy import deepcopy
from dataclasses import replace

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import (
    DomainProfileBindingBasis,
    DomainProfileBindingProvenanceModel,
    DomainProfileResolutionContextModel,
    DomainProfileSemanticContractModel,
    resolve_domain_profile_definition,
)
from raes_contracts.planning import ChangeAction
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.realization_profiles import (
    profile_binding_tree,
    profile_resource_address,
    profile_selection_violation,
)
from raes_contracts.realization_structure import validate_realization_value

RESOURCE_LABEL_SEMANTICS = DomainProfileSemanticContractModel(
    authority="https://openrae.org/profiles",
    contract_id="portable-resource-labels",
    revision="1",
    digest=canonical_json_digest(
        {
            "contract": "portable-resource-labels/v1",
            "value": "public record of nonempty string keys and string values",
            "effect": "portable resource labels only; no infrastructure, policy, participant or evidence authority",
        }
    ),
)


def reference_profile_configuration(context, choices):
    """Revalidate explicit local configuration; never infer semantic support."""

    if context is None:
        if choices:
            raise ValueError("Profile choices require an admitted local context")
        return None, {}
    if (
        not isinstance(context, DomainProfileResolutionContextModel)
        or not validate_realization_value((context, choices), python_carriers=True).conformant
    ):
        raise ValueError("Reference profile configuration exceeds bounded input limits")
    context = DomainProfileResolutionContextModel.model_validate(context.model_dump(mode="json"))
    if any(row.semantic_contract != RESOURCE_LABEL_SEMANTICS for row in context.support_declarations):
        raise ValueError("Reference provisioner does not implement the declared profile semantics")
    if not isinstance(choices, dict) or any(not _labels(value) for value in choices.values()):
        raise ValueError("Reference profile choices must be public resource-label records")
    return deepcopy(context), deepcopy(choices)


def _labels(value):
    return isinstance(value, dict) and all(
        isinstance(key, str) and key and isinstance(item, str) for key, item in value.items()
    )


def reference_profile_diagnostics(plan, context):
    """Execute the installed semantic validator over the entire binding tree."""

    try:
        for operation in plan.operations:
            for binding in profile_binding_tree(getattr(operation, "profile_bindings", ())).values():
                resolved = resolve_domain_profile_definition(binding.coordinate, context)
                if (
                    not resolved.resolved
                    or resolved.definition.semantic_contract != RESOURCE_LABEL_SEMANTICS
                    or not _labels(binding.value)
                    or profile_resource_address(binding) != operation.address
                ):
                    raise ValueError("Unsupported resource labels")
    except (AttributeError, TypeError, ValueError):
        return [
            Diagnostic(
                "reference-backend.profile-invalid",
                "provisioning",
                "profiles",
                "Reference profile realization is unsupported.",
            )
        ]
    return []


def prepare_reference_profiles(plan, snapshot, context, choices):
    """Return one configured completion, preserving still-admitted current choices."""

    if plan.profile_authority is None:
        return RealizationPreparation.for_request(plan, snapshot, operations=tuple(plan.operations))
    existing = tuple(binding for op in plan.operations for binding in op.profile_bindings)
    if profile_selection_violation(plan.profile_authority, existing, context) is None:
        bindings = existing
    else:

        def select(binding):
            value = choices.get(binding.coordinate.definition_digest, binding.value)
            return binding.model_copy(
                update={
                    "value": deepcopy(value),
                    "provenance": DomainProfileBindingProvenanceModel(
                        basis=DomainProfileBindingBasis.BACKEND_SELECTED,
                        source_ref="urn:openrae:reference:profile-preparation",
                    ),
                    "children": tuple(select(child) for child in binding.children),
                }
            )

        bindings = tuple(select(binding) for binding in plan.profile_authority.bindings)
    operations = tuple(
        replace(
            op,
            profile_bindings=tuple(binding for binding in bindings if profile_resource_address(binding) == op.address),
        )
        if op.action is not ChangeAction.DELETE
        else op
        for op in plan.operations
    )
    selected = replace(plan, operations=list(operations))
    diagnostics = reference_profile_diagnostics(selected, context)
    if profile_selection_violation(plan.profile_authority, bindings, context):
        diagnostics.append(
            Diagnostic(
                "reference-backend.profile-choice-unavailable",
                "provisioning",
                "profiles",
                "No supported configured profile completion is available.",
            )
        )
    return RealizationPreparation.for_request(
        plan, snapshot, operations=operations, diagnostics=tuple(diagnostics), success=not diagnostics
    )
