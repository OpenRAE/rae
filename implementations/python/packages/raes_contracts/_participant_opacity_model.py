"""Exact finite participant-opacity transition-model contract."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from raes_contracts._base import ContractModel, PrefixedDigestString
from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.source_identity import SourceArtifactIdentityModel

from ._participant_opacity_common import (
    MAX_OPACITY_MODEL_STATES,
    MAX_OPACITY_MODEL_TRANSITIONS,
    MODEL_CHECK_PROVENANCE_NONCLAIM,
    Revision,
    SafeKey,
    SafeRef,
)
from .canonical import canonical_json_digest
from .versions import PARTICIPANT_OPACITY_MODEL_CHECK_INPUT_SCHEMA_VERSION


class ParticipantOpacityModelStateModel(ContractModel):
    """One state in the complete finite transition model.

    Reachability is deliberately absent: the model checker derives it from the
    initial-state set and transition relation.
    """

    ordinal: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES - 1)
    state_ref: SafeRef
    run_ref: SafeRef
    cut_ref: SafeRef
    strategy_ref: SafeRef
    scheduler_ref: SafeRef
    environment_ref: SafeRef
    order_ref: SafeRef
    evaluation_point: bool
    secret_holds: bool
    initial_information_key: SafeKey
    observation_key: SafeKey
    memory_key: SafeKey
    release_state_key: SafeKey
    coalition_fusion_key: SafeKey | None = None


class ParticipantOpacityModelTransitionModel(ContractModel):
    """One safe labelled edge in the complete finite transition relation."""

    ordinal: int = Field(ge=0, le=MAX_OPACITY_MODEL_TRANSITIONS - 1)
    transition_ref: SafeRef
    source_state_ordinal: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES - 1)
    target_state_ordinal: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES - 1)
    action_ref: SafeRef
    observation_event_key: SafeKey


class ParticipantOpacityModelAssumptionsModel(ContractModel):
    """Exact profile-derived domains and non-strengthening assumptions."""

    strategy_kind: Literal["passive", "active"]
    strategy_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)
    scheduler_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)
    environment_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)
    order_treatment: Literal[
        "total-order",
        "named-linearization",
        "all-linearizations",
        "partial-order",
        "causal-frontier",
    ]
    order_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)
    cut_ref: SafeRef
    nondeterminism: Literal["possibilistic-support"]
    time_model: Literal["untimed"]
    progress: Literal["progress-insensitive"]
    probability: Literal["outside-baseline"]

    @model_validator(mode="after")
    def _validate_canonical_domains(
        self,
    ) -> ParticipantOpacityModelAssumptionsModel:
        for values, label in (
            (self.strategy_refs, "strategy refs"),
            (self.scheduler_refs, "scheduler refs"),
            (self.environment_refs, "environment refs"),
            (self.order_refs, "order refs"),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{label} must be unique and sorted")
        return self

    @property
    def canonical_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class ParticipantOpacityModelCheckDeclaredCountsModel(ContractModel):
    """Exact realized cardinalities of the finite transition artifact."""

    states: int = Field(ge=1, le=MAX_OPACITY_MODEL_STATES)
    transitions: int = Field(ge=0, le=MAX_OPACITY_MODEL_TRANSITIONS)
    initial_states: int = Field(ge=1, le=MAX_OPACITY_MODEL_STATES)
    evaluation_points: int = Field(ge=1, le=MAX_OPACITY_MODEL_STATES)
    runs: int = Field(ge=1, le=MAX_OPACITY_MODEL_STATES)
    cuts: int = Field(ge=1, le=MAX_OPACITY_MODEL_STATES)
    strategies: int = Field(ge=1, le=1_000)
    scheduler_environment_pairs: int = Field(ge=1, le=10_000)
    order_variants: int = Field(ge=1, le=1_000)


class ParticipantOpacityModelCheckInputModel(ContractModel):
    """Closed finite transition model admitted for model checking."""

    schema_version: Literal[PARTICIPANT_OPACITY_MODEL_CHECK_INPUT_SCHEMA_VERSION] = (
        PARTICIPANT_OPACITY_MODEL_CHECK_INPUT_SCHEMA_VERSION
    )
    analysis_profile: Literal["raes-participant-opacity-model-check/v1"]
    source: SourceArtifactIdentityModel
    catalog_digest: PrefixedDigestString
    profile_id: SafeRef
    profile_revision: Revision
    profile_digest: PrefixedDigestString
    model_ref: SafeRef
    model_revision: Revision
    materializer_id: SafeRef
    materializer_version: Revision
    materializer_digest: PrefixedDigestString
    complete_model: bool
    assumptions: ParticipantOpacityModelAssumptionsModel
    declared_counts: ParticipantOpacityModelCheckDeclaredCountsModel
    initial_state_ordinals: tuple[int, ...] = Field(
        min_length=1,
        max_length=MAX_OPACITY_MODEL_STATES,
    )
    states: tuple[ParticipantOpacityModelStateModel, ...] = Field(
        min_length=1,
        max_length=MAX_OPACITY_MODEL_STATES,
    )
    transitions: tuple[ParticipantOpacityModelTransitionModel, ...] = Field(
        max_length=MAX_OPACITY_MODEL_TRANSITIONS,
    )
    claim: BehavioralClaimBindingModel

    @model_validator(mode="after")
    def _validate_transition_model(
        self,
    ) -> ParticipantOpacityModelCheckInputModel:
        _validate_model_identities(self)
        _validate_model_transitions(self)
        _validate_model_counts(self)
        _validate_model_declared_domains(self)
        _validate_model_initial_domain(self)
        _validate_model_check_claim_scope(self.claim, self.assumptions)
        return self

    @property
    def canonical_digest(self) -> str:
        """Digest the already-canonical complete transition artifact."""

        return canonical_json_digest(self.model_dump(mode="json"))


def _validate_model_identities(request: ParticipantOpacityModelCheckInputModel) -> None:
    state_ordinals = tuple(state.ordinal for state in request.states)
    transition_ordinals = tuple(transition.ordinal for transition in request.transitions)
    if state_ordinals != tuple(range(len(request.states))):
        raise ValueError("state ordinals must canonically and contiguously cover the state count")
    if transition_ordinals != tuple(range(len(request.transitions))):
        raise ValueError("transition ordinals must canonically and contiguously cover the transition count")
    if len({state.state_ref for state in request.states}) != len(request.states):
        raise ValueError("model state refs must be unique")
    if len({transition.transition_ref for transition in request.transitions}) != len(request.transitions):
        raise ValueError("model transition refs must be unique")
    if request.initial_state_ordinals != tuple(sorted(set(request.initial_state_ordinals))):
        raise ValueError("initial state ordinals must be unique and sorted")
    # A negative ordinal would index from the end of the states, so require the declared range.
    if any(not 0 <= ordinal < len(request.states) for ordinal in request.initial_state_ordinals):
        raise ValueError("initial state ordinals must reference declared states")


def _validate_model_transitions(request: ParticipantOpacityModelCheckInputModel) -> None:
    for transition in request.transitions:
        if transition.source_state_ordinal >= len(request.states) or transition.target_state_ordinal >= len(
            request.states
        ):
            raise ValueError("transition endpoints must reference declared states")
        source = request.states[transition.source_state_ordinal]
        target = request.states[transition.target_state_ordinal]
        source_domain = (
            source.strategy_ref,
            source.scheduler_ref,
            source.environment_ref,
            source.order_ref,
        )
        target_domain = (
            target.strategy_ref,
            target.scheduler_ref,
            target.environment_ref,
            target.order_ref,
        )
        if source_domain != target_domain:
            raise ValueError("transitions must remain inside one strategy/scheduler/environment/order domain")


def _validate_model_counts(request: ParticipantOpacityModelCheckInputModel) -> None:
    realized = {
        "states": len(request.states),
        "transitions": len(request.transitions),
        "initial_states": len(request.initial_state_ordinals),
        "evaluation_points": sum(state.evaluation_point for state in request.states),
        "runs": len({state.run_ref for state in request.states}),
        "cuts": len({state.cut_ref for state in request.states}),
        "strategies": len({state.strategy_ref for state in request.states}),
        "scheduler_environment_pairs": len({(state.scheduler_ref, state.environment_ref) for state in request.states}),
        "order_variants": len({state.order_ref for state in request.states}),
    }
    if realized != request.declared_counts.model_dump(mode="python"):
        raise ValueError("declared model-check counts must exactly match the transition model")


def _validate_model_declared_domains(request: ParticipantOpacityModelCheckInputModel) -> None:
    assumptions = request.assumptions
    if {state.strategy_ref for state in request.states} != set(assumptions.strategy_refs):
        raise ValueError("transition-model strategy domain must exactly match the assumptions")
    if {state.scheduler_ref for state in request.states} != set(assumptions.scheduler_refs):
        raise ValueError("transition-model scheduler domain must exactly match the assumptions")
    if {state.environment_ref for state in request.states} != set(assumptions.environment_refs):
        raise ValueError("transition-model environment domain must exactly match the assumptions")
    expected_pairs = {
        (scheduler_ref, environment_ref)
        for scheduler_ref in assumptions.scheduler_refs
        for environment_ref in assumptions.environment_refs
    }
    actual_pairs = {(state.scheduler_ref, state.environment_ref) for state in request.states}
    if actual_pairs != expected_pairs:
        raise ValueError("transition-model scheduler/environment domain must be the assumptions Cartesian product")
    if {state.order_ref for state in request.states} != set(assumptions.order_refs):
        raise ValueError("transition-model order domain must exactly match the assumptions")
    if {state.cut_ref for state in request.states} != {assumptions.cut_ref}:
        raise ValueError("transition-model cut domain must exactly match the assumptions")


def _validate_model_initial_domain(request: ParticipantOpacityModelCheckInputModel) -> None:
    initial_states = tuple(request.states[ordinal] for ordinal in request.initial_state_ordinals)
    actual = {
        (state.strategy_ref, state.scheduler_ref, state.environment_ref, state.order_ref) for state in initial_states
    }
    assumptions = request.assumptions
    expected = {
        (strategy_ref, scheduler_ref, environment_ref, order_ref)
        for strategy_ref in assumptions.strategy_refs
        for scheduler_ref in assumptions.scheduler_refs
        for environment_ref in assumptions.environment_refs
        for order_ref in assumptions.order_refs
    }
    if actual != expected:
        raise ValueError("initial states must cover every assumed strategy/scheduler/environment/order domain")


def _validate_model_check_claim_scope(
    claim: BehavioralClaimBindingModel,
    assumptions: ParticipantOpacityModelAssumptionsModel,
) -> None:
    expected_quantifier = "all-strategies" if assumptions.strategy_kind == "active" else "all-traces"
    if (
        claim.assurance_axis,
        claim.assurance_status,
        claim.evidence_scope,
        claim.quantifier_scope,
    ) != ("model-check", "model-checked", "model-check", expected_quantifier):
        raise ValueError("opacity model-check claims must use the profile-matched universal assurance coordinates")
    if MODEL_CHECK_PROVENANCE_NONCLAIM not in claim.explicit_non_claims:
        raise ValueError("normalized-model evidence must disclaim source and materializer authenticity")


__all__ = (
    "ParticipantOpacityModelAssumptionsModel",
    "ParticipantOpacityModelCheckDeclaredCountsModel",
    "ParticipantOpacityModelCheckInputModel",
    "ParticipantOpacityModelStateModel",
    "ParticipantOpacityModelTransitionModel",
)
