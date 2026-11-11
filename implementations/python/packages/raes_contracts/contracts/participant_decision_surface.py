"""Portable SEM-220 participant decision-surface contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, StrictInt, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .base import ContractModel, NonEmptyString
from .participant_context import ParticipantContextViewModel
from .participant_decision_surface_exposure import (
    ParticipantDecisionSurfaceExposureBindingModel,
)
from .schema_invariants import add_raes_invariant

ParticipantDecisionSurfaceVisibility = Literal[
    "observable",
    "discovered",
    "inferred",
    "disclosed",
    "deceptive",
]
ParticipantDecisionSurfaceEligibility = Literal["eligible", "ineligible", "unknown", "unsupported"]
ParticipantDecisionSurfaceSupport = Literal["supported", "unsupported", "unknown"]
type ParticipantDecisionSurfaceArgumentScalar = str | int | float | bool
type ParticipantDecisionSurfaceArgumentValue = (
    ParticipantDecisionSurfaceArgumentScalar | list[ParticipantDecisionSurfaceArgumentScalar]
)


def _require_unique(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


class ParticipantDecisionSurfaceActionEntryModel(ContractModel):
    """One presented or generable action without lifecycle implications."""

    entry_id: NonEmptyString
    action_contract_address: NonEmptyString
    presentation_basis_ref: NonEmptyString
    visibility: ParticipantDecisionSurfaceVisibility
    eligibility: ParticipantDecisionSurfaceEligibility
    eligibility_reason_refs: list[NonEmptyString] = Field(default_factory=list)
    constraint_refs: list[NonEmptyString] = Field(min_length=1)
    selection_shape_ref: NonEmptyString
    support: ParticipantDecisionSurfaceSupport
    support_refs: list[NonEmptyString] = Field(default_factory=list)
    affordance_refs: list[NonEmptyString] = Field(default_factory=list)
    realization_refs: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_entry_facts(self) -> ParticipantDecisionSurfaceActionEntryModel:
        for field_name in (
            "eligibility_reason_refs",
            "constraint_refs",
            "support_refs",
            "affordance_refs",
            "realization_refs",
        ):
            _require_unique(getattr(self, field_name), field_name)
        if self.eligibility != "eligible" and not self.eligibility_reason_refs:
            raise ValueError("eligibility_reason_refs are required unless eligibility is eligible")
        if self.eligibility == "eligible" and self.eligibility_reason_refs:
            raise ValueError("eligible action entries must not carry eligibility_reason_refs")
        if self.support == "supported" and not self.support_refs:
            raise ValueError("support_refs are required when support is supported")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"eligibility": {"enum": ["ineligible", "unknown", "unsupported"]}},
                        "required": ["eligibility"],
                    },
                    "then": {"properties": {"eligibility_reason_refs": {"minItems": 1}}},
                },
                {
                    "if": {
                        "properties": {"support": {"const": "supported"}},
                        "required": ["support"],
                    },
                    "then": {"properties": {"support_refs": {"minItems": 1}}},
                },
            ]
        )
        return json_schema


class ParticipantDecisionSurfaceOpenEndedFormModel(ContractModel):
    surface_form: Literal["open_ended_generation"]
    selection_meaning_ref: NonEmptyString
    proposal_binding_ref: NonEmptyString
    argument_shape_ref: NonEmptyString
    validation_policy_ref: NonEmptyString
    allowed_action_contract_addresses: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_allowed_actions(self) -> ParticipantDecisionSurfaceOpenEndedFormModel:
        _require_unique(self.allowed_action_contract_addresses, "allowed_action_contract_addresses")
        return self


class ParticipantDecisionSurfaceConstrainedFormModel(ContractModel):
    surface_form: Literal["constrained_form"]
    selection_meaning_ref: NonEmptyString
    action_entry_id: NonEmptyString
    argument_shape_ref: NonEmptyString
    validation_policy_ref: NonEmptyString
    constraint_refs: list[NonEmptyString] = Field(min_length=1)
    default_disclosure_refs: list[NonEmptyString] = Field(min_length=1)
    normalization_disclosure_refs: list[NonEmptyString] = Field(min_length=1)
    omission_disclosure_refs: list[NonEmptyString] = Field(min_length=1)
    loss_disclosure_refs: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_mapping_disclosures(self) -> ParticipantDecisionSurfaceConstrainedFormModel:
        for field_name in (
            "constraint_refs",
            "default_disclosure_refs",
            "normalization_disclosure_refs",
            "omission_disclosure_refs",
            "loss_disclosure_refs",
        ):
            _require_unique(getattr(self, field_name), field_name)
        return self


class ParticipantDecisionSurfaceCandidateSetFormModel(ContractModel):
    surface_form: Literal["candidate_action_set"]
    selection_meaning_ref: NonEmptyString
    candidate_entry_ids: list[NonEmptyString] = Field(min_length=1)
    open_extension_binding_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_candidate_ids(self) -> ParticipantDecisionSurfaceCandidateSetFormModel:
        _require_unique(self.candidate_entry_ids, "candidate_entry_ids")
        return self


ParticipantDecisionSurfaceFormModel = Annotated[
    ParticipantDecisionSurfaceOpenEndedFormModel
    | ParticipantDecisionSurfaceConstrainedFormModel
    | ParticipantDecisionSurfaceCandidateSetFormModel,
    Field(discriminator="surface_form"),
]


def _surface_entry_indexes(
    entries: list[ParticipantDecisionSurfaceActionEntryModel],
) -> tuple[
    dict[str, ParticipantDecisionSurfaceActionEntryModel],
    dict[str, ParticipantDecisionSurfaceActionEntryModel],
]:
    entries_by_id = {entry.entry_id: entry for entry in entries}
    entries_by_address = {entry.action_contract_address: entry for entry in entries}
    _require_unique([entry.entry_id for entry in entries], "action_entries.entry_id")
    _require_unique(
        [entry.action_contract_address for entry in entries],
        "action_entries.action_contract_address",
    )
    return entries_by_id, entries_by_address


def _validate_candidate_form_relations(
    form: ParticipantDecisionSurfaceCandidateSetFormModel,
    entries_by_id: dict[str, ParticipantDecisionSurfaceActionEntryModel],
) -> None:
    unknown = sorted(set(form.candidate_entry_ids) - entries_by_id.keys())
    if unknown:
        raise ValueError("candidate_entry_ids must reference action_entries: " + ", ".join(unknown))


def _validate_constrained_form_relations(
    form: ParticipantDecisionSurfaceConstrainedFormModel,
    entries_by_id: dict[str, ParticipantDecisionSurfaceActionEntryModel],
) -> None:
    entry = entries_by_id.get(form.action_entry_id)
    if entry is None:
        raise ValueError("constrained form action_entry_id must reference action_entries")
    if entry.selection_shape_ref != form.argument_shape_ref:
        raise ValueError("constrained form argument_shape_ref must match the selected action entry")


def _validate_open_ended_form_relations(
    form: ParticipantDecisionSurfaceOpenEndedFormModel,
    entries_by_address: dict[str, ParticipantDecisionSurfaceActionEntryModel],
) -> None:
    unknown = sorted(set(form.allowed_action_contract_addresses) - entries_by_address.keys())
    if unknown:
        raise ValueError(
            "open-ended allowed_action_contract_addresses must reference action_entries: " + ", ".join(unknown)
        )
    mismatched = sorted(
        address
        for address in form.allowed_action_contract_addresses
        if entries_by_address[address].selection_shape_ref != form.argument_shape_ref
    )
    if mismatched:
        raise ValueError("open-ended argument_shape_ref must match allowed action entries: " + ", ".join(mismatched))


def _validate_surface_form_relations(
    form: ParticipantDecisionSurfaceFormModel,
    entries_by_id: dict[str, ParticipantDecisionSurfaceActionEntryModel],
    entries_by_address: dict[str, ParticipantDecisionSurfaceActionEntryModel],
) -> None:
    if isinstance(form, ParticipantDecisionSurfaceCandidateSetFormModel):
        _validate_candidate_form_relations(form, entries_by_id)
    elif isinstance(form, ParticipantDecisionSurfaceConstrainedFormModel):
        _validate_constrained_form_relations(form, entries_by_id)
    else:
        _validate_open_ended_form_relations(form, entries_by_address)


def _validate_surface_affordances(
    affordance_refs: list[str],
    entries: list[ParticipantDecisionSurfaceActionEntryModel],
) -> None:
    entry_affordances = {ref for entry in entries for ref in entry.affordance_refs}
    unknown = sorted(set(affordance_refs) - entry_affordances)
    if unknown:
        raise ValueError("affordance_refs must be carried by action_entries: " + ", ".join(unknown))


def _surface_exposed_refs(surface: ParticipantDecisionSurfaceModel) -> set[str]:
    return {
        *surface.visible_context_refs,
        *(entry.action_contract_address for entry in surface.action_entries),
        *surface.affordance_refs,
    }


def _surface_exposure_binding_index(
    surface: ParticipantDecisionSurfaceModel,
) -> dict[str, ParticipantDecisionSurfaceExposureBindingModel]:
    bindings = {binding.item_ref: binding for binding in surface.exposure_bindings}
    _require_unique([binding.item_ref for binding in surface.exposure_bindings], "exposure_bindings.item_ref")
    expected = _surface_exposed_refs(surface)
    if bindings.keys() != expected:
        missing = sorted(expected - bindings.keys())
        extra = sorted(bindings.keys() - expected)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ValueError("exposure_bindings must exactly cover serialized surface refs: " + "; ".join(details))
    return bindings


def _validate_binding_surface_coordinates(
    binding: ParticipantDecisionSurfaceExposureBindingModel,
    surface: ParticipantDecisionSurfaceModel,
) -> None:
    comparisons = (
        ("participant_address", binding.participant_address, surface.participant_address),
        ("episode_id", binding.episode_id, surface.episode_id),
        ("audience_scope_ref", binding.audience_scope_ref, surface.audience_scope_ref),
        ("observation_point", binding.observation_point, surface.observation_point),
        ("observation_order", binding.observation_order, surface.observation_order),
        ("projection_policy_ref", binding.projection_policy_ref, surface.projection_policy_ref),
        ("projection_policy_revision", binding.projection_policy_revision, surface.projection_policy_revision),
        ("exposure_policy_ref", binding.exposure_policy_ref, surface.exposure_policy_ref),
    )
    mismatched = [name for name, binding_value, surface_value in comparisons if binding_value != surface_value]
    if mismatched:
        raise ValueError(
            f"exposure binding {binding.item_ref!r} disagrees with the surface on: " + ", ".join(mismatched)
        )


def _validate_binding_surface_evidence(
    binding: ParticipantDecisionSurfaceExposureBindingModel,
    surface: ParticipantDecisionSurfaceModel,
) -> None:
    carried_refs = (
        ("evidence_refs", binding.evidence_refs, surface.evidence_refs),
        ("provenance_refs", binding.provenance_refs, surface.provenance_refs),
        ("result markings", binding.result_marking_definition_refs, surface.marking_definition_refs),
    )
    for label, binding_refs, surface_refs in carried_refs:
        if not set(binding_refs).issubset(surface_refs):
            raise ValueError(f"exposure binding {binding.item_ref!r} {label} must be carried by the surface")


def _validate_binding_realization_evidence(
    binding: ParticipantDecisionSurfaceExposureBindingModel,
    surface: ParticipantDecisionSurfaceModel,
) -> None:
    if binding.realization is None:
        return
    carried_refs = (
        ("evidence", binding.realization.evidence_refs, surface.evidence_refs),
        ("provenance", binding.realization.provenance_refs, surface.provenance_refs),
    )
    for label, realization_refs, surface_refs in carried_refs:
        if not set(realization_refs).issubset(surface_refs):
            raise ValueError(
                f"exposure binding {binding.item_ref!r} realization {label} must be carried by the surface"
            )


def _validate_surface_exposure_bindings(surface: ParticipantDecisionSurfaceModel) -> None:
    _surface_exposure_binding_index(surface)
    for binding in surface.exposure_bindings:
        _validate_binding_surface_coordinates(binding, surface)
        _validate_binding_surface_evidence(binding, surface)
        _validate_binding_realization_evidence(binding, surface)


class ParticipantDecisionSurfaceModel(ContractModel):
    """One participant-local decision projection at one episode order point."""

    surface_id: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    observation_point: NonEmptyString
    observation_order: StrictInt = Field(ge=0)
    behavior_specification_address: NonEmptyString
    observation_boundary_address: NonEmptyString
    context_view_ref: NonEmptyString
    implementation_selection_ref: NonEmptyString
    decision_control_mode: NonEmptyString
    audience_scope_ref: NonEmptyString
    projection_policy_ref: NonEmptyString
    projection_policy_revision: NonEmptyString
    exposure_policy_ref: NonEmptyString
    visibility_projection_ref: NonEmptyString
    visible_context_refs: list[NonEmptyString] = Field(min_length=1)
    action_entries: list[ParticipantDecisionSurfaceActionEntryModel] = Field(min_length=1)
    affordance_refs: list[NonEmptyString] = Field(default_factory=list)
    exposure_bindings: list[ParticipantDecisionSurfaceExposureBindingModel] = Field(min_length=1)
    form: ParticipantDecisionSurfaceFormModel
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    marking_definition_refs: list[NonEmptyString] = Field(default_factory=list)
    redaction_policy_ref: NonEmptyString | None = None
    semantic_limitations: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_surface_relations(self) -> ParticipantDecisionSurfaceModel:
        for field_name in (
            "visible_context_refs",
            "affordance_refs",
            "evidence_refs",
            "provenance_refs",
            "marking_definition_refs",
            "semantic_limitations",
        ):
            _require_unique(getattr(self, field_name), field_name)
        entries_by_id, entries_by_address = _surface_entry_indexes(self.action_entries)
        _validate_surface_form_relations(self.form, entries_by_id, entries_by_address)
        _validate_surface_affordances(self.affordance_refs, self.action_entries)
        _validate_surface_exposure_bindings(self)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        add_raes_invariant(
            json_schema,
            "decision-surface-entry-reference-agreement",
            "Candidate, constrained-form, and open-ended action references must resolve to action entries and "
            "their governed selection shapes.",
            validator="raes_contracts.contracts.ParticipantDecisionSurfaceModel._validate_surface_relations",
            inputs=[{"contract_id": "participant-decision-surface-v1", "instance_path": "#"}],
        )
        add_raes_invariant(
            json_schema,
            "decision-surface-presentation-not-lifecycle-evidence",
            "Surface membership or presentation carries no selection, admission, execution, result, or outcome fact; "
            "those facts remain in their existing lifecycle contracts.",
            validator="raes_contracts.contracts.ParticipantDecisionSurfaceModel",
            inputs=[{"contract_id": "participant-decision-surface-v1", "instance_path": "#"}],
        )
        add_raes_invariant(
            json_schema,
            "decision-surface-sem226-item-exposure-agreement",
            "Every serialized context, action, and affordance reference must have one participant-, audience-, "
            "order-, immutable-policy-, authorization-, marking-, evidence-, and provenance-bound exposure decision; "
            "realized delivery is an optional item- and delivery-authorization-bound occurrence.",
            validator="raes_contracts.contracts.ParticipantDecisionSurfaceModel._validate_surface_relations",
            inputs=[{"contract_id": "participant-decision-surface-v1", "instance_path": "#/exposure_bindings"}],
        )
        return json_schema


class ParticipantDecisionSurfaceSelectionModel(ContractModel):
    """A referenced proposal selected from one surface, before admission."""

    surface_id: NonEmptyString
    observation_order: StrictInt = Field(ge=0)
    action_contract_address: NonEmptyString
    argument_shape_ref: NonEmptyString
    proposal_ref: NonEmptyString
    arguments: dict[
        NonEmptyString,
        str | int | float | bool | list[str | int | float | bool],
    ] = Field(default_factory=dict)


def validate_participant_decision_surface_context(
    surface: ParticipantDecisionSurfaceModel,
    context: ParticipantContextViewModel,
) -> None:
    """Require the typed payload to agree with its SEM-214/216 envelope."""

    comparisons: tuple[tuple[str, object, object], ...] = (
        ("context_view_ref", surface.context_view_ref, context.view_id),
        ("participant_address", surface.participant_address, context.participant_address),
        ("episode_id", surface.episode_id, context.episode_id),
        ("observation_point", surface.observation_point, context.observation_point),
        ("surface_id/payload_ref", surface.surface_id, context.payload_ref),
        ("projection_policy_ref", surface.projection_policy_ref, context.derivation_basis_ref),
        ("transformation_rule_ref", surface.projection_policy_ref, context.transformation.transformation_rule_ref),
        ("visibility_projection_ref", surface.visibility_projection_ref, context.visibility_projection_ref),
        ("evidence_refs", surface.evidence_refs, context.evidence_refs),
        ("provenance_refs", surface.provenance_refs, context.provenance_refs),
        ("marking_definition_refs", surface.marking_definition_refs, context.marking_definition_refs),
        ("redaction_policy_ref", surface.redaction_policy_ref, context.redaction_policy_ref),
        ("semantic_limitations", surface.semantic_limitations, context.semantic_limitations),
    )
    mismatched = [name for name, surface_value, context_value in comparisons if surface_value != context_value]
    if mismatched:
        raise ValueError("decision surface and context view disagree on: " + ", ".join(mismatched))
