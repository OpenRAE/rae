"""Typed SEM-218 apparatus admission for portable process-resource limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes.explicitness import ExplicitnessClass
from raes.runtime_resource_limits import process_resource_limit_domain_admits
from raes_contracts.apparatus import (
    DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND,
    ProcessResourceLimitCapability,
    RealizationSupportDeclaration,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.vocabulary import (
    ProcessResourceLimitKind,
    ProcessResourceLimitScope,
    RealizationSupportMode,
    observation_requirement_satisfied,
)

if TYPE_CHECKING:
    from .realization import CompiledRealizationRequirement


@dataclass(frozen=True)
class RealizationValueConstraint:
    """Finite authored domain for one semantic realization-record leaf."""

    identity_digest: str
    leaf: str
    parameter: tuple[str, ...]
    allowed_values: tuple[object, ...]

    def __post_init__(self) -> None:
        if not self.identity_digest.startswith("sha256:"):
            raise ValueError("realization value constraint requires a semantic identity digest")
        if self.leaf not in {"soft", "hard"}:
            raise ValueError("realization value constraint leaf must be soft or hard")
        if not self.parameter or not self.allowed_values:
            raise ValueError("realization value constraint requires a parameter and finite domain")


@dataclass(frozen=True)
class ProcessResourceLimitDemand:
    """Compiled portable process-limit demand used for apparatus admission."""

    identity_digest: str
    resource: ProcessResourceLimitKind
    scope: ProcessResourceLimitScope
    soft: int | str
    hard: int | str


def process_resource_limit_support_diagnostic(
    requirement: CompiledRealizationRequirement,
    declarations: list[RealizationSupportDeclaration],
    explicitness: ExplicitnessClass | None,
    realization_envelope: BackendRealizationEnvelopeModel | None,
) -> Diagnostic | None:
    """Check one process-limit demand against typed apparatus declarations."""

    compatible = [
        declaration
        for declaration in declarations
        if _posture_supported(declaration, explicitness) and _observation_supported(declaration, requirement)
    ]
    if not compatible:
        diagnostic = Diagnostic(
            code="realization.unsupported-process-resource-limits",
            domain=requirement.domain,
            address=requirement.address,
            message=(
                "Backend declares no typed process-resource-limit support with effective guest observation for "
                f"'{requirement.field_path}'."
            ),
            severity=Severity.ERROR,
        )
    elif explicitness is ExplicitnessClass.OPEN:
        diagnostic = (
            None
            if any(
                bound_process_resource_limit_capabilities(declaration, realization_envelope)
                for declaration in compatible
            )
            else _domain_diagnostic(requirement)
        )
    elif any(
        _demands_admitted(
            requirement,
            bound_process_resource_limit_capabilities(declaration, realization_envelope),
        )
        for declaration in compatible
    ):
        diagnostic = None
    else:
        diagnostic = _domain_diagnostic(requirement)
    return diagnostic


def bound_process_resource_limit_capabilities(
    declaration: RealizationSupportDeclaration,
    realization_envelope: BackendRealizationEnvelopeModel | None,
) -> tuple[ProcessResourceLimitCapability, ...]:
    """Return claims repeated exactly by the selected material configuration."""

    if realization_envelope is None:
        return ()
    configured = {
        ProcessResourceLimitCapability(
            resource=capability.resource,
            scopes=frozenset(capability.scopes),
            minimum=capability.minimum,
            maximum=capability.maximum,
            supports_unlimited=capability.supports_unlimited,
        )
        for capability in realization_envelope.configuration.process_resource_limits
    }
    return tuple(capability for capability in declaration.process_resource_limits if capability in configured)


def _posture_supported(
    declaration: RealizationSupportDeclaration,
    explicitness: ExplicitnessClass | None,
) -> bool:
    if explicitness is ExplicitnessClass.OPEN:
        return declaration.support_mode is RealizationSupportMode.OPEN_REALIZATION
    if explicitness is ExplicitnessClass.CONSTRAINED:
        return "process-resource-limits" in declaration.supported_constraint_kinds
    return DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND in declaration.supported_exact_requirement_kinds


def _observation_supported(
    declaration: RealizationSupportDeclaration,
    requirement: CompiledRealizationRequirement,
) -> bool:
    capability = declaration.observation_capabilities.get("process-resource-limits")
    if capability is None:
        return False
    return observation_requirement_satisfied(
        actual_scope=capability.verification_scope,
        actual_source=capability.observation_strength,
        required_scope=requirement.verification_scope,
        required_source=requirement.required_observation_strength,
    )


def _demands_admitted(
    requirement: CompiledRealizationRequirement,
    capabilities: tuple[ProcessResourceLimitCapability, ...],
) -> bool:
    constraints = {
        (constraint.identity_digest, constraint.leaf): constraint.allowed_values
        for constraint in requirement.value_constraints
    }
    return all(
        any(
            process_resource_limit_domain_admits(
                capability,
                resource=demand.resource,
                scope=demand.scope,
                soft_values=constraints.get((demand.identity_digest, "soft"), (demand.soft,)),
                hard_values=constraints.get((demand.identity_digest, "hard"), (demand.hard,)),
            )
            for capability in capabilities
        )
        for demand in requirement.process_resource_limits
    )


def _domain_diagnostic(requirement: CompiledRealizationRequirement) -> Diagnostic:
    return Diagnostic(
        code="realization.process-resource-limit-domain-mismatch",
        domain=requirement.domain,
        address=requirement.address,
        message=(
            "Backend process-resource-limit apparatus domain does not admit every authored resource, scope, and "
            f"soft/hard value for '{requirement.field_path}'."
        ),
        severity=Severity.ERROR,
    )


__all__ = [
    "ProcessResourceLimitDemand",
    "RealizationValueConstraint",
    "bound_process_resource_limit_capabilities",
    "process_resource_limit_support_diagnostic",
]
