"""Typed requests and all-or-none results for RAES transformations."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.contracts import (
    ArtifactTransformationKind,
    ArtifactTransformationLossKind,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    ExternalConceptBindingDocumentModel,
)
from raes_contracts.contracts.base import ContractModel
from raes_contracts.errors import InvalidInputError

from ._identifiers import require_portable_identifier
from .scenario import ExpandedScenario, Scenario

SDLAuthoringArtifact = Scenario | ExpandedScenario


class _TransformationRefusal(InvalidInputError):
    """A supplied artifact or linked document cannot complete the requested transformation."""


@dataclass(frozen=True, slots=True)
class RenameSDLDeclarationRequest:
    """Exact rename request; aliases and inferred targets are not accepted."""

    target_address: str
    new_local_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_address, str) or not self.target_address or len(self.target_address) > 4096:
            raise ValueError("target_address must be a non-empty bounded canonical address")
        require_portable_identifier(self.new_local_name, field_name="new_local_name")


@dataclass(frozen=True, slots=True)
class RemoveSDLDeclarationRequest:
    """Exact declaration-removal request."""

    target_address: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_address, str) or not self.target_address or len(self.target_address) > 4096:
            raise ValueError("target_address must be a non-empty bounded canonical address")


@dataclass(frozen=True, slots=True)
class ArtifactTransformationPolicy:
    """Closed authorization for specifically named transformation losses."""

    allowed_loss_kinds: tuple[ArtifactTransformationLossKind, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_loss_kinds, tuple) or any(
            not isinstance(item, ArtifactTransformationLossKind) for item in self.allowed_loss_kinds
        ):
            raise TypeError("allowed_loss_kinds must be a tuple of ArtifactTransformationLossKind values")
        expected = tuple(sorted(set(self.allowed_loss_kinds), key=lambda item: item.value))
        if self.allowed_loss_kinds != expected:
            raise ValueError("allowed_loss_kinds must be sorted and unique")


@dataclass(frozen=True, slots=True)
class SDLTransformationResult:
    """All-or-none SDL result with explicitly transformed linked artifacts."""

    output: SDLAuthoringArtifact | None
    binding_documents: tuple[ExternalConceptBindingDocumentModel, ...]
    report: ArtifactTransformationReportModel

    @property
    def succeeded(self) -> bool:
        return self.output is not None and self.report.status == ArtifactTransformationStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class PortableContractTransformationResult:
    """Isolated admitted portable-contract result and canonical report."""

    output: ContractModel
    report: ArtifactTransformationReportModel


@dataclass(frozen=True, slots=True)
class CanonicalArtifactComparison:
    """Exact comparison under one owning canonicalization profile."""

    artifact_kind: ArtifactTransformationKind
    canonicalization_profile: str
    relation_profile: str
    left_digest: str
    right_digest: str
    equivalent: bool


__all__ = [
    "ArtifactTransformationPolicy",
    "CanonicalArtifactComparison",
    "PortableContractTransformationResult",
    "RemoveSDLDeclarationRequest",
    "RenameSDLDeclarationRequest",
    "SDLAuthoringArtifact",
    "SDLTransformationResult",
]
