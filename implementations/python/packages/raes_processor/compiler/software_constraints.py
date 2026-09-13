"""Conjoin authored software version and explicitly linked package constraints."""

from raes.runtime_packages import RuntimePackage
from raes.runtime_software import RuntimeSoftwareComponent
from raes_contracts.realization_structure import (
    RealizationAllOf,
    RealizationDomainValue,
    RealizationLiteral,
    RealizationOrigin,
    RecursiveRealizationStructure,
)


def software_leaf_constraint(
    component: RuntimeSoftwareComponent,
    key: str,
    *,
    authored_exact: bool,
    linked_package: RuntimePackage | None,
) -> RecursiveRealizationStructure | None:
    """Absence stays open; selecting a reference adds only its implied coordinates."""

    constraints = []
    domain = getattr(component, f"{key}_constraint", None) if key in {"version", "package_version"} else None
    linked = linked_package is not None and key in {"package_version", "package_name", "package_manager"}
    if domain is None and not linked:
        return None
    if authored_exact:
        constraints.append(RealizationLiteral(kind="literal", value=getattr(component, key)))
    if domain is not None:
        constraints.append(RealizationDomainValue(kind="domain", domain=domain))
    if linked:
        constraints.append(
            RealizationLiteral(
                kind="literal",
                origin=RealizationOrigin.PROCESSOR,
                value=getattr(linked_package, key.removeprefix("package_")),
            )
        )
    return constraints[0] if len(constraints) == 1 else RealizationAllOf(kind="all-of", constraints=tuple(constraints))
