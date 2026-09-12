"""Plan-owned enclosing membership for prepared portable node additions."""

from collections.abc import Iterable, Mapping
from typing import Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel
from .realization_structure import (
    RealizationConstraintDocument,
    RealizationKeyedCollectionConstraint,
    RealizationRecordConstraint,
)

PORTABLE_NODE_COLLECTION_PROFILE = "raes/portable-node-membership/v1"


class _NodeOperation(Protocol):
    @property
    def action(self) -> str: ...

    @property
    def address(self) -> str: ...

    @property
    def resource_type(self) -> str: ...

    @property
    def payload(self) -> Mapping[str, object]: ...


def node_collection_members(
    operations: Iterable[_NodeOperation], *, namespaces: Iterable[str] = ("",)
) -> dict[str, list[dict[str, object]]]:
    """Project portable membership without embedding node recipes or secrets."""

    members = sorted(
        (
            {
                "address": operation.address,
                "resource_type": operation.resource_type,
                "name": operation.payload.get("name"),
            }
            for operation in operations
            if operation.resource_type in {"node", "network"} and operation.action != "delete"
        ),
        key=lambda item: item["address"],
    )
    grouped = {namespace: [] for namespace in namespaces}
    for member in members:
        name = member["name"]
        if not isinstance(name, str):
            raise ValueError("portable membership requires a canonical qualified name")
        namespace = name.rpartition(".")[0]
        grouped.setdefault(namespace, []).append(member)
    return grouped


class PreparedNodeCollectionAuthority(ContractModel):
    """An authenticated enclosing grant, independent of per-node child openness."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    scope_pointer: Literal["/nodes"] = "/nodes"
    source: Literal["authored-scope", "legacy-default"]
    governing_scope: str | None = Field(default=None, max_length=4096)
    constraint_document: RealizationConstraintDocument
    constraint_binding: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _validate_profile(self) -> "PreparedNodeCollectionAuthority":
        root = self.constraint_document.root
        if (
            self.constraint_document.semantic_profile != PORTABLE_NODE_COLLECTION_PROFILE
            or not isinstance(root, RealizationRecordConstraint)
            or root.closure.posture.value not in {"closed", "undefined"}
            or self.constraint_document.default_closure.posture.value != "closed"
            or self.constraint_document.scopes
            or "" not in root.fields
            or any(
                not isinstance(collection, RealizationKeyedCollectionConstraint)
                or collection.collection_kind != "portable-node"
                or collection.identity_fields != ("address",)
                for collection in root.fields.values()
            )
        ):
            raise ValueError("prepared node collection requires its canonical keyed membership profile")
        return self

    @property
    def authored_addresses(self) -> frozenset[str]:
        return frozenset(
            member.identity[0]
            for collection in self.constraint_document.root.fields.values()
            for member in collection.members
        )
