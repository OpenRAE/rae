"""Closed source-neutral contracts for governed SDL candidate synthesis."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from raes_contracts.canonical import canonical_json_digest

from ..versions import (
    SDL_CANDIDATE_SYNTHESIS_INPUT_SCHEMA_VERSION,
    SDL_CANDIDATE_SYNTHESIS_RECORD_SCHEMA_VERSION,
)
from .artifact_transformations import (
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
)
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .candidate_synthesis_profiles import (
    CandidateSynthesisProfileCoordinateModel,
    CandidateSynthesisProfileDefinitionModel,
    CandidateSynthesisProfileLimitsModel,
)
from .candidate_synthesis_traces import (
    CandidateSynthesisConstructTraceModel,
    CandidateSynthesisContributionModel,
    CanonicalSDLRef,
    SynthesisContributionKind,
    validate_resolved_contributions,
)
from .external_concept_bindings import ExternalConceptSchemeCoordinateModel
from .schema_invariants import add_raes_invariant

StableId = Annotated[
    str,
    Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$", max_length=128),
]


class CandidateSynthesisSourceModel(ContractModel):
    """Pinned source, extraction, and adaptation boundary."""

    source_id: StableId
    authority: NonEmptyString
    scheme_id: NonEmptyString
    assertion_format: NonEmptyString
    revision: NonEmptyString
    content_digest: PrefixedDigestString
    assertion_set_digest: PrefixedDigestString
    extraction_query: CandidateSynthesisProfileCoordinateModel
    adapter: CandidateSynthesisProfileCoordinateModel
    information_flow_policy_refs: tuple[CandidateSynthesisProfileCoordinateModel, ...] = Field(
        min_length=1,
        max_length=32,
    )

    @field_validator("information_flow_policy_refs")
    @classmethod
    def _validate_information_flow_refs(
        cls,
        value: tuple[CandidateSynthesisProfileCoordinateModel, ...],
    ) -> tuple[CandidateSynthesisProfileCoordinateModel, ...]:
        keys = tuple((item.profile_id, item.version, item.digest) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("information-flow policy references must be sorted and unique")
        return value


class ConceptSourceAssertionModel(ContractModel):
    kind: Literal["concept"] = "concept"
    assertion_id: StableId
    concept: ExternalConceptSchemeCoordinateModel


class RelationshipSourceAssertionModel(ContractModel):
    kind: Literal["relationship"] = "relationship"
    assertion_id: StableId
    source_assertion_id: StableId
    target_assertion_id: StableId
    relationship_term: ExternalConceptSchemeCoordinateModel


class PreconditionSourceAssertionModel(ContractModel):
    kind: Literal["precondition"] = "precondition"
    assertion_id: StableId
    subject_assertion_id: StableId
    predicate_term: ExternalConceptSchemeCoordinateModel


class OrderingSourceAssertionModel(ContractModel):
    kind: Literal["ordering"] = "ordering"
    assertion_id: StableId
    left_assertion_id: StableId
    right_assertion_id: StableId
    ordering_term: ExternalConceptSchemeCoordinateModel
    direction: Literal["left-before-right", "right-before-left", "unspecified"]


class ParameterizationSourceAssertionModel(ContractModel):
    kind: Literal["parameterization"] = "parameterization"
    assertion_id: StableId
    subject_assertion_id: StableId
    parameter_term: ExternalConceptSchemeCoordinateModel
    candidate_values: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=64)

    @field_validator("candidate_values")
    @classmethod
    def _validate_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("parameter candidate_values must be sorted and unique")
        return value


class ExampleSourceAssertionModel(ContractModel):
    kind: Literal["example"] = "example"
    assertion_id: StableId
    subject_assertion_id: StableId
    example_ref: ExternalConceptSchemeCoordinateModel


SourceAssertion = Annotated[
    ConceptSourceAssertionModel
    | RelationshipSourceAssertionModel
    | PreconditionSourceAssertionModel
    | OrderingSourceAssertionModel
    | ParameterizationSourceAssertionModel
    | ExampleSourceAssertionModel,
    Field(discriminator="kind"),
]


class CandidateSynthesisTargetModel(ContractModel):
    scenario_id: StableId
    scenario_version: NonEmptyString


class CandidateSynthesisAssumptionModel(ContractModel):
    assumption_id: StableId
    assertion_ids: tuple[StableId, ...] = Field(min_length=1, max_length=64)
    statement: NonEmptyString

    @field_validator("assertion_ids")
    @classmethod
    def _validate_assertion_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("assumption assertion_ids must be sorted and unique")
        return value


class CandidateSynthesisDecisionModel(ContractModel):
    decision_id: StableId
    actor_kind: Literal["author", "governed-policy"]
    actor_ref: NonEmptyString
    assertion_ids: tuple[StableId, ...] = Field(min_length=1, max_length=64)
    target_ref: CanonicalSDLRef
    node_type: Literal["compute", "switch"]
    basis: NonEmptyString

    @field_validator("assertion_ids")
    @classmethod
    def _validate_assertion_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("decision assertion_ids must be sorted and unique")
        return value

    @field_validator("target_ref")
    @classmethod
    def _validate_node_target_limit(cls, value: str) -> str:
        if len(value.removeprefix("nodes.")) > 35:
            raise ValueError("candidate node target identifiers must be at most 35 characters")
        return value


def _assertion_coordinates(assertion: SourceAssertion) -> tuple[ExternalConceptSchemeCoordinateModel, ...]:
    if isinstance(assertion, ConceptSourceAssertionModel):
        coordinate = assertion.concept
    elif isinstance(assertion, RelationshipSourceAssertionModel):
        coordinate = assertion.relationship_term
    elif isinstance(assertion, PreconditionSourceAssertionModel):
        coordinate = assertion.predicate_term
    elif isinstance(assertion, OrderingSourceAssertionModel):
        coordinate = assertion.ordering_term
    elif isinstance(assertion, ParameterizationSourceAssertionModel):
        coordinate = assertion.parameter_term
    else:
        coordinate = assertion.example_ref
    return (coordinate,)


def _assertion_refs(assertion: SourceAssertion) -> tuple[str, ...]:
    if isinstance(assertion, RelationshipSourceAssertionModel):
        refs = (assertion.source_assertion_id, assertion.target_assertion_id)
    elif isinstance(
        assertion,
        (PreconditionSourceAssertionModel, ParameterizationSourceAssertionModel, ExampleSourceAssertionModel),
    ):
        refs = (assertion.subject_assertion_id,)
    elif isinstance(assertion, OrderingSourceAssertionModel):
        refs = (assertion.left_assertion_id, assertion.right_assertion_id)
    else:
        refs = ()
    return refs


def _validate_source_assertion_join(
    source: CandidateSynthesisSourceModel,
    assertions: tuple[SourceAssertion, ...],
) -> tuple[str, ...]:
    assertion_ids = tuple(item.assertion_id for item in assertions)
    if assertion_ids != tuple(sorted(set(assertion_ids))):
        raise ValueError("assertions must be sorted and unique by assertion_id")
    expected_digest = canonical_json_digest([item.model_dump(mode="json") for item in assertions])
    if source.assertion_set_digest != expected_digest:
        raise ValueError("assertion_set_digest does not match the complete assertion set")
    known = set(assertion_ids)
    for assertion in assertions:
        if not set(_assertion_refs(assertion)) <= known:
            raise ValueError("source assertion references must resolve inside the assertion set")
        for coordinate in _assertion_coordinates(assertion):
            if (
                coordinate.authority != source.authority
                or coordinate.scheme_id != source.scheme_id
                or coordinate.revision != source.revision
                or coordinate.source_digest != source.content_digest
            ):
                raise ValueError("source assertion coordinate is stale against the pinned source envelope")
    return assertion_ids


class CandidateSynthesisInputModel(ContractModel):
    """Bounded, source-neutral input to one trusted synthesis profile."""

    schema_version: Literal[SDL_CANDIDATE_SYNTHESIS_INPUT_SCHEMA_VERSION] = SDL_CANDIDATE_SYNTHESIS_INPUT_SCHEMA_VERSION
    input_id: StableId
    input_version: NonEmptyString
    source: CandidateSynthesisSourceModel
    assertions: tuple[SourceAssertion, ...] = Field(min_length=1, max_length=4096)
    target: CandidateSynthesisTargetModel
    transformation_profile: CandidateSynthesisProfileCoordinateModel
    policy_digest: PrefixedDigestString
    assumptions: tuple[CandidateSynthesisAssumptionModel, ...] = Field(default=(), max_length=1024)
    decisions: tuple[CandidateSynthesisDecisionModel, ...] = Field(default=(), max_length=1024)

    @model_validator(mode="after")
    def _validate_joined_input(self) -> CandidateSynthesisInputModel:
        assertion_ids = _validate_source_assertion_join(self.source, self.assertions)
        known = set(assertion_ids)
        assumption_ids = tuple(item.assumption_id for item in self.assumptions)
        if assumption_ids != tuple(sorted(set(assumption_ids))):
            raise ValueError("assumptions must be sorted and unique by assumption_id")
        decision_ids = tuple(item.decision_id for item in self.decisions)
        if decision_ids != tuple(sorted(set(decision_ids))):
            raise ValueError("decisions must be sorted and unique by decision_id")
        targets = tuple(item.target_ref for item in self.decisions)
        if targets != tuple(sorted(set(targets))):
            raise ValueError("decision target_ref values must be sorted and unique")
        for item in (*self.assumptions, *self.decisions):
            if not set(item.assertion_ids) <= known:
                raise ValueError("assumption and decision references must resolve inside the assertion set")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        add_raes_invariant(
            schema,
            "candidate-synthesis-pinned-source-join",
            "Every assertion and reference resolves inside one digest-pinned source envelope and assertion set.",
            validator="raes_contracts.contracts.CandidateSynthesisInputModel.model_validate",
            inputs=[{"contract_id": "sdl-candidate-synthesis-input-v1", "instance_path": "#"}],
        )
        add_raes_invariant(
            schema,
            "candidate-synthesis-stable-input-order",
            "Assertions, assumptions, decisions, references, values, and target identities use stable unique ordering.",
            validator="raes_contracts.contracts.CandidateSynthesisInputModel.model_validate",
            inputs=[{"contract_id": "sdl-candidate-synthesis-input-v1", "instance_path": "#"}],
        )
        return schema


class CandidateSynthesisDisposition(str, Enum):
    SUCCESS = "success"
    REQUIRES_DECISION = "requires-decision"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    NON_REPRODUCIBLE = "non-reproducible"


class CandidateSynthesisReason(str, Enum):
    AMBIGUOUS_ORDERING = "ambiguous-ordering"
    MISSING_NATIVE_SEMANTICS = "missing-native-semantics"
    UNSUPPORTED_RELATION = "unsupported-relation"
    UNRESOLVED_PARAMETERIZATION = "unresolved-parameterization"
    STALE_INPUT = "stale-input"
    TRANSFORMATION_PROFILE_UNAVAILABLE = "transformation-profile-unavailable"


class CandidateSynthesisChoiceModel(ContractModel):
    choice_id: StableId
    reason: CandidateSynthesisReason
    assertion_ids: tuple[StableId, ...] = Field(min_length=1, max_length=64)
    alternatives: tuple[NonEmptyString, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def _validate_ordering(self) -> CandidateSynthesisChoiceModel:
        if self.assertion_ids != tuple(sorted(set(self.assertion_ids))):
            raise ValueError("choice assertion_ids must be sorted and unique")
        if self.alternatives != tuple(sorted(set(self.alternatives))):
            raise ValueError("choice alternatives must be sorted and unique")
        return self


class CandidateSynthesisRecordModel(ContractModel):
    """Digest-bound provenance and refusal record for one synthesis attempt."""

    schema_version: Literal[SDL_CANDIDATE_SYNTHESIS_RECORD_SCHEMA_VERSION] = (
        SDL_CANDIDATE_SYNTHESIS_RECORD_SCHEMA_VERSION
    )
    record_id: StableId
    input_id: StableId
    input_digest: PrefixedDigestString
    disposition: CandidateSynthesisDisposition
    input: CandidateSynthesisInputModel
    profile: CandidateSynthesisProfileDefinitionModel | None = None
    unresolved_choices: tuple[CandidateSynthesisChoiceModel, ...] = Field(default=(), max_length=1024)
    construct_traces: tuple[CandidateSynthesisConstructTraceModel, ...] = Field(default=(), max_length=4096)
    candidate_exact_digest: PrefixedDigestString | None = None
    candidate_canonical_digest: PrefixedDigestString | None = None
    transformation_report: ArtifactTransformationReportModel

    @model_validator(mode="after")
    def _validate_result_shape(self) -> CandidateSynthesisRecordModel:
        self._validate_input_binding()
        if self.disposition == CandidateSynthesisDisposition.SUCCESS:
            self._validate_success_shape()
            self._validate_construct_contributions()
        else:
            self._validate_refusal_shape()
        self._validate_record_ordering()
        return self

    def _validate_input_binding(self) -> None:
        assertion_ids = {item.assertion_id for item in self.input.assertions}
        for item in self.unresolved_choices:
            if not set(item.assertion_ids) <= assertion_ids:
                raise ValueError("record provenance references must resolve inside the assertion set")
        expected_input_digest = canonical_json_digest(self.input.model_dump(mode="json"))
        if self.input_digest != expected_input_digest:
            raise ValueError("record input_digest does not match the complete admitted input")
        if self.input_id != self.input.input_id:
            raise ValueError("record input_id does not match the admitted input")
        if self.input_digest != self.transformation_report.source_digest:
            raise ValueError("record input_digest must match the transformation source digest")
        if self.profile is not None and self.input.transformation_profile != self.profile.coordinate():
            raise ValueError("record profile artifact does not match the input transformation coordinate")

    def _validate_success_shape(self) -> None:
        if self.profile is None:
            raise ValueError("successful synthesis requires the complete transformation profile artifact")
        if self.candidate_exact_digest is None or self.candidate_canonical_digest is None:
            raise ValueError("successful synthesis requires exact and canonical candidate digests")
        if self.unresolved_choices:
            raise ValueError("successful synthesis cannot retain unresolved choices")
        if not self.construct_traces:
            raise ValueError("successful synthesis requires complete construct traces")
        if self.transformation_report.status != ArtifactTransformationStatus.SUCCESS:
            raise ValueError("successful synthesis requires a successful transformation report")
        if self.candidate_canonical_digest != self.transformation_report.target_digest:
            raise ValueError("candidate canonical digest must match the transformation target digest")

    def _validate_refusal_shape(self) -> None:
        if self.candidate_exact_digest is not None or self.candidate_canonical_digest is not None:
            raise ValueError("refused synthesis cannot expose candidate digests")
        if not self.unresolved_choices:
            raise ValueError("refused synthesis requires typed unresolved choices")
        if self.construct_traces:
            raise ValueError("refused synthesis cannot expose generated construct traces")
        if self.transformation_report.status != ArtifactTransformationStatus.REFUSED:
            raise ValueError("refused synthesis requires a refused transformation report")

    def _validate_record_ordering(self) -> None:
        choice_ids = tuple(item.choice_id for item in self.unresolved_choices)
        if choice_ids != tuple(sorted(set(choice_ids))):
            raise ValueError("unresolved choices must be sorted and unique by choice_id")
        trace_refs = tuple(item.target_ref for item in self.construct_traces)
        if trace_refs != tuple(sorted(set(trace_refs))):
            raise ValueError("construct traces must be sorted and unique by target_ref")

    def _validate_construct_contributions(self) -> None:
        if self.profile is None:
            raise ValueError("construct traces require the complete transformation profile artifact")
        assertions = {item.assertion_id for item in self.input.assertions}
        assumptions = {item.assumption_id for item in self.input.assumptions}
        author_decisions = {item.decision_id for item in self.input.decisions if item.actor_kind == "author"}
        policy_decisions = {item.decision_id for item in self.input.decisions if item.actor_kind == "governed-policy"}
        owners = {
            SynthesisContributionKind.IMPORTED_ASSERTION: assertions,
            SynthesisContributionKind.TRANSFORMATION_ASSUMPTION: assumptions,
            SynthesisContributionKind.INFERRED_STRUCTURE: set(self.profile.rule_ids),
            SynthesisContributionKind.TRANSFORMATION_DEFAULT: set(self.profile.default_ids),
            SynthesisContributionKind.AUTHOR_DECISION: author_decisions,
            SynthesisContributionKind.GOVERNED_POLICY_DECISION: policy_decisions,
        }
        contributions_by_target = {
            trace.target_ref: {(item.kind, item.ref_id) for item in trace.contributions}
            for trace in self.construct_traces
        }
        decisions_by_target = {item.target_ref: item for item in self.input.decisions}
        if set(contributions_by_target) != set(decisions_by_target):
            raise ValueError("construct traces must exactly cover decision target_ref values")
        for target_ref, contributions in contributions_by_target.items():
            decision = decisions_by_target[target_ref]
            expected_decision_kind = (
                SynthesisContributionKind.AUTHOR_DECISION
                if decision.actor_kind == "author"
                else SynthesisContributionKind.GOVERNED_POLICY_DECISION
            )
            required = {
                *((SynthesisContributionKind.IMPORTED_ASSERTION, item) for item in decision.assertion_ids),
                (expected_decision_kind, decision.decision_id),
            }
            required.update(
                (SynthesisContributionKind.TRANSFORMATION_ASSUMPTION, item.assumption_id)
                for item in self.input.assumptions
                if set(item.assertion_ids) & set(decision.assertion_ids)
            )
            validate_resolved_contributions(contributions, owners, required)

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        add_raes_invariant(
            schema,
            "candidate-synthesis-all-or-none",
            (
                "Success carries one complete digest-bound candidate and traces; "
                "refusal carries no candidate and typed choices."
            ),
            validator="raes_contracts.contracts.CandidateSynthesisRecordModel.model_validate",
            inputs=[{"contract_id": "sdl-candidate-synthesis-record-v1", "instance_path": "#"}],
        )
        add_raes_invariant(
            schema,
            "candidate-synthesis-provenance-separation",
            (
                "Source assertions, assumptions, decisions, construct contributions, "
                "unresolved choices, and transformation evidence remain distinct."
            ),
            validator="raes_contracts.contracts.CandidateSynthesisRecordModel.model_validate",
            inputs=[{"contract_id": "sdl-candidate-synthesis-record-v1", "instance_path": "#"}],
        )
        return schema


__all__ = [
    "CandidateSynthesisAssumptionModel",
    "CandidateSynthesisChoiceModel",
    "CandidateSynthesisConstructTraceModel",
    "CandidateSynthesisContributionModel",
    "CandidateSynthesisDecisionModel",
    "CandidateSynthesisDisposition",
    "CandidateSynthesisInputModel",
    "CandidateSynthesisProfileCoordinateModel",
    "CandidateSynthesisProfileDefinitionModel",
    "CandidateSynthesisProfileLimitsModel",
    "CandidateSynthesisReason",
    "CandidateSynthesisRecordModel",
    "CandidateSynthesisSourceModel",
    "CandidateSynthesisTargetModel",
    "ConceptSourceAssertionModel",
    "ExampleSourceAssertionModel",
    "OrderingSourceAssertionModel",
    "ParameterizationSourceAssertionModel",
    "PreconditionSourceAssertionModel",
    "RelationshipSourceAssertionModel",
    "SourceAssertion",
    "SynthesisContributionKind",
]
