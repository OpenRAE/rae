"""Non-authoritative partial descriptions carried by existing lifecycle contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ..canonical import canonical_json_digest
from ..domain_profiles import (
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingOwnerModel,
    DomainProfileBindingUse,
)
from ..observation_demand import ObservationBasis
from ..realization_structure import (
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationOrigin,
    RealizationPresence,
    RealizationRecordConstraint,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
    semantic_address_contains,
    validate_realization_value,
)
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString, _parse_rfc3339_datetime
from .experiment_references import ExperimentReferenceModel

DescriptionPointer = Annotated[str, Field(pattern=r"^(?:/(?:[^~/]|~[01])*)*$", max_length=4096)]


class DescriptionModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def _bound_input(cls, value: object) -> object:
        if not validate_realization_value(value, python_carriers=True).conformant:
            raise ValueError("description exceeds the supported finite value bounds")
        return value


class DescriptionProvenanceModel(DescriptionModel):
    """Actual source and basis, inherited unless a fact explicitly overrides it."""

    observer_ref: ExperimentReferenceModel
    recorded_at: Rfc3339DateTimeString
    basis: ObservationBasis
    window_ref: NonEmptyString
    operation_ref: ExperimentReferenceModel | None = None
    configuration_ref: ExperimentReferenceModel | None = None
    evidence_refs: tuple[ExperimentReferenceModel, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def _validate_provenance(self) -> DescriptionProvenanceModel:
        _parse_rfc3339_datetime("recorded_at", self.recorded_at)
        if not self.observer_ref.ref_version:
            raise ValueError("description observer requires an explicit version")
        if (
            self.basis in {ObservationBasis.OBSERVED, ObservationBasis.INDEPENDENTLY_VERIFIED}
            and not self.evidence_refs
        ):
            raise ValueError("observed description basis requires evidence references")
        return self


class DescriptionFactModel(DescriptionModel):
    """One assertion; different sources at the same subject remain separate facts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"state": {"const": "known"}}, "required": ["state"]},
                    "then": {"required": ["value"], "properties": {"value": {"not": {"type": "null"}}}},
                    "else": {"properties": {"value": {"type": "null"}, "profile_bindings": {"maxItems": 0}}},
                }
            ]
        },
    )

    fact_id: NonEmptyString
    subject: DescriptionPointer
    component_ref: NonEmptyString | None = None
    state: Literal["known", "not-observed", "known-absent", "withheld", "contradictory", "not-applicable"]
    value: RecursiveRealizationStructure | None = None
    provenance: DescriptionProvenanceModel | None = None
    profile_bindings: tuple[DomainProfileBindingModel, ...] = Field(default=(), max_length=256)
    limitations: tuple[NonEmptyString, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def _validate_state(self) -> DescriptionFactModel:
        if self.state != "known" and (self.value is not None or self.profile_bindings):
            raise ValueError("nonknown facts cannot carry values or profile bindings")
        if self.state == "known" and self.value is None:
            raise ValueError("known facts require an explicit typed value")
        if self.value is not None:
            _validate_descriptive_value(self.value)
        for binding in self.profile_bindings:
            _validate_descriptive_binding(binding, self.subject)
        return self


class DescriptionCoverageModel(DescriptionModel):
    """Enumeration coverage in a named universe; never author collection closure."""

    subject: DescriptionPointer
    kind: Literal["field", "collection"]
    universe: NonEmptyString
    profile: NonEmptyString
    status: Literal["partial", "complete", "not-observed", "withheld"]
    recursive: bool = False
    fact_ids: tuple[NonEmptyString, ...] = Field(default=(), max_length=4096)
    provenance: DescriptionProvenanceModel | None = None
    limitations: tuple[NonEmptyString, ...] = Field(default=(), max_length=256)


class TypedRealizationDescriptionModel(DescriptionModel):
    """Versioned descriptive content, separate from its original author request."""

    schema_version: Literal["realization-description/v1"]
    description_id: NonEmptyString
    description_version: NonEmptyString
    semantic_profile: NonEmptyString
    authored_ref: ExperimentReferenceModel
    provenance: DescriptionProvenanceModel
    facts: tuple[DescriptionFactModel, ...] = Field(default=(), max_length=4096)
    coverage: tuple[DescriptionCoverageModel, ...] = Field(default=(), max_length=4096)
    limitations: tuple[NonEmptyString, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def _validate_description(self) -> TypedRealizationDescriptionModel:
        if not self.authored_ref.ref_version or not self.authored_ref.ref_digest:
            raise ValueError("original authored reference requires version and digest")
        facts = {fact.fact_id: fact for fact in self.facts}
        if len(facts) != len(self.facts):
            raise ValueError("description fact ids must be unique")
        for fact in self.facts:
            provenance = fact.provenance or self.provenance
            for binding in iter_description_bindings(fact.profile_bindings):
                _validate_binding_provenance(binding, provenance)
        for coverage in self.coverage:
            _validate_coverage_references(coverage, facts)
        return self


def _validate_coverage_references(
    coverage: DescriptionCoverageModel, facts: Mapping[str, DescriptionFactModel]
) -> None:
    if len(coverage.fact_ids) != len(set(coverage.fact_ids)):
        raise ValueError("coverage fact ids must be unique")
    if any(
        fact_id not in facts or not semantic_address_contains(coverage.subject, facts[fact_id].subject)
        for fact_id in coverage.fact_ids
    ):
        raise ValueError("coverage must reference facts inside its named scope")


def _validate_descriptive_value(value: RecursiveRealizationStructure) -> None:
    if value.origin not in {RealizationOrigin.BACKEND, RealizationOrigin.OBSERVATION}:
        raise ValueError("descriptive values require explicit backend or observation origin")
    if value.presence is not RealizationPresence.REQUIRED:
        raise ValueError("descriptive values cannot carry author presence constraints")
    if isinstance(value, RealizationLiteral):
        return
    children = _descriptive_children(value)
    _validate_descriptive_coverage(value)
    for child in children:
        _validate_descriptive_value(child)


def _descriptive_children(value: RecursiveRealizationStructure) -> tuple[RecursiveRealizationStructure, ...]:
    if isinstance(value, RealizationRecordConstraint):
        children = tuple(value.fields.values())
    elif isinstance(value, RealizationSequenceConstraint):
        children = value.items
    elif isinstance(value, RealizationKeyedCollectionConstraint):
        _validate_descriptive_identities(value)
        children = tuple(member.constraint for member in value.members)
    else:
        raise ValueError("descriptions cannot carry delegated, domain, reference, or conjunction authority")
    return children


def _validate_descriptive_identities(value: RealizationKeyedCollectionConstraint) -> None:
    if value.aliases:
        raise ValueError("descriptions retain actual identities, not comparison aliases")
    for member in value.members:
        if not isinstance(member.constraint, RealizationRecordConstraint):
            raise ValueError("descriptive member identity requires a record value")
        actual = tuple(member.constraint.fields.get(name) for name in value.identity_fields)
        if any(not isinstance(item, RealizationLiteral) for item in actual) or (
            canonical_json_digest([item.value for item in actual]) != canonical_json_digest(list(member.identity))
        ):
            raise ValueError("descriptive member identity must match supplied identity fields")


def _validate_descriptive_coverage(value: RecursiveRealizationStructure) -> None:
    if value.closure.posture.value != "undefined":
        raise ValueError("description coverage must not be encoded as author closure")
    if isinstance(value, (RealizationSequenceConstraint, RealizationKeyedCollectionConstraint)) and (
        value.min_items != 0 or value.max_items != 4096
    ):
        raise ValueError("description coverage must not carry author cardinality constraints")


_DESCRIPTION_HOST_PHASES = {
    "experiment-evidence-record-v1": "capture",
    "experiment-run-v1": "realization-description",
}


def _validate_descriptive_binding(
    binding: DomainProfileBindingModel, subject: str, parent: DomainProfileBindingOwnerModel | None = None
) -> None:
    if binding.owner.use not in {DomainProfileBindingUse.TYPED_REPORT, DomainProfileBindingUse.OPAQUE_EXCHANGE}:
        raise ValueError("description profiles cannot carry author constraints")
    owner = binding.owner
    if _DESCRIPTION_HOST_PHASES.get(owner.owning_contract_id) != owner.lifecycle_phase or not semantic_address_contains(
        subject, owner.canonical_address[1:]
    ):
        raise ValueError("description profile owner must match the fact scope and supported lifecycle carrier")
    if parent is not None and (owner.owning_contract_id, owner.lifecycle_phase) != (
        parent.owning_contract_id,
        parent.lifecycle_phase,
    ):
        raise ValueError("nested description profile owner must retain its lifecycle carrier")
    for child in binding.children:
        _validate_descriptive_binding(child, owner.canonical_address[1:], owner)


def iter_description_bindings(bindings: tuple[DomainProfileBindingModel, ...]) -> Iterator[DomainProfileBindingModel]:
    for binding in bindings:
        yield binding
        yield from iter_description_bindings(binding.children)


def _validate_binding_provenance(binding: DomainProfileBindingModel, provenance: DescriptionProvenanceModel) -> None:
    expected = {
        ObservationBasis.BACKEND_SELECTED: DomainProfileBindingBasis.BACKEND_SELECTED,
        ObservationBasis.OBSERVED: DomainProfileBindingBasis.OBSERVED,
        ObservationBasis.INDEPENDENTLY_VERIFIED: DomainProfileBindingBasis.OBSERVED,
    }.get(provenance.basis)
    if binding.provenance.basis is not expected:
        raise ValueError("description profile basis must match its fact provenance")
    if not set(binding.provenance.evidence_refs) <= {ref.ref_id for ref in provenance.evidence_refs}:
        raise ValueError("description profile evidence must join its fact provenance")


def validate_description_host(description: TypedRealizationDescriptionModel | None, host: str) -> None:
    if description is None:
        return
    if any(
        binding.owner.owning_contract_id != host
        for fact in description.facts
        for binding in iter_description_bindings(fact.profile_bindings)
    ):
        raise ValueError("description profile owner must match the enclosing lifecycle carrier")


__all__ = [
    "DescriptionCoverageModel",
    "DescriptionFactModel",
    "DescriptionProvenanceModel",
    "TypedRealizationDescriptionModel",
]
