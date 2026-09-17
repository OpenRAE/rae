"""Coupled operating-system capability-domain validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from raes.nodes import OSFamily
from raes.operating_systems import normalize_os_distribution, normalize_os_version
from raes.runtime_values import parse_runtime_enum_identity
from raes.value_parsing import extract_variable_name
from raes_backend_protocols.capabilities import ProvisionerCapabilities

from ..models import CompiledCapabilityConstraint, Diagnostic, NodeRuntime, RuntimeModel

_OS_DISTRIBUTION_DOMAIN_INVALID = "provisioner.os-distribution-variable-domain-invalid"
_OS_VERSION_DOMAIN_INVALID = "provisioner.os-version-variable-domain-invalid"

_ScalarDomain = tuple[str, ...] | None
_OperatingSystemDomains = tuple[_ScalarDomain, _ScalarDomain, _ScalarDomain]
_OperatingSystemChoice = tuple[str, str, str]


@dataclass(frozen=True)
class FeasibleOperatingSystemDomains:
    """Coupled apparatus choices remaining after authored-domain intersection."""

    families: tuple[str, ...]
    distributions: tuple[str, ...]
    versions: tuple[str, ...]

    def values_for(self, requirement_kind: str) -> tuple[str, ...]:
        return {
            "os-family": self.families,
            "os-distribution": self.distributions,
            "os-version": self.versions,
        }[requirement_kind]


def _capability_constraint(
    model: RuntimeModel,
    *,
    address: str,
    concern: str,
) -> CompiledCapabilityConstraint | None:
    return next(
        (
            constraint
            for constraint in model.capability_constraints
            if constraint.address == address and constraint.concern == concern
        ),
        None,
    )


def _error_diagnostic(code: str, address: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, domain="provisioning", address=address, message=message)


def _family_domain(
    model: RuntimeModel,
    node: NodeRuntime,
) -> tuple[tuple[str, ...] | None, Diagnostic | None]:
    constraint = _capability_constraint(model, address=node.address, concern="nodes.os")
    diagnostic = None
    if constraint is None:
        unresolved = extract_variable_name(node.os_family)
        if unresolved is not None:
            diagnostic = _error_diagnostic(
                "provisioner.os-family-variable-ref-unbound",
                node.address,
                f"Provisioner capability validation cannot resolve undeclared variable '{unresolved}' "
                "referenced by nodes.os.",
            )
        domain = (node.os_family,) if node.os_family else None
    else:
        domain, diagnostic = _validated_family_constraint(constraint, node.address)
    return (None, diagnostic) if diagnostic is not None else (domain, None)


def _validated_family_constraint(
    constraint: CompiledCapabilityConstraint,
    address: str,
) -> tuple[tuple[str, ...], Diagnostic | None]:
    variable_name = ".".join(constraint.parameter)
    validated: list[str] = []
    diagnostic = None
    for raw_value in constraint.allowed_values:
        token, message = _parse_family_domain_value(raw_value, variable_name)
        if message is not None:
            diagnostic = _error_diagnostic("provisioner.os-family-variable-domain-invalid", address, message)
            break
        if token is not None:
            validated.append(token)
    return tuple(validated), diagnostic


def _parse_family_domain_value(raw_value: object, variable_name: str) -> tuple[str | None, str | None]:
    try:
        return parse_runtime_enum_identity(raw_value, OSFamily, field_name="os"), None
    except ValueError as exc:
        return None, f"Variable '{variable_name}' has an invalid nodes.os domain: {exc}."


def _scalar_domain_or_open(
    model: RuntimeModel,
    node: NodeRuntime,
    *,
    concern: str,
    value: str,
    field_name: str,
    invalid_code: str,
    normalizer: Callable[[object], object],
) -> tuple[tuple[str, ...] | None, Diagnostic | None]:
    if not value and _capability_constraint(model, address=node.address, concern=concern) is None:
        return None, None
    return _validated_scalar_domain(
        model,
        node,
        concern=concern,
        value=value,
        field_name=field_name,
        invalid_code=invalid_code,
        normalizer=normalizer,
    )


def _validated_scalar_domain(
    model: RuntimeModel,
    node: NodeRuntime,
    *,
    concern: str,
    value: str,
    field_name: str,
    invalid_code: str,
    normalizer: Callable[[object], object],
) -> tuple[tuple[str, ...] | None, Diagnostic | None]:
    constraint = _capability_constraint(model, address=node.address, concern=concern)
    variable_name = extract_variable_name(value)
    if constraint is None:
        if variable_name is not None:
            return None, _error_diagnostic(
                f"provisioner.{field_name}-variable-ref-unbound",
                node.address,
                f"Provisioner capability validation cannot resolve undeclared variable '{variable_name}' "
                f"referenced by nodes.{field_name}.",
            )
        raw_values: tuple[object, ...] = (value,)
    else:
        variable_name = ".".join(constraint.parameter)
        raw_values = constraint.allowed_values

    validated: list[str] = []
    diagnostic = None
    label = variable_name or field_name
    for raw_value in raw_values:
        token, message = _normalize_scalar_domain_value(raw_value, label, field_name, normalizer)
        if message is not None:
            diagnostic = _error_diagnostic(invalid_code, node.address, message)
            break
        if token is not None:
            validated.append(token)
    return (None, diagnostic) if diagnostic is not None else (tuple(validated), None)


def _normalize_scalar_domain_value(
    raw_value: object,
    label: str,
    field_name: str,
    normalizer: Callable[[object], object],
) -> tuple[str | None, str | None]:
    parsed = None
    message = None
    try:
        parsed = normalizer(raw_value)
    except (TypeError, ValueError) as exc:
        message = (
            f"Variable '{label}' allowed_values contain value {raw_value!r} invalid for nodes.{field_name}: {exc}."
        )
    if message is None and extract_variable_name(parsed) is not None:
        message = f"Variable '{label}' has a non-concrete nodes.{field_name} domain."
    token = getattr(parsed, "value", parsed)
    if message is None and (not isinstance(token, str) or not token):
        message = f"Variable '{label}' contains an invalid nodes.{field_name} value."
    return token if isinstance(token, str) else None, message


def feasible_operating_system_domains(
    model: RuntimeModel,
    node: NodeRuntime,
    provisioner: ProvisionerCapabilities,
) -> tuple[FeasibleOperatingSystemDomains | None, Diagnostic | None]:
    """Intersect exact, constrained, and open OS intent with coupled rows."""

    os_requirements = {
        requirement.requirement_kind
        for requirement in model.realization_requirements
        if requirement.address == node.address
        and requirement.requirement_kind in {"os-family", "os-distribution", "os-version"}
    }
    feasible_domains = None
    diagnostic = None
    if os_requirements:
        domains, diagnostic = _authored_operating_system_domains(model, node)
        if diagnostic is None:
            family_domain, distribution_domain, version_domain = domains
            feasible = _intersect_operating_system_domains(
                provisioner,
                family_domain=family_domain,
                distribution_domain=distribution_domain,
                version_domain=version_domain,
            )
            if feasible:
                feasible_domains = _feasible_domains(feasible)
            else:
                diagnostic = _error_diagnostic(
                    "provisioner.unsupported-operating-system",
                    node.address,
                    "Provisioner has no coupled operating-system compatibility row intersecting the authored "
                    "exact, constrained, and open OS domains.",
                )
    return feasible_domains, diagnostic


def _authored_operating_system_domains(
    model: RuntimeModel,
    node: NodeRuntime,
) -> tuple[_OperatingSystemDomains | None, Diagnostic | None]:
    family_domain, diagnostic = _family_domain(model, node)
    if diagnostic is not None:
        return None, diagnostic
    distribution_domain, diagnostic = _scalar_domain_or_open(
        model,
        node,
        concern="nodes.os_distribution",
        value=node.os_distribution,
        field_name="os_distribution",
        invalid_code=_OS_DISTRIBUTION_DOMAIN_INVALID,
        normalizer=normalize_os_distribution,
    )
    if diagnostic is not None:
        return None, diagnostic
    version_domain, diagnostic = _scalar_domain_or_open(
        model,
        node,
        concern="nodes.os_version",
        value=node.os_version,
        field_name="os_version",
        invalid_code=_OS_VERSION_DOMAIN_INVALID,
        normalizer=normalize_os_version,
    )
    domains = (family_domain, distribution_domain, version_domain)
    return (None, diagnostic) if diagnostic is not None else (domains, None)


def _intersect_operating_system_domains(
    provisioner: ProvisionerCapabilities,
    *,
    family_domain: _ScalarDomain,
    distribution_domain: _ScalarDomain,
    version_domain: _ScalarDomain,
) -> set[_OperatingSystemChoice]:
    return {
        (row.family, row.distribution, version)
        for row in provisioner.operating_systems
        if family_domain is None or row.family in family_domain
        if distribution_domain is None or row.distribution in distribution_domain
        for version in row.versions
        if version_domain is None or version in version_domain
    }


def _feasible_domains(feasible: set[_OperatingSystemChoice]) -> FeasibleOperatingSystemDomains:
    return FeasibleOperatingSystemDomains(
        families=tuple(sorted({family for family, _, _ in feasible})),
        distributions=tuple(sorted({distribution for _, distribution, _ in feasible})),
        versions=tuple(sorted({version for _, _, version in feasible})),
    )


def operating_system_choice_supported(
    provisioner: ProvisionerCapabilities, family: str, distribution: str, version: str
) -> bool:
    """Check one selected tuple against coupled rows without combining leaf sets."""

    unmodelled = any(value in {"unknown", "other"} for value in (family, distribution, version))
    if unmodelled or (family and family not in provisioner.supported_os_families):
        return False
    if not distribution and not version:
        return bool(family)
    return bool(
        _intersect_operating_system_domains(
            provisioner,
            family_domain=(family,) if family else None,
            distribution_domain=(distribution,) if distribution else None,
            version_domain=(version,) if version else None,
        )
    )


def validate_node_operating_system(
    model: RuntimeModel,
    node: NodeRuntime,
    provisioner: ProvisionerCapabilities,
) -> list[Diagnostic]:
    """Reject only an empty intersection with the coupled capability rows."""

    _, diagnostic = feasible_operating_system_domains(model, node, provisioner)
    return [diagnostic] if diagnostic is not None else []
