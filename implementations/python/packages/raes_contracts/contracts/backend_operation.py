"""Bounded portable requests for one backend invocation, never execution authority."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ..addressing import CompiledAddress
from ..operation_lifecycle import OperationAdmissionContext, OperationKind
from ..versions import (
    BACKEND_OPERATION_CAPABILITIES_SCHEMA_VERSION,
    BACKEND_OPERATION_CONTROL_SCHEMA_VERSION,
    BACKEND_OPERATION_REQUEST_SCHEMA_VERSION,
)
from .base import ContractModel, Rfc3339DateTimeString, _parse_rfc3339_datetime

OperationIdentifier = Annotated[str, Field(min_length=1, max_length=256)]
OperationDigest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
OperationCounter = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
OperationPositive = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
OperationGuarantee = Literal[
    "cancellation", "effect-observation", "cessation-evidence", "partial-effects", "external-fencing"
]


class OperationContractModel(ContractModel):
    """Immutable bounded values; decoding a value supplies no authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _unique_collections(self) -> Self:
        for name in type(self).model_fields:
            values = getattr(self, name)
            if isinstance(values, tuple) and len(values) != len(set(values)):
                raise ValueError("operation collections must contain unique values")
        return self


class OperationArtifactReferenceModel(OperationContractModel):
    """Content-bound reference resolved through the owning admitted artifact authority."""

    contract_id: Annotated[str, Field(max_length=128, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+$")]
    artifact_id: OperationIdentifier
    digest: OperationDigest


class OperationBudgetModel(OperationContractModel):
    """Remaining apparatus budget; the origin is retained across duplicate delivery."""

    origin_id: OperationIdentifier
    started_at: Annotated[Rfc3339DateTimeString, Field(max_length=64)]
    limit_ms: OperationPositive
    remaining_ms: OperationPositive

    @model_validator(mode="after")
    def _budget_bounds(self) -> Self:
        _parse_rfc3339_datetime("started_at", self.started_at)
        if self.remaining_ms > self.limit_ms:
            raise ValueError("remaining budget cannot exceed its original limit")
        return self


class OperationEffectScopeModel(OperationContractModel):
    """Target/run exclusion is the default; narrowing needs admitted independence."""

    kind: Literal["target-run", "resources"] = "target-run"
    addresses: tuple[CompiledAddress, ...] = Field(default=(), max_length=256)
    independence: OperationArtifactReferenceModel | None = None

    @model_validator(mode="after")
    def _scope_boundary(self) -> Self:
        if self.kind == "target-run" and (self.addresses or self.independence is not None):
            raise ValueError("target/run scope cannot carry a narrowed resource boundary")
        if self.kind == "resources" and (not self.addresses or self.independence is None):
            raise ValueError("resource scope requires addresses and admitted independence evidence")
        return self


class BackendOperationBindingModel(OperationContractModel):
    """Original context and invocation identity, including state-publication fences."""

    operation_id: OperationIdentifier
    invocation_id: OperationIdentifier
    attempt_id: OperationIdentifier
    worker_id: OperationIdentifier
    deployment_id: OperationIdentifier
    owner_generation: OperationCounter
    execution_generation: OperationCounter
    backend_id: OperationIdentifier
    baseline_revision: OperationIdentifier
    context: OperationAdmissionContext
    effect_scope: OperationEffectScopeModel = Field(default_factory=OperationEffectScopeModel)


class BackendOperationRequestModel(OperationContractModel):
    """Exact admitted command and requirements checked again immediately before dispatch."""

    schema_version: Literal[BACKEND_OPERATION_REQUEST_SCHEMA_VERSION] = BACKEND_OPERATION_REQUEST_SCHEMA_VERSION
    binding: BackendOperationBindingModel
    command: OperationArtifactReferenceModel
    requirement_refs: tuple[OperationArtifactReferenceModel, ...] = Field(default=(), max_length=64)
    required_guarantees: tuple[OperationGuarantee, ...] = Field(default=(), max_length=5)
    budget: OperationBudgetModel


class BackendOperationCapabilitiesModel(OperationContractModel):
    """Installed provider declaration; neither willingness nor a conformance proof."""

    schema_version: Literal[BACKEND_OPERATION_CAPABILITIES_SCHEMA_VERSION] = (
        BACKEND_OPERATION_CAPABILITIES_SCHEMA_VERSION
    )
    backend_id: OperationIdentifier
    revision: OperationDigest
    supported_operation_kinds: tuple[OperationKind, ...] = Field(min_length=1, max_length=32)
    guarantees: tuple[OperationGuarantee, ...] = Field(default=(), max_length=5)


class BackendOperationControlModel(OperationContractModel):
    """Independently authorized, idempotent control/observation of the original invocation."""

    schema_version: Literal[BACKEND_OPERATION_CONTROL_SCHEMA_VERSION] = BACKEND_OPERATION_CONTROL_SCHEMA_VERSION
    binding: BackendOperationBindingModel
    request_digest: OperationDigest
    control_id: OperationIdentifier
    actor_id: OperationIdentifier
    authorization_scope: tuple[OperationIdentifier, ...] = Field(min_length=1, max_length=64)
    action: Literal["cancel", "observe", "reconcile"]
    budget: OperationBudgetModel
