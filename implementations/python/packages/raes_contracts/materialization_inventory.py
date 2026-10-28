"""Value-free causal receipts in the existing materialized SDL contract."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel
from .addressing import CompiledAddress

RUNTIME_DESCENDANTS_CONTRACT = "backend-runtime-descendants-v1"
INVENTORY_MAX_MEMBERS = 4096
InventoryIdentity = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
InventoryDigest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
InventoryTargetScope = Annotated[str, Field(min_length=8, max_length=256, pattern=r"^target:[^\s\x00-\x1f]+$")]


class InventoryInvariant(str, Enum):
    BINDING = "binding"
    COVERAGE = "coverage"
    MEMBERSHIP = "membership"
    LINEAGE = "lineage"
    IDENTITY = "identity"
    REPLAY = "replay"
    PROVENANCE = "provenance"
    CAPABILITY = "capability"
    SHAPE = "shape"
    ARCHIVE = "archive"


class RuntimeInventoryEvidence(ContractModel):
    """Producer-scoped native receipt identity, not independent observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: InventoryIdentity
    operation_id: InventoryIdentity
    attempt_id: InventoryIdentity
    evidence_digest: InventoryDigest


class RuntimeDescendantBinding(ContractModel):
    """Stable causal identity; topology and ownership remain separate facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    address: CompiledAddress
    parent_address: CompiledAddress
    source_address: CompiledAddress
    parent_instance_index: int = Field(default=0, ge=0, strict=True)
    native_identity_digest: InventoryDigest
    creation: RuntimeInventoryEvidence
    state: Literal["active", "terminated", "autoremoved"] = "active"
    lifecycle: RuntimeInventoryEvidence | None = None

    @model_validator(mode="after")
    def _require_lifecycle_evidence(self) -> "RuntimeDescendantBinding":
        if self.address in {self.parent_address, self.source_address}:
            raise ValueError("descendant cannot be its own causal ancestor")
        if (self.state == "active") != (self.lifecycle is None):
            raise ValueError("terminal descendant state requires its separate lifecycle receipt")
        return self


class RuntimeConcernSelection(ContractModel):
    """A choice claim naming an admitted concern, never a provenance ledger write."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    address: CompiledAddress
    field_path: str = Field(min_length=1, max_length=4096)
    requirement_kind: InventoryIdentity


class RuntimeInventoryReport(ContractModel):
    """Complete bounded producer inventory, joined to the descriptive SDL bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: Literal["backend-runtime-descendants-v1"] = RUNTIME_DESCENDANTS_CONTRACT
    attempt_id: InventoryIdentity
    sequence: int = Field(ge=1, le=2147483647, strict=True)
    complete: bool = Field(strict=True)
    scope: Literal["/nodes"] = "/nodes"
    source_digest: InventoryDigest
    run_id: InventoryIdentity
    unavailable_evidence: tuple[InventoryDigest, ...] = Field(default=(), max_length=256)
    target_scope: InventoryTargetScope
    descendants: tuple[RuntimeDescendantBinding, ...] = Field(default=(), max_length=INVENTORY_MAX_MEMBERS)
    backend_selections: tuple[RuntimeConcernSelection, ...] = Field(default=(), max_length=INVENTORY_MAX_MEMBERS)

    @model_validator(mode="after")
    def _require_unique_identities(self) -> "RuntimeInventoryReport":
        for identities in (
            [entry.address for entry in self.descendants],
            [entry.native_identity_digest for entry in self.descendants],
            [(entry.address, entry.field_path, entry.requirement_kind) for entry in self.backend_selections],
        ):
            if len(identities) != len(set(identities)):
                raise ValueError("descendant inventory identities must be unique")
        if any(
            receipt.run_id != self.run_id
            for entry in self.descendants
            for receipt in (entry.creation, entry.lifecycle)
            if receipt is not None
        ):
            raise ValueError("descendant receipt belongs to another run")
        return self
