"""Finite-domain capability constraints retained during instantiation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from ._base import extract_variable_name
from .nodes import Node
from .phase_contracts import CapabilityConstraint
from .runtime_resource_limits import RuntimeProcessResourceLimit
from .scenario import ExpandedScenario, Scenario
from .variables import Variable


def _json_pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _finite_domain_constraint(
    *,
    field_pointer: str,
    value: object,
    variables: Mapping[str, Variable],
) -> CapabilityConstraint | None:
    variable_ref = extract_variable_name(value) if isinstance(value, str) else None
    variable = variables.get(variable_ref) if variable_ref is not None else None
    if variable is None or not variable.allowed_values:
        return None
    return CapabilityConstraint(
        field_pointer=field_pointer,
        parameter=(variable_ref,),
        allowed_values=tuple(variable.allowed_values),
    )


def _present_constraints(
    *constraints: CapabilityConstraint | None,
) -> list[CapabilityConstraint]:
    return [constraint for constraint in constraints if constraint is not None]


def _node_process_limits(node: Node) -> Sequence[RuntimeProcessResourceLimit]:
    runtime = node.runtime
    policy = runtime.operational_policy if runtime is not None else None
    resource_limits = policy.resource_limits if policy is not None else None
    return resource_limits.process_limits if resource_limits is not None else ()


def _process_limit_capability_constraints(
    *,
    node_name: str,
    process_limits: Sequence[RuntimeProcessResourceLimit],
    variables: Mapping[str, Variable],
) -> list[CapabilityConstraint]:
    constraints: list[CapabilityConstraint] = []
    node_pointer = f"/nodes/{_json_pointer_segment(node_name)}"
    for index, process_limit in enumerate(process_limits):
        pointer = f"{node_pointer}/runtime/operational_policy/resource_limits/process_limits/{index}"
        constraints.extend(
            _present_constraints(
                *(
                    _finite_domain_constraint(
                        field_pointer=f"{pointer}/{leaf}",
                        value=getattr(process_limit, leaf),
                        variables=variables,
                    )
                    for leaf in ("soft", "hard")
                )
            )
        )
    return constraints


def _node_capability_constraints(
    *,
    node_name: str,
    node: Node,
    variables: Mapping[str, Variable],
) -> list[CapabilityConstraint]:
    node_pointer = f"/nodes/{_json_pointer_segment(node_name)}"
    constraints = _present_constraints(
        _finite_domain_constraint(
            field_pointer=f"{node_pointer}/os",
            value=node.os,
            variables=variables,
        ),
        _finite_domain_constraint(
            field_pointer=f"{node_pointer}/os_distribution",
            value=node.os_distribution,
            variables=variables,
        ),
        _finite_domain_constraint(
            field_pointer=f"{node_pointer}/os_version",
            value=node.os_version,
            variables=variables,
        ),
        _finite_domain_constraint(
            field_pointer=f"{node_pointer}/architecture",
            value=node.architecture,
            variables=variables,
        ),
    )
    constraints.extend(
        _process_limit_capability_constraints(
            node_name=node_name,
            process_limits=_node_process_limits(node),
            variables=variables,
        )
    )
    existing = {constraint.field_pointer for constraint in constraints}
    constraints.extend(
        constraint
        for constraint in _runtime_scalar_constraints(
            node.runtime,
            pointer=f"{node_pointer}/runtime",
            variables=variables,
        )
        if constraint.field_pointer not in existing
    )
    return constraints


def _runtime_scalar_constraints(
    value: object, *, pointer: str, variables: Mapping[str, Variable]
) -> list[CapabilityConstraint]:
    """Retain public typed scalar domains, never classification-governed raw alternatives.

    Classified records require their owning safe projection before a domain can
    be published. Until that projection is representable, compilation rejects
    the missing bound; retaining raw alternatives here would bypass that owner.
    """

    if isinstance(value, BaseModel):
        fields = type(value).model_fields
        classified = any(name.endswith(("classification", "sensitivity")) for name in fields) or getattr(
            value, "command_redacted", False
        )
        if classified:
            return []
        children = (
            (name, getattr(value, name))
            for name, info in fields.items()
            if not isinstance(info.json_schema_extra, dict)
            or info.json_schema_extra.get("x-raes-realization-dimension") is not False
        )
    elif isinstance(value, Mapping):
        children = value.items()
    elif isinstance(value, (list, tuple)):
        children = enumerate(value)
    else:
        constraint = _finite_domain_constraint(field_pointer=pointer, value=value, variables=variables)
        return [constraint] if constraint is not None else []
    return [
        constraint
        for name, child in children
        for constraint in _runtime_scalar_constraints(
            child, pointer=f"{pointer}/{_json_pointer_segment(str(name))}", variables=variables
        )
    ]


def capture_capability_constraints(
    scenario: Scenario | ExpandedScenario,
) -> tuple[CapabilityConstraint, ...]:
    """Retain the finite domains needed by pre-realization capability checks."""

    constraints: list[CapabilityConstraint] = []
    for node_name, node in scenario.nodes.items():
        constraints.extend(
            _node_capability_constraints(
                node_name=node_name,
                node=node,
                variables=scenario.variables,
            )
        )
    for node_name, infrastructure in scenario.infrastructure.items():
        constraints.extend(
            _present_constraints(
                _finite_domain_constraint(
                    field_pointer=f"/infrastructure/{_json_pointer_segment(node_name)}/count",
                    value=infrastructure.count,
                    variables=scenario.variables,
                )
            )
        )
    return tuple(constraints)
