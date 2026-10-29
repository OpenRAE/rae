"""Pure SDL-owned construction and admission of one completely selected family."""

from __future__ import annotations

from collections.abc import Mapping

import rfc8785
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.contracts import (
    BindingOwnerModel,
    ExperimentSelectionMemberOutcomeModel,
    ExperimentSelectionOrderOutcomeModel,
    ExperimentSelectionReferenceOutcomeModel,
    ExperimentSelectionSubsetOutcomeModel,
    LiteralBindingValueModel,
)
from raes_contracts.contracts.experiment_treatments import ExperimentScenarioSelectionDescriptorModel
from raes_contracts.experiment_bindings import ExperimentBindingTargetError, ScenarioBindingResolution

from ._declarations import build_declaration_index
from ._errors import SDLInstantiationError, SDLSelectionError
from ._selection_provenance import reconcile_selection_provenance
from .experiment_selection import validate_selection_outcome
from .instantiate import instantiate_scenario
from .phase_contracts import TrialInstantiationProvenance
from .scenario import ExpandedScenario, InstantiatedScenario
from .selected_structure import apply_structural_writes, structural_target_owner, structural_writes
from .variation import (
    COLLECTION_TARGET_SPECS,
    REFERENCE_TARGET_SPECS,
    TIMING_TARGET_SPECS,
    AlternativeVariationPoint,
    CollectionTarget,
    LogicalTimingTarget,
    LogicalTimingVariationPoint,
    OrderVariationPoint,
    ParameterVariationPoint,
    ReferenceTarget,
    SelectionRelation,
    SubsetVariationPoint,
    VariableTarget,
    VariationPoint,
    structural_members,
)
from .variation_structure import StructuralTarget

_SDL_BINDING_OWNER = BindingOwnerModel(
    contract_id="sdl-authoring-input-v1",
    contract_version="1",
    validator_id="raes-selected-scenario",
    validator_version="1",
)


def _require_family(family: ExpandedScenario) -> None:
    if not isinstance(family, ExpandedScenario) or not family.semantic_validated:
        raise ValueError("selected-scenario construction requires an admitted ExpandedScenario")


def _canonical_owner_address(family: ExpandedScenario, reference: str, section: str) -> str:
    matches = sorted(
        address for address in build_declaration_index(family).resolve(reference) if address.startswith(f"{section}.")
    )
    if len(matches) != 1:
        raise ValueError("variation target owner must resolve exactly once")
    return matches[0]


def _canonical_target_id(family: ExpandedScenario, point: VariationPoint) -> str:
    target = point.target
    if isinstance(target, VariableTarget):
        target_id = f"variables.{target.variable}"
    elif isinstance(target, StructuralTarget):
        section, owner = structural_target_owner(family, target)
        target_id = f"{section}.{owner}.{str(target.slot).split('.', 1)[1]}"
    elif isinstance(target, ReferenceTarget):
        owner_section, _ = REFERENCE_TARGET_SPECS[target.slot]
        owner = _canonical_owner_address(family, target.owner, owner_section)
        target_id = f"{owner}.{target.slot.value.split('.', 1)[1]}"
    elif isinstance(target, CollectionTarget):
        owner_section, _ = COLLECTION_TARGET_SPECS[target.slot]
        owner = _canonical_owner_address(family, target.owner, owner_section)
        target_id = f"{owner}.{target.slot.value.split('.', 1)[1]}"
    elif isinstance(target, LogicalTimingTarget):
        owner_section, _, _ = TIMING_TARGET_SPECS[target.slot]
        owner = _canonical_owner_address(family, target.owner, owner_section)
        target_id = f"{owner}.{target.slot.value.split('.', 1)[1]}"
    else:
        raise ValueError("unsupported variation target")
    return target_id


def _point_value_type(family: ExpandedScenario, point: VariationPoint) -> str:
    if isinstance(point, ParameterVariationPoint):
        return family.variables[point.target.variable].type.value
    if isinstance(point, LogicalTimingVariationPoint):
        return TIMING_TARGET_SPECS[point.target.slot][1]
    return "string"


class ExpandedScenarioBindingTargetResolver:
    """Production scenario-plane target resolver backed by one admitted family."""

    def __init__(self, family: ExpandedScenario) -> None:
        _require_family(family)
        self._family = family

    def validate_selection(self, descriptor: ExperimentScenarioSelectionDescriptorModel) -> None:
        """Admit a typed treatment through the same SDL owner and canonical targets.

        A refused treatment raises ``SDLSelectionError`` (ADR-116).
        """
        from .canonical import canonical_sdl_digest

        target = descriptor.target
        point = self._family.variation_points.get(target.variation_point_id)
        if (
            target.scenario_family_id != self._family.name
            or descriptor.scenario_family_digest != canonical_sdl_digest(self._family).value
            or point is None
            or target.target_id != _canonical_target_id(self._family, point)
            or descriptor.owner != _SDL_BINDING_OWNER
        ):
            raise SDLSelectionError("selection treatment does not match its authoritative SDL target")
        validate_selection_outcome(point, descriptor.outcome)

    def resolve(
        self,
        scenario_family_id: str,
        variation_point_id: str,
        supplied_target_id: str,
    ) -> ScenarioBindingResolution:
        if scenario_family_id != self._family.name:
            raise ExperimentBindingTargetError("scenario binding target family does not match the admitted family")
        point = self._family.variation_points.get(variation_point_id)
        if point is None:
            raise ExperimentBindingTargetError("scenario binding target variation point is not declared")
        if isinstance(point, (SubsetVariationPoint, OrderVariationPoint)) or isinstance(point.target, StructuralTarget):
            raise ExperimentBindingTargetError(
                "structural and collection variation points are not scalar binding targets"
            )
        canonical_target_id = _canonical_target_id(self._family, point)
        if supplied_target_id != canonical_target_id:
            raise ExperimentBindingTargetError("scenario binding target id is not the canonical SDL target")
        return ScenarioBindingResolution(
            canonical_target_id=canonical_target_id,
            value_type=_point_value_type(self._family, point),
            allowed_value_kinds=["literal"],
            sensitivity="public",
            owner=_SDL_BINDING_OWNER,
        )


def _selected_member_ids(point: VariationPoint, outcome: object) -> set[str]:
    if isinstance(point, AlternativeVariationPoint) and isinstance(outcome, ExperimentSelectionMemberOutcomeModel):
        return {outcome.member_id}
    if isinstance(point, (SubsetVariationPoint, OrderVariationPoint)) and isinstance(
        outcome,
        (ExperimentSelectionSubsetOutcomeModel, ExperimentSelectionOrderOutcomeModel),
    ):
        return set(outcome.member_ids)
    return set()


def _resolve_relation_point(family: ExpandedScenario, reference: str) -> str:
    rendered = reference.removeprefix("variation_points.")
    matches = sorted(
        point_id
        for point_id in family.variation_points
        if rendered == point_id or rendered == point_id.rsplit(".", 1)[-1]
    )
    if len(matches) != 1:
        raise SDLSelectionError("selection relation point must resolve exactly once")
    return matches[0]


def _validate_relation(
    family: ExpandedScenario,
    selected_members: Mapping[str, set[str]],
    *,
    owner_point: str,
    owner_member: str,
    relation: SelectionRelation,
    required: bool,
) -> None:
    target_point = _resolve_relation_point(family, relation.point)
    target_selected = selected_members[target_point]
    violation = (
        any(member not in target_selected for member in relation.members)
        if required
        else any(member in target_selected for member in relation.members)
    )
    if violation:
        relation_kind = "requires" if required else "excludes"
        raise SDLSelectionError(
            f"selection for variation point '{owner_point}' member '{owner_member}' violates {relation_kind}"
        )


def _validate_cross_point_relations(
    family: ExpandedScenario,
    outcomes: Mapping[str, object],
) -> None:
    selected_members = {
        point_id: _selected_member_ids(point, outcomes[point_id]) for point_id, point in family.variation_points.items()
    }
    for point_id, point in family.variation_points.items():
        for member_id in sorted(selected_members[point_id]):
            member = structural_members(point).get(member_id)
            if member is None:
                continue
            for relation in member.requires:
                _validate_relation(
                    family,
                    selected_members,
                    owner_point=point_id,
                    owner_member=member_id,
                    relation=relation,
                    required=True,
                )
            for relation in member.excludes:
                _validate_relation(
                    family,
                    selected_members,
                    owner_point=point_id,
                    owner_member=member_id,
                    relation=relation,
                    required=False,
                )


def _owner_payload(
    payload: dict[str, object],
    family: ExpandedScenario,
    owner_reference: str,
    owner_section: str,
) -> dict[str, object]:
    owner_address = _canonical_owner_address(family, owner_reference, owner_section)
    owner_name = owner_address.removeprefix(f"{owner_section}.")
    section = payload.get(owner_section)
    owner = section.get(owner_name) if isinstance(section, dict) else None
    if not isinstance(owner, dict):
        raise SDLSelectionError("variation target owner payload is unavailable")
    return owner


def _apply_structural_outcome(
    payload: dict[str, object],
    family: ExpandedScenario,
    point: VariationPoint,
    outcome: object,
) -> None:
    target = point.target
    if isinstance(target, StructuralTarget):
        apply_structural_writes(payload, structural_writes(family, target, point.alternatives[outcome.member_id]))
    elif isinstance(target, ReferenceTarget):
        owner_section, _ = REFERENCE_TARGET_SPECS[target.slot]
        owner = _owner_payload(payload, family, target.owner, owner_section)
        field_name = target.slot.value.split(".", 1)[1]
        if isinstance(outcome, ExperimentSelectionReferenceOutcomeModel):
            owner[field_name] = outcome.reference_id
        elif isinstance(point, AlternativeVariationPoint) and isinstance(
            outcome,
            ExperimentSelectionMemberOutcomeModel,
        ):
            owner[field_name] = point.alternatives[outcome.member_id].reference
    elif isinstance(target, CollectionTarget):
        owner_section, _ = COLLECTION_TARGET_SPECS[target.slot]
        owner = _owner_payload(payload, family, target.owner, owner_section)
        field_name = target.slot.value.split(".", 1)[1]
        member_ids = outcome.member_ids
        references = [point.members[member_id].reference for member_id in member_ids]
        current = owner.get(field_name)
        owner[field_name] = (
            {reference: current.get(reference, "") for reference in references}
            if isinstance(current, dict)
            else references
        )
    elif isinstance(target, LogicalTimingTarget) and isinstance(outcome, LiteralBindingValueModel):
        owner_section, _, _ = TIMING_TARGET_SPECS[target.slot]
        owner = _owner_payload(payload, family, target.owner, owner_section)
        owner[target.slot.value.split(".", 1)[1]] = outcome.value


def _resolved_reference_value(
    point: VariationPoint,
    outcome: object,
) -> str:
    if isinstance(outcome, ExperimentSelectionReferenceOutcomeModel):
        value = outcome.reference_id
    elif isinstance(point, AlternativeVariationPoint) and isinstance(
        outcome,
        ExperimentSelectionMemberOutcomeModel,
    ):
        value = point.alternatives[outcome.member_id].reference
    else:
        raise SDLSelectionError("variation outcome does not resolve to a canonical reference value")
    return value


def _resolved_collection_value(
    payload: dict[str, object],
    family: ExpandedScenario,
    point: VariationPoint,
    outcome: object,
) -> object:
    if not isinstance(point.target, CollectionTarget) or not isinstance(
        outcome,
        (ExperimentSelectionSubsetOutcomeModel, ExperimentSelectionOrderOutcomeModel),
    ):
        raise SDLSelectionError("variation outcome does not resolve to a canonical collection value")
    references = [point.members[member_id].reference for member_id in outcome.member_ids]
    owner_section, _ = COLLECTION_TARGET_SPECS[point.target.slot]
    current = _owner_payload(payload, family, point.target.owner, owner_section).get(
        point.target.slot.value.split(".", 1)[1]
    )
    return (
        {reference: current.get(reference, "") for reference in references} if isinstance(current, dict) else references
    )


def _resolved_target_value(
    payload: dict[str, object],
    family: ExpandedScenario,
    point: VariationPoint,
    outcome: object,
) -> object:
    target = point.target
    if isinstance(target, VariableTarget) and isinstance(outcome, LiteralBindingValueModel):
        value: object = outcome.value
    elif isinstance(target, ReferenceTarget):
        value = _resolved_reference_value(point, outcome)
    elif isinstance(target, CollectionTarget):
        value = _resolved_collection_value(payload, family, point, outcome)
    elif isinstance(target, LogicalTimingTarget) and isinstance(outcome, LiteralBindingValueModel):
        value = outcome.value
    else:
        raise SDLSelectionError("variation outcome does not resolve to a canonical target value")
    return value


def _owner_target_write_path(family: ExpandedScenario, point: VariationPoint) -> tuple[str, str, str]:
    target = point.target
    if isinstance(target, ReferenceTarget):
        specs = REFERENCE_TARGET_SPECS
    elif isinstance(target, CollectionTarget):
        specs = COLLECTION_TARGET_SPECS
    else:
        specs = TIMING_TARGET_SPECS
    section = specs[target.slot][0]
    owner = _canonical_owner_address(family, target.owner, section).removeprefix(f"{section}.")
    target_id = _canonical_target_id(family, point)
    return section, owner, target_id.removeprefix(f"{section}.{owner}.")


def _resolved_point_writes(
    payload: dict[str, object], family: ExpandedScenario, point: VariationPoint, outcome: object
) -> dict[tuple[str, ...], object]:
    if isinstance(point.target, StructuralTarget):
        return structural_writes(family, point.target, point.alternatives[outcome.member_id])
    if isinstance(point.target, VariableTarget):
        path = ("variables", point.target.variable)
    else:
        path = _owner_target_write_path(family, point)
    return {path: _resolved_target_value(payload, family, point, outcome)}


def _record_target_write(
    writes: dict[tuple[str, ...], tuple[type[object], bytes]], path: tuple[str, ...], value: object
) -> bool:
    try:
        encoded = canonical_json_bytes(value)
    except rfc8785.CanonicalizationError as exc:
        # A selected value with an integer outside the I-JSON range has no canonical form to compare.
        raise SDLSelectionError("a selected variation value has no canonical JSON form") from exc
    fingerprint = (type(value), encoded)
    prior = writes.get(path)
    if prior is not None and prior != fingerprint:
        raise SDLSelectionError("multiple variation points resolve conflicting values for one canonical target")
    writes[path] = fingerprint
    return len(path) == 3 and path[2] == "presence" and value is False


def _validate_target_writes(
    payload: dict[str, object],
    family: ExpandedScenario,
    outcomes: Mapping[str, object],
) -> None:
    writes: dict[tuple[str, ...], tuple[type[object], bytes]] = {}
    absent: set[tuple[str, ...]] = set()
    for point_id in sorted(family.variation_points):
        point = family.variation_points[point_id]
        resolved = _resolved_point_writes(payload, family, point, outcomes[point_id])
        for path, value in resolved.items():
            if _record_target_write(writes, path, value):
                absent.add(path[:2])
    if any(path[:2] in absent and path[2:] != ("presence",) for path in writes):
        raise SDLSelectionError("declaration absence conflicts with a descendant variation write")


def select_scenario_family(
    family: ExpandedScenario,
    outcomes: Mapping[str, object],
    *,
    trial_provenance: TrialInstantiationProvenance | None = None,
) -> InstantiatedScenario:
    """Construct and semantically admit the exact concrete scenario selected from *family*."""

    _require_family(family)
    missing = sorted(set(family.variation_points) - set(outcomes))
    unknown = sorted(set(outcomes) - set(family.variation_points))
    if missing or unknown:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unknown:
            details.append("unknown: " + ", ".join(unknown))
        raise SDLSelectionError("complete scenario-family selection required (" + "; ".join(details) + ")")
    for point_id in sorted(family.variation_points):
        validate_selection_outcome(family.variation_points[point_id], outcomes[point_id])
    _validate_cross_point_relations(family, outcomes)

    payload = family.model_dump(mode="python", by_alias=True)
    _validate_target_writes(payload, family, outcomes)
    parameters: dict[str, object] = {}
    for point_id in sorted(family.variation_points):
        point = family.variation_points[point_id]
        outcome = outcomes[point_id]
        if isinstance(point, ParameterVariationPoint) and isinstance(outcome, LiteralBindingValueModel):
            parameters[point.target.variable] = outcome.value
        else:
            _apply_structural_outcome(payload, family, point, outcome)
    payload["variation_points"] = {}
    if any(isinstance(point.target, StructuralTarget) for point in family.variation_points.values()):
        reconcile_selection_provenance(family, payload)
    try:
        selected_family = ExpandedScenario.model_validate(payload)
        return instantiate_scenario(
            selected_family,
            parameters=parameters,
            trial_provenance=trial_provenance,
        )
    except (SDLInstantiationError, ValidationError) as exc:
        raise SDLSelectionError("selected scenario failed whole-scenario semantic admission") from exc


__all__ = ["ExpandedScenarioBindingTargetResolver", "SDLSelectionError", "select_scenario_family"]
