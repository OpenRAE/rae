"""Typed, secret-free carrier for compiled identity-domain topology."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from raes_contracts.addressing import require_compiled_address
from raes_contracts.domain_profiles import DomainProfileBindingModel, DomainProfileCoordinateModel

DOMAIN_NODE_ROLES = frozenset({"controller", "member"})


def domain_topology_profile(payload: Mapping[str, object]) -> str | DomainProfileCoordinateModel:
    """Return the concrete domain profile carried by a resource payload."""

    binding = payload.get("domain_topology")
    profile = binding.get("profile") if isinstance(binding, Mapping) else None
    if isinstance(profile, (Mapping, DomainProfileBindingModel)):
        try:
            return DomainProfileBindingModel.model_validate(profile).coordinate
        except ValueError:
            return "invalid-profile"
    return profile if isinstance(profile, str) else ""


@dataclass(frozen=True)
class DomainTopologyBinding:
    """Normalized domain realization intent attached to a plan resource."""

    domain_id: str
    profile: str | DomainProfileBindingModel
    dns_name: str
    netbios_name: str
    authority_account_address: str
    role: str
    controller_addresses: tuple[str, ...]

    def __post_init__(self) -> None:
        required_fields = (
            ("domain_id",)
            if isinstance(self.profile, DomainProfileBindingModel)
            else ("domain_id", "profile", "dns_name", "netbios_name")
        )
        for field_name in required_fields:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"DomainTopologyBinding.{field_name} must be non-empty")
        require_compiled_address(
            self.authority_account_address,
            field_name="DomainTopologyBinding.authority_account_address",
        )
        if self.role not in DOMAIN_NODE_ROLES:
            raise ValueError("DomainTopologyBinding.role must be 'controller' or 'member'")
        if not self.controller_addresses:
            raise ValueError("DomainTopologyBinding.controller_addresses must not be empty")
        if len(self.controller_addresses) != len(set(self.controller_addresses)):
            raise ValueError("DomainTopologyBinding.controller_addresses must be unique")
        for address in self.controller_addresses:
            require_compiled_address(address, field_name="DomainTopologyBinding.controller_addresses")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> DomainTopologyBinding:
        """Parse untrusted plan data without coercing values or extension keys."""

        field_names = {
            "domain_id",
            "profile",
            "dns_name",
            "netbios_name",
            "authority_account_address",
            "role",
            "controller_addresses",
        }
        if set(payload) - field_names:
            raise ValueError("DomainTopologyBinding contains unknown fields")

        def required_string(field_name: str) -> str:
            value = payload.get(field_name)
            if not isinstance(value, str):
                raise ValueError("DomainTopologyBinding scalar fields must be strings")
            return value

        controller_addresses = payload.get("controller_addresses", ())
        if (
            isinstance(controller_addresses, (str, bytes, Mapping))
            or not isinstance(controller_addresses, Sequence)
            or any(not isinstance(value, str) for value in controller_addresses)
        ):
            raise ValueError("DomainTopologyBinding.controller_addresses must be a sequence")
        return cls(
            domain_id=required_string("domain_id"),
            profile=DomainProfileBindingModel.model_validate(payload["profile"])
            if isinstance(payload.get("profile"), (Mapping, DomainProfileBindingModel))
            else required_string("profile"),
            dns_name=required_string("dns_name"),
            netbios_name=required_string("netbios_name"),
            authority_account_address=required_string("authority_account_address"),
            role=required_string("role"),
            controller_addresses=tuple(controller_addresses),
        )


__all__ = [
    "DOMAIN_NODE_ROLES",
    "DomainTopologyBinding",
    "domain_topology_profile",
]
