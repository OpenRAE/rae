"""Closed structural slots and typed choices over existing SDL inventory."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, ConfigDict, Field, StrictBool, WithJsonSchema, field_validator, model_validator
from raes_contracts.canonical import canonical_json_bytes

from ._base import SDLModel
from ._identifiers import PortableIdentifier, require_qualified_identifier
from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES, iter_runtime_family_references
from .stateful_resources import validate_mount_destination


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


class RuntimeChildInventorySlot(StrEnum):
    """Reviewed child-record membership; the owner is one top-level runtime record."""

    NETWORK_DETECTION_RULE_SOURCES = "nodes.runtime.network_detection_engines.rule_sources"


class DeclarationPresenceSlot(StrEnum):
    """Reviewed whole-declaration presence; the slot prefix names the owner section."""

    ACCOUNTS = "accounts.presence"
    CONTENT = "content.presence"
    PERSISTENT_VOLUMES = "persistent_volumes.presence"
    GENERATED_ARTIFACTS = "generated_artifacts.presence"
    RELATIONSHIPS = "relationships.presence"
    PROPOSITIONS = "propositions.presence"
    ASSERTIONS = "assertions.presence"
    EVIDENCE_REQUIREMENTS = "evidence_requirements.presence"


class ResourceConsumerSlot(StrEnum):
    """Reviewed consumer-row membership of one stateful resource."""

    PERSISTENT_VOLUMES = "persistent_volumes.consumers"
    GENERATED_ARTIFACTS = "generated_artifacts.consumers"


NODE_PRESENCE_SLOT = "nodes.presence"


class StructuralTarget(SDLModel):
    kind: Literal["structural"]
    owner: QualifiedReference
    slot: (
        Literal["nodes.presence"]
        | RuntimeInventorySlot
        | RuntimeChildInventorySlot
        | DeclarationPresenceSlot
        | ResourceConsumerSlot
    )


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


class DeclarationPresenceAlternative(_SelectionMember):
    """Whole-declaration presence; absence never removes incoming references."""

    kind: Literal["declaration-presence"]
    present: StrictBool


class ConsumerSelector(SDLModel):
    """One existing consumer row, identified by its node and mount destination."""

    node: QualifiedReference
    mount_destination: str

    _contained_mount_destination = field_validator("mount_destination")(validate_mount_destination)


class ResourceConsumersAlternative(_SelectionMember):
    """The consumer rows that the owner resource keeps, in source order."""

    kind: Literal["resource-consumers"]
    consumers: list[ConsumerSelector] = Field(json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _unique_consumers(self) -> ResourceConsumersAlternative:
        selectors = [(selector.node, selector.mount_destination) for selector in self.consumers]
        if len(selectors) != len(set(selectors)):
            raise ValueError("consumer selectors must be unique")
        return self


AlternativeMember = (
    VariationMember
    | NodePresenceAlternative
    | RuntimeInventoryAlternative
    | DeclarationPresenceAlternative
    | ResourceConsumersAlternative
)

# Owner section, then candidate domain. Candidate domains are for navigation; semantic
# admission further restricts inventory and consumer rows to the exact owner and family.
# A child-inventory owner is a runtime record, so it resolves as a targetable reference.
STRUCTURAL_TARGET_SPECS: dict[str, tuple[str, str]] = {
    NODE_PRESENCE_SLOT: ("nodes", "nodes"),
    **{slot.value: ("nodes", "targetable") for slot in RuntimeInventorySlot},
    **{slot.value: ("targetable", "targetable") for slot in RuntimeChildInventorySlot},
    **{slot.value: (slot.value.split(".", 1)[0],) * 2 for slot in DeclarationPresenceSlot},
    **{slot.value: (slot.value.split(".", 1)[0], "nodes") for slot in ResourceConsumerSlot},
}

STRUCTURAL_MEMBER_KINDS: dict[str, tuple[str, ...]] = {
    "node-presence": (NODE_PRESENCE_SLOT,),
    "runtime-inventory": tuple(slot.value for slot in (*RuntimeInventorySlot, *RuntimeChildInventorySlot)),
    "declaration-presence": tuple(slot.value for slot in DeclarationPresenceSlot),
    "resource-consumers": tuple(slot.value for slot in ResourceConsumerSlot),
}

_STRUCTURAL_MEMBER_TYPES: dict[str, type[_SelectionMember]] = {
    NODE_PRESENCE_SLOT: NodePresenceAlternative,
    **dict.fromkeys(STRUCTURAL_MEMBER_KINDS["runtime-inventory"], RuntimeInventoryAlternative),
    **dict.fromkeys(STRUCTURAL_MEMBER_KINDS["declaration-presence"], DeclarationPresenceAlternative),
    **dict.fromkeys(STRUCTURAL_MEMBER_KINDS["resource-consumers"], ResourceConsumersAlternative),
}


def validate_alternative_members(
    target: object,
    alternatives: dict[str, AlternativeMember],
) -> None:
    expected = _STRUCTURAL_MEMBER_TYPES[str(target.slot)] if isinstance(target, StructuralTarget) else VariationMember
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
    elif isinstance(member, DeclarationPresenceAlternative):
        value = {"present": member.present}
    elif isinstance(member, ResourceConsumersAlternative):
        value = sorted([selector.node, selector.mount_destination] for selector in member.consumers)
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


def runtime_child_slot_collections(slot: RuntimeChildInventorySlot) -> tuple[str, str]:
    """Return the top-level runtime collection and the child collection that *slot* names."""

    collection, child = slot.value.removeprefix("nodes.runtime.").split(".")
    return collection, child


def selected_child_rows(
    family: object, node: str, record_id: str, slot: RuntimeChildInventorySlot, references: list[str]
) -> list[dict[str, Any]]:
    """Resolve existing child records of one runtime record; preserve their authored order and content."""

    collection, child = runtime_child_slot_collections(slot)
    spec = next(item for item in RUNTIME_SERVICE_FAMILIES if item.collection_name == collection)
    child_spec = next(item for item in spec.child_refs if item.collection_name == child)
    record = next(
        item for item in getattr(family.nodes[node].runtime, collection) if getattr(item, spec.id_field) == record_id
    )
    base = f"nodes.{node}.runtime.{collection}.{record_id}.{child}"
    rows = {f"{base}.{getattr(item, child_spec.id_field)}": item for item in getattr(record, child)}
    if not set(references).issubset(rows):
        raise ValueError("inventory candidate is undefined or outside the target owner collection")
    selected = set(references)
    return [item.model_dump(mode="python", by_alias=True) for address, item in rows.items() if address in selected]
