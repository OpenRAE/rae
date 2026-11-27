"""Typed trusted inject resolution, separate from runtime claims and dispatch authority."""

from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from io import BytesIO
from typing import Literal, Protocol, Self

from pydantic import ConfigDict, Field, model_validator
from raes_contracts.associated_artifacts import (
    AssociatedArtifactValidationLimits,
    validate_associated_artifact_payloads,
)
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    InjectOccurrenceModel,
    InjectOccurrenceOutcomeModel,
    InjectTriggerRequestModel,
)
from raes_contracts.contracts.base import ContractModel
from raes_contracts.planning import OrchestrationPlan
from raes_contracts.runtime_state import OperationAdmissionContext, RuntimeSnapshot


@dataclass(frozen=True)
class InjectAdmission:
    plan: OrchestrationPlan
    occurrence: InjectOccurrenceModel


class InjectArtifactContent(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, ser_json_bytes="base64", val_json_bytes="base64")
    artifact_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    content: bytes = Field(max_length=65536)


class InjectExecutionEvidence(ContractModel):
    """Internal durable record codec for approved non-secret artifact bytes; no dispatch authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["raes-inject-evidence/v1"] = "raes-inject-evidence/v1"
    manifest: AssociatedArtifactManifestModel
    contents: tuple[InjectArtifactContent, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _content_integrity(self) -> Self:
        readers = {item.artifact_id: BytesIO(item.content) for item in self.contents}
        if len(readers) != len(self.contents) or any(
            item.sensitivity not in {"public", "internal"} for item in self.manifest.artifacts.values()
        ):
            raise ValueError("inject evidence requires unique approved non-secret artifact contents")
        diagnostics = validate_associated_artifact_payloads(
            self.manifest,
            artifact_readers=readers,
            limits=AssociatedArtifactValidationLimits(
                max_artifacts=32, max_artifact_bytes=65536, max_total_bytes=2 * 1024 * 1024
            ),
        )
        if diagnostics:
            raise ValueError("inject artifact evidence does not match its bounded content commitment")
        return self


@dataclass(frozen=True)
class ResolvedInjectOutcome:
    outcome: InjectOccurrenceOutcomeModel
    evidence: InjectExecutionEvidence


class InjectExecutionResolver(Protocol):
    """Host-installed artifact, order, truth/time and evidence authority.

    Admission returns immutable pins under the configured realization contract.
    Revalidation checks current authority, preconditions, target revisions and
    time without renewing a budget or choosing another order. Outcome resolution
    independently authenticates bounded readback and produced artifact content;
    it cannot treat provider booleans or reference syntax as evidence. None of
    these methods owns operation claims, dispatch grants or terminal commits.
    """

    def admit(
        self,
        request: InjectTriggerRequestModel,
        context: OperationAdmissionContext,
        operation_id: str,
        revision: int,
        snapshot: RuntimeSnapshot,
    ) -> InjectAdmission: ...
    def revalidate(self, occurrence: InjectOccurrenceModel, snapshot: RuntimeSnapshot) -> None: ...
    def resolve_outcome(
        self,
        occurrence: InjectOccurrenceModel,
        request: BackendOperationRequestModel,
        response: BackendOperationResponseModel,
    ) -> ResolvedInjectOutcome: ...


def require_inject_resolver(resolver: InjectExecutionResolver | None) -> None:
    if resolver is None:
        return
    for name, count in (("admit", 5), ("revalidate", 2), ("resolve_outcome", 3)):
        try:
            signature(getattr(resolver, name)).bind(*(object() for _ in range(count)))
        except AttributeError, TypeError, ValueError:
            raise TypeError("inject execution requires its installed typed resolution methods") from None
