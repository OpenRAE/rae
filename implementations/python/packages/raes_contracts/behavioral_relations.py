"""Versioned behavioral-relation authority and claim-binding validation."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from .contracts import (
    BehavioralClaimBindingModel,
    BehavioralRelationId,
    BehavioralTaxonomyRevision,
    ContractModel,
    NonEmptyString,
)
from .corpus import CONCEPT_AUTHORITY, corpus_family_root
from .versions import BEHAVIORAL_RELATIONS_SCHEMA_VERSION

if TYPE_CHECKING:
    from .behavioral_relation_profiles import BehavioralRelationProfileModel


class ImmutablePublicationLocatorModel(ContractModel):
    kind: Literal["doi", "isbn", "report"]
    value: NonEmptyString


class BehavioralBibliographySourceModel(ContractModel):
    source_id: BehavioralRelationId
    title: NonEmptyString
    authors: list[NonEmptyString] = Field(min_length=1)
    publication_year: int = Field(ge=1900, le=2100)
    publication_venue: NonEmptyString
    edition_or_version: NonEmptyString
    immutable_locator: ImmutablePublicationLocatorModel


class TransitionSignatureModel(ContractModel):
    applicability: Literal["applicable", "not-applicable"]
    labels: NonEmptyString
    transition_relation: NonEmptyString
    observable_actions: NonEmptyString
    hidden_actions: NonEmptyString
    stuttering_actions: NonEmptyString
    not_applicable_rationale: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_applicability(self) -> TransitionSignatureModel:
        if self.applicability == "not-applicable" and self.not_applicable_rationale is None:
            raise ValueError("not-applicable transition signatures require a rationale")
        if self.applicability == "applicable" and self.not_applicable_rationale is not None:
            raise ValueError("applicable transition signatures must not carry a not-applicable rationale")
        return self


class ObservationProjectionModel(ContractModel):
    applicability: Literal["required", "parameterized", "identity", "not-applicable"]
    subject: NonEmptyString
    policy_ref: NonEmptyString
    policy_revision: NonEmptyString
    redaction_scope: NonEmptyString
    order_treatment: NonEmptyString
    simultaneity_treatment: NonEmptyString


class RelationQuantificationModel(ContractModel):
    states: NonEmptyString
    traces: NonEmptyString
    schedulers: NonEmptyString
    strategies: NonEmptyString
    environments: NonEmptyString
    observations: NonEmptyString


class RelationDimensionTreatmentModel(ContractModel):
    status: Literal["supported", "parameterized", "abstracted", "outside-scope"]
    treatment: NonEmptyString


class RelationDimensionsModel(ContractModel):
    nondeterminism: RelationDimensionTreatmentModel
    concurrency: RelationDimensionTreatmentModel
    probability: RelationDimensionTreatmentModel
    time: RelationDimensionTreatmentModel
    partial_order: RelationDimensionTreatmentModel


class RelationPreservationModel(ContractModel):
    property: NonEmptyString
    proof_obligation: NonEmptyString


class RelationAssuranceModel(ContractModel):
    definition_status: Literal["defined", "future"]
    implementation_status: Literal["implemented", "partial", "not-implemented", "not-applicable"]
    test_status: Literal["tested", "bounded", "not-tested", "not-applicable"]
    proof_status: Literal["proved", "model-checked", "deliberately-unproved", "future", "not-applicable"]
    checker_status: Literal["implemented", "partial", "not-implemented", "not-applicable"] = "not-applicable"
    model_check_status: Literal["model-checked", "not-model-checked", "future", "not-applicable"] = "not-applicable"
    runtime_enforcement_status: Literal["enforced", "partial", "not-enforced", "future", "not-applicable"] = (
        "not-applicable"
    )
    backend_declaration_status: Literal["declared", "not-declared", "future", "not-applicable"] = "not-applicable"
    backend_realization_status: Literal["realized", "partial", "not-realized", "future", "not-applicable"] = (
        "not-applicable"
    )
    backend_conformance_status: Literal["conformant", "bounded", "not-tested", "future", "not-applicable"] = (
        "not-applicable"
    )
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)

    def _validate_implementation_aggregate(self) -> None:
        implementation_axes = (
            self.checker_status,
            self.runtime_enforcement_status,
            self.backend_realization_status,
        )
        explicit_implementation_axes = [status for status in implementation_axes if status != "not-applicable"]
        positive_implementation_states = {
            "implemented",
            "partial",
            "enforced",
            "realized",
        }
        has_positive_implementation = any(
            status in positive_implementation_states for status in explicit_implementation_axes
        )
        if explicit_implementation_axes:
            if has_positive_implementation and self.implementation_status not in {"implemented", "partial"}:
                raise ValueError(
                    "relation assurance implementation aggregate contradicts a positive checker, runtime, "
                    "or backend-realization axis"
                )
            if not has_positive_implementation and self.implementation_status != "not-implemented":
                raise ValueError(
                    "relation assurance implementation aggregate must be not-implemented when every explicit "
                    "checker, runtime, and backend-realization axis is negative"
                )

    def _validate_legacy_model_check_aggregate(self) -> None:
        if self.proof_status == "model-checked" and self.model_check_status != "model-checked":
            raise ValueError(
                "relation assurance proof aggregate reports model checking but the model-check axis does not"
            )

    def _validate_backend_conformance(self) -> None:
        if self.backend_conformance_status in {"conformant", "bounded"} and self.backend_realization_status not in {
            "realized",
            "partial",
        }:
            raise ValueError("relation assurance backend conformance requires a realized or partially realized backend")

    def _has_positive_axis(self) -> bool:
        positive_axis_states = (
            self.implementation_status in {"implemented", "partial"},
            self.test_status in {"tested", "bounded"},
            self.proof_status in {"proved", "model-checked"},
            self.checker_status in {"implemented", "partial"},
            self.model_check_status == "model-checked",
            self.runtime_enforcement_status in {"enforced", "partial"},
            self.backend_declaration_status == "declared",
            self.backend_realization_status in {"realized", "partial"},
            self.backend_conformance_status in {"conformant", "bounded"},
        )
        return any(positive_axis_states)

    @model_validator(mode="after")
    def _validate_axis_consistency(self) -> RelationAssuranceModel:
        self._validate_implementation_aggregate()
        self._validate_legacy_model_check_aggregate()
        self._validate_backend_conformance()
        if self.definition_status == "future" and self._has_positive_axis():
            raise ValueError("relation assurance cannot report positive axes for a future definition")
        return self


class BehavioralRelationDefinitionModel(ContractModel):
    relation_id: BehavioralRelationId
    display_name: NonEmptyString
    relation_class: Literal["predicate", "set-relation", "behavioral", "epistemic", "strategic", "empirical"]
    definition: NonEmptyString
    left_carrier: NonEmptyString
    right_carrier: NonEmptyString
    initial_states: NonEmptyString
    transition_signature: TransitionSignatureModel
    observation_projection: ObservationProjectionModel
    projection_required: bool
    relation_parameter_profile_required: bool = False
    direction: Literal["unary", "left-to-right", "right-to-left", "symmetric"]
    quantification: RelationQuantificationModel
    dimensions: RelationDimensionsModel
    preservation: RelationPreservationModel
    bounded_evidence: list[NonEmptyString] = Field(min_length=1)
    explicit_non_claims: list[NonEmptyString] = Field(min_length=1)
    incompatible_claim_surfaces: list[NonEmptyString] = Field(min_length=1)
    assurance: RelationAssuranceModel
    source_refs: list[BehavioralRelationId] = Field(min_length=1)


class BehavioralClaimSurfaceModel(ContractModel):
    surface_id: BehavioralRelationId
    intended_relation_ids: list[BehavioralRelationId] = Field(min_length=1)
    evidence_boundary: NonEmptyString
    prohibited_relation_ids: list[BehavioralRelationId] = Field(min_length=1)
    explicit_non_claims: list[NonEmptyString] = Field(min_length=1)


class ExampleTransitionModel(ContractModel):
    source: NonEmptyString
    action: NonEmptyString
    target: NonEmptyString


class ExampleTransitionSystemModel(ContractModel):
    states: list[NonEmptyString] = Field(min_length=1)
    initial_state: NonEmptyString
    transitions: list[ExampleTransitionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_transitions(self) -> ExampleTransitionSystemModel:
        state_set = set(self.states)
        if len(state_set) != len(self.states):
            raise ValueError("example transition-system states must be unique")
        if self.initial_state not in state_set:
            raise ValueError("example initial state must be declared")
        for transition in self.transitions:
            if transition.source not in state_set or transition.target not in state_set:
                raise ValueError("example transitions must reference declared states")
        return self


class BehavioralWorkedExampleModel(ContractModel):
    example_id: BehavioralRelationId
    purpose: NonEmptyString
    left_system: ExampleTransitionSystemModel
    right_system: ExampleTransitionSystemModel
    tested_visible_trace: list[NonEmptyString] = Field(min_length=1)
    hidden_action: NonEmptyString
    expected_strong_bisimulation: bool
    expected_weak_matching: bool
    evidence_boundary: NonEmptyString
    explicit_non_claims: list[NonEmptyString] = Field(min_length=1)


class BehavioralRelationCatalogModel(ContractModel):
    schema_version: Literal[BEHAVIORAL_RELATIONS_SCHEMA_VERSION] = BEHAVIORAL_RELATIONS_SCHEMA_VERSION
    taxonomy_id: Literal["raes-behavioral-relations"] = "raes-behavioral-relations"
    taxonomy_revision: BehavioralTaxonomyRevision
    bibliography: list[BehavioralBibliographySourceModel] = Field(min_length=1)
    relations: dict[BehavioralRelationId, BehavioralRelationDefinitionModel] = Field(min_length=1)
    claim_surfaces: list[BehavioralClaimSurfaceModel] = Field(min_length=1)
    worked_examples: dict[BehavioralRelationId, BehavioralWorkedExampleModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_catalog_references(self) -> BehavioralRelationCatalogModel:
        source_ids = _bibliography_source_ids(self.bibliography)
        relation_ids = set(self.relations)
        _validate_relation_references(self.relations, source_ids)
        _validate_claim_surface_references(self.claim_surfaces, relation_ids)
        _validate_worked_example_references(self.worked_examples)
        return self


def _bibliography_source_ids(
    bibliography: list[BehavioralBibliographySourceModel],
) -> set[str]:
    source_ids = [source.source_id for source in bibliography]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("behavioral-relation bibliography source ids must be unique")
    return set(source_ids)


def _validate_relation_references(
    relations: dict[BehavioralRelationId, BehavioralRelationDefinitionModel],
    source_ids: set[str],
) -> None:
    for key, relation in relations.items():
        if key != relation.relation_id:
            raise ValueError("behavioral-relation map keys must match embedded relation ids")
        missing_sources = sorted(set(relation.source_refs) - source_ids)
        if missing_sources:
            raise ValueError(f"relation {key!r} references unknown bibliography sources: {missing_sources}")


def _validate_claim_surface_references(
    claim_surfaces: list[BehavioralClaimSurfaceModel],
    relation_ids: set[BehavioralRelationId],
) -> None:
    surface_ids = [surface.surface_id for surface in claim_surfaces]
    if len(surface_ids) != len(set(surface_ids)):
        raise ValueError("behavioral claim-surface ids must be unique")
    for surface in claim_surfaces:
        missing_relations = sorted(
            (set(surface.intended_relation_ids) | set(surface.prohibited_relation_ids)) - relation_ids
        )
        if missing_relations:
            raise ValueError(f"claim surface {surface.surface_id!r} references unknown relations: {missing_relations}")


def _validate_worked_example_references(
    worked_examples: dict[BehavioralRelationId, BehavioralWorkedExampleModel],
) -> None:
    for key, example in worked_examples.items():
        if key != example.example_id:
            raise ValueError("worked-example map keys must match embedded example ids")


def behavioral_relation_catalog_path() -> Path:
    return corpus_family_root(CONCEPT_AUTHORITY) / "behavioral-relations-v1.json"


_HISTORICAL_CATALOG_PATHS = {
    "rev8": corpus_family_root(CONCEPT_AUTHORITY) / "history" / "behavioral-relations-v1-rev8.json",
    "rev9": corpus_family_root(CONCEPT_AUTHORITY) / "history" / "behavioral-relations-v1-rev9.json",
    "rev10": corpus_family_root(CONCEPT_AUTHORITY) / "history" / "behavioral-relations-v1-rev10.json",
    "rev11": corpus_family_root(CONCEPT_AUTHORITY) / "history" / "behavioral-relations-v1-rev11.json",
}


@cache
def load_behavioral_relation_catalog() -> BehavioralRelationCatalogModel:
    return BehavioralRelationCatalogModel.model_validate_json(
        behavioral_relation_catalog_path().read_text(encoding="utf-8")
    )


@cache
def load_behavioral_relation_catalog_revision(
    taxonomy_revision: str,
) -> BehavioralRelationCatalogModel:
    """Resolve the exact catalog revision named by stored evidence."""

    path = _HISTORICAL_CATALOG_PATHS.get(taxonomy_revision)
    if path is not None:
        try:
            catalog = BehavioralRelationCatalogModel.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError("historical behavioral relation catalog is invalid") from None
        if catalog.taxonomy_revision != taxonomy_revision:
            raise ValueError("historical behavioral relation catalog revision does not match its registry entry")
        return catalog
    current = load_behavioral_relation_catalog()
    if current.taxonomy_revision == taxonomy_revision:
        return current
    raise ValueError("requested behavioral relation catalog revision is unsupported")


def _resolve_binding_relation(
    binding: BehavioralClaimBindingModel,
    catalog: BehavioralRelationCatalogModel,
) -> BehavioralRelationDefinitionModel:
    if binding.taxonomy_id != catalog.taxonomy_id:
        raise ValueError("behavioral claim binding taxonomy coordinates do not match the canonical catalog")
    if binding.taxonomy_revision != catalog.taxonomy_revision:
        raise ValueError("behavioral claim binding taxonomy coordinates do not match the canonical catalog")
    relation = catalog.relations.get(binding.relation_id)
    if relation is None:
        raise ValueError(f"behavioral claim binding references unknown relation {binding.relation_id!r}")
    return relation


def _validate_binding_requirements(
    binding: BehavioralClaimBindingModel,
    relation: BehavioralRelationDefinitionModel,
) -> None:
    required_bindings = (
        (
            relation.projection_required,
            binding.observation_projection_ref,
            "an observation projection binding",
        ),
        (
            relation.relation_parameter_profile_required,
            binding.relation_parameter_profile_ref,
            "a relation parameter profile binding",
        ),
        (
            relation.relation_parameter_profile_required,
            binding.assurance_axis,
            "an assurance axis",
        ),
    )
    for required, value, description in required_bindings:
        if required and value is None:
            raise ValueError(f"relation {binding.relation_id!r} requires {description}")


def _validate_binding_profile(
    binding: BehavioralClaimBindingModel,
    catalog: BehavioralRelationCatalogModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    """Join a required profile to the exact catalog and claim coordinates."""

    from .behavioral_relation_profiles import ParticipantCrossingParametersModel

    if isinstance(profile.parameters, ParticipantCrossingParametersModel):
        if binding.right_carrier_ref != profile.parameters.right.model_id:
            raise ValueError("behavioral claim binding right carrier does not match the resolved profile")

    expected = (
        (
            profile.profile_id,
            binding.relation_parameter_profile_ref,
            "profile identity",
        ),
        (
            profile.profile_revision,
            binding.relation_parameter_profile_revision,
            "profile revision",
        ),
        (profile.taxonomy_id, binding.taxonomy_id, "profile taxonomy id"),
        (
            profile.taxonomy_revision,
            binding.taxonomy_revision,
            "profile taxonomy revision",
        ),
        (profile.taxonomy_id, catalog.taxonomy_id, "profile catalog taxonomy id"),
        (
            profile.taxonomy_revision,
            catalog.taxonomy_revision,
            "profile catalog taxonomy revision",
        ),
        (profile.relation_id, binding.relation_id, "profile relation"),
        (profile.left_carrier_ref, binding.left_carrier_ref, "profile carrier"),
        (
            profile.observation_projection_ref,
            binding.observation_projection_ref,
            "profile observation projection",
        ),
        (
            profile.observation_projection_revision,
            binding.observation_projection_revision,
            "profile observation projection revision",
        ),
    )
    for profile_value, binding_value, label in expected:
        if profile_value != binding_value:
            raise ValueError(f"behavioral claim binding {label} does not match the resolved profile")


def validate_behavioral_claim_binding(
    binding: BehavioralClaimBindingModel,
    catalog: BehavioralRelationCatalogModel | None = None,
    profile: BehavioralRelationProfileModel | None = None,
) -> BehavioralClaimBindingModel:
    """Resolve a consumer binding against its exact catalog and profile revisions."""

    catalog = load_behavioral_relation_catalog_revision(binding.taxonomy_revision) if catalog is None else catalog
    relation = _resolve_binding_relation(binding, catalog)
    _validate_binding_requirements(binding, relation)
    if relation.relation_parameter_profile_required:
        if profile is None:
            from .behavioral_relation_profiles import (
                load_behavioral_relation_profile_revision,
            )

            assert binding.relation_parameter_profile_ref is not None
            assert binding.relation_parameter_profile_revision is not None
            profile = load_behavioral_relation_profile_revision(
                binding.relation_parameter_profile_ref,
                binding.relation_parameter_profile_revision,
            )
        _validate_binding_profile(binding, catalog, profile)
    elif profile is not None:
        raise ValueError("behavioral claim binding supplied a profile for a relation that does not require one")
    return binding


__all__ = [
    "BehavioralClaimSurfaceModel",
    "BehavioralBibliographySourceModel",
    "BehavioralRelationCatalogModel",
    "BehavioralRelationDefinitionModel",
    "BehavioralWorkedExampleModel",
    "ExampleTransitionModel",
    "ExampleTransitionSystemModel",
    "behavioral_relation_catalog_path",
    "load_behavioral_relation_catalog",
    "load_behavioral_relation_catalog_revision",
    "validate_behavioral_claim_binding",
]
