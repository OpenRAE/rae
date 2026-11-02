"""Reusable mixed-control policies and finite scripts (ACT-617, MC-01 and MC-02).

A rev1 policy is selected only by the required
``semantics: mixed-control-policy-occurrence/rev1`` pin and by its required
``form``. Its permitted transitions are reusable permissions: they carry no
fixed state revision, effective order or proposal identity, so one edge can be
applied any number of times. Each application is a separate API-409
``participant-control-occurrence-v2`` occurrence. A finite script pins an
ordered list of steps over those edges.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator
from raes_contracts.identifiers import PortableIdentifier, portable_identifier_map_schema
from raes_contracts.participant_mixed_control_vocabulary import (
    MIXED_CONTROL_COORDINATE_LIMIT,
    MixedControlControllerState,
    MixedControlDispositionRules,
    MixedControlOrderStrategy,
    MixedControlTransitionKind,
    ParticipantControlTargetKind,
    omit_property_titles,
)
from raes_contracts.sdl_model import SDLModel

MIXED_CONTROL_POLICY_SEMANTICS = "mixed-control-policy-occurrence/rev1"
MixedControlCoordinate = Annotated[StrictInt, Field(ge=0, le=MIXED_CONTROL_COORDINATE_LIMIT)]
MixedControlRef = Annotated[str, Field(min_length=1, pattern=r"\S")]
_UNIQUE_REFS = {"uniqueItems": True}
_PROPERTIES = "properties"
_ALL_OF = "allOf"

MIXED_CONTROL_KIND_TARGETS: dict[MixedControlTransitionKind, frozenset[ParticipantControlTargetKind]] = {
    MixedControlTransitionKind.PROPOSAL: frozenset(),
    MixedControlTransitionKind.APPROVAL: frozenset({ParticipantControlTargetKind.PROPOSAL}),
    MixedControlTransitionKind.DENIAL: frozenset({ParticipantControlTargetKind.PROPOSAL}),
    MixedControlTransitionKind.EXTERNAL_DIRECTION: frozenset(
        {
            ParticipantControlTargetKind.PROPOSAL,
            ParticipantControlTargetKind.ACTION,
            ParticipantControlTargetKind.CONTROL,
        }
    ),
    MixedControlTransitionKind.INTERVENTION: frozenset(
        {
            ParticipantControlTargetKind.ACTION,
            ParticipantControlTargetKind.CONTROL,
            ParticipantControlTargetKind.ATTEMPT,
        }
    ),
    MixedControlTransitionKind.HANDOFF: frozenset(),
    MixedControlTransitionKind.OVERRIDE: frozenset(
        {ParticipantControlTargetKind.CONTROL, ParticipantControlTargetKind.DECISION}
    ),
    MixedControlTransitionKind.CANCELLATION: frozenset(
        {
            ParticipantControlTargetKind.PROPOSAL,
            ParticipantControlTargetKind.DECISION,
            ParticipantControlTargetKind.ADMITTED_ACTION,
            ParticipantControlTargetKind.ATTEMPT,
        }
    ),
}
"""The closed MC-05 target set of each kind; a direction edge narrows its own set with ``target_kinds``."""


def _require_unique(values: list[str], label: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"mixed-control {label} must be unique")
    return values


DirectionTargetKind = Literal[
    ParticipantControlTargetKind.PROPOSAL,
    ParticipantControlTargetKind.ACTION,
    ParticipantControlTargetKind.CONTROL,
]
StepTargetKind = Literal[
    ParticipantControlTargetKind.PROPOSAL,
    ParticipantControlTargetKind.ACTION,
    ParticipantControlTargetKind.CONTROL,
    ParticipantControlTargetKind.DECISION,
    ParticipantControlTargetKind.ADMITTED_ACTION,
    ParticipantControlTargetKind.ATTEMPT,
]
_KIND_ONLY_FIELDS = (
    (MixedControlTransitionKind.EXTERNAL_DIRECTION, "target_kinds"),
    (MixedControlTransitionKind.HANDOFF, "completion_evidence_refs"),
)
_DirectionTargets = Annotated[list[DirectionTargetKind], Field(min_length=1, json_schema_extra=_UNIQUE_REFS)]
_CompletionEvidence = Annotated[list[MixedControlRef], Field(min_length=1, json_schema_extra=_UNIQUE_REFS)]


def _only_when(selector: str, value: str, name: str) -> dict[str, Any]:
    """``name`` is a non-null array exactly when ``selector`` equals ``value``; otherwise absent or null."""

    return {
        "if": {_PROPERTIES: {selector: {"const": value}}},
        "then": {"required": [name], _PROPERTIES: {name: {"type": "array"}}},
        "else": {_PROPERTIES: {name: {"type": "null"}}},
    }


def _permitted_transition_schema(schema: dict[str, Any]) -> None:
    """Publish the kind-specific fields as closed JSON Schema conditionals."""

    omit_property_titles(schema)
    schema[_ALL_OF] = [_only_when("transition_kind", kind.value, name) for kind, name in _KIND_ONLY_FIELDS]


class MixedControlPermittedTransition(SDLModel):
    """One reusable permission (MC-01); kind-specific fields follow MC-05."""

    # Only an external-direction edge has ``target_kinds`` and only a handoff edge has
    # ``completion_evidence_refs``; every other kind uses its fixed MC-05 target set.

    model_config = ConfigDict(json_schema_extra=_permitted_transition_schema)

    transition_kind: MixedControlTransitionKind
    from_state_ref: PortableIdentifier
    to_state_ref: PortableIdentifier
    valid_from_order: MixedControlCoordinate
    valid_until_order: MixedControlCoordinate
    evidence_refs: list[MixedControlRef] = Field(min_length=1, json_schema_extra=_UNIQUE_REFS)
    target_kinds: _DirectionTargets | None = None
    completion_evidence_refs: _CompletionEvidence | None = None

    @field_validator("evidence_refs", "target_kinds", "completion_evidence_refs")
    @classmethod
    def _unique_refs(cls, values: list | None) -> list | None:
        return values if values is None else _require_unique(values, "permitted-transition refs")

    @model_validator(mode="after")
    def _validate_permission(self) -> MixedControlPermittedTransition:
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("mixed-control permitted-transition window must not be inverted")
        kind = MixedControlTransitionKind(self.transition_kind)
        for owner, name in _KIND_ONLY_FIELDS:
            if kind is owner and getattr(self, name) is None:
                raise ValueError(f"{kind.value} permitted transitions require {name}")
            if kind is not owner and getattr(self, name) is not None:
                raise ValueError(f"{kind.value} permitted transitions cannot carry {name}")
        return self

    def target_kinds_allowed(self) -> frozenset[ParticipantControlTargetKind]:
        """Return the MC-05 target kinds this edge permits."""

        if self.target_kinds is not None:
            return frozenset(ParticipantControlTargetKind(kind) for kind in self.target_kinds)
        return MIXED_CONTROL_KIND_TARGETS[MixedControlTransitionKind(self.transition_kind)]


def _script_step_schema(schema: dict[str, Any]) -> None:
    omit_property_titles(schema)
    bounds = ("valid_from_order", "valid_until_order")
    non_null = {"not": {"type": "null"}}
    schema[_ALL_OF] = [
        {
            "if": {_PROPERTIES: {first: non_null}, "required": [first]},
            "then": {_PROPERTIES: {second: non_null}, "required": [second]},
        }
        for first, second in (bounds, bounds[::-1])
    ]


class MixedControlScriptStep(SDLModel):
    """One finite-script step; it only narrows its edge."""

    model_config = ConfigDict(json_schema_extra=_script_step_schema)

    step_id: PortableIdentifier
    permitted_transition_ref: PortableIdentifier
    expected_state_revision: MixedControlCoordinate | None = None
    valid_from_order: MixedControlCoordinate | None = None
    valid_until_order: MixedControlCoordinate | None = None
    target_kind: StepTargetKind | None = None
    target_step_ref: PortableIdentifier | None = None

    @model_validator(mode="after")
    def _validate_step_window(self) -> MixedControlScriptStep:
        if (self.valid_from_order is None) != (self.valid_until_order is None):
            raise ValueError("mixed-control script step window requires both valid_from_order and valid_until_order")
        if self.valid_from_order is not None and self.valid_until_order < self.valid_from_order:
            raise ValueError("mixed-control script step window must not be inverted")
        if self.target_step_ref == self.step_id:
            raise ValueError("mixed-control script step cannot target itself")
        return self


_ScriptSteps = Annotated[list[MixedControlScriptStep], Field(min_length=1)]


def _policy_schema(schema: dict[str, Any]) -> None:
    """Publish the form's script rule as a closed conditional and the MC-08 bound over legacy states."""

    omit_property_titles(schema)
    schema[_ALL_OF] = [_only_when("form", "finite-script", "script_steps")]
    states = schema[_PROPERTIES]["controller_states"]
    bound = {"maximum": MIXED_CONTROL_COORDINATE_LIMIT}
    window = {_PROPERTIES: {"valid_from_order": bound, "valid_until_order": bound}}
    patterns = states.get("patternProperties", {})
    for pattern, value in patterns.items():
        patterns[pattern] = {_ALL_OF: [value, window]}


class MixedControlPolicy(SDLModel):
    """A rev1 reusable policy or finite script (MC-01, MC-02)."""

    # A reusable-policy permits any finite trace its edges admit and has no script_steps.
    # A finite-script requires an ordered list of distinct steps over those edges.
    model_config = ConfigDict(json_schema_extra=_policy_schema)

    semantics: Literal["mixed-control-policy-occurrence/rev1"]
    form: Literal["reusable-policy", "finite-script"]
    participant_ref: str
    policy_revision: str
    order_strategy: MixedControlOrderStrategy
    initial_state_ref: PortableIdentifier
    dispositions: MixedControlDispositionRules
    controller_states: dict[PortableIdentifier, MixedControlControllerState] = Field(
        min_length=1, json_schema_extra=portable_identifier_map_schema
    )
    permitted_transitions: dict[PortableIdentifier, MixedControlPermittedTransition] = Field(
        min_length=1, json_schema_extra=portable_identifier_map_schema
    )
    script_steps: _ScriptSteps | None = None

    @field_validator("participant_ref", "policy_revision")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mixed-control participant and policy revision must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_policy_graph(self) -> MixedControlPolicy:
        if self.initial_state_ref not in self.controller_states:
            raise ValueError("mixed_control initial_state_ref must resolve to controller_states")
        for state_id, state in self.controller_states.items():
            if state.policy_revision != self.policy_revision:
                raise ValueError(f"mixed-control controller state '{state_id}' has a stale policy revision")
            if state.valid_until_order > MIXED_CONTROL_COORDINATE_LIMIT:
                raise ValueError(
                    f"mixed-control controller state '{state_id}' order window must be less than or equal to "
                    f"{MIXED_CONTROL_COORDINATE_LIMIT}"
                )
        for transition_id, transition in self.permitted_transitions.items():
            if any(ref not in self.controller_states for ref in (transition.from_state_ref, transition.to_state_ref)):
                raise ValueError(
                    f"mixed-control permitted transition '{transition_id}' has an unknown controller-state ref"
                )
        self._validate_script()
        return self

    def _validate_script(self) -> None:
        if self.form == "reusable-policy":
            if self.script_steps is not None:
                raise ValueError("a reusable-policy mixed_control has no script_steps")
            return
        if self.script_steps is None:
            raise ValueError("a finite-script mixed_control requires script_steps")
        step_ids = [step.step_id for step in self.script_steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("mixed-control script step identities must be distinct")
        for step in self.script_steps:
            if step.permitted_transition_ref not in self.permitted_transitions:
                raise ValueError(f"mixed-control script step '{step.step_id}' names an unknown permitted transition")


def mixed_control_policy_semantics(declaration: object) -> str:
    """Return the explicit interpretation pin of one authored ``mixed_control`` value."""

    return MIXED_CONTROL_POLICY_SEMANTICS if isinstance(declaration, MixedControlPolicy) else ""


__all__ = [
    "MIXED_CONTROL_KIND_TARGETS",
    "MIXED_CONTROL_POLICY_SEMANTICS",
    "DirectionTargetKind",
    "MixedControlCoordinate",
    "MixedControlPermittedTransition",
    "MixedControlPolicy",
    "MixedControlScriptStep",
    "StepTargetKind",
    "mixed_control_policy_semantics",
]
