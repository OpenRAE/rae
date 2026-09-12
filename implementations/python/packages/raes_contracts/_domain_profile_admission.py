"""Operation-specific fail-closed admission for domain-profile bindings."""

from __future__ import annotations

from dataclasses import dataclass

from ._domain_profile_contracts import (
    DomainProfileAdmissionOutcome,
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingUse,
    DomainProfileDefinitionModel,
    DomainProfileDefinitionProvenanceModel,
    DomainProfileLimitsModel,
    DomainProfileOperation,
    DomainProfileResolutionContextModel,
    DomainProfileResolutionOutcome,
    DomainProfileSupportDeclarationModel,
)
from ._domain_profile_resolution import DomainProfileDefinitionResolution, resolve_domain_profile_definition
from ._domain_profile_validation import (
    _inspect_json_value,
    _InspectionBudget,
    _ProfileAdmissionError,
    _validate_structural_value,
)
from .diagnostics import Diagnostic, Severity


@dataclass(frozen=True, slots=True)
class DomainProfileBindingAdmission:
    binding_id: str
    outcome: DomainProfileAdmissionOutcome
    resolution_outcome: DomainProfileResolutionOutcome | None
    structurally_valid: bool
    semantics_supported: bool
    opaque: bool
    definition_provenance: DomainProfileDefinitionProvenanceModel | None
    binding_basis: DomainProfileBindingBasis
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class DomainProfileAdmissionReport:
    results: tuple[DomainProfileBindingAdmission, ...]
    bindings_total: int
    diagnostics_truncated: bool = False

    @property
    def admitted(self) -> bool:
        return (
            not self.diagnostics_truncated
            and len(self.results) == self.bindings_total
            and all(
                result.outcome
                in {
                    DomainProfileAdmissionOutcome.VALIDATED,
                    DomainProfileAdmissionOutcome.OPAQUE_PRESERVED,
                }
                for result in self.results
            )
        )


def _required_operations(
    binding: DomainProfileBindingModel,
    policy: DomainProfileAdmissionPolicyModel,
) -> tuple[DomainProfileOperation, ...]:
    by_use = {
        DomainProfileBindingUse.CONSTRAINT: {
            DomainProfileOperation.STRUCTURAL_VALIDATION,
            DomainProfileOperation.SEMANTIC_VALIDATION,
        },
        DomainProfileBindingUse.TYPED_REPORT: {
            DomainProfileOperation.STRUCTURAL_VALIDATION,
            DomainProfileOperation.TYPED_REPORT,
        },
        DomainProfileBindingUse.ANNOTATION: {DomainProfileOperation.STRUCTURAL_VALIDATION},
        DomainProfileBindingUse.OPAQUE_EXCHANGE: set(),
    }
    return tuple(sorted(by_use[binding.owner.use] | set(policy.required_operations), key=str))


def _admission_diagnostic(
    outcome: DomainProfileAdmissionOutcome,
    *,
    warning: bool = False,
) -> tuple[Diagnostic, ...]:
    messages = {
        DomainProfileAdmissionOutcome.OPAQUE_PRESERVED: (
            "the unresolved profile value is preserved as non-binding opaque data without semantic claims"
        ),
        DomainProfileAdmissionOutcome.RESOLUTION_REFUSED: (
            "the exact required profile definition could not be resolved from the supplied local context"
        ),
        DomainProfileAdmissionOutcome.CONTEXT_REFUSED: (
            "the profile definition does not permit the requested host context"
        ),
        DomainProfileAdmissionOutcome.UNSUPPORTED_OPERATION: (
            "the exact profile and semantic contract lack support for a required operation"
        ),
        DomainProfileAdmissionOutcome.UNSUPPORTED_VOCABULARY: (
            "the structural validator does not support every required schema vocabulary"
        ),
        DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD: (
            "the profile schema uses a keyword outside the admitted safe subset"
        ),
        DomainProfileAdmissionOutcome.SCHEMA_INVALID: "the supplied profile schema is not safely admissible",
        DomainProfileAdmissionOutcome.VALUE_INVALID: "the profile value does not satisfy its exact schema",
        DomainProfileAdmissionOutcome.LIMIT_EXCEEDED: "domain profile admission exhausted a configured limit",
    }
    return (
        Diagnostic(
            code=f"domain-profile.{outcome.value}",
            domain="domain-profile",
            address="#",
            message=messages[outcome],
            severity=Severity.WARNING if warning else Severity.ERROR,
        ),
    )


def _admission_result(
    binding: DomainProfileBindingModel,
    outcome: DomainProfileAdmissionOutcome,
    *,
    semantics_supported: bool = False,
    opaque: bool = False,
    provenance: DomainProfileDefinitionProvenanceModel | None = None,
    resolution_outcome: DomainProfileResolutionOutcome | None = None,
    diagnostics: tuple[Diagnostic, ...] | None = None,
) -> DomainProfileBindingAdmission:
    selected_diagnostics = diagnostics
    if selected_diagnostics is None:
        selected_diagnostics = ()
        if outcome is not DomainProfileAdmissionOutcome.VALIDATED:
            selected_diagnostics = _admission_diagnostic(
                outcome,
                warning=outcome is DomainProfileAdmissionOutcome.OPAQUE_PRESERVED,
            )
    return DomainProfileBindingAdmission(
        binding_id=binding.binding_id,
        outcome=outcome,
        resolution_outcome=resolution_outcome,
        structurally_valid=outcome is DomainProfileAdmissionOutcome.VALIDATED,
        semantics_supported=semantics_supported,
        opaque=opaque,
        definition_provenance=provenance,
        binding_basis=binding.provenance.basis,
        diagnostics=selected_diagnostics,
    )


def _matching_support(
    definition: DomainProfileDefinitionModel,
    context: DomainProfileResolutionContextModel,
) -> DomainProfileSupportDeclarationModel | None:
    exact = [
        declaration
        for declaration in context.support_declarations
        if declaration.coordinate == definition.coordinate
        and declaration.semantic_contract == definition.semantic_contract
    ]
    return exact[0] if len(exact) == 1 else None


def _opaque_exchange_allowed(
    binding: DomainProfileBindingModel,
    policy: DomainProfileAdmissionPolicyModel,
) -> bool:
    return (
        binding.owner.use is DomainProfileBindingUse.OPAQUE_EXCHANGE
        and policy.allow_opaque_exchange
        and not _required_operations(binding, policy)
    )


def _admit_unresolved_binding(
    binding: DomainProfileBindingModel,
    context: DomainProfileResolutionContextModel,
    policy: DomainProfileAdmissionPolicyModel,
    resolution: DomainProfileDefinitionResolution,
) -> DomainProfileBindingAdmission:
    if resolution.outcome is not DomainProfileResolutionOutcome.DEFINITION_UNAVAILABLE or not _opaque_exchange_allowed(
        binding, policy
    ):
        return _admission_result(
            binding,
            DomainProfileAdmissionOutcome.RESOLUTION_REFUSED,
            resolution_outcome=resolution.outcome,
            diagnostics=resolution.diagnostics,
        )
    try:
        _inspect_json_value(binding.value, _InspectionBudget(context.limits))
        result = _admission_result(
            binding,
            DomainProfileAdmissionOutcome.OPAQUE_PRESERVED,
            opaque=True,
            resolution_outcome=resolution.outcome,
        )
    except _ProfileAdmissionError as exc:
        result = _admission_result(
            binding,
            exc.outcome,
            resolution_outcome=resolution.outcome,
        )
    return result


def _resolved_support(
    binding: DomainProfileBindingModel,
    definition: DomainProfileDefinitionModel,
    context: DomainProfileResolutionContextModel,
    required: tuple[DomainProfileOperation, ...],
) -> tuple[tuple[DomainProfileOperation, ...], DomainProfileSupportDeclarationModel]:
    if binding.owner.context not in definition.allowed_contexts:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.CONTEXT_REFUSED,
            "the profile definition does not permit the requested host context",
        )
    selected_required = required or (DomainProfileOperation.STRUCTURAL_VALIDATION,)
    support = _matching_support(definition, context)
    if support is None or not set(selected_required) <= set(support.operations):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.UNSUPPORTED_OPERATION,
            "the exact profile and semantic contract lack support for a required operation",
        )
    return selected_required, support


def _admit_resolved_binding(
    binding: DomainProfileBindingModel,
    context: DomainProfileResolutionContextModel,
    required: tuple[DomainProfileOperation, ...],
    resolution: DomainProfileDefinitionResolution,
) -> DomainProfileBindingAdmission:
    definition = resolution.definition
    assert definition is not None
    try:
        selected_required, support = _resolved_support(binding, definition, context, required)
        if DomainProfileOperation.STRUCTURAL_VALIDATION in selected_required:
            _validate_structural_value(binding, definition, support, context.limits)
        result = _admission_result(
            binding,
            DomainProfileAdmissionOutcome.VALIDATED,
            semantics_supported=bool(set(support.operations) - {DomainProfileOperation.STRUCTURAL_VALIDATION}),
            provenance=resolution.provenance,
            resolution_outcome=resolution.outcome,
        )
    except _ProfileAdmissionError as exc:
        result = _admission_result(
            binding,
            exc.outcome,
            resolution_outcome=resolution.outcome,
        )
    return result


def _admit_one_binding(
    binding: DomainProfileBindingModel,
    context: DomainProfileResolutionContextModel,
    policy: DomainProfileAdmissionPolicyModel,
) -> DomainProfileBindingAdmission:
    required = _required_operations(binding, policy)
    resolution = resolve_domain_profile_definition(binding.coordinate, context)
    if not resolution.resolved:
        return _admit_unresolved_binding(binding, context, policy, resolution)
    return _admit_resolved_binding(binding, context, required, resolution)


def _flatten_bindings(
    bindings: tuple[DomainProfileBindingModel, ...],
    limits: DomainProfileLimitsModel,
) -> tuple[DomainProfileBindingModel, ...]:
    flattened: list[DomainProfileBindingModel] = []

    def visit(binding: DomainProfileBindingModel, depth: int) -> None:
        if depth > limits.max_depth or len(flattened) >= limits.max_bindings:
            raise _ProfileAdmissionError(
                DomainProfileAdmissionOutcome.LIMIT_EXCEEDED,
                "domain profile binding tree exceeds a configured limit",
            )
        flattened.append(binding)
        for child in binding.children:
            visit(child, depth + 1)

    for binding in bindings:
        visit(binding, 0)
    if len({binding.binding_id for binding in flattened}) != len(flattened):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.RESOLUTION_REFUSED,
            "domain profile binding ids must be globally unique in one admission request",
        )
    return tuple(flattened)


def admit_domain_profile_bindings(
    bindings: tuple[DomainProfileBindingModel, ...],
    context: DomainProfileResolutionContextModel,
    *,
    policy: DomainProfileAdmissionPolicyModel,
) -> DomainProfileAdmissionReport:
    """Resolve and negotiate every binding before a caller performs mutation."""

    if not bindings:
        return DomainProfileAdmissionReport(results=(), bindings_total=0)
    try:
        flattened = _flatten_bindings(bindings, context.limits)
    except _ProfileAdmissionError as exc:
        return DomainProfileAdmissionReport(
            results=(_admission_result(bindings[0], exc.outcome),),
            bindings_total=len(bindings),
        )
    results: list[DomainProfileBindingAdmission] = []
    diagnostic_count = 0
    diagnostics_truncated = False
    for binding in flattened:
        result = _admit_one_binding(binding, context, policy)
        additional = len(result.diagnostics)
        if diagnostic_count + additional > context.limits.max_diagnostics:
            diagnostics_truncated = True
            break
        results.append(result)
        diagnostic_count += additional
    return DomainProfileAdmissionReport(
        results=tuple(results),
        bindings_total=len(flattened),
        diagnostics_truncated=diagnostics_truncated,
    )
