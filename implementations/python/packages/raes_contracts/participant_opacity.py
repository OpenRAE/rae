"""Portable contracts for bounded participant-predicate opacity analysis."""

from __future__ import annotations

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
    MAX_OPACITY_POINTS,
    MODEL_CHECK_PROVENANCE_NONCLAIM,
    NORMALIZED_INPUT_PROVENANCE_NONCLAIM,
    Revision,
    SafeKey,
    SafeRef,
)
from ._participant_opacity_model import (
    ParticipantOpacityModelAssumptionsModel,
    ParticipantOpacityModelCheckDeclaredCountsModel,
    ParticipantOpacityModelCheckInputModel,
    ParticipantOpacityModelStateModel,
    ParticipantOpacityModelTransitionModel,
)
from ._participant_opacity_model_check import (
    ParticipantOpacityModelCheckConfigurationModel,
    ParticipantOpacityModelCheckCounterexampleDigestInput,
    ParticipantOpacityModelCheckCounterexampleModel,
    ParticipantOpacityModelCheckCoverageModel,
    ParticipantOpacityModelCheckEvidenceModel,
    ParticipantOpacityModelCheckOutcome,
    ParticipantOpacityStrategyCoverageModel,
    UnsupportedParticipantOpacityModelCheckModel,
    participant_opacity_model_check_counterexample_digest,
)
from .canonical import canonical_json_digest
from .diagnostics import DiagnosticModel
from .versions import (
    PARTICIPANT_OPACITY_ANALYSIS_EVIDENCE_SCHEMA_VERSION,
    PARTICIPANT_OPACITY_ANALYSIS_INPUT_SCHEMA_VERSION,
)


class ParticipantOpacityOutcome(str, Enum):
    """Closed bounded-analysis outcomes."""

    NO_COUNTEREXAMPLE = "no-counterexample-within-declared-finite-bounds"
    COUNTEREXAMPLE = "counterexample-found"
    VACUOUS = "vacuous-secret-domain"
    UNSUPPORTED = "unsupported"


class ParticipantOpacityDeclaredCountsModel(ContractModel):
    """Exact realized cardinalities of every finite quantified coordinate."""

    points: int = Field(ge=1, le=MAX_OPACITY_POINTS)
    runs: int = Field(ge=1, le=MAX_OPACITY_POINTS)
    cuts: int = Field(ge=1, le=MAX_OPACITY_POINTS)
    strategies: int = Field(ge=1, le=MAX_OPACITY_POINTS)
    scheduler_environment_pairs: int = Field(ge=1, le=MAX_OPACITY_POINTS)
    order_variants: int = Field(ge=1, le=MAX_OPACITY_POINTS)


class OpacityPossiblePointModel(ContractModel):
    """One safe abstract point in a complete declared finite carrier."""

    ordinal: int = Field(ge=0, le=MAX_OPACITY_POINTS - 1)
    point_ref: SafeRef
    run_ref: SafeRef
    cut_ref: SafeRef
    strategy_ref: SafeRef
    scheduler_ref: SafeRef
    environment_ref: SafeRef
    order_ref: SafeRef
    reachable: bool
    secret_holds: bool
    initial_information_key: SafeKey
    observation_key: SafeKey
    memory_key: SafeKey
    release_state_key: SafeKey
    coalition_fusion_key: SafeKey | None = None


class ParticipantOpacityAnalysisInputModel(ContractModel):
    """Normalized finite carrier supplied by a trusted materializer."""

    schema_version: Literal[PARTICIPANT_OPACITY_ANALYSIS_INPUT_SCHEMA_VERSION] = (
        PARTICIPANT_OPACITY_ANALYSIS_INPUT_SCHEMA_VERSION
    )
    analysis_profile: Literal["raes-participant-opacity-bounded-test/v1"]
    source: SourceArtifactIdentityModel
    profile_id: SafeRef
    profile_revision: Revision
    profile_digest: PrefixedDigestString
    normalized_model_ref: SafeRef
    materializer_id: SafeRef
    materializer_version: Revision
    materializer_digest: PrefixedDigestString
    complete_enumeration: bool
    declared_counts: ParticipantOpacityDeclaredCountsModel
    claim: BehavioralClaimBindingModel
    points: tuple[OpacityPossiblePointModel, ...] = Field(
        min_length=1,
        max_length=MAX_OPACITY_POINTS,
    )

    @model_validator(mode="after")
    def _validate_finite_carrier(
        self,
    ) -> ParticipantOpacityAnalysisInputModel:
        ordinals = [point.ordinal for point in self.points]
        point_refs = [point.point_ref for point in self.points]
        if len(ordinals) != len(set(ordinals)) or set(ordinals) != set(range(len(self.points))):
            raise ValueError("point ordinals must uniquely and contiguously cover the point count")
        if len(point_refs) != len(set(point_refs)):
            raise ValueError("possible point refs must be unique")
        realized = {
            "points": len(self.points),
            "runs": len({point.run_ref for point in self.points}),
            "cuts": len({point.cut_ref for point in self.points}),
            "strategies": len({point.strategy_ref for point in self.points}),
            "scheduler_environment_pairs": len({(point.scheduler_ref, point.environment_ref) for point in self.points}),
            "order_variants": len({point.order_ref for point in self.points}),
        }
        declared = self.declared_counts.model_dump(mode="python")
        if realized != declared:
            raise ValueError("declared finite counts must exactly match the realized carrier count")
        return self

    def canonicalized(self) -> ParticipantOpacityAnalysisInputModel:
        """Return a canonical point ordering without changing carrier meaning."""

        ordered = tuple(sorted(self.points, key=lambda point: point.ordinal))
        if ordered == self.points:
            return self
        return self.model_copy(update={"points": ordered})

    @property
    def canonical_digest(self) -> str:
        """Digest the canonicalized finite carrier and all joined identities."""

        return canonical_json_digest(self.canonicalized().model_dump(mode="json"))


class ParticipantOpacityCheckerConfigurationModel(ContractModel):
    """Complete output-affecting identity of the bounded checker."""

    profile: Literal["raes-participant-opacity-checker/v1"]
    tool_id: Literal["raes-processor-participant-opacity"]
    tool_version: Literal["1.0.0"]
    algorithm: Literal["exhaustive-information-cell-scan/v1"]
    information_cell_key: Literal["initial-observation-memory-release-coalition-strategy-order/v1"]
    counterexample_selection: Literal["lowest-canonical-ordinal/v1"]
    max_points: Literal[4096]

    @property
    def canonical_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class ParticipantOpacityCounterexampleModel(ContractModel):
    """Sanitized reference to one canonical secret-only information cell."""

    safe_ref: Annotated[
        str,
        Field(pattern=r"^participant-opacity-counterexample:[0-9]{6}$"),
    ]
    counterexample_digest: PrefixedDigestString
    actual_point_ordinal: int = Field(ge=0, le=MAX_OPACITY_POINTS - 1)
    examined_cell_size: int = Field(ge=1, le=MAX_OPACITY_POINTS)


class UnsupportedParticipantOpacityAnalysisModel(ContractModel):
    """Stable fail-closed reason set for a valid but non-positive analysis."""

    profile: Literal["raes-participant-opacity-unsupported/v1"]
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_reasons(
        self,
    ) -> UnsupportedParticipantOpacityAnalysisModel:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("unsupported reason codes must be unique and sorted")
        return self


class ParticipantOpacityAnalysisEvidenceModel(ContractModel):
    """Digest-bound bounded result with no raw possible-point contents."""

    schema_version: Literal[PARTICIPANT_OPACITY_ANALYSIS_EVIDENCE_SCHEMA_VERSION] = (
        PARTICIPANT_OPACITY_ANALYSIS_EVIDENCE_SCHEMA_VERSION
    )
    analysis_profile: Literal["raes-participant-opacity-bounded-test/v1"]
    provenance_scope: Literal["normalized-input-only"]
    taxonomy_id: Literal["raes-behavioral-relations"]
    taxonomy_revision: Revision
    relation_id: Literal["participant-predicate-opacity"]
    profile_id: SafeRef
    profile_revision: Revision
    profile_digest: PrefixedDigestString
    normalized_model_ref: SafeRef
    normalized_model_digest: PrefixedDigestString
    checker_configuration: ParticipantOpacityCheckerConfigurationModel
    checker_configuration_digest: PrefixedDigestString
    claim: BehavioralClaimBindingModel
    outcome: ParticipantOpacityOutcome
    checked_points: int = Field(ge=0, le=MAX_OPACITY_POINTS)
    checked_secret_points: int = Field(ge=0, le=MAX_OPACITY_POINTS)
    diagnostics: tuple[DiagnosticModel, ...] = Field(max_length=MAX_OPACITY_DIAGNOSTICS)
    counterexample: ParticipantOpacityCounterexampleModel | None = None
    unsupported: UnsupportedParticipantOpacityAnalysisModel | None = None

    @model_validator(mode="after")
    def _validate_evidence_join(
        self,
    ) -> ParticipantOpacityAnalysisEvidenceModel:
        _validate_evidence_counts(self)
        _validate_checker_configuration_join(self)
        _validate_outcome_payloads(self)
        _validate_claim_join(self)
        return self


def _validate_evidence_counts(evidence: ParticipantOpacityAnalysisEvidenceModel) -> None:
    if evidence.checked_secret_points > evidence.checked_points:
        raise ValueError("checked secret points cannot exceed checked points")
    decided = evidence.outcome in {
        ParticipantOpacityOutcome.NO_COUNTEREXAMPLE,
        ParticipantOpacityOutcome.COUNTEREXAMPLE,
    }
    if decided and (evidence.checked_points == 0 or evidence.checked_secret_points == 0):
        raise ValueError("decided outcomes require nonzero checked and secret point counts")
    if decided and evidence.diagnostics:
        raise ValueError("decided outcomes cannot carry error diagnostics")
    if evidence.outcome is ParticipantOpacityOutcome.VACUOUS and evidence.checked_secret_points != 0:
        raise ValueError("a vacuous secret domain requires zero checked secret points")


def _validate_checker_configuration_join(evidence: ParticipantOpacityAnalysisEvidenceModel) -> None:
    if evidence.checker_configuration_digest != evidence.checker_configuration.canonical_digest:
        raise ValueError("checker_configuration_digest must bind the checker configuration")


def _validate_outcome_payloads(evidence: ParticipantOpacityAnalysisEvidenceModel) -> None:
    expected_counterexample = evidence.outcome is ParticipantOpacityOutcome.COUNTEREXAMPLE
    expected_unsupported = evidence.outcome in {
        ParticipantOpacityOutcome.VACUOUS,
        ParticipantOpacityOutcome.UNSUPPORTED,
    }
    if (evidence.counterexample is not None) != expected_counterexample:
        raise ValueError("counterexample payload must exactly match the counterexample outcome")
    if evidence.counterexample is not None:
        _validate_counterexample_join(evidence)
    if (evidence.unsupported is not None) != expected_unsupported:
        raise ValueError("unsupported payload must exactly match a non-positive unsupported outcome")
    if evidence.unsupported is not None:
        _validate_unsupported_join(evidence)


def _validate_counterexample_join(evidence: ParticipantOpacityAnalysisEvidenceModel) -> None:
    counterexample = evidence.counterexample
    if counterexample is None:
        raise ValueError("counterexample outcome requires a counterexample payload")
    expected_digest = participant_opacity_counterexample_digest(
        safe_ref=counterexample.safe_ref,
        actual_point_ordinal=counterexample.actual_point_ordinal,
        examined_cell_size=counterexample.examined_cell_size,
        normalized_model_digest=evidence.normalized_model_digest,
    )
    if counterexample.counterexample_digest != expected_digest:
        raise ValueError("counterexample_digest must bind the sanitized counterexample identity")


def _validate_unsupported_join(evidence: ParticipantOpacityAnalysisEvidenceModel) -> None:
    unsupported = evidence.unsupported
    if unsupported is None:
        raise ValueError("unsupported outcome requires an unsupported payload")
    diagnostic_codes = tuple(sorted({diagnostic.code for diagnostic in evidence.diagnostics}))
    if unsupported.reason_codes != diagnostic_codes:
        raise ValueError("unsupported reason codes must match evidence diagnostics")


def _validate_claim_join(evidence: ParticipantOpacityAnalysisEvidenceModel) -> None:
    claim = evidence.claim
    if claim.taxonomy_id != evidence.taxonomy_id:
        raise ValueError("evidence claim taxonomy id must match the evidence")
    if claim.taxonomy_revision != evidence.taxonomy_revision:
        raise ValueError("evidence claim taxonomy revision must match the evidence")
    if claim.relation_id != evidence.relation_id:
        raise ValueError("evidence claim relation must match the evidence")
    if claim.relation_parameter_profile_ref != evidence.profile_id:
        raise ValueError("evidence claim profile id must match the evidence")
    if claim.relation_parameter_profile_revision != evidence.profile_revision:
        raise ValueError("evidence claim profile revision must match the evidence")
    _validate_claim_scope(claim)


def _validate_claim_scope(claim: BehavioralClaimBindingModel) -> None:
    if (
        claim.assurance_axis,
        claim.assurance_status,
        claim.evidence_scope,
        claim.quantifier_scope,
    ) != ("bounded-test", "tested", "finite", "finite-cases"):
        raise ValueError("opacity evidence claim must remain bounded-test/tested/finite/finite-cases")
    if NORMALIZED_INPUT_PROVENANCE_NONCLAIM not in claim.explicit_non_claims:
        raise ValueError("normalized-input evidence must disclaim source and materializer authenticity")


def participant_opacity_counterexample_digest(
    *,
    safe_ref: str,
    actual_point_ordinal: int,
    examined_cell_size: int,
    normalized_model_digest: str,
) -> str:
    """Digest only the sanitized counterexample identity and model join."""

    return canonical_json_digest(
        {
            "safe_ref": safe_ref,
            "actual_point_ordinal": actual_point_ordinal,
            "examined_cell_size": examined_cell_size,
            "normalized_model_digest": normalized_model_digest,
        }
    )


__all__ = [
    "MAX_OPACITY_POINTS",
    "MAX_OPACITY_MODEL_STATES",
    "MAX_OPACITY_MODEL_TRANSITIONS",
    "MODEL_CHECK_PROVENANCE_NONCLAIM",
    "NORMALIZED_INPUT_PROVENANCE_NONCLAIM",
    "OpacityPossiblePointModel",
    "ParticipantOpacityAnalysisEvidenceModel",
    "ParticipantOpacityAnalysisInputModel",
    "ParticipantOpacityCheckerConfigurationModel",
    "ParticipantOpacityCounterexampleModel",
    "ParticipantOpacityDeclaredCountsModel",
    "ParticipantOpacityOutcome",
    "ParticipantOpacityModelAssumptionsModel",
    "ParticipantOpacityModelCheckConfigurationModel",
    "ParticipantOpacityModelCheckCounterexampleDigestInput",
    "ParticipantOpacityModelCheckCounterexampleModel",
    "ParticipantOpacityModelCheckCoverageModel",
    "ParticipantOpacityModelCheckDeclaredCountsModel",
    "ParticipantOpacityModelCheckEvidenceModel",
    "ParticipantOpacityModelCheckInputModel",
    "ParticipantOpacityModelCheckOutcome",
    "ParticipantOpacityModelStateModel",
    "ParticipantOpacityModelTransitionModel",
    "ParticipantOpacityStrategyCoverageModel",
    "UnsupportedParticipantOpacityAnalysisModel",
    "UnsupportedParticipantOpacityModelCheckModel",
    "participant_opacity_counterexample_digest",
    "participant_opacity_model_check_counterexample_digest",
]
