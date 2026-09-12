"""Shared invariants for compute-substrate author constraints."""

from __future__ import annotations

from collections.abc import Iterable

from .bounded_domains import DomainDescriptor, EnumDomain, ExactDomain, GovernedReferenceDomain


def validate_planned_substrate_targets(
    identities: Iterable[tuple[str, str]],
    live_node_addresses: Iterable[str],
) -> None:
    """Bind every portable substrate constraint to one live node operation."""

    selected = tuple(identities)
    if len(selected) != len(set(selected)):
        raise ValueError("Provisioning plan realization constraints must identify unique concerns")
    if {address for address, _ in selected} - set(live_node_addresses):
        raise ValueError("Provisioning plan realization constraints must reference non-delete node operations")


def validate_compute_substrate_constraint(
    posture: object,
    domain: DomainDescriptor | None,
) -> None:
    """Require the governed domain shape admitted at every artifact phase."""

    posture_value = getattr(posture, "value", posture)
    if posture_value == "open":
        if domain is not None:
            raise ValueError("open compute-substrate constraint must not carry a domain")
        return
    if posture_value not in {"constrained", "exact"}:
        raise ValueError("compute-substrate constraint posture is invalid")
    if domain is None:
        raise ValueError(f"{posture_value} compute-substrate constraint must carry a domain")
    if not isinstance(domain, (ExactDomain, EnumDomain, GovernedReferenceDomain)):
        raise ValueError("compute-substrate requires an exact, enum, or governed-reference domain")

    values = _domain_values(domain)
    if posture_value == "exact" and len(values) != 1:
        raise ValueError("exact compute-substrate constraint requires a singleton domain")

    # Loading the catalog lazily avoids the schema-bundle import cycle through
    # raes_contracts.contracts.
    from .controlled_vocabularies import validate_controlled_vocabulary_value

    for value in values:
        if not isinstance(value, str):
            raise ValueError("compute-substrate domain members must be strings")
        validate_controlled_vocabulary_value("compute-substrates", value)


def _domain_values(domain: ExactDomain | EnumDomain | GovernedReferenceDomain) -> tuple[object, ...]:
    if isinstance(domain, ExactDomain):
        return (domain.value,)
    if isinstance(domain, EnumDomain):
        return tuple(domain.values)
    return tuple(domain.allowed_refs)


__all__ = ["validate_compute_substrate_constraint"]
