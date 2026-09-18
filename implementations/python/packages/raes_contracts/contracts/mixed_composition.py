"""Closed portable mixed-participant composition profile contracts.

The profile publishes sealed realization/admission intent for ``sem-234/rev1``.
It deliberately contains no mutable runtime state, trial/run identity, backend
commands, or observed apparatus facts.  Structural validation is local to the
root; :func:`validate_mixed_composition_context` performs the trusted joins that
schema validation cannot establish.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, ValidationInfo, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .._canonical import canonical_json_digest
from ..addressing import CompiledAddress
from ..json_ingress import JSONValue, parse_bounded_json_object
from ..versions import MIXED_PARTICIPANT_COMPOSITION_PROFILE_SCHEMA_VERSION
from ..vocabulary import ParticipantFeatureSupportLevel
from .base import ContractModel, NonEmptyString, PositiveInteger, PrefixedDigestString
from .experiment_manifest_references import ExperimentManifestReferenceModel
from .experiment_references import ExperimentReferenceModel
from .participant_crossing import (
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
)
from .participant_runtime import ParticipantRuntimeMappingLoss, ParticipantRuntimeOrderingBasis
from .realization_plans import RealizationEnvelopeIdentityModel
from .schema_invariants import _add_raes_invariant

MIXED_COMPOSITION_CONTRACT_ID = "mixed-participant-composition-profile-v1"
MIXED_COMPOSITION_SCHEMA_VERSION = MIXED_PARTICIPANT_COMPOSITION_PROFILE_SCHEMA_VERSION
MIXED_COMPOSITION_SEMANTIC_REVISION = "sem-234/rev1"
MIXED_COMPOSITION_PROFILE_REVISION = "mixed-cross-backend-participant-control-v1@rev1"

_PLACEHOLDER_DIGEST = "sha256:" + "0" * 64
_SUPPORT_RANK = {
    ParticipantFeatureSupportLevel.UNSUPPORTED: 0,
    ParticipantFeatureSupportLevel.DISCLOSED_WEAK: 1,
    ParticipantFeatureSupportLevel.BOUNDED: 2,
    ParticipantFeatureSupportLevel.EXACT: 3,
}

AllocationTargetKind = Literal[
    "participant",
    "controlled-scope",
    "action-family",
    "observation-source",
    "crossing",
]
CompositionMode = Literal["alternative", "simultaneous-mixed", "staged"]
RealizationForm = Literal["simulation", "emulation-or-operation"]


def _require_unique(label: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")


def _require_key_identity(label: str, values: Mapping[str, object], attribute: str) -> None:
    for key, value in values.items():
        if getattr(value, attribute) != key:
            raise ValueError(f"{label} map key must equal embedded {attribute}")


class MixedCompositionValidationLimits(ContractModel):
    """Caller-selected resource limits for composition parsing and resolution."""

    max_source_bytes: PositiveInteger = 1_048_576
    max_json_depth: PositiveInteger = 64
    max_json_nodes: PositiveInteger = 20_000
    max_components: PositiveInteger = 64
    max_allocations: PositiveInteger = 1_024
    max_edges: PositiveInteger = 1_024
    max_phases: PositiveInteger = 256
    max_transitions: PositiveInteger = 512
    max_nested_profiles: PositiveInteger = 64
    max_context_work: PositiveInteger = 100_000


class CompositionFeatureRequirementModel(ContractModel):
    """One API-407 feature strength required from one allocated provider."""

    feature: NonEmptyString
    required_level: ParticipantFeatureSupportLevel = ParticipantFeatureSupportLevel.EXACT
    allowed_downgrade_level: ParticipantFeatureSupportLevel | None = None
    downgrade_policy_ref: NonEmptyString | None = None
    downgrade_provenance_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_downgrade(self) -> CompositionFeatureRequirementModel:
        coordinates = (
            self.allowed_downgrade_level,
            self.downgrade_policy_ref,
            self.downgrade_provenance_ref,
        )
        if any(value is not None for value in coordinates) and not all(value is not None for value in coordinates):
            raise ValueError("feature downgrade requires level, policy, and provenance references")
        if self.allowed_downgrade_level is not None:
            if _SUPPORT_RANK[self.allowed_downgrade_level] >= _SUPPORT_RANK[self.required_level]:
                raise ValueError("feature downgrade level must be weaker than the required level")
            if self.allowed_downgrade_level is ParticipantFeatureSupportLevel.UNSUPPORTED:
                raise ValueError("unsupported participant features cannot be authorized as a downgrade")
        return self


class MixedCompositionComponentModel(ContractModel):
    """One exact admitted apparatus component, not an observed runtime fact."""

    component_id: NonEmptyString
    apparatus_identity_ref: NonEmptyString
    realization_form: RealizationForm
    manifest_ref: ExperimentManifestReferenceModel
    realization_envelope: RealizationEnvelopeIdentityModel
    native_ownership_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _require_sealed_manifest(self) -> MixedCompositionComponentModel:
        if self.manifest_ref.ref_digest is None:
            raise ValueError("composition component manifest references must be digest-pinned")
        return self


class MixedCompositionAllocationModel(ContractModel):
    """Stable allocation of one compiled semantic target to one provider."""

    allocation_id: NonEmptyString
    target_kind: AllocationTargetKind
    target_address: CompiledAddress
    provider_component_id: NonEmptyString
    phase_ids: list[NonEmptyString] = Field(min_length=1)
    participant_identity_ref: NonEmptyString
    controller_ref: NonEmptyString
    action_authority_ref: NonEmptyString
    routing_ref: NonEmptyString
    feature_requirements: list[CompositionFeatureRequirementModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_allocation(self) -> MixedCompositionAllocationModel:
        _require_unique("allocation phase_ids", self.phase_ids)
        features = [requirement.feature for requirement in self.feature_requirements]
        _require_unique("allocation feature requirements", features)
        return self


class MixedCompositionEvidenceBindingModel(ContractModel):
    """Typed obligation-to-evidence reference; it is not an evidence body."""

    obligation_ref: NonEmptyString
    evidence_ref: NonEmptyString


class MixedCompositionTimeBindingModel(ContractModel):
    """Edge-relative order/coupling over an incumbent time-model mapping."""

    time_model_ref: NonEmptyString
    time_model_digest: PrefixedDigestString
    source_clock_address: CompiledAddress
    target_clock_address: CompiledAddress
    mapping_address: CompiledAddress
    ordering_basis: ParticipantRuntimeOrderingBasis
    temporal_coupling: Literal["tight", "bounded-asynchronous", "asynchronous"]


class MixedCompositionMappingLossModel(ContractModel):
    """Prospective mapping-loss obligation using the incumbent loss vocabulary."""

    kind: ParticipantRuntimeMappingLoss
    basis_ref: NonEmptyString
    affected_ref: NonEmptyString
    limitation_ref: NonEmptyString


class MixedCompositionFailureBehaviorModel(ContractModel):
    failure_ref: NonEmptyString
    disposition: Literal["fail-profile", "hold-phase", "abort-transition"]


class MixedCompositionEdgeModel(ContractModel):
    """One directed composition edge; never an API-423 runtime occurrence."""

    edge_id: NonEmptyString
    source_component_id: NonEmptyString
    target_component_id: NonEmptyString
    phase_ids: list[NonEmptyString] = Field(min_length=1)
    crossing_scope_address: CompiledAddress
    crossing_subject: ParticipantCrossingSubjectReferenceModel
    audience_scope_ref: NonEmptyString
    policy: ParticipantCrossingPolicyReferenceModel
    controller_ref: NonEmptyString
    authority_ref: NonEmptyString
    routing_ref: NonEmptyString
    disclosure_authority_ref: NonEmptyString
    native_ownership_ref: NonEmptyString | None = None
    time_binding: MixedCompositionTimeBindingModel
    mapping_loss: MixedCompositionMappingLossModel
    failure_behavior: MixedCompositionFailureBehaviorModel
    evidence_bindings: list[MixedCompositionEvidenceBindingModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_edge(self) -> MixedCompositionEdgeModel:
        if self.source_component_id == self.target_component_id:
            raise ValueError("composition edges must connect distinct components")
        _require_unique("edge phase_ids", self.phase_ids)
        _require_unique(
            "edge evidence obligations",
            [binding.obligation_ref for binding in self.evidence_bindings],
        )
        return self


class MixedCompositionPhaseModel(ContractModel):
    """One finite admitted membership slice, not mutable runtime state."""

    phase_id: NonEmptyString
    active_component_ids: list[NonEmptyString] = Field(min_length=1)
    active_allocation_ids: list[NonEmptyString] = Field(min_length=1)
    active_edge_ids: list[NonEmptyString] = Field(default_factory=list)
    evidence_bindings: list[MixedCompositionEvidenceBindingModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_phase(self) -> MixedCompositionPhaseModel:
        _require_unique("phase active_component_ids", self.active_component_ids)
        _require_unique("phase active_allocation_ids", self.active_allocation_ids)
        _require_unique("phase active_edge_ids", self.active_edge_ids)
        _require_unique(
            "phase evidence obligations",
            [binding.obligation_ref for binding in self.evidence_bindings],
        )
        return self


class MixedCompositionTransitionModel(ContractModel):
    """One bounded pre-admitted phase transition declaration."""

    transition_id: NonEmptyString
    source_phase_id: NonEmptyString
    target_phase_id: NonEmptyString
    trigger_ref: NonEmptyString
    evaluator_ref: NonEmptyString
    progress_bound: PositiveInteger
    failure_disposition: Literal["fail-profile", "hold-phase"]
    evidence_bindings: list[MixedCompositionEvidenceBindingModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_transition(self) -> MixedCompositionTransitionModel:
        if self.source_phase_id == self.target_phase_id:
            raise ValueError("composition transitions must connect distinct phases")
        _require_unique(
            "transition evidence obligations",
            [binding.obligation_ref for binding in self.evidence_bindings],
        )
        return self


class MixedParticipantCompositionProfileModel(ContractModel):
    """One sealed portable mixed-participant composition root."""

    contract_id: Literal[MIXED_COMPOSITION_CONTRACT_ID] = MIXED_COMPOSITION_CONTRACT_ID
    schema_version: Literal[MIXED_COMPOSITION_SCHEMA_VERSION] = MIXED_COMPOSITION_SCHEMA_VERSION
    semantic_revision: Literal[MIXED_COMPOSITION_SEMANTIC_REVISION] = MIXED_COMPOSITION_SEMANTIC_REVISION
    profile_revision: Literal[MIXED_COMPOSITION_PROFILE_REVISION] = MIXED_COMPOSITION_PROFILE_REVISION
    profile_id: NonEmptyString
    scenario_snapshot_ref: ExperimentReferenceModel
    composition_mode: CompositionMode
    control_loop_posture: Literal["open-loop", "closed-loop"]
    world_assumption: Literal["closed-world", "bounded-open-world"]
    federation_membership: Literal["fixed", "pre-admitted-staged"]
    components: dict[NonEmptyString, MixedCompositionComponentModel] = Field(min_length=1)
    allocations: dict[NonEmptyString, MixedCompositionAllocationModel] = Field(min_length=1)
    edges: dict[NonEmptyString, MixedCompositionEdgeModel] = Field(default_factory=dict)
    phases: dict[NonEmptyString, MixedCompositionPhaseModel] = Field(min_length=1)
    initial_phase_id: NonEmptyString
    phase_order: list[NonEmptyString] = Field(min_length=1)
    transitions: dict[NonEmptyString, MixedCompositionTransitionModel] = Field(default_factory=dict)
    nested_profile_refs: dict[NonEmptyString, PrefixedDigestString] = Field(default_factory=dict)
    profile_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_profile(self, info: ValidationInfo) -> MixedParticipantCompositionProfileModel:
        self._validate_identity_maps()
        self._validate_scenario_reference()
        self._validate_phase_graph()
        self._validate_mode()
        if not (isinstance(info.context, dict) and info.context.get("skip_profile_digest")):
            expected = canonical_json_digest(_canonical_profile_content(self))
            if self.profile_digest != expected:
                raise ValueError("profile_digest does not match the canonical profile content")
        return self

    def _validate_identity_maps(self) -> None:
        _require_key_identity("components", self.components, "component_id")
        _require_key_identity("allocations", self.allocations, "allocation_id")
        _require_key_identity("edges", self.edges, "edge_id")
        _require_key_identity("phases", self.phases, "phase_id")
        _require_key_identity("transitions", self.transitions, "transition_id")
        identities = [component.apparatus_identity_ref for component in self.components.values()]
        if len(identities) != len(set(identities)):
            raise ValueError("composition components must have distinct apparatus identity references")

    def _validate_scenario_reference(self) -> None:
        reference = self.scenario_snapshot_ref
        if reference.ref_kind != "scenario-snapshot" or reference.ref_digest is None:
            raise ValueError("composition profile requires a digest-pinned scenario-snapshot reference")
        if reference.ref_path is not None:
            raise ValueError("composition scenario snapshot references must not carry host paths")

    def _validate_phase_graph(self) -> None:
        phase_ids = set(self.phases)
        if self.initial_phase_id not in phase_ids:
            raise ValueError("initial_phase_id must resolve inside phases")
        if len(self.phase_order) != len(set(self.phase_order)) or set(self.phase_order) != phase_ids:
            raise ValueError("phase_order must contain every phase exactly once")
        if self.phase_order[0] != self.initial_phase_id:
            raise ValueError("phase_order must begin with initial_phase_id")

        seen_components: set[str] = set()
        seen_allocations: set[str] = set()
        seen_edges: set[str] = set()
        active_phase_by_allocation: dict[str, set[str]] = {key: set() for key in self.allocations}
        active_phase_by_edge: dict[str, set[str]] = {key: set() for key in self.edges}
        for phase in self.phases.values():
            components = set(phase.active_component_ids)
            allocations = set(phase.active_allocation_ids)
            edges = set(phase.active_edge_ids)
            if not components <= set(self.components):
                raise ValueError("phase references an unknown component")
            if not allocations <= set(self.allocations):
                raise ValueError("phase references an unknown allocation")
            if not edges <= set(self.edges):
                raise ValueError("phase references an unknown edge")
            seen_components.update(components)
            seen_allocations.update(allocations)
            seen_edges.update(edges)
            providers_by_target: dict[tuple[str, str], str] = {}
            for allocation_id in allocations:
                allocation = self.allocations[allocation_id]
                active_phase_by_allocation[allocation_id].add(phase.phase_id)
                if allocation.provider_component_id not in components:
                    raise ValueError("phase allocation provider must be an active component")
                target = (allocation.target_kind, allocation.target_address)
                incumbent = providers_by_target.setdefault(target, allocation.provider_component_id)
                if incumbent != allocation.provider_component_id:
                    raise ValueError("each phase target must have exactly one canonical provider")
            for edge_id in edges:
                edge = self.edges[edge_id]
                active_phase_by_edge[edge_id].add(phase.phase_id)
                if edge.source_component_id not in components or edge.target_component_id not in components:
                    raise ValueError("active edge endpoints must both be active components")

        if seen_components != set(self.components):
            raise ValueError("composition profile must not contain orphan components")
        if seen_allocations != set(self.allocations):
            raise ValueError("composition profile must not contain orphan allocations")
        if seen_edges != set(self.edges):
            raise ValueError("composition profile must not contain orphan edges")
        for allocation_id, active_phases in active_phase_by_allocation.items():
            if active_phases != set(self.allocations[allocation_id].phase_ids):
                raise ValueError("allocation phase_ids must equal its active phase membership")
        for edge_id, active_phases in active_phase_by_edge.items():
            if active_phases != set(self.edges[edge_id].phase_ids):
                raise ValueError("edge phase_ids must equal its active phase membership")

        transition_pairs: set[tuple[str, str]] = set()
        for transition in self.transitions.values():
            if transition.source_phase_id not in phase_ids or transition.target_phase_id not in phase_ids:
                raise ValueError("transition phases must resolve inside the profile")
            pair = (transition.source_phase_id, transition.target_phase_id)
            if pair in transition_pairs:
                raise ValueError("phase transitions must have one canonical transition per directed pair")
            transition_pairs.add(pair)
        expected_pairs = set(zip(self.phase_order, self.phase_order[1:], strict=False))
        if transition_pairs != expected_pairs:
            raise ValueError("transitions must exactly connect adjacent phase_order entries")
        if self.federation_membership == "fixed":
            memberships = {tuple(sorted(phase.active_component_ids)) for phase in self.phases.values()}
            if len(memberships) != 1:
                raise ValueError("fixed federation membership cannot vary by phase")

    def _validate_mode(self) -> None:
        if self.composition_mode == "alternative":
            if len(self.components) != 1 or self.edges:
                raise ValueError("alternative profiles require exactly one component and no composition edges")
            if any(len(phase.active_component_ids) != 1 for phase in self.phases.values()):
                raise ValueError("alternative profile phases require exactly one active component")
        elif self.composition_mode == "simultaneous-mixed":
            mixed = any(
                len({self.components[component_id].realization_form for component_id in phase.active_component_ids})
                >= 2
                for phase in self.phases.values()
            )
            if not mixed:
                raise ValueError("simultaneous-mixed profiles require distinct active realization forms")
        elif self.composition_mode == "staged":
            memberships = {tuple(sorted(phase.active_component_ids)) for phase in self.phases.values()}
            if len(self.phases) < 2 or len(memberships) < 2:
                raise ValueError("staged profiles require a finite membership change across at least two phases")

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            schema,
            "mixed-composition-root-local-graph-valid",
            "The sealed root has exact keyed identities, closed references, one provider per target and phase, "
            "complete finite phase membership, mode-specific realization rules, and a matching canonical digest.",
            validator="raes_contracts.contracts.mixed_composition.MixedParticipantCompositionProfileModel._validate_profile",
            inputs=[{"contract_id": MIXED_COMPOSITION_CONTRACT_ID, "instance_path": "#"}],
        )
        _add_raes_invariant(
            schema,
            "mixed-composition-trusted-context-required",
            "Schema validity does not resolve scenario targets, manifests, envelopes, participant features, "
            "crossing policies, clocks, evidence, or nested profiles; trusted contextual validation is required.",
            validator="raes_contracts.contracts.mixed_composition_resolution.validate_mixed_composition_context",
            inputs=[{"contract_id": MIXED_COMPOSITION_CONTRACT_ID, "instance_path": "#"}],
        )
        return schema


def _canonical_profile_content(profile: MixedParticipantCompositionProfileModel) -> dict[str, object]:
    payload = profile.model_dump(mode="json")
    payload.pop("profile_digest", None)
    return payload


def seal_mixed_composition_profile(**fields: object) -> MixedParticipantCompositionProfileModel:
    """Validate and seal one composition root with its RFC 8785 content digest."""

    provisional = MixedParticipantCompositionProfileModel.model_validate(
        {**fields, "profile_digest": _PLACEHOLDER_DIGEST},
        context={"skip_profile_digest": True},
    )
    digest = canonical_json_digest(_canonical_profile_content(provisional))
    return MixedParticipantCompositionProfileModel.model_validate({**fields, "profile_digest": digest})


def _validate_json_shape(payload: JSONValue, limits: MixedCompositionValidationLimits) -> None:
    stack: list[tuple[JSONValue, int]] = [(payload, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > limits.max_json_nodes:
            raise ValueError("mixed composition JSON exceeds the configured node limit")
        if depth > limits.max_json_depth:
            raise ValueError("mixed composition JSON exceeds the configured depth limit")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)


def _validate_profile_limits(
    profile: MixedParticipantCompositionProfileModel,
    limits: MixedCompositionValidationLimits,
) -> None:
    counts = (
        (len(profile.components), limits.max_components, "component"),
        (len(profile.allocations), limits.max_allocations, "allocation"),
        (len(profile.edges), limits.max_edges, "edge"),
        (len(profile.phases), limits.max_phases, "phase"),
        (len(profile.transitions), limits.max_transitions, "transition"),
        (len(profile.nested_profile_refs), limits.max_nested_profiles, "nested profile"),
    )
    for actual, maximum, label in counts:
        if actual > maximum:
            raise ValueError(f"mixed composition exceeds the configured {label} limit")


def parse_mixed_composition_profile(
    source: str | bytes | bytearray,
    *,
    limits: MixedCompositionValidationLimits | None = None,
) -> MixedParticipantCompositionProfileModel:
    """Parse one bounded, duplicate-rejecting mixed-composition JSON object."""

    selected = limits or MixedCompositionValidationLimits()
    payload = parse_bounded_json_object(
        source,
        max_bytes=selected.max_source_bytes,
        max_depth=selected.max_json_depth,
    )
    _validate_json_shape(payload, selected)
    profile = MixedParticipantCompositionProfileModel.model_validate(payload)
    _validate_profile_limits(profile, selected)
    return profile
