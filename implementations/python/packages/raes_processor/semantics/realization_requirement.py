"""Typed compiled realization requirement shared by planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.addressing import require_compiled_address
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.compute_substrate import validate_compute_substrate_constraint
from raes_contracts.realization_structure import RealizationConstraintDocument, RealizationStructure
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

if TYPE_CHECKING:
    from raes.artifact_requirements import ArtifactRequirement
    from raes_contracts.bounded_domains import DomainDescriptor

    from .realization_process_limits import ProcessResourceLimitDemand, RealizationValueConstraint


@dataclass(frozen=True)
class CompiledRealizationRequirement:
    """One compiled realization concern with its SEM-218 authority metadata."""

    field_path: str
    address: str
    domain: str
    requirement_kind: str
    explicitness: ExplicitnessClass | None
    provenance: ExplicitnessProvenance
    governing_scope: str | None = None
    delegated: bool = False
    artifact_requirement: ArtifactRequirement | None = None
    verification_scope: RealizationVerificationScope | None = None
    required_observation_strength: ObservationStrength | None = None
    value_domain: DomainDescriptor | None = None
    constraint_provenance: str | None = None
    value_constraints: tuple[RealizationValueConstraint, ...] = ()
    process_resource_limits: tuple[ProcessResourceLimitDemand, ...] = ()
    structure: RealizationStructure | None = None
    constraint_document: RealizationConstraintDocument | None = None
    constraint_binding: str | None = None
    structure_error: bool = False
    recursive_pending: bool = False

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        if self.structure is not None and self.constraint_document is not None:
            raise ValueError("realization requirement cannot carry two independently editable structures")
        if (self.constraint_document is None) != (self.constraint_binding is None):
            raise ValueError("recursive authority requires its source binding")
        if self.recursive_pending and (self.structure is not None or self.constraint_document is not None):
            raise ValueError("pending recursive authority cannot carry an executable structure")
        self._validate_authority_metadata()
        self._validate_requirement_metadata()

    def _validate_authority_metadata(self) -> None:
        if self.delegated != (self.explicitness is None):
            raise ValueError("delegated realization requirements must carry unresolved explicitness")
        if self.verification_scope is not None and not isinstance(
            self.verification_scope,
            RealizationVerificationScope,
        ):
            raise TypeError("verification_scope must be RealizationVerificationScope")
        if self.required_observation_strength is not None and not isinstance(
            self.required_observation_strength,
            ObservationStrength,
        ):
            raise TypeError("required_observation_strength must be ObservationStrength")

    def _validate_requirement_metadata(self) -> None:
        self._validate_process_limit_metadata()
        self._validate_constraint_metadata()
        self._validate_artifact_metadata()

    def _validate_process_limit_metadata(self) -> None:
        if self.requirement_kind != "process-resource-limits" and (
            self.value_constraints or self.process_resource_limits
        ):
            raise ValueError("process-limit realization metadata requires process-resource-limits")

    def _validate_constraint_metadata(self) -> None:
        if self.requirement_kind == "compute-substrate":
            validate_compute_substrate_constraint(self.explicitness, self.value_domain)
        elif self.requirement_kind in {"os-family", "os-distribution", "os-version"}:
            if self.value_domain is not None and not isinstance(self.value_domain, EnumDomain):
                raise ValueError("operating-system constraint domain must be a finite enum")
            if self.value_domain is not None and self.explicitness is not ExplicitnessClass.CONSTRAINED:
                raise ValueError("operating-system constraint domain requires constrained explicitness")
            if self.constraint_provenance is not None and self.value_domain is None:
                raise ValueError("operating-system constraint provenance requires a finite domain")
        elif self.value_domain is not None or self.constraint_provenance is not None:
            raise ValueError("constraint domain metadata requires compute-substrate")

    def _validate_artifact_metadata(self) -> None:
        if self.artifact_requirement is None:
            return
        if self.requirement_kind != "source-artifact":
            raise ValueError("artifact_requirement requires requirement_kind='source-artifact'")
        if self.explicitness is not self.artifact_requirement.explicitness:
            raise ValueError("compiled artifact requirement explicitness must match its source contract")


__all__ = ["CompiledRealizationRequirement"]
