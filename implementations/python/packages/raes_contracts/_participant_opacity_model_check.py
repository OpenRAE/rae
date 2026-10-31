"""Evidence contract for exact finite participant-opacity model checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from raes_contracts._base import ContractModel, PrefixedDigestString
from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.source_identity import SourceArtifactIdentityModel

from ._participant_opacity_common import (
    MAX_OPACITY_DIAGNOSTICS,
    MAX_OPACITY_MODEL_STATES,
    MAX_OPACITY_MODEL_TRANSITIONS,
    Revision,
    SafeRef,
)
from ._participant_opacity_model import (
    ParticipantOpacityModelAssumptionsModel,
    ParticipantOpacityModelCheckDeclaredCountsModel,
    _validate_model_check_claim_scope,
)
from .canonical import canonical_json_digest
from .diagnostics import DiagnosticModel
from .versions import PARTICIPANT_OPACITY_MODEL_CHECK_EVIDENCE_SCHEMA_VERSION


class ParticipantOpacityModelCheckOutcome(str, Enum):
    """Closed finite-state model-check outcomes."""

    HOLDS = "holds-on-exact-complete-finite-model"
    COUNTEREXAMPLE = "counterexample-found"
    VACUOUS = "vacuous-secret-domain"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ParticipantOpacityModelCheckCounterexampleDigestInput:
    """Exact safe counterexample coordinates and artifact joins to digest."""

    safe_ref: str
    actual_state_ordinal: int
    actual_path_transition_ordinals: tuple[int, ...]
    strategy_ref: str
    examined_cell_size: int
    model_digest: str
    profile_digest: str
    derived_carrier_digest: str


class ParticipantOpacityModelCheckConfigurationModel(ContractModel):
    """Complete output-affecting identity of the explicit-state checker."""

    profile: Literal["raes-participant-opacity-explicit-state/v1"]
    tool_id: Literal["raes-processor-participant-opacity-model-check"]
    tool_version: Literal["1.0.0"]
    package: Literal["raes"]
    package_version: Revision
    algorithm: Literal["complete-finite-transition-fixed-point/v1"]
    traversal: Literal["breadth-first-canonical/v1"]
    opacity_kernel: Literal["participant-opacity-information-cell-kernel/v1"]
    information_cell_key: Literal["initial-observation-memory-release-coalition-strategy-order/v1"]
    counterexample_selection: Literal["lowest-state-ordinal-canonical-shortest-path/v1"]
    max_states: Literal[4096]
    max_transitions: Literal[65536]

    @property
    def canonical_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class ParticipantOpacityStrategyCoverageModel(ContractModel):
    """Complete reached coverage for one declared participant strategy."""

    strategy_ref: SafeRef
    explored_states: int = Field(ge=1, le=MAX_OPACITY_MODEL_STATES)
    explored_transitions: int = Field(ge=0, le=MAX_OPACITY_MODEL_TRANSITIONS)
    reachable_evaluation_points: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES)
    reachable_secret_points: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES)


class ParticipantOpacityModelCheckCoverageModel(ContractModel):
    """Declared and explored fixed-point coverage with no hidden partial pass."""

    declared: ParticipantOpacityModelCheckDeclaredCountsModel
    explored_states: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES)
    explored_transitions: int = Field(ge=0, le=MAX_OPACITY_MODEL_TRANSITIONS)
    reachable_evaluation_points: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES)
    reachable_secret_points: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES)
    strategy_coverage: tuple[ParticipantOpacityStrategyCoverageModel, ...] = Field(max_length=1_000)
    explored_scheduler_environment_pairs: int = Field(ge=0, le=10_000)
    explored_order_variants: int = Field(ge=0, le=1_000)
    complete_fixed_point: bool

    @model_validator(mode="after")
    def _validate_coverage(
        self,
    ) -> ParticipantOpacityModelCheckCoverageModel:
        if self.explored_states > self.declared.states:
            raise ValueError("explored states cannot exceed declared states")
        if self.explored_transitions > self.declared.transitions:
            raise ValueError("explored transitions cannot exceed declared transitions")
        if self.reachable_evaluation_points > self.explored_states:
            raise ValueError("reachable evaluation points cannot exceed explored states")
        if self.reachable_secret_points > self.reachable_evaluation_points:
            raise ValueError("reachable secret points cannot exceed evaluation points")
        strategy_refs = tuple(item.strategy_ref for item in self.strategy_coverage)
        if strategy_refs != tuple(sorted(set(strategy_refs))):
            raise ValueError("strategy coverage must be unique and sorted")
        if sum(item.explored_states for item in self.strategy_coverage) != self.explored_states:
            raise ValueError("per-strategy explored states must sum to total explored states")
        if sum(item.explored_transitions for item in self.strategy_coverage) != self.explored_transitions:
            raise ValueError("per-strategy explored transitions must sum to total explored transitions")
        if sum(item.reachable_evaluation_points for item in self.strategy_coverage) != self.reachable_evaluation_points:
            raise ValueError("per-strategy evaluation points must sum to total evaluation points")
        if sum(item.reachable_secret_points for item in self.strategy_coverage) != self.reachable_secret_points:
            raise ValueError("per-strategy secret points must sum to total secret points")
        return self


class ParticipantOpacityModelCheckCounterexampleModel(ContractModel):
    """Sanitized canonical path to one reachable secret-only information cell."""

    safe_ref: Annotated[
        str,
        Field(pattern=r"^participant-opacity-model-check-counterexample:[0-9]{6}$"),
    ]
    counterexample_digest: PrefixedDigestString
    actual_state_ordinal: int = Field(ge=0, le=MAX_OPACITY_MODEL_STATES - 1)
    actual_path_transition_ordinals: tuple[int, ...] = Field(max_length=MAX_OPACITY_MODEL_STATES)
    strategy_ref: SafeRef
    examined_cell_size: int = Field(ge=1, le=MAX_OPACITY_MODEL_STATES)


class UnsupportedParticipantOpacityModelCheckModel(ContractModel):
    """Stable non-positive reason set for a valid model-check request."""

    profile: Literal["raes-participant-opacity-model-check-unsupported/v1"]
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_reasons(
        self,
    ) -> UnsupportedParticipantOpacityModelCheckModel:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("unsupported model-check reason codes must be unique and sorted")
        return self


class ParticipantOpacityModelCheckEvidenceModel(ContractModel):
    """Replayable evidence for one exact complete finite transition model."""

    schema_version: Literal[PARTICIPANT_OPACITY_MODEL_CHECK_EVIDENCE_SCHEMA_VERSION] = (
        PARTICIPANT_OPACITY_MODEL_CHECK_EVIDENCE_SCHEMA_VERSION
    )
    analysis_profile: Literal["raes-participant-opacity-model-check/v1"]
    provenance_scope: Literal["normalized-model-only"]
    taxonomy_id: Literal["raes-behavioral-relations"]
    taxonomy_revision: Revision
    catalog_digest: PrefixedDigestString
    relation_id: Literal["participant-predicate-opacity"]
    profile_id: SafeRef
    profile_revision: Revision
    profile_digest: PrefixedDigestString
    source: SourceArtifactIdentityModel
    model_ref: SafeRef
    model_revision: Revision
    model_digest: PrefixedDigestString
    materializer_id: SafeRef
    materializer_version: Revision
    materializer_digest: PrefixedDigestString
    assumptions: ParticipantOpacityModelAssumptionsModel
    assumptions_digest: PrefixedDigestString
    checker_configuration: ParticipantOpacityModelCheckConfigurationModel
    checker_configuration_digest: PrefixedDigestString
    derived_carrier_digest: PrefixedDigestString
    claim: BehavioralClaimBindingModel
    coverage: ParticipantOpacityModelCheckCoverageModel
    outcome: ParticipantOpacityModelCheckOutcome
    diagnostics: tuple[DiagnosticModel, ...] = Field(max_length=MAX_OPACITY_DIAGNOSTICS)
    counterexample: ParticipantOpacityModelCheckCounterexampleModel | None = None
    unsupported: UnsupportedParticipantOpacityModelCheckModel | None = None

    @model_validator(mode="after")
    def _validate_model_check_evidence(
        self,
    ) -> ParticipantOpacityModelCheckEvidenceModel:
        if self.assumptions_digest != self.assumptions.canonical_digest:
            raise ValueError("assumptions_digest must bind the model-check assumptions")
        if self.checker_configuration_digest != self.checker_configuration.canonical_digest:
            raise ValueError("checker_configuration_digest must bind the model-check configuration")
        if self.claim.taxonomy_id != self.taxonomy_id:
            raise ValueError("model-check claim taxonomy id must match the evidence")
        if self.claim.taxonomy_revision != self.taxonomy_revision:
            raise ValueError("model-check claim taxonomy revision must match the evidence")
        if self.claim.relation_id != self.relation_id:
            raise ValueError("model-check claim relation must match the evidence")
        if self.claim.relation_parameter_profile_ref != self.profile_id:
            raise ValueError("model-check claim profile id must match the evidence")
        if self.claim.relation_parameter_profile_revision != self.profile_revision:
            raise ValueError("model-check claim profile revision must match the evidence")
        _validate_model_check_claim_scope(self.claim, self.assumptions)
        _validate_model_check_coverage_join(self)
        _validate_model_check_outcome(self)
        return self


def _validate_model_check_coverage_join(
    evidence: ParticipantOpacityModelCheckEvidenceModel,
) -> None:
    assumptions = evidence.assumptions
    coverage = evidence.coverage
    declared = coverage.declared
    if declared.strategies != len(assumptions.strategy_refs):
        raise ValueError("declared strategy count must match the model-check assumptions")
    if declared.scheduler_environment_pairs != (len(assumptions.scheduler_refs) * len(assumptions.environment_refs)):
        raise ValueError("declared scheduler/environment count must match the model-check assumptions")
    if declared.order_variants != len(assumptions.order_refs):
        raise ValueError("declared order count must match the model-check assumptions")
    if coverage.complete_fixed_point:
        strategy_refs = tuple(item.strategy_ref for item in coverage.strategy_coverage)
        if strategy_refs != assumptions.strategy_refs:
            raise ValueError("complete strategy coverage must exactly match the model-check assumptions")
        if coverage.explored_scheduler_environment_pairs != declared.scheduler_environment_pairs:
            raise ValueError("complete scheduler/environment coverage must match the declared model domain")
        if coverage.explored_order_variants != declared.order_variants:
            raise ValueError("complete order coverage must match the declared model domain")


def _validate_model_check_outcome(
    evidence: ParticipantOpacityModelCheckEvidenceModel,
) -> None:
    _validate_model_check_payload_presence(evidence)
    _validate_decided_model_check_outcome(evidence)
    _validate_nonpositive_model_check_outcome(evidence)
    if evidence.counterexample is not None:
        _validate_counterexample_join(evidence)


def _validate_model_check_payload_presence(
    evidence: ParticipantOpacityModelCheckEvidenceModel,
) -> None:
    counterexample_expected = evidence.outcome is ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE
    unsupported_expected = evidence.outcome in {
        ParticipantOpacityModelCheckOutcome.VACUOUS,
        ParticipantOpacityModelCheckOutcome.UNSUPPORTED,
    }
    if (evidence.counterexample is not None) != counterexample_expected:
        raise ValueError("model-check counterexample payload must exactly match the outcome")
    if (evidence.unsupported is not None) != unsupported_expected:
        raise ValueError("model-check unsupported payload must exactly match a non-positive outcome")


def _validate_decided_model_check_outcome(
    evidence: ParticipantOpacityModelCheckEvidenceModel,
) -> None:
    decided = evidence.outcome in {
        ParticipantOpacityModelCheckOutcome.HOLDS,
        ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE,
    }
    if decided and not evidence.coverage.complete_fixed_point:
        raise ValueError("decided model-check outcomes require a complete fixed point")
    if decided and evidence.diagnostics:
        raise ValueError("decided model-check outcomes cannot carry error diagnostics")
    if decided and (
        evidence.coverage.reachable_evaluation_points == 0 or evidence.coverage.reachable_secret_points == 0
    ):
        raise ValueError("decided model-check outcomes require reachable secret evaluation points")


def _validate_nonpositive_model_check_outcome(
    evidence: ParticipantOpacityModelCheckEvidenceModel,
) -> None:
    if (
        evidence.outcome is ParticipantOpacityModelCheckOutcome.VACUOUS
        and evidence.coverage.reachable_secret_points != 0
    ):
        raise ValueError("a vacuous model check requires zero reachable secret points")
    if evidence.unsupported is not None:
        diagnostic_codes = tuple(sorted({item.code for item in evidence.diagnostics}))
        if evidence.unsupported.reason_codes != diagnostic_codes:
            raise ValueError("model-check unsupported reason codes must match diagnostics")


def _validate_counterexample_join(
    evidence: ParticipantOpacityModelCheckEvidenceModel,
) -> None:
    counterexample = evidence.counterexample
    assert counterexample is not None
    if counterexample.actual_state_ordinal >= evidence.coverage.declared.states:
        raise ValueError("model-check counterexample state must reference the declared model")
    if any(
        ordinal >= evidence.coverage.declared.transitions for ordinal in counterexample.actual_path_transition_ordinals
    ):
        raise ValueError("model-check counterexample path must reference declared transitions")
    expected_digest = participant_opacity_model_check_counterexample_digest(
        ParticipantOpacityModelCheckCounterexampleDigestInput(
            safe_ref=counterexample.safe_ref,
            actual_state_ordinal=counterexample.actual_state_ordinal,
            actual_path_transition_ordinals=counterexample.actual_path_transition_ordinals,
            strategy_ref=counterexample.strategy_ref,
            examined_cell_size=counterexample.examined_cell_size,
            model_digest=evidence.model_digest,
            profile_digest=evidence.profile_digest,
            derived_carrier_digest=evidence.derived_carrier_digest,
        )
    )
    if counterexample.counterexample_digest != expected_digest:
        raise ValueError("model-check counterexample digest must bind the safe counterexample")


def participant_opacity_model_check_counterexample_digest(
    digest_input: ParticipantOpacityModelCheckCounterexampleDigestInput,
) -> str:
    """Digest the safe path identity and exact model/profile/carrier joins."""

    return canonical_json_digest(
        {
            "safe_ref": digest_input.safe_ref,
            "actual_state_ordinal": digest_input.actual_state_ordinal,
            "actual_path_transition_ordinals": digest_input.actual_path_transition_ordinals,
            "strategy_ref": digest_input.strategy_ref,
            "examined_cell_size": digest_input.examined_cell_size,
            "model_digest": digest_input.model_digest,
            "profile_digest": digest_input.profile_digest,
            "derived_carrier_digest": digest_input.derived_carrier_digest,
        }
    )


__all__ = (
    "ParticipantOpacityModelCheckConfigurationModel",
    "ParticipantOpacityModelCheckCounterexampleModel",
    "ParticipantOpacityModelCheckCounterexampleDigestInput",
    "ParticipantOpacityModelCheckCoverageModel",
    "ParticipantOpacityModelCheckEvidenceModel",
    "ParticipantOpacityModelCheckOutcome",
    "ParticipantOpacityStrategyCoverageModel",
    "UnsupportedParticipantOpacityModelCheckModel",
    "participant_opacity_model_check_counterexample_digest",
)
