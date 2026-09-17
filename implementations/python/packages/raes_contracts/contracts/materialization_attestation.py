"""Typed run-archive reference for post-materialization SDL descriptions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from raes_contracts.materialization import MaterializationSource

from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .experiment_artifacts import ExperimentArtifactRefModel
from .experiment_references import ExperimentReferenceModel

if TYPE_CHECKING:
    from .experiment_run import ExperimentRunModel


class MaterializationPlanModel(ContractModel):
    """Phase-independent descriptive purpose and authenticated source context."""

    purpose: Literal["execution", "inspection"] = Field(
        default="execution", exclude_if=lambda value: value == "execution"
    )
    materialization_source: MaterializationSource | None = Field(default=None, exclude_if=lambda value: value is None)
    augmentation_scope_required: bool = Field(default=False, strict=True, exclude_if=lambda value: not value)
    operation_id: NonEmptyString | None = Field(default=None, exclude_if=lambda value: value is None)


class MaterializationAttestationReferenceModel(ExperimentReferenceModel):
    """A descriptive artifact identity, never the original scenario snapshot."""

    ref_kind: Literal["materialization-attestation"] = "materialization-attestation"
    ref_version: Literal["raes-sdl-materialized/v1"] = "raes-sdl-materialized/v1"
    ref_digest: PrefixedDigestString
    ref_path: NonEmptyString


class MaterializationArchiveRecord(ContractModel):
    """Published protected bytes and their distinct semantic identity."""

    reference: MaterializationAttestationReferenceModel
    artifact: ExperimentArtifactRefModel
    run_id: NonEmptyString
    operation_id: NonEmptyString

    @model_validator(mode="after")
    def _validate_archive_join(self) -> MaterializationArchiveRecord:
        if (
            self.artifact.role != "materialization-attestation"
            or self.reference.ref_id != self.artifact.artifact_id
            or self.artifact.uri != f"urn:sha256:{self.artifact.checksum.value}"
            or self.artifact.checksum.algorithm != "sha256"
            or self.artifact.media_type != "application/vnd.raes.sdl+yaml"
            or self.artifact.sensitivity not in {"restricted", "redacted"}
        ):
            raise ValueError("materialization artifact reference does not bind the protected SDL artifact")
        return self


def validate_run_materializations(run: ExperimentRunModel) -> None:
    """Bind descriptive carriers to the run's actual archived artifact records."""
    from raes_contracts.materialization import require_materialization_records

    require_materialization_records(tuple(run.materialization_attestations))
    if any(record.run_id != run.run_id for record in run.materialization_attestations):
        raise ValueError("materialization attestation belongs to a different run")
    archived = {record.reference.model_dump_json(exclude_none=True) for record in run.materialization_attestations}
    for disclosure in run.augmentation_disclosures:
        for reference in disclosure.carrier_refs:
            if reference.ref_kind == "materialization-attestation":
                typed = MaterializationAttestationReferenceModel.model_validate(reference.model_dump(mode="json"))
                if typed.model_dump_json(exclude_none=True) not in archived:
                    raise ValueError("materialization carrier must bind an archived run artifact")


def attach_materialization_invariants(contract_id: str, schema: dict[str, Any]) -> None:
    """Disclose the context-dependent checks that schema shape alone cannot prove."""
    from .schema_invariants import _add_raes_invariant

    invariants = {
        "materialized-scenario-v1": (
            "materialized-sdl-source-and-inventory-binding",
            "Complete origins, source/plan/predecessor/producer identity and realized inventory require "
            "the admitted source and execution context; descriptive admission grants no execution authority.",
            "raes_processor.planner.admit_materialization_submission",
        ),
        "backend-materialization-attestation-v1": (
            "backend-materialization-submission-admission",
            "SDL bytes require bounded parsing and semantic, original-authority, complete inventory "
            "and execution-context validation after materialization hooks.",
            "raes_processor.planner.admit_materialization_submission",
        ),
        "materialization-archive-record-v1": (
            "materialization-archive-byte-and-lineage-binding",
            "The typed record must join protected immutable published SDL bytes to their size, checksum, "
            "semantic identity, run and operation; metadata alone does not prove delivery.",
            "raes_processor.planner.validate_materialization_archive_record",
        ),
        "experiment-run-v1": (
            "run-materialization-carriers-archived",
            "Materialization records belong to this run and materialization disclosure carriers bind "
            "exactly one archived record; the original scenario snapshot reference is not replaced.",
            "raes_contracts.contracts.materialization_attestation.validate_run_materializations",
        ),
    }
    if contract_id in invariants:
        identity, description, validator = invariants[contract_id]
        _add_raes_invariant(
            schema,
            identity,
            description,
            validator=validator,
            inputs=[{"contract_id": contract_id, "instance_path": "#"}],
        )
