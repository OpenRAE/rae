"""Typed EXP-731 evidence-requirement refinement and extension relations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal, TypeAlias

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.identifiers import require_qualified_identifier

from .base import ContractModel, NonEmptyString
from .experiment_capture import ExperimentCaptureRequirementModel, ExperimentCaptureSpecModel
from .experiment_manifest_references import ExperimentCaptureSpecReferenceModel
from .experiment_references import (
    ExperimentReferenceModel,
    ExperimentScenarioSnapshotReferenceModel,
)
from .schema_invariants import _add_raes_invariant

if TYPE_CHECKING:
    from raes.evidence_requirements import EvidenceRequirement
    from raes.scenario import Scenario

EvidenceRequirementRefinementDimension: TypeAlias = Literal[
    "field-selectors",
    "artifact-roles",
    "integrity-requirements",
    "loss-disclosure",
]

_AUTHORITY_KINDS_BY_SCOPE = {
    "task": frozenset({"task"}),
    "run": frozenset({"authoring-input", "run"}),
    "study": frozenset({"study"}),
}


class ExperimentEvidenceRequirementRelationModel(ContractModel):
    """One explicit scoped relationship to an immutable authored requirement.

    The relation carries lineage only.  The authored requirement and the
    materialized capture requirement remain independent obligations.
    """

    relation_id: NonEmptyString
    relation_version: NonEmptyString
    relation_kind: Literal["refine", "extend"]
    scope: Literal["task", "run", "study"]
    authority_ref: ExperimentReferenceModel
    base_scenario_ref: ExperimentScenarioSnapshotReferenceModel
    base_requirement_address: NonEmptyString
    capture_spec_ref: ExperimentCaptureSpecReferenceModel
    capture_requirement_ref: NonEmptyString
    refinement_dimensions: list[EvidenceRequirementRefinementDimension] = Field(
        default_factory=list,
        max_length=4,
        json_schema_extra={"uniqueItems": True},
    )
    rationale: NonEmptyString
    provenance_refs: list[ExperimentReferenceModel] = Field(default_factory=list)

    @field_validator("base_requirement_address")
    @classmethod
    def _validate_base_requirement_address(cls, value: str) -> str:
        prefix = "evidence_requirements."
        if not value.startswith(prefix):
            raise ValueError("base_requirement_address must identify an evidence_requirements declaration")
        require_qualified_identifier(value.removeprefix(prefix), field_name="base_requirement_address")
        return value

    @model_validator(mode="after")
    def _validate_relation_shape(self) -> ExperimentEvidenceRequirementRelationModel:
        self._validate_authority_ref()
        self._validate_base_scenario_ref()
        self._validate_capture_spec_ref()
        self._validate_relation_dimensions()
        return self

    def _validate_authority_ref(self) -> None:
        allowed_authority_kinds = _AUTHORITY_KINDS_BY_SCOPE[self.scope]
        if self.authority_ref.ref_kind not in allowed_authority_kinds:
            expected = ", ".join(sorted(allowed_authority_kinds))
            raise ValueError(f"{self.scope} evidence relations require authority_ref.ref_kind in {{{expected}}}")
        if self.authority_ref.ref_version is None:
            raise ValueError("evidence relation authority_ref must include ref_version")
        if self.authority_ref.ref_digest is not None or self.authority_ref.ref_path is not None:
            raise ValueError("evidence relation authority_ref must not carry ref_digest or ref_path")

    def _validate_base_scenario_ref(self) -> None:
        if self.base_scenario_ref.ref_version is None or self.base_scenario_ref.ref_digest is None:
            raise ValueError("base_scenario_ref must include ref_version and ref_digest")
        if self.base_scenario_ref.ref_path is not None:
            raise ValueError("base_scenario_ref must use portable identity rather than ref_path")

    def _validate_capture_spec_ref(self) -> None:
        if self.capture_spec_ref.ref_version is None:
            raise ValueError("capture_spec_ref must include ref_version")

    def _validate_relation_dimensions(self) -> None:
        if len(self.refinement_dimensions) != len(set(self.refinement_dimensions)):
            raise ValueError("refinement_dimensions must be unique")
        if self.relation_kind == "refine" and not self.refinement_dimensions:
            raise ValueError("refine evidence relations must declare refinement_dimensions")
        if self.relation_kind == "extend" and self.refinement_dimensions:
            raise ValueError("extend evidence relations must not declare refinement_dimensions")

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"relation_kind": {"const": "refine"}}, "required": ["relation_kind"]},
                    "then": {
                        "required": ["refinement_dimensions"],
                        "properties": {"refinement_dimensions": {"minItems": 1}},
                    },
                },
                {
                    "if": {"properties": {"relation_kind": {"const": "extend"}}, "required": ["relation_kind"]},
                    "then": {"properties": {"refinement_dimensions": {"maxItems": 0}}},
                },
            ]
        )
        _add_raes_invariant(
            json_schema,
            "evidence-requirement-relation-lineage-valid",
            "Evidence requirement relations must resolve an exact immutable SDL declaration and a separately "
            "identified capture requirement. Refinements preserve every declared base dimension and strengthen "
            "at least one governed dimension; extensions remain independent obligations.",
            validator="raes_contracts.contracts.validate_evidence_requirement_relations",
            inputs=[
                {"contract_id": "sdl-authoring-input-v1", "instance_path": "#/evidence_requirements"},
                {"contract_id": "experiment-capture-spec-v1", "instance_path": "#"},
            ],
        )
        return json_schema


def _reference_identity(reference: ExperimentReferenceModel) -> tuple[str, str, str | None, str | None, str | None]:
    return (
        reference.ref_kind,
        reference.ref_id,
        reference.ref_version,
        reference.ref_digest,
        reference.ref_path,
    )


def _validate_relation_owner(
    relation: ExperimentEvidenceRequirementRelationModel,
    *,
    scope: Literal["task", "run", "study"],
    authority_kind: Literal["task", "authoring-input", "run", "study"],
    expected_authority: tuple[str, str, str | None, str | None, str | None],
) -> None:
    if relation.scope != scope:
        raise ValueError(f"evidence_requirement_relations on this carrier must use scope={scope!r}")
    if _reference_identity(relation.authority_ref) != expected_authority:
        label = "run-plan" if authority_kind == "authoring-input" else authority_kind
        raise ValueError(f"evidence relation authority_ref must match the {label} carrier")


def _validate_relation_scenario_reference(
    relation: ExperimentEvidenceRequirementRelationModel,
    scenario_ref: ExperimentReferenceModel | None,
) -> None:
    if scenario_ref is None:
        return
    if scenario_ref.ref_kind == "scenario":
        if relation.base_scenario_ref.ref_id != scenario_ref.ref_id:
            raise ValueError("evidence relation base_scenario_ref must match the carrier scenario identity")
        return
    if _reference_identity(relation.base_scenario_ref) != _reference_identity(scenario_ref):
        raise ValueError("evidence relation base_scenario_ref must match the carrier scenario reference")


def validate_evidence_requirement_relation_carrier(
    relations: Sequence[ExperimentEvidenceRequirementRelationModel],
    *,
    scope: Literal["task", "run", "study"],
    authority_kind: Literal["task", "authoring-input", "run", "study"],
    authority_id: str,
    authority_version: str,
    scenario_ref: ExperimentReferenceModel | None = None,
) -> None:
    """Validate relation ownership using one existing experiment carrier."""

    relation_ids = [relation.relation_id for relation in relations]
    if len(relation_ids) != len(set(relation_ids)):
        raise ValueError("evidence_requirement_relations relation_id values must be unique")
    expected_authority = (authority_kind, authority_id, authority_version, None, None)
    for relation in relations:
        _validate_relation_owner(
            relation,
            scope=scope,
            authority_kind=authority_kind,
            expected_authority=expected_authority,
        )
        _validate_relation_scenario_reference(relation, scenario_ref)


def _resolved_authored_requirement(
    relation: ExperimentEvidenceRequirementRelationModel,
    scenario: Scenario,
) -> EvidenceRequirement:
    if _reference_identity(relation.base_scenario_ref) != _resolved_scenario_identity(scenario):
        raise ValueError("evidence relation base_scenario_ref must match the resolved authored scenario")
    requirement_name = relation.base_requirement_address.removeprefix("evidence_requirements.")
    requirement = scenario.evidence_requirements.get(requirement_name)
    if requirement is None:
        raise ValueError("base_requirement_address must resolve to exactly one authored evidence requirement")
    return requirement


def _resolved_scenario_identity(scenario: Scenario) -> tuple[str, str, str | None, str | None, str | None]:
    from raes import canonical_sdl_digest

    return (
        "scenario-snapshot",
        scenario.name,
        scenario.version,
        canonical_sdl_digest(scenario).value,
        None,
    )


def _resolved_capture_requirement(
    relation: ExperimentEvidenceRequirementRelationModel,
    capture_specs: Mapping[str, ExperimentCaptureSpecModel],
) -> ExperimentCaptureRequirementModel:
    matching_specs = [
        capture_spec
        for capture_spec in capture_specs.values()
        if capture_spec.capture_spec_id == relation.capture_spec_ref.ref_id
        and capture_spec.spec_version == relation.capture_spec_ref.ref_version
    ]
    if len(matching_specs) != 1:
        raise ValueError("capture_spec_ref must resolve to exactly one supplied capture specification")
    capture_spec = matching_specs[0]
    if not any(
        _reference_identity(reference) == _reference_identity(relation.authority_ref)
        for reference in capture_spec.scope_refs
    ):
        raise ValueError("capture specification scope_refs must include the evidence relation authority_ref")
    requirement = capture_spec.capture_requirements.get(relation.capture_requirement_ref)
    if requirement is None:
        raise ValueError("capture_requirement_ref must resolve in the exact supplied capture specification")
    return requirement


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _set_refinement(
    *,
    dimension: str,
    base: set[str],
    scoped: set[str],
) -> bool:
    if not base.issubset(scoped):
        raise ValueError(f"{dimension} refinement must preserve every authored value")
    return scoped != base


def _alternative_refinement(
    *,
    dimension: str,
    base: set[str],
    scoped: set[str],
) -> bool:
    """Compare sets whose members are alternatives accepted by one artifact.

    Adding alternatives broadens satisfaction. A scoped requirement therefore
    strengthens an authored alternative set only by narrowing it. An empty
    authored set carries no role constraint, so introducing a non-empty scoped
    set is also a strengthening.
    """

    if not base:
        return bool(scoped)
    if not scoped or not scoped.issubset(base):
        raise ValueError(f"{dimension} refinement must not add accepted values")
    return scoped != base


def _dimension_is_stricter(
    dimension: EvidenceRequirementRefinementDimension,
    authored: EvidenceRequirement,
    scoped: ExperimentCaptureRequirementModel,
) -> bool:
    if dimension == "field-selectors":
        is_stricter = _set_refinement(
            dimension=dimension,
            base=set(authored.field_selectors),
            scoped=set(scoped.field_selectors),
        )
    elif dimension == "artifact-roles":
        base = {authored.artifact_role} if authored.artifact_role else set()
        is_stricter = _alternative_refinement(
            dimension=dimension,
            base=base,
            scoped=set(scoped.required_artifact_roles),
        )
    elif dimension == "integrity-requirements":
        authored_integrity = _enum_value(authored.integrity)
        base = set() if authored_integrity == "none" else {authored_integrity}
        is_stricter = _set_refinement(dimension=dimension, base=base, scoped=set(scoped.integrity_requirements))
    else:
        base_required = _enum_value(authored.loss_disclosure) == "required"
        if base_required and not scoped.loss_disclosure_required:
            raise ValueError("loss-disclosure refinement must preserve the authored required disclosure")
        is_stricter = scoped.loss_disclosure_required and not base_required
    return is_stricter


def validate_evidence_requirement_relations(
    relations: Sequence[ExperimentEvidenceRequirementRelationModel],
    *,
    scenario: Scenario,
    capture_specs: Mapping[str, ExperimentCaptureSpecModel],
) -> tuple[ExperimentEvidenceRequirementRelationModel, ...]:
    """Resolve and validate scoped relationships without mutating their inputs.

    Every relationship resolves exact caller-supplied artifacts.  It performs
    no URI lookup, host-path discovery, subprocess invocation, or persistence.
    """

    validated = tuple(relations)
    relation_ids = [relation.relation_id for relation in validated]
    if len(relation_ids) != len(set(relation_ids)):
        raise ValueError("evidence requirement relation ids must be unique")
    for relation in validated:
        authored = _resolved_authored_requirement(relation, scenario)
        scoped = _resolved_capture_requirement(relation, capture_specs)
        if (
            authored.capture_spec_ref == relation.capture_spec_ref.ref_id
            and authored.capture_requirement_ref == relation.capture_requirement_ref
        ):
            raise ValueError("scoped evidence relation must identify an obligation separate from the authored base")
        if relation.relation_kind == "refine":
            comparisons = []
            for dimension in relation.refinement_dimensions:
                comparisons.append(_dimension_is_stricter(dimension, authored, scoped))
            if not any(comparisons):
                raise ValueError("refinement_dimensions must strengthen at least one authored dimension")
    return validated


def validate_evidence_requirement_relations_against_artifacts(
    relations: Sequence[ExperimentEvidenceRequirementRelationModel],
    *,
    scenarios: Mapping[str, Scenario],
    capture_specs: Mapping[str, ExperimentCaptureSpecModel],
) -> tuple[ExperimentEvidenceRequirementRelationModel, ...]:
    """Resolve each relation against exactly one supplied authored scenario."""

    validated = tuple(relations)
    relation_ids = [relation.relation_id for relation in validated]
    if len(relation_ids) != len(set(relation_ids)):
        raise ValueError("evidence requirement relation ids must be unique")
    for relation in validated:
        matching_scenarios = [
            scenario
            for scenario in scenarios.values()
            if _resolved_scenario_identity(scenario) == _reference_identity(relation.base_scenario_ref)
        ]
        if len(matching_scenarios) != 1:
            raise ValueError("base_scenario_ref must resolve to exactly one supplied authored scenario")
        validate_evidence_requirement_relations(
            (relation,),
            scenario=matching_scenarios[0],
            capture_specs=capture_specs,
        )
    return validated


__all__ = [
    "EvidenceRequirementRefinementDimension",
    "ExperimentEvidenceRequirementRelationModel",
    "validate_evidence_requirement_relation_carrier",
    "validate_evidence_requirement_relations",
    "validate_evidence_requirement_relations_against_artifacts",
]
