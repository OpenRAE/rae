"""Typed scenario treatment criteria shared by experiment, plan, and archive."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .._canonical import canonical_json_digest
from .base import ContractModel, NonEmptyString, Sha256DigestString
from .experiment_bindings import (
    BindingOwnerModel,
    ExperimentBindingDescriptorModel,
    LiteralBindingValueModel,
    ScenarioBindingTargetModel,
)
from .experiment_selection import ExperimentSelectionOutcomeModel
from .schema_invariants import _add_raes_invariant

if TYPE_CHECKING:
    from .admitted_trial_plan import AdmittedTrialEntryModel, AdmittedTrialPlanModel
    from .admitted_trial_plan_components import ExperimentScenarioFamilyReferenceModel


class ExperimentFactorLevelSelectionModel(ContractModel):
    """One owner-bound typed outcome on an exact composed scenario family."""

    target: ScenarioBindingTargetModel
    scenario_family_digest: Sha256DigestString
    owner: BindingOwnerModel
    outcome: ExperimentSelectionOutcomeModel

    @model_validator(mode="after")
    def _validate_literal(self) -> ExperimentFactorLevelSelectionModel:
        if (
            isinstance(self.outcome, LiteralBindingValueModel)
            and isinstance(self.outcome.value, float)
            and not math.isfinite(self.outcome.value)
        ):
            raise ValueError("selection treatment literal must be finite")
        return self

    def descriptor(
        self, factor_id: str, level_id: str, condition_id: str
    ) -> ExperimentScenarioSelectionDescriptorModel:
        selection_id = (
            "selection-"
            + canonical_json_digest([condition_id, factor_id, self.target.canonical_key()]).split(":", 1)[1]
        )
        return ExperimentScenarioSelectionDescriptorModel(
            selection_id=selection_id,
            source_factor_id=factor_id,
            source_factor_level_id=level_id,
            source_condition_id=condition_id,
            **self.model_dump(mode="python"),
        )


class ExperimentScenarioSelectionDescriptorModel(ExperimentFactorLevelSelectionModel):
    """An exact typed selection with its complete treatment source joins."""

    selection_id: NonEmptyString
    source_factor_id: NonEmptyString
    source_factor_level_id: NonEmptyString
    source_condition_id: NonEmptyString

    @model_validator(mode="after")
    def _validate_identity(self) -> ExperimentScenarioSelectionDescriptorModel:
        expected = (
            "selection-"
            + canonical_json_digest(
                [self.source_condition_id, self.source_factor_id, self.target.canonical_key()]
            ).split(":", 1)[1]
        )
        if self.selection_id != expected:
            raise ValueError("selection identity must match its source and canonical target")
        return self

    def realization_payload(self) -> dict[str, object]:
        """Typed intent without source labels, for condition overlap comparison."""
        return self.model_dump(
            mode="json", exclude={"selection_id", "source_factor_id", "source_factor_level_id", "source_condition_id"}
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            schema,
            "experiment-selection-treatment-identity-valid",
            "Typed selection identity binds the exact source condition, factor and canonical scenario target. "
            "Parent condition, plan and archive validation also checks source levels, family pins and owner joins.",
            validator=(
                "raes_contracts.contracts.experiment_treatments."
                "ExperimentScenarioSelectionDescriptorModel._validate_identity"
            ),
            inputs=[
                {
                    "contract_id": "experiment-authoring-input-v1",
                    "instance_path": "#/run_plan/allocation/condition_assignments",
                },
                {"contract_id": "experiment-study-v1", "instance_path": "#/run_allocation/condition_assignments"},
                {"contract_id": "admitted-trial-plan-v1", "instance_path": "#/entries"},
                {"contract_id": "experiment-run-v1", "instance_path": "#/realized_selections"},
            ],
        )
        return schema


def validate_selection_descriptor_set(
    selections: list[ExperimentScenarioSelectionDescriptorModel],
    bindings: Sequence[ExperimentBindingDescriptorModel] = (),
) -> None:
    """Reject repeated selection identities and competing claims on a point."""
    ids = [selection.selection_id for selection in selections]
    if len(ids) != len(set(ids)):
        raise ValueError("selection identities must be unique")
    targets = [selection.target for selection in selections]
    targets.extend(binding.target for binding in bindings if isinstance(binding.target, ScenarioBindingTargetModel))
    points = [(target.scenario_family_id, target.variation_point_id) for target in targets]
    if len(points) != len(set(points)):
        raise ValueError("factorial effects must select each scenario point at most once")


def _validate_entry_treatments(
    entry: AdmittedTrialEntryModel,
    selections: list[ExperimentScenarioSelectionDescriptorModel],
    family: ExperimentScenarioFamilyReferenceModel,
) -> None:
    validate_selection_descriptor_set(selections, [binding.descriptor for binding in entry.bindings])
    levels = {}
    for descriptor in [*selections, *(binding.descriptor for binding in entry.bindings)]:
        previous = levels.setdefault(descriptor.source_factor_id, descriptor.source_factor_level_id)
        if previous != descriptor.source_factor_level_id:
            raise ValueError("entry treatment source factor levels must agree")
    for selection in selections:
        if selection.source_condition_id != entry.coordinate.condition_id:
            raise ValueError("entry treatment condition must match the coordinate")
        if (
            selection.target.scenario_family_id != family.ref_id
            or selection.scenario_family_digest != family.ref_digest
        ):
            raise ValueError("entry treatment family must match the pinned family")


def validate_plan_treatments(plan: AdmittedTrialPlanModel) -> None:
    """Check treatment profile, coordinate, and exact pinned family agreement."""
    for entry in plan.entries.values():
        selections = [record.treatment for record in entry.selections if record.treatment is not None]
        if not selections:
            continue
        if plan.profiles.treatment_profile != "factorial-treatments-v1":
            raise ValueError("typed treatment records require the treatment profile")
        _validate_entry_treatments(entry, selections, plan.input_refs.scenario_family_ref)
