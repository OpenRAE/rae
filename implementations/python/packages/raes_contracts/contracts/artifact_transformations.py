"""Closed portable reports for pure RAES artifact transformations."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import ConfigDict, Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..diagnostics import DiagnosticModel
from ..versions import ARTIFACT_TRANSFORMATION_REPORT_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .schema_invariants import _add_raes_invariant

_REPORT_VALIDATOR = "raes_contracts.contracts.ArtifactTransformationReportModel.model_validate"
OperationProfile = str


class ArtifactTransformationStatus(str, Enum):
    SUCCESS = "success"
    REFUSED = "refused"


class ArtifactTransformationKind(str, Enum):
    SDL_AUTHORING = "sdl-authoring"
    SDL_MATERIALIZATION = "sdl-materialization"
    PORTABLE_CONTRACT = "portable-contract"


class TransformationCheckOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not-applicable"


class PreservationOutcome(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    NOT_APPLICABLE = "not-applicable"


class ArtifactTransformationLossKind(str, Enum):
    DECLARATION_REMOVED = "declaration-removed"
    SEMANTIC_OMISSION = "semantic-omission"


class ArtifactTransformationCheckModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)
    outcome: TransformationCheckOutcome
    diagnostic_codes: tuple[str, ...] = ()

    @field_validator("diagnostic_codes")
    @classmethod
    def _validate_diagnostic_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("transformation check diagnostic_codes must be sorted and unique")
        return value


class ArtifactTransformationIdentityMapModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    declaration_kind: NonEmptyString
    before: NonEmptyString
    after: NonEmptyString


class ArtifactTransformationPreservationModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: NonEmptyString
    outcome: PreservationOutcome
    evidence_digests: tuple[PrefixedDigestString, ...] = ()
    limitations: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def _validate_evidence(self) -> ArtifactTransformationPreservationModel:
        if self.outcome == PreservationOutcome.VERIFIED and not self.evidence_digests:
            raise ValueError("verified preservation requires evidence_digests")
        if self.evidence_digests != tuple(sorted(set(self.evidence_digests))):
            raise ValueError("preservation evidence_digests must be sorted and unique")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("preservation limitations must be sorted and unique")
        return self


class ArtifactTransformationLossModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ArtifactTransformationLossKind
    affected_identity: NonEmptyString
    diagnostic: DiagnosticModel


class ArtifactTransformationReportModel(ContractModel):
    """Deterministic all-or-none report for one semantic operation."""

    model_config = ConfigDict(
        title="RAES Artifact Transformation Report v1",
        extra="forbid",
        frozen=True,
    )

    schema_version: Literal[ARTIFACT_TRANSFORMATION_REPORT_SCHEMA_VERSION] = (
        ARTIFACT_TRANSFORMATION_REPORT_SCHEMA_VERSION
    )
    operation_profile: str = Field(
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*/v[1-9][0-9]*$",
        max_length=128,
    )
    status: ArtifactTransformationStatus
    artifact_kind: ArtifactTransformationKind
    source_profile: NonEmptyString
    target_profile: NonEmptyString
    canonicalization_profile: NonEmptyString
    source_digest: PrefixedDigestString
    target_digest: PrefixedDigestString | None = None
    policy_digest: PrefixedDigestString
    derivation_digest: PrefixedDigestString
    preconditions: tuple[ArtifactTransformationCheckModel, ...] = Field(min_length=1)
    postconditions: tuple[ArtifactTransformationCheckModel, ...] = ()
    affected_identities: tuple[NonEmptyString, ...] = ()
    identity_map: tuple[ArtifactTransformationIdentityMapModel, ...] = ()
    preservation: ArtifactTransformationPreservationModel
    losses: tuple[ArtifactTransformationLossModel, ...] = ()
    diagnostics: tuple[DiagnosticModel, ...] = ()

    def _validate_status_shape(self) -> None:
        if self.status == ArtifactTransformationStatus.SUCCESS:
            if self.target_digest is None:
                raise ValueError("successful transformation requires target_digest")
            if self.preservation.outcome == PreservationOutcome.FAILED:
                raise ValueError("successful transformation cannot report failed preservation")
        else:
            if self.target_digest is not None:
                raise ValueError("refused transformation must not expose target_digest")
            if not self.diagnostics:
                raise ValueError("refused transformation requires diagnostics")

    def _validate_identity_ordering(self) -> None:
        if self.affected_identities != tuple(sorted(set(self.affected_identities))):
            raise ValueError("affected_identities must be sorted and unique")
        identity_order = tuple((item.before, item.after, item.declaration_kind) for item in self.identity_map)
        if identity_order != tuple(sorted(set(identity_order))):
            raise ValueError("identity_map must be sorted and unique")
        loss_order = tuple((item.kind.value, item.affected_identity) for item in self.losses)
        if loss_order != tuple(sorted(set(loss_order))):
            raise ValueError("losses must be sorted and unique")

    def _validate_check_ordering(self) -> None:
        for checks, label in ((self.preconditions, "preconditions"), (self.postconditions, "postconditions")):
            check_ids = tuple(check.check_id for check in checks)
            if check_ids != tuple(sorted(set(check_ids))):
                raise ValueError(f"{label} must be sorted and unique by check_id")

    def _validate_diagnostic_ordering(self) -> None:
        diagnostic_order = tuple(
            (item.code, item.address, item.severity.value, item.message) for item in self.diagnostics
        )
        if diagnostic_order != tuple(sorted(set(diagnostic_order))):
            raise ValueError("diagnostics must be sorted and unique")

    @model_validator(mode="after")
    def _validate_result_shape(self) -> ArtifactTransformationReportModel:
        self._validate_status_shape()
        self._validate_identity_ordering()
        self._validate_check_ordering()
        self._validate_diagnostic_ordering()
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"status": {"const": "success"}}, "required": ["status"]},
                    "then": {
                        "required": ["target_digest"],
                        "properties": {"target_digest": {"type": "string"}},
                    },
                },
                {
                    "if": {"properties": {"status": {"const": "refused"}}, "required": ["status"]},
                    "then": {
                        "properties": {
                            "target_digest": {"type": "null"},
                            "diagnostics": {"minItems": 1},
                        }
                    },
                },
            ]
        )
        _add_raes_invariant(
            json_schema,
            "artifact-transformation-all-or-none",
            "Success carries a complete target digest; refusal carries no target and at least one bounded diagnostic.",
            validator=_REPORT_VALIDATOR,
            inputs=[{"contract_id": "artifact-transformation-report-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "artifact-transformation-deterministic-order",
            "Checks, identities, mappings, losses, diagnostics, and evidence use stable closed ordering.",
            validator=_REPORT_VALIDATOR,
            inputs=[{"contract_id": "artifact-transformation-report-v1", "instance_path": "#"}],
        )
        return json_schema


__all__ = [
    "ArtifactTransformationCheckModel",
    "ArtifactTransformationIdentityMapModel",
    "ArtifactTransformationKind",
    "ArtifactTransformationLossKind",
    "ArtifactTransformationLossModel",
    "ArtifactTransformationPreservationModel",
    "ArtifactTransformationReportModel",
    "ArtifactTransformationStatus",
    "PreservationOutcome",
    "TransformationCheckOutcome",
]
