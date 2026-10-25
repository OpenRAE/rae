"""Closed structural slots and typed choices over existing SDL inventory."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, ConfigDict, Field, StrictBool, WithJsonSchema, model_validator
from raes_contracts.canonical import canonical_json_bytes

from ._base import SDLModel
from ._identifiers import PortableIdentifier, require_qualified_identifier
from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES, iter_runtime_family_references


def _qualified_reference(value: str) -> str:
    return require_qualified_identifier(value, field_name="variation reference")


QualifiedReference = Annotated[
    str,
    AfterValidator(_qualified_reference),
    WithJsonSchema({"type": "string", "minLength": 1, "maxLength": 2048}),
]


class SelectionRelation(SDLModel):
    """A finite cross-point member requirement or exclusion."""

    point: QualifiedReference
    members: list[PortableIdentifier] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_members(self) -> SelectionRelation:
        if len(self.members) != len(set(self.members)):
            raise ValueError("selection relation members must be unique")
        return self


class _SelectionMember(SDLModel):
    description: str = ""
    requires: list[SelectionRelation] = Field(default_factory=list)
    excludes: list[SelectionRelation] = Field(default_factory=list)


class VariationMember(_SelectionMember):
    """One named semantic object referenced by a structural point."""

    reference: QualifiedReference


class RuntimeInventorySlot(StrEnum):
    """Reviewed write permission; runtime registration alone grants no writes."""

    SERVICE_LISTENERS = "nodes.runtime.service_listeners"
    APPLICATIONS = "nodes.runtime.applications"
    DATABASE_SERVICES = "nodes.runtime.database_services"
    DNS_SERVICES = "nodes.runtime.dns_services"
    IDENTITY_AUTHORITIES = "nodes.runtime.identity_authorities"
    FILE_SERVICES = "nodes.runtime.file_services"
    MAIL_SERVICES = "nodes.runtime.mail_services"
    NETWORK_SENSORS = "nodes.runtime.network_sensors"
    NETWORK_DETECTION_ENGINES = "nodes.runtime.network_detection_engines"
    SECURITY_MONITORING_MANAGERS = "nodes.runtime.security_monitoring_managers"
    SSH_SERVERS = "nodes.runtime.ssh_servers"
    APP_AUTHORIZATIONS = "nodes.runtime.app_authorizations"
    SCHEDULED_JOBS = "nodes.runtime.scheduled_jobs"
    DATASTORE_SERVICES = "nodes.runtime.datastore_services"
    PLATFORM_APPLICATIONS = "nodes.runtime.platform_applications"
    FORWARDING_AGENTS = "nodes.runtime.forwarding_agents"
    ORCHESTRATION_AUTHORITIES = "nodes.runtime.orchestration_authorities"


class StructuralTarget(SDLModel):
    kind: Literal["structural"]
    owner: QualifiedReference
    slot: Literal["nodes.presence"] | RuntimeInventorySlot


class RuntimeInventoryAlternative(_SelectionMember):
    kind: Literal["runtime-inventory"]
    references: list[QualifiedReference] = Field(json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _unique_references(self) -> RuntimeInventoryAlternative:
        if len(self.references) != len(set(self.references)):
            raise ValueError("inventory references must be unique")
        return self


class NodePresenceAlternative(_SelectionMember):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"present": {"const": False}}, "required": ["present"]},
                    "then": {"properties": {"inventory": {"maxProperties": 0}}},
                }
            ]
        }
    )

    kind: Literal["node-presence"]
    present: StrictBool
    inventory: dict[
        RuntimeInventorySlot, Annotated[list[QualifiedReference], Field(json_schema_extra={"uniqueItems": True})]
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_inventory(self) -> NodePresenceAlternative:
        if not self.present and self.inventory:
            raise ValueError("absent node alternatives cannot select inventory")
        if any(len(refs) != len(set(refs)) for refs in self.inventory.values()):
            raise ValueError("inventory references must be unique")
        return self


AlternativeMember = VariationMember | NodePresenceAlternative | RuntimeInventoryAlternative

# Candidate domains are for navigation; semantic admission further restricts inventory
# to the exact owner and family, through the canonical runtime reference traversal.
STRUCTURAL_TARGET_SPECS: dict[str, tuple[str, str]] = {
    "nodes.presence": ("nodes", "nodes"),
    **{slot.value: ("nodes", "targetable") for slot in RuntimeInventorySlot},
}


def validate_alternative_members(
    target: object,
    alternatives: dict[str, AlternativeMember],
) -> None:
    if isinstance(target, StructuralTarget):
        expected = NodePresenceAlternative if target.slot == "nodes.presence" else RuntimeInventoryAlternative
    else:
        expected = VariationMember
    if any(not isinstance(member, expected) for member in alternatives.values()):
        raise ValueError("alternative member type must match its target slot")
    values = [alternative_value(member) for member in alternatives.values()]
    if len(values) != len(set(values)):
        raise ValueError("alternative references or structural values must be unique")


def alternative_value(member: AlternativeMember) -> bytes:
    if isinstance(member, VariationMember):
        value: object = member.reference
    elif isinstance(member, RuntimeInventoryAlternative):
        value = sorted(member.references)
    else:
        value = {
            "present": member.present,
            "inventory": {slot.value: sorted(refs) for slot, refs in member.inventory.items()},
        }
    return canonical_json_bytes(value)


def selected_inventory_rows(
    family: object, owner: str, slot: RuntimeInventorySlot, references: list[str]
) -> list[dict[str, Any]]:
    """Resolve existing top-level records; preserve their authored order and content."""

    collection = slot.value.removeprefix("nodes.runtime.")
    spec = next(item for item in RUNTIME_SERVICE_FAMILIES if item.collection_name == collection)
    node = family.nodes[owner]
    if node.runtime is None:
        raise ValueError("inventory target requires an existing node runtime")
    admitted = {
        ref.address
        for ref in iter_runtime_family_references(family, family_keys=[spec.key])
        if ref.node_name == owner and not ref.collection_path
    }
    if not set(references).issubset(admitted):
        raise ValueError("inventory candidate is undefined or outside the target owner collection")
    selected = set(references)
    return [
        item.model_dump(mode="python", by_alias=True)
        for item in getattr(node.runtime, collection)
        if f"nodes.{owner}.runtime.{collection}.{getattr(item, spec.id_field)}" in selected
    ]
