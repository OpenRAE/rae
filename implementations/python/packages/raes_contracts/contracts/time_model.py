"""Portable shared-time declaration, runtime-state, and provenance contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from ..addressing import CompiledAddress
from ..versions import (
    REALIZED_TIME_MODEL_SCHEMA_VERSION,
    TIME_MODEL_SCHEMA_VERSION,
    TIME_RUNTIME_STATE_SCHEMA_VERSION,
)
from .base import ContractModel, NonEmptyString

TimeDomainKind = Literal["wall_clock", "monotonic", "simulated", "logical", "external"]
TimeDomainVisibility = Literal["runtime_only", "participant_visible", "evidence_only"]
TimeEpochKind = Literal["unix", "scenario_start", "run_start", "unanchored", "external"]
ClockAuthorityKind = Literal["runtime", "backend", "system", "external"]
ClockMonotonicity = Literal["strict", "non_decreasing", "may_jump"]
TimeMappingKind = Literal["identity", "affine_rational"]
TimeAdvancementMode = Literal["real_time", "dilated", "stepped", "event_driven", "externally_paced"]
TimeSynchronizationMode = Literal["none", "authority", "barrier", "conservative"]
TimeResetBehavior = Literal["unsupported", "new_segment_zero", "new_segment_preserve_value"]
TimeReplayBehavior = Literal["unsupported", "restart_from_anchor", "restore_recorded_advances"]
TemporalConstraintKind = Literal["precedence", "duration", "window", "deadline", "cadence"]
ClockLifecycleState = Literal["running", "paused"]
ClockTransitionKind = Literal["initialize", "advance", "pause", "resume", "jump", "reset", "replay"]


class ExactRatioModel(ContractModel):
    """Reduced positive rational value."""

    numerator: StrictInt = Field(gt=0)
    denominator: StrictInt = Field(gt=0)

    @model_validator(mode="after")
    def _validate_reduced(self) -> ExactRatioModel:
        from math import gcd

        if gcd(self.numerator, self.denominator) != 1:
            raise ValueError("exact ratios must be reduced")
        return self


class TimeCoordinateModel(ContractModel):
    """Exact superdense coordinate within one discontinuity segment."""

    segment: StrictInt = Field(default=0, ge=0)
    tick: StrictInt
    microstep: StrictInt = Field(default=0, ge=0)


class TimeDomainDeclarationModel(ContractModel):
    address: CompiledAddress
    kind: TimeDomainKind
    tick_period_seconds: ExactRatioModel
    epoch: TimeEpochKind
    visibility: TimeDomainVisibility
    description: NonEmptyString

    @model_validator(mode="after")
    def _validate_epoch(self) -> TimeDomainDeclarationModel:
        if self.kind == "wall_clock" and self.epoch != "unix":
            raise ValueError("wall_clock time domains require the unix epoch")
        if self.kind == "monotonic" and self.epoch == "unix":
            raise ValueError("monotonic time domains cannot use the unix epoch")
        return self


class ClockDeclarationModel(ContractModel):
    address: CompiledAddress
    time_domain_address: CompiledAddress
    authority_kind: ClockAuthorityKind
    authority_ref: NonEmptyString
    monotonicity: ClockMonotonicity
    supports_pause: bool = False
    supports_reset: bool = False
    supports_jump: bool = False
    description: NonEmptyString

    @model_validator(mode="after")
    def _validate_jump_policy(self) -> ClockDeclarationModel:
        if self.monotonicity == "may_jump" and not self.supports_jump:
            raise ValueError("may_jump clocks must declare supports_jump")
        if self.monotonicity != "may_jump" and self.supports_jump:
            raise ValueError("supports_jump requires may_jump monotonicity")
        return self


class TimeDomainMappingDeclarationModel(ContractModel):
    address: CompiledAddress
    source_domain_address: CompiledAddress
    target_domain_address: CompiledAddress
    mapping_kind: TimeMappingKind
    scale: ExactRatioModel = Field(default_factory=lambda: ExactRatioModel(numerator=1, denominator=1))
    offset_ticks: StrictInt = 0
    description: NonEmptyString


class TimeProgressionPolicyDeclarationModel(ContractModel):
    address: CompiledAddress
    clock_address: CompiledAddress
    advancement_mode: TimeAdvancementMode
    pacing_ratio: ExactRatioModel = Field(default_factory=lambda: ExactRatioModel(numerator=1, denominator=1))
    synchronization_mode: TimeSynchronizationMode
    step_ticks: StrictInt | None = Field(default=None, gt=0)
    drift_bound_ticks: StrictInt | None = Field(default=None, ge=0)
    reset_behavior: TimeResetBehavior
    replay_behavior: TimeReplayBehavior
    description: NonEmptyString

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> TimeProgressionPolicyDeclarationModel:
        if self.advancement_mode == "stepped" and self.step_ticks is None:
            raise ValueError("stepped progression requires step_ticks")
        if self.advancement_mode != "stepped" and self.step_ticks is not None:
            raise ValueError("step_ticks is valid only for stepped progression")
        if self.advancement_mode not in {"real_time", "dilated"} and self.pacing_ratio != ExactRatioModel(
            numerator=1, denominator=1
        ):
            raise ValueError("non-unit pacing_ratio is valid only for real_time or dilated progression")
        return self


class TemporalConstraintDeclarationModel(ContractModel):
    address: CompiledAddress
    kind: TemporalConstraintKind
    clock_address: CompiledAddress
    subject_addresses: list[CompiledAddress] = Field(min_length=1)
    start: TimeCoordinateModel | None = None
    end: TimeCoordinateModel | None = None
    duration_ticks: StrictInt | None = Field(default=None, gt=0)
    cadence_ticks: StrictInt | None = Field(default=None, gt=0)
    description: NonEmptyString

    @model_validator(mode="after")
    def _validate_constraint_shape(self) -> TemporalConstraintDeclarationModel:
        if len(self.subject_addresses) != len(set(self.subject_addresses)):
            raise ValueError("temporal constraint subject_addresses must be unique")
        required_by_kind = {
            "precedence": (len(self.subject_addresses) == 2, "exactly two subjects"),
            "duration": (self.duration_ticks is not None, "duration_ticks"),
            "window": (self.start is not None and self.end is not None, "start and end"),
            "deadline": (self.end is not None, "end"),
            "cadence": (self.cadence_ticks is not None, "cadence_ticks"),
        }
        valid, requirement = required_by_kind[self.kind]
        if not valid:
            raise ValueError(f"{self.kind} temporal constraint requires {requirement}")
        if (
            self.start is not None
            and self.end is not None
            and (
                self.start.segment,
                self.start.tick,
                self.start.microstep,
            )
            > (
                self.end.segment,
                self.end.tick,
                self.end.microstep,
            )
        ):
            raise ValueError("temporal constraint start must not follow end")
        return self


def _validate_address_map(label: str, values: dict[str, object]) -> None:
    for key, value in values.items():
        if key != getattr(value, "address", None):
            raise ValueError(f"{label} map key must equal embedded address")


def _validate_acyclic_mappings(mappings: dict[str, TimeDomainMappingDeclarationModel]) -> None:
    graph: dict[str, set[str]] = {}
    for mapping in mappings.values():
        graph.setdefault(mapping.source_domain_address, set()).add(mapping.target_domain_address)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(domain: str) -> None:
        if domain in visiting:
            raise ValueError("time-domain mapping graph must be acyclic")
        if domain in visited:
            return
        visiting.add(domain)
        for target in graph.get(domain, set()):
            visit(target)
        visiting.remove(domain)
        visited.add(domain)

    for domain in graph:
        visit(domain)


def _validate_identity_mapping(
    mapping: TimeDomainMappingDeclarationModel,
    domains: dict[CompiledAddress, TimeDomainDeclarationModel],
) -> None:
    if mapping.mapping_kind != "identity":
        return
    source = domains[mapping.source_domain_address]
    target = domains[mapping.target_domain_address]
    if source.tick_period_seconds != target.tick_period_seconds or source.epoch != target.epoch:
        raise ValueError("identity mappings require matching tick periods and epochs")
    if mapping.scale != ExactRatioModel(numerator=1, denominator=1) or mapping.offset_ticks != 0:
        raise ValueError("identity mappings require unit scale and zero offset")


class TimeModelDeclarationModel(ContractModel):
    """Canonical backend-neutral declaration compiled from authored SDL."""

    schema_version: Literal[TIME_MODEL_SCHEMA_VERSION] = TIME_MODEL_SCHEMA_VERSION
    domains: dict[CompiledAddress, TimeDomainDeclarationModel] = Field(min_length=1)
    clocks: dict[CompiledAddress, ClockDeclarationModel] = Field(min_length=1)
    mappings: dict[CompiledAddress, TimeDomainMappingDeclarationModel] = Field(default_factory=dict)
    progression_policies: dict[CompiledAddress, TimeProgressionPolicyDeclarationModel] = Field(default_factory=dict)
    temporal_constraints: dict[CompiledAddress, TemporalConstraintDeclarationModel] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_references(self) -> TimeModelDeclarationModel:
        _validate_address_map("domains", self.domains)
        _validate_address_map("clocks", self.clocks)
        _validate_address_map("mappings", self.mappings)
        _validate_address_map("progression_policies", self.progression_policies)
        _validate_address_map("temporal_constraints", self.temporal_constraints)
        self._validate_clock_references()
        self._validate_mapping_references()
        self._validate_policy_references()
        self._validate_constraint_references()
        return self

    def _validate_clock_references(self) -> None:
        for clock in self.clocks.values():
            if clock.time_domain_address not in self.domains:
                raise ValueError(f"clock {clock.address!r} references an unknown time domain")

    def _validate_mapping_references(self) -> None:
        for mapping in self.mappings.values():
            if mapping.source_domain_address not in self.domains or mapping.target_domain_address not in self.domains:
                raise ValueError(f"mapping {mapping.address!r} references an unknown time domain")
            if mapping.source_domain_address == mapping.target_domain_address:
                raise ValueError("time-domain mappings must connect distinct domains")
            _validate_identity_mapping(mapping, self.domains)
        _validate_acyclic_mappings(self.mappings)

    def _validate_policy_references(self) -> None:
        policy_clocks: list[str] = []
        for policy in self.progression_policies.values():
            if policy.clock_address not in self.clocks:
                raise ValueError(f"progression policy {policy.address!r} references an unknown clock")
            policy_clocks.append(policy.clock_address)
            clock = self.clocks[policy.clock_address]
            if policy.reset_behavior != "unsupported" and not clock.supports_reset:
                raise ValueError("progression reset behavior requires clock reset support")
            if policy.replay_behavior != "unsupported" and not clock.supports_reset:
                raise ValueError("progression replay behavior requires clock reset support")
        if len(policy_clocks) != len(set(policy_clocks)):
            raise ValueError("a clock may have at most one progression policy")

    def _validate_constraint_references(self) -> None:
        known_subjects = set(self.domains) | set(self.clocks) | set(self.progression_policies)
        for constraint in self.temporal_constraints.values():
            if constraint.clock_address not in self.clocks:
                raise ValueError(f"temporal constraint {constraint.address!r} references an unknown clock")
            if any(
                not _is_declared_resource_subject(subject)
                and subject not in known_subjects
                for subject in constraint.subject_addresses
            ):
                raise ValueError(f"temporal constraint {constraint.address!r} references an unknown subject")

    def canonical_digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_declared_resource_subject(address: str) -> bool:
    """Admit compiler-owned resource addresses as temporal subjects.

    Most authored resources compile under ``sdl``. Participant-directed inject
    deliveries are the one current exception: the participant compiler owns
    their canonical address because the delivery is a participant relation to
    an orchestration occurrence. Keep that exception exact so an arbitrary
    participant address cannot bypass the time-model reference check.
    """

    parts = address.split(".")
    return address.startswith("sdl.") or (
        len(parts) == 5
        and all(parts)
        and parts[0] == "participant"
        and parts[1] == "behavior-specification"
        and parts[3] == "inject-delivery"
    )


class ClockTransitionEventModel(ContractModel):
    sequence: StrictInt = Field(ge=0)
    kind: ClockTransitionKind
    previous: TimeCoordinateModel | None
    resulting: TimeCoordinateModel
    resulting_state: ClockLifecycleState


class RuntimeClockStateModel(ContractModel):
    clock_address: CompiledAddress
    time_domain_address: CompiledAddress
    progression_policy_address: CompiledAddress | None = None
    authority_kind: ClockAuthorityKind
    authority_ref: NonEmptyString
    state: ClockLifecycleState
    coordinate: TimeCoordinateModel
    sequence: StrictInt = Field(ge=0)
    history: list[ClockTransitionEventModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_history(self) -> RuntimeClockStateModel:
        if self.history[0].kind != "initialize" or self.history[0].previous is not None:
            raise ValueError("clock history must begin with initialize and no previous coordinate")
        prior: ClockTransitionEventModel | None = None
        for expected_sequence, event in enumerate(self.history):
            if event.sequence != expected_sequence:
                raise ValueError("clock history sequence values must be contiguous from zero")
            if prior is not None:
                if event.previous != prior.resulting:
                    raise ValueError("clock transition previous coordinate must match prior result")
                self._validate_transition(prior, event)
            prior = event
        final = self.history[-1]
        if self.sequence != final.sequence or self.coordinate != final.resulting or self.state != final.resulting_state:
            raise ValueError("runtime clock state must equal the final history event")
        return self

    @staticmethod
    def _validate_transition(previous: ClockTransitionEventModel, event: ClockTransitionEventModel) -> None:
        prior_coordinate = previous.resulting
        if event.kind == "advance":
            if event.resulting.segment != prior_coordinate.segment:
                raise ValueError("advance must remain in the current segment")
            if (event.resulting.tick, event.resulting.microstep) <= (
                prior_coordinate.tick,
                prior_coordinate.microstep,
            ):
                raise ValueError("advance must increase the superdense coordinate")
        elif event.kind in {"pause", "resume"}:
            if event.resulting != prior_coordinate:
                raise ValueError("pause and resume must preserve the coordinate")
        elif event.kind in {"jump", "reset", "replay"}:
            if event.resulting.segment != prior_coordinate.segment + 1:
                raise ValueError("jump, reset, and replay must create exactly one new segment")
        elif event.kind == "initialize":
            raise ValueError("initialize may appear only as the first clock event")


class TimeRuntimeStateModel(ContractModel):
    """Typed observable state for all clocks governed by one declaration."""

    schema_version: Literal[TIME_RUNTIME_STATE_SCHEMA_VERSION] = TIME_RUNTIME_STATE_SCHEMA_VERSION
    declaration_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    clocks: dict[CompiledAddress, RuntimeClockStateModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_clock_keys(self) -> TimeRuntimeStateModel:
        for key, state in self.clocks.items():
            if key != state.clock_address:
                raise ValueError("runtime clock-state map key must equal clock_address")
        return self


class TimeApparatusBindingModel(ContractModel):
    address: CompiledAddress
    component_ref: NonEmptyString
    realization_kind: Literal["runtime_managed", "backend_native", "system", "external"]
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    limitations: list[NonEmptyString] = Field(default_factory=list)


class TimingLimitModel(ContractModel):
    limit_id: NonEmptyString
    subject_address: CompiledAddress
    kind: Literal["resolution", "drift", "jitter", "latency", "lookahead", "other"]
    value: ExactRatioModel
    unit: NonEmptyString
    evidence_refs: list[NonEmptyString] = Field(min_length=1)


class RealizedTimeModelProvenanceModel(ContractModel):
    """Run-scoped declaration/realization comparison and apparatus evidence."""

    schema_version: Literal[REALIZED_TIME_MODEL_SCHEMA_VERSION] = REALIZED_TIME_MODEL_SCHEMA_VERSION
    run_id: NonEmptyString
    declaration_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    declared_model: TimeModelDeclarationModel
    realized_model: TimeModelDeclarationModel
    apparatus_bindings: dict[CompiledAddress, TimeApparatusBindingModel] = Field(min_length=1)
    synchronization_assumptions: list[NonEmptyString] = Field(min_length=1)
    timing_limits: list[TimingLimitModel] = Field(default_factory=list)
    deviations: list[NonEmptyString] = Field(default_factory=list)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_provenance(self) -> RealizedTimeModelProvenanceModel:
        if self.declaration_digest != self.declared_model.canonical_digest():
            raise ValueError("declaration_digest must match declared_model")
        declared_sets = (
            set(self.declared_model.domains),
            set(self.declared_model.clocks),
            set(self.declared_model.mappings),
            set(self.declared_model.progression_policies),
            set(self.declared_model.temporal_constraints),
        )
        realized_sets = (
            set(self.realized_model.domains),
            set(self.realized_model.clocks),
            set(self.realized_model.mappings),
            set(self.realized_model.progression_policies),
            set(self.realized_model.temporal_constraints),
        )
        if declared_sets != realized_sets:
            raise ValueError("realized time model must preserve all declared portable addresses")
        for key, binding in self.apparatus_bindings.items():
            if key != binding.address:
                raise ValueError("apparatus binding map key must equal embedded address")
        required_bindings = set(self.declared_model.clocks) | set(self.declared_model.progression_policies)
        if not required_bindings.issubset(self.apparatus_bindings):
            raise ValueError("apparatus bindings must cover every declared clock and progression policy")
        known_addresses = set().union(*declared_sets)
        if any(binding.address not in known_addresses for binding in self.apparatus_bindings.values()):
            raise ValueError("apparatus binding references an unknown portable time address")
        if any(limit.subject_address not in known_addresses for limit in self.timing_limits):
            raise ValueError("timing limit references an unknown portable time address")
        if self.declared_model != self.realized_model and not self.deviations:
            raise ValueError("a non-equivalent realized model requires deviations")
        return self


def validate_time_runtime_state(
    declaration: TimeModelDeclarationModel,
    state: TimeRuntimeStateModel,
) -> None:
    """Bind typed runtime readback to the admitted declaration."""

    if state.declaration_digest != declaration.canonical_digest():
        raise ValueError("runtime time state declaration_digest does not match the admitted model")
    if set(state.clocks) != set(declaration.clocks):
        raise ValueError("runtime time state must cover exactly the admitted clock set")
    policies_by_clock = {policy.clock_address: policy.address for policy in declaration.progression_policies.values()}
    for address, runtime_clock in state.clocks.items():
        declared_clock = declaration.clocks[address]
        if runtime_clock.time_domain_address != declared_clock.time_domain_address:
            raise ValueError(f"runtime clock {address!r} changed its declared time domain")
        if runtime_clock.authority_kind != declared_clock.authority_kind:
            raise ValueError(f"runtime clock {address!r} changed its declared authority kind")
        if runtime_clock.authority_ref != declared_clock.authority_ref:
            raise ValueError(f"runtime clock {address!r} changed its declared authority reference")
        if runtime_clock.progression_policy_address != policies_by_clock.get(address):
            raise ValueError(f"runtime clock {address!r} changed its declared progression policy")


def validate_realized_time_model(
    declaration: TimeModelDeclarationModel,
    provenance: RealizedTimeModelProvenanceModel,
    *,
    run_id: str | None = None,
) -> None:
    """Bind one run provenance record to its declared portable model."""

    if provenance.declared_model != declaration:
        raise ValueError("realized-time provenance declared_model does not match the admitted declaration")
    if provenance.declaration_digest != declaration.canonical_digest():
        raise ValueError("realized-time provenance declaration_digest does not match the admitted declaration")
    if run_id is not None and provenance.run_id != run_id:
        raise ValueError("realized-time provenance run_id does not match the experiment run")


def validate_time_runtime_transition(
    previous: TimeRuntimeStateModel | None,
    next_state: TimeRuntimeStateModel | None,
) -> None:
    """Require shared-time readback to preserve admitted identity and history."""

    if previous is None:
        return
    if next_state is None:
        raise ValueError("runtime transition removed initialized shared-time state")
    if previous.declaration_digest != next_state.declaration_digest:
        raise ValueError("runtime transition changed the admitted time-model digest")
    if set(previous.clocks) != set(next_state.clocks):
        raise ValueError("runtime transition changed the admitted clock set")
    for address, prior_clock in previous.clocks.items():
        next_clock = next_state.clocks[address]
        if len(next_clock.history) < len(prior_clock.history):
            raise ValueError(f"runtime clock {address!r} truncated append-only history")
        if next_clock.history[: len(prior_clock.history)] != prior_clock.history:
            raise ValueError(f"runtime clock {address!r} rewrote append-only history")


__all__ = [
    "ClockDeclarationModel",
    "ClockTransitionEventModel",
    "ExactRatioModel",
    "RealizedTimeModelProvenanceModel",
    "RuntimeClockStateModel",
    "TemporalConstraintDeclarationModel",
    "TimeApparatusBindingModel",
    "TimeCoordinateModel",
    "TimeDomainDeclarationModel",
    "TimeDomainMappingDeclarationModel",
    "TimeModelDeclarationModel",
    "TimeProgressionPolicyDeclarationModel",
    "TimeRuntimeStateModel",
    "TimingLimitModel",
    "validate_realized_time_model",
    "validate_time_runtime_transition",
    "validate_time_runtime_state",
]
