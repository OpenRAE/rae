"""Authored ACT-620 references; selection intent grants no disclosure authority."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from raes_contracts.contracts.participant_control_context import ParticipantControlContextAssetReferenceModel

from ._base import SDLModel, is_variable_ref

if TYPE_CHECKING:
    from raes_contracts.contracts.experiment_bindings import (
        ParticipantConfigurationModel,
        ParticipantControlContextConfigurationSelectionModel,
    )

    from ._declarations import DeclarationIndex
    from .scenario import ScenarioContent


class ParticipantControlContextReference(SDLModel):
    """One pinned authored intent in a participant-local selection slot."""

    declaration_ref: str = Field(min_length=1, max_length=1024, pattern=r"\S")
    asset_ref: ParticipantControlContextAssetReferenceModel
    disposition: Literal["selected", "withheld"] = "selected"

    @field_validator("asset_ref")
    @classmethod
    def _immutable_pin(
        cls, value: ParticipantControlContextAssetReferenceModel
    ) -> ParticipantControlContextAssetReferenceModel:
        from ._scenario_instantiation import collect_variable_tokens

        if collect_variable_tokens(value.model_dump(mode="json")):
            raise ValueError("control-context.immutable-reference-token")
        return value


@dataclass(frozen=True)
class ResolvedControlContextSelection:
    """Exact authored selection, separate from ACT-620 authorized evidence."""

    slot_id: str
    participant_address: str
    declaration_address: str
    asset_ref: ParticipantControlContextAssetReferenceModel
    disposition: str
    owner_address: str


def resolve_control_context_reference(
    scenario: ScenarioContent,
    index: DeclarationIndex,
    reference: str,
    expected: ParticipantControlContextAssetReferenceModel,
    participant_name: str,
    *,
    allow_unresolved: bool = True,
) -> str:
    """Resolve through the existing index, then check immutable pin and scope."""
    from raes_contracts.participant_control_context import control_context_asset_reference

    from .entities import flatten_entities

    candidates = index.resolve(reference)
    if len(candidates) != 1:
        reason = "missing" if not candidates else "ambiguous"
        raise ValueError("control-context.reference-" + reason)
    address = next(iter(candidates))
    declaration = index.declaration_for(address)
    if declaration is None or declaration.kind != "control_context_assets":
        raise ValueError("control-context.reference-incompatible")
    asset = scenario.control_context_assets[declaration.model_tokens[1]]
    if control_context_asset_reference(asset) != expected:
        raise ValueError("control-context.reference-stale")
    agent = scenario.agents.get(participant_name)
    if agent is None:
        raise ValueError("control-context.participant-missing")
    role = agent.effective_role(flatten_entities(scenario.entities))
    if (
        f"agents.{participant_name}" not in asset.participant_addresses
        and role not in asset.role_refs
        and not (allow_unresolved and is_variable_ref(role))
    ):
        raise ValueError("control-context.scope-incompatible")
    return address


def authored_control_context_bindings(
    scenario: ScenarioContent,
) -> Iterator[tuple[str, str, str, ParticipantControlContextReference]]:
    """Use the incumbent direct-participant and reusable-role selection rules."""
    from .entities import flatten_entities
    from .semantics.participant_behavior import select_participants

    for name, agent in scenario.agents.items():
        for slot, binding in agent.control_context.items():
            yield f"agents.{name}", name, slot, binding
    entities = flatten_entities(scenario.entities)
    roles = {name: agent.effective_role(entities) for name, agent in scenario.agents.items()}
    for name, spec in scenario.behavior_specifications.items():
        for participant in sorted(select_participants(spec, set(scenario.agents), roles)):
            for slot, binding in spec.control_context.items():
                yield f"behavior_specifications.{name}", participant, slot, binding


def resolve_authored_control_context(
    scenario: ScenarioContent, index: DeclarationIndex
) -> tuple[tuple[ResolvedControlContextSelection, ...], tuple[str, ...]]:
    """Collect bounded failures without disclosing descriptor or reference values."""
    from raes_contracts.participant_control_context import control_context_asset_reference

    errors: list[str] = []
    versions: dict[tuple[str, str], ParticipantControlContextAssetReferenceModel] = {}
    for asset in scenario.control_context_assets.values():
        key = asset.asset_id, asset.asset_version
        pin = control_context_asset_reference(asset)
        if key in versions and versions[key] != pin:
            errors.append("control-context.descriptor-conflict")
        versions[key] = pin
    selections: list[ResolvedControlContextSelection] = []
    claimed: set[tuple[str, str]] = set()
    for owner, participant, slot, binding in authored_control_context_bindings(scenario):
        key = participant, slot
        if key in claimed:
            errors.append("control-context.selection-conflict")
        claimed.add(key)
        if is_variable_ref(binding.declaration_ref):
            continue
        try:
            address = resolve_control_context_reference(
                scenario, index, binding.declaration_ref, binding.asset_ref, participant
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        selections.append(
            ResolvedControlContextSelection(
                slot, f"agents.{participant}", address, binding.asset_ref, binding.disposition, owner
            )
        )
    return tuple(selections), tuple(dict.fromkeys(errors))


class SDLControlContextConfigurationValidator:
    """Trusted ADR-094 owner adapter over an explicitly supplied SDL family."""

    def __init__(self, scenario: ScenarioContent) -> None:
        self._scenario = scenario

    def for_scenario(self, scenario: ScenarioContent) -> SDLControlContextConfigurationValidator:
        """Bind the same trusted owner check to this concrete trial selection."""
        return type(self)(scenario)

    def validate_and_normalize(self, configuration: ParticipantConfigurationModel) -> ParticipantConfigurationModel:
        return configuration

    def validate_control_context_reference(
        self, participant_address: str, selection: ParticipantControlContextConfigurationSelectionModel
    ) -> None:
        from ._declarations import build_declaration_index
        from .validator import SemanticValidator

        # Reconstruct the mutable input, rather than trusting its validation flag.
        scenario = type(self._scenario).model_validate(self._scenario.model_dump(mode="python"))
        SemanticValidator(scenario).validate()
        participants = {f"agents.{name}": name for name in scenario.agents}
        participant_name = participants.get(participant_address)
        if participant_name is None:
            raise ValueError("control-context.participant-missing")
        index = build_declaration_index(scenario)
        resolved = resolve_control_context_reference(
            scenario, index, selection.declaration_ref, selection.asset_ref, participant_name, allow_unresolved=False
        )
        if resolved != selection.declaration_ref:
            raise ValueError("control-context.canonical-reference-required")
        selections, errors = resolve_authored_control_context(scenario, index)
        if errors or any(
            item.participant_address == participant_address and item.slot_id == selection.slot_id for item in selections
        ):
            raise ValueError("control-context.selection-conflict")
