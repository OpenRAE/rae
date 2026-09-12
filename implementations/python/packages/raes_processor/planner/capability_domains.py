"""Finite-variable capability-domain validation for provisioner gates."""

from raes.architectures import normalize_architecture
from raes.infrastructure import MINIMUM_NODE_COUNT
from raes.nodes import OSFamily
from raes.runtime_values import parse_runtime_enum_identity
from raes.value_parsing import extract_variable_name, parse_int_or_var
from raes_backend_protocols.account_features import provisioner_account_features

from ..models import CompiledCapabilityConstraint, Diagnostic, NodeRuntime, ResolvedResource, RuntimeModel

_COUNT_DOMAIN_INVALID = "provisioner.count-variable-domain-invalid"
_OS_FAMILY_DOMAIN_INVALID = "provisioner.os-family-variable-domain-invalid"
_ARCHITECTURE_DOMAIN_INVALID = "provisioner.node-architecture-variable-domain-invalid"


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
    return Diagnostic(
        code=code,
        domain="provisioning",
        address=address,
        message=message,
    )


def _os_allowed_value(
    raw_value: str | int | float | bool,
    variable_name: str,
    address: str,
) -> tuple[str | None, Diagnostic | None]:
    try:
        return parse_runtime_enum_identity(raw_value, OSFamily, field_name="os"), None
    except ValueError as exc:
        message = f"Variable '{variable_name}' has an invalid nodes.os domain: {exc}."
        return None, _error_diagnostic(_OS_FAMILY_DOMAIN_INVALID, address, message)


def _validate_os_allowed_values(
    variable_name: str,
    allowed_values: tuple[str | int | float | bool, ...],
    *,
    address: str,
) -> tuple[tuple[str, ...] | None, Diagnostic | None]:
    validated_values: list[str] = []
    for raw_value in allowed_values:
        value, error = _os_allowed_value(raw_value, variable_name, address)
        if error is not None:
            return None, error
        validated_values.append(value)

    return tuple(validated_values), None


def _node_os_without_constraint(
    node: NodeRuntime,
    supported_os_families: frozenset[str],
) -> list[Diagnostic]:
    unresolved = extract_variable_name(node.os_family)
    if unresolved is not None:
        return [
            _error_diagnostic(
                "provisioner.os-family-variable-ref-unbound",
                node.address,
                (
                    "Provisioner capability validation cannot resolve undeclared "
                    f"variable '{unresolved}' referenced by nodes.os."
                ),
            )
        ]
    if node.os_family in supported_os_families:
        return []
    return [
        Diagnostic(
            code="provisioner.unsupported-os-family",
            domain="provisioning",
            address=node.address,
            message=f"Provisioner does not support OS family '{node.os_family}'.",
        )
    ]


def _node_os_with_constraint(
    constraint: CompiledCapabilityConstraint,
    node: NodeRuntime,
    supported_os_families: frozenset[str],
) -> list[Diagnostic]:
    variable_name = ".".join(constraint.parameter)
    finite_domain, domain_error = _validate_os_allowed_values(
        variable_name,
        constraint.allowed_values,
        address=node.address,
    )
    if domain_error is not None:
        return [domain_error]

    diagnostics: list[Diagnostic] = []
    if finite_domain is not None:
        supported_values = sorted({value for value in finite_domain if value in supported_os_families})
        if not supported_values:
            diagnostics.append(
                Diagnostic(
                    code="provisioner.unsupported-os-family",
                    domain="provisioning",
                    address=node.address,
                    message=(f"Provisioner supports no OS family allowed by variable '{variable_name}'."),
                )
            )
    return diagnostics


def _validate_node_os_family(
    model: RuntimeModel,
    node: NodeRuntime,
    supported_os_families: frozenset[str],
) -> list[Diagnostic]:
    if not node.os_family:
        return []

    constraint = _capability_constraint(model, address=node.address, concern="nodes.os")
    if constraint is None:
        return _node_os_without_constraint(node, supported_os_families)
    return _node_os_with_constraint(constraint, node, supported_os_families)


def _node_os_domain(
    model: RuntimeModel,
    node: NodeRuntime,
) -> tuple[tuple[str, ...] | None, Diagnostic | None]:
    constraint = _capability_constraint(model, address=node.address, concern="nodes.os")
    if constraint is None:
        unresolved = extract_variable_name(node.os_family)
        if unresolved is not None:
            return None, _error_diagnostic(
                "provisioner.os-family-variable-ref-unbound",
                node.address,
                f"Provisioner capability validation cannot resolve undeclared variable '{unresolved}' "
                "referenced by nodes.os.",
            )
        return (node.os_family,), None
    return _validate_os_allowed_values(
        ".".join(constraint.parameter),
        constraint.allowed_values,
        address=node.address,
    )


def _architecture_allowed_value(
    raw_value: str | int | float | bool,
    variable_name: str,
    address: str,
) -> tuple[str | None, Diagnostic | None]:
    try:
        parsed = normalize_architecture(raw_value)
    except ValueError as exc:
        message = (
            f"Variable '{variable_name}' allowed_values contain value {raw_value!r} "
            f"invalid for nodes.architecture: {exc}."
        )
    else:
        if extract_variable_name(parsed) is not None:
            message = f"Variable '{variable_name}' has a non-concrete nodes.architecture domain."
        else:
            token = getattr(parsed, "value", parsed)
            if isinstance(token, str) and token:
                return token, None
            message = (
                f"Variable '{variable_name}' allowed_values contain value {raw_value!r} "
                "that could not be validated for nodes.architecture."
            )
    return None, _error_diagnostic(_ARCHITECTURE_DOMAIN_INVALID, address, message)


def _validate_architecture_allowed_values(
    variable_name: str,
    allowed_values: tuple[str | int | float | bool, ...],
    *,
    address: str,
) -> tuple[tuple[str, ...] | None, Diagnostic | None]:
    validated_values: list[str] = []
    for raw_value in allowed_values:
        value, error = _architecture_allowed_value(raw_value, variable_name, address)
        if error is not None:
            return None, error
        validated_values.append(value)

    return tuple(validated_values), None


def _node_architecture_without_constraint(
    node: NodeRuntime,
    supported_node_architectures: frozenset[str],
) -> list[Diagnostic]:
    unresolved = extract_variable_name(node.architecture)
    if unresolved is not None:
        return [
            _error_diagnostic(
                "provisioner.node-architecture-variable-ref-unbound",
                node.address,
                (
                    "Provisioner capability validation cannot resolve undeclared "
                    f"variable '{unresolved}' referenced by nodes.architecture."
                ),
            )
        ]
    if node.architecture in supported_node_architectures:
        return []
    return [
        Diagnostic(
            code="provisioner.unsupported-node-architecture",
            domain="provisioning",
            address=node.address,
            message=f"Provisioner does not support node architecture '{node.architecture}'.",
        )
    ]


def _node_architecture_with_constraint(
    constraint: CompiledCapabilityConstraint,
    node: NodeRuntime,
    supported_node_architectures: frozenset[str],
) -> list[Diagnostic]:
    variable_name = ".".join(constraint.parameter)
    finite_domain, domain_error = _validate_architecture_allowed_values(
        variable_name,
        constraint.allowed_values,
        address=node.address,
    )
    if domain_error is not None:
        return [domain_error]

    diagnostics: list[Diagnostic] = []
    if finite_domain is not None:
        unsupported_values = sorted({value for value in finite_domain if value not in supported_node_architectures})
        if unsupported_values:
            rendered = ", ".join(repr(value) for value in unsupported_values)
            diagnostics.append(
                Diagnostic(
                    code="provisioner.unsupported-node-architecture",
                    domain="provisioning",
                    address=node.address,
                    message=(
                        "Provisioner does not support all node architectures allowed by "
                        f"variable '{variable_name}': {rendered}."
                    ),
                )
            )
    return diagnostics


def _validate_node_architecture(
    model: RuntimeModel,
    node: NodeRuntime,
    supported_node_architectures: frozenset[str],
) -> list[Diagnostic]:
    if not node.architecture:
        return []

    constraint = _capability_constraint(model, address=node.address, concern="nodes.architecture")
    if constraint is None:
        return _node_architecture_without_constraint(node, supported_node_architectures)
    return _node_architecture_with_constraint(constraint, node, supported_node_architectures)


def _count_allowed_value(
    raw_value: str | int | float | bool,
    variable_name: str,
    address: str,
) -> tuple[int | None, Diagnostic | None]:
    try:
        parsed = parse_int_or_var(
            raw_value,
            minimum=MINIMUM_NODE_COUNT,
            field_name="count",
        )
    except ValueError as exc:
        message = (
            f"Variable '{variable_name}' allowed_values contain value {raw_value!r} "
            f"invalid for infrastructure.count: {exc}."
        )
    else:
        if extract_variable_name(parsed) is not None:
            message = f"Variable '{variable_name}' has a non-concrete infrastructure.count domain."
        elif isinstance(parsed, int):
            return parsed, None
        else:
            message = (
                f"Variable '{variable_name}' allowed_values contain value {raw_value!r} "
                "that could not be validated for infrastructure.count."
            )
    return None, _error_diagnostic(_COUNT_DOMAIN_INVALID, address, message)


def _validate_count_allowed_values(
    variable_name: str,
    allowed_values: tuple[str | int | float | bool, ...],
    *,
    address: str,
) -> tuple[int | None, Diagnostic | None]:
    validated_values: list[int] = []
    for raw_value in allowed_values:
        value, error = _count_allowed_value(raw_value, variable_name, address)
        if error is not None:
            return None, error
        validated_values.append(value)

    return max(validated_values), None


def _count_without_constraint(
    count: object,
    resource: ResolvedResource,
) -> tuple[int | None, Diagnostic | None]:
    if isinstance(count, int):
        return count, None
    unresolved = extract_variable_name(count) if isinstance(count, str) else None
    if unresolved is None:
        return None, None
    return None, _error_diagnostic(
        "provisioner.count-variable-ref-unbound",
        resource.address,
        (
            "Provisioner capability validation cannot resolve undeclared "
            f"variable '{unresolved}' referenced by infrastructure.count."
        ),
    )


def _count_with_constraint(
    constraint: CompiledCapabilityConstraint,
    resource: ResolvedResource,
) -> tuple[int | None, Diagnostic | None]:
    variable_name = ".".join(constraint.parameter)
    finite_upper_bound, domain_error = _validate_count_allowed_values(
        variable_name,
        constraint.allowed_values,
        address=resource.address,
    )
    if domain_error is not None:
        return None, domain_error
    return finite_upper_bound, None


def _resource_count_upper_bound(
    model: RuntimeModel,
    resource: ResolvedResource,
) -> tuple[int | None, Diagnostic | None]:
    count = resource.spec.get("infrastructure", {}).get("count", 1)

    constraint = _capability_constraint(
        model,
        address=resource.address,
        concern="infrastructure.count",
    )
    if constraint is None:
        return _count_without_constraint(count, resource)
    return _count_with_constraint(constraint, resource)


def _account_features(account_spec: dict[str, object]) -> set[str]:
    # Delegates to the shared canonical extractor so the planner gate and the
    # libvirt backend's capability-envelope diagnostics never diverge (issue #605).
    return set(provisioner_account_features(account_spec))
