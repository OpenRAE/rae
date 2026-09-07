"""Trusted evidence assembly for bounded repeatability-consistency (ASR-514).

The assembler admits a baseline run and one repetition run of the same
held-fixed subject, invokes the digest-pinned, capability-checked validator to
derive each side's projected outcome and the variation, reset, and cleanup
dispositions, resolves every projected observation and verification fact through
the exact run traceability, and seals the comparison evidence. It performs no
execution, scheduling, replay, canonicalization of runs, secret access, or
persistence.

Trust boundary: this is a trusted-composition-only surface. The runs are
digest-verified (``run_digest`` equals the run's canonical digest), so the set
of evidence-record identities that belong to each run is fixed by that verified
digest; an evidence reference is admitted only when it is a member of the
admitted run's declared evidence set. The experiment-run traceability model does
not admit per-evidence content digests, and this comparator adds no evidence
store, so content authenticity of an individual evidence record remains owned by
the platform evidence provenance and resolution layer that supplies the records
to this trusted composition.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from raes_contracts.contracts import (
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentTaskModel,
    validate_experiment_run_against_task,
)
from raes_contracts.satisfiability import canonical_contract_digest, canonical_json_digest

from .repeatability_types import (
    RepeatabilityConsistencyEvidence,
    RepetitionProjection,
    _new_repeatability_consistency_evidence,
    _RepeatabilityConsistencyEvidenceParts,
)
from .repeatability_validation import RepeatabilityConsistencyCase, RepetitionRef
from .verification_authority import (
    VerificationBinding,
    VerificationDisposition,
    VerificationRecordIdentity,
)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_unique_text(values: tuple[str, ...], field_name: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field_name} entries must be non-empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} entries must be unique")


def _validate_record_header(
    record: VariationVerificationRecord | ResetVerificationRecord | CleanupVerificationRecord,
) -> None:
    _require_text(record.record_id, "record_id")
    _require_text(record.record_version, "record_version")
    _require_unique_text(record.evidence_record_refs, "evidence_record_refs")
    if not record.evidence_record_refs:
        raise ValueError("evidence_record_refs must not be empty")


@dataclass(frozen=True)
class VariationVerificationRecord:
    """Run-bound inputs from which an admitted adapter verifies variation."""

    record_id: str
    record_version: str
    pair_run_refs: tuple[str, ...]
    policy_id: str
    policy_version: str
    observed_variation_refs: tuple[str, ...]
    evidence_record_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_record_header(self)
        for field_name in ("policy_id", "policy_version"):
            _require_text(getattr(self, field_name), field_name)
        _require_unique_text(self.pair_run_refs, "pair_run_refs")
        _require_unique_text(self.observed_variation_refs, "observed_variation_refs")


@dataclass(frozen=True)
class ResetVerificationRecord:
    """Run-bound inputs from which an admitted adapter verifies reset/isolation."""

    record_id: str
    record_version: str
    pair_run_refs: tuple[str, ...]
    evidence_record_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_record_header(self)
        _require_unique_text(self.pair_run_refs, "pair_run_refs")


@dataclass(frozen=True)
class CleanupVerificationRecord:
    """Run-bound inputs from which an admitted adapter verifies cleanup."""

    record_id: str
    record_version: str
    subject_ref: str
    residual_state: tuple[str, ...]
    evidence_record_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_record_header(self)
        _require_text(self.subject_ref, "subject_ref")
        _require_unique_text(self.residual_state, "residual_state")


@dataclass(frozen=True)
class RepeatabilityRunInput:
    """One admitted run and its typed task, labelled by its repetition id."""

    repetition_id: str
    task: ExperimentTaskModel
    run: ExperimentRunModel
    evidence: ExperimentRunEvidenceInputs | None = None


@dataclass(frozen=True)
class RepeatabilityRunPair:
    """The typed baseline and repetition task/run inputs for one comparison."""

    baseline: RepeatabilityRunInput
    repetition: RepeatabilityRunInput


@dataclass(frozen=True)
class RepeatabilityVerificationRecords:
    """The three pair-bound verification inputs for one comparison."""

    variation: VariationVerificationRecord
    reset: ResetVerificationRecord
    cleanup: CleanupVerificationRecord

    def as_tuple(
        self,
    ) -> tuple[VariationVerificationRecord, ResetVerificationRecord, CleanupVerificationRecord]:
        """Return the records in canonical comparison order."""

        return (self.variation, self.reset, self.cleanup)


class RepeatabilityEvidenceValidator(Protocol):
    """Host-owned adapter admitted by the case's exact executable binding."""

    binding: VerificationBinding

    def project_outcome(
        self,
        *,
        role: str,
        case: RepeatabilityConsistencyCase,
        run: ExperimentRunModel,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> RepetitionProjection: ...

    def verify_variation(
        self,
        *,
        case: RepeatabilityConsistencyCase,
        record: VariationVerificationRecord,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> VerificationDisposition: ...

    def verify_reset(
        self,
        *,
        case: RepeatabilityConsistencyCase,
        record: ResetVerificationRecord,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> VerificationDisposition: ...

    def verify_cleanup(
        self,
        *,
        case: RepeatabilityConsistencyCase,
        record: CleanupVerificationRecord,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> VerificationDisposition: ...


def _run_ref(run: ExperimentRunModel) -> str:
    return f"experiment-run:{run.run_id}@{run.run_version}"


def _snapshot_ref(run: ExperimentRunModel) -> str:
    snapshot = run.scenario_snapshot_ref
    return f"scenario-snapshot:{snapshot.ref_id}@{snapshot.ref_version}"


def _validate_side(
    role: str,
    rep: RepetitionRef,
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    evidence: ExperimentRunEvidenceInputs | None,
) -> None:
    try:
        validate_experiment_run_against_task(task, run, evidence=evidence)
    except ValueError as exc:
        raise ValueError(f"{role} task/run validation failed") from exc
    snapshot = run.scenario_snapshot_ref
    if (
        rep.run_ref != _run_ref(run)
        or rep.run_digest != canonical_contract_digest(run)
        or rep.subject_ref != _snapshot_ref(run)
        or rep.subject_digest != snapshot.ref_digest
    ):
        raise ValueError(f"{role} does not match the validated task, run, and scenario snapshot")


def _run_evidence_index(run: ExperimentRunModel) -> set[tuple[str, str | None]]:
    return {(reference.ref_id, reference.ref_version) for reference in run.traceability.evidence_record_refs}


def _record_matches_run(record: ExperimentEvidenceRecordModel, run: ExperimentRunModel) -> bool:
    return (
        record.run_ref.ref_kind == "run"
        and record.run_ref.ref_id == run.run_id
        and record.run_ref.ref_version == run.run_version
        and (record.evidence_record_id, record.record_version) in _run_evidence_index(run)
    )


def _validate_evidence_refs(
    label: str,
    refs: tuple[str, ...],
    runs: tuple[ExperimentRunModel, ...],
    evidence_by_id: dict[str, ExperimentEvidenceRecordModel],
) -> None:
    for evidence_ref in refs:
        record = evidence_by_id.get(evidence_ref)
        if record is None or not any(_record_matches_run(record, run) for run in runs):
            raise ValueError(f"{label} evidence must resolve through an admitted run traceability")


def _validate_verification_joins(
    case: RepeatabilityConsistencyCase,
    records: RepeatabilityVerificationRecords,
    pair_run_refs: frozenset[str],
) -> None:
    variation, reset, cleanup = records.as_tuple()
    if (variation.policy_id, variation.policy_version) != (
        case.variation_policy.policy_id,
        case.variation_policy.policy_version,
    ):
        raise ValueError("variation verification does not match the admitted variation policy")
    if frozenset(variation.pair_run_refs) != pair_run_refs:
        raise ValueError("variation verification does not cover the admitted pair")
    if frozenset(reset.pair_run_refs) != pair_run_refs:
        raise ValueError("reset verification does not cover the admitted pair")
    if cleanup.subject_ref != case.subject_ref:
        raise ValueError("cleanup verification does not match the admitted subject")


def _record_digest(
    record: VariationVerificationRecord | ResetVerificationRecord | CleanupVerificationRecord,
) -> str:
    return canonical_json_digest({"record_kind": type(record).__name__, **asdict(record)})


def _identity(
    record: VariationVerificationRecord | ResetVerificationRecord | CleanupVerificationRecord,
    binding: VerificationBinding,
) -> VerificationRecordIdentity:
    return VerificationRecordIdentity(
        record_id=record.record_id,
        record_version=record.record_version,
        record_digest=_record_digest(record),
        producer_id=binding.producer_id,
        producer_version=binding.producer_version,
        producer_digest=binding.producer_digest,
        validator_id=binding.validator_id,
        validator_version=binding.validator_version,
        validator_digest=binding.validator_digest,
    )


def _project(
    role: str,
    rep: RepetitionRef,
    run: ExperimentRunModel,
    validator: RepeatabilityEvidenceValidator,
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    case: RepeatabilityConsistencyCase,
    evidence_by_id: dict[str, ExperimentEvidenceRecordModel],
) -> RepetitionProjection:
    projection = validator.project_outcome(role=role, case=case, run=run, evidence_records=evidence_records)
    if not isinstance(projection, RepetitionProjection):
        raise ValueError("validator must derive typed RepetitionProjection values")
    if projection.run_ref != rep.run_ref:
        raise ValueError(f"{role} projection does not identify its admitted run")
    _validate_evidence_refs(f"{role} projection", projection.evidence_refs, (run,), evidence_by_id)
    return projection


def assemble_repeatability_consistency_evidence(
    case: RepeatabilityConsistencyCase,
    *,
    runs: RepeatabilityRunPair,
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    verification_records: RepeatabilityVerificationRecords,
    validator: RepeatabilityEvidenceValidator,
) -> RepeatabilityConsistencyEvidence:
    """Invoke the admitted adapter and assemble evidence after every join passes."""

    if (
        runs.baseline.repetition_id != case.baseline.repetition_id
        or runs.repetition.repetition_id != case.repetition.repetition_id
    ):
        raise ValueError("run pair repetition ids must match the admitted case baseline and repetition")
    _validate_side("baseline", case.baseline, runs.baseline.task, runs.baseline.run, runs.baseline.evidence)
    _validate_side("repetition", case.repetition, runs.repetition.task, runs.repetition.run, runs.repetition.evidence)

    binding = getattr(validator, "binding", None)
    if not isinstance(binding, VerificationBinding) or binding != case.verification_authority:
        raise ValueError("validator binding does not match the authority admitted by the case")

    evidence_by_id = {record.evidence_record_id: record for record in evidence_records}
    if len(evidence_by_id) != len(evidence_records):
        raise ValueError("evidence_records must use unique evidence_record_id values")

    baseline_projection = _project(
        "baseline", case.baseline, runs.baseline.run, validator, evidence_records, case, evidence_by_id
    )
    repetition_projection = _project(
        "repetition", case.repetition, runs.repetition.run, validator, evidence_records, case, evidence_by_id
    )

    pair_runs = (runs.baseline.run, runs.repetition.run)
    pair_run_refs = frozenset((case.baseline.run_ref, case.repetition.run_ref))
    _validate_verification_joins(case, verification_records, pair_run_refs)
    for label, record in zip(
        ("variation verification", "reset verification", "cleanup verification"),
        verification_records.as_tuple(),
        strict=True,
    ):
        _validate_evidence_refs(label, record.evidence_record_refs, pair_runs, evidence_by_id)

    variation_disposition = validator.verify_variation(
        case=case, record=verification_records.variation, evidence_records=evidence_records
    )
    reset_disposition = validator.verify_reset(
        case=case, record=verification_records.reset, evidence_records=evidence_records
    )
    cleanup_disposition = validator.verify_cleanup(
        case=case, record=verification_records.cleanup, evidence_records=evidence_records
    )
    dispositions = (variation_disposition, reset_disposition, cleanup_disposition)
    if any(not isinstance(disposition, VerificationDisposition) for disposition in dispositions):
        raise ValueError("validator methods must return VerificationDisposition values")

    permitted = set(case.variation_policy.permitted_variation_refs)
    observed = set(verification_records.variation.observed_variation_refs)
    unmatched = tuple(sorted(observed - permitted))
    records = verification_records.as_tuple()
    record_ids = [record.record_id for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("verification records must use unique record_id values")
    return _new_repeatability_consistency_evidence(
        _RepeatabilityConsistencyEvidenceParts(
            case_digest=case.digest,
            baseline_artifact_ref=case.baseline.projected_artifact_ref,
            baseline_projection=baseline_projection,
            repetition_artifact_ref=case.repetition.projected_artifact_ref,
            repetition_projection=repetition_projection,
            variation_disposition=variation_disposition,
            unmatched_dimension_refs=unmatched,
            reset_disposition=reset_disposition,
            reset_evidence_refs=verification_records.reset.evidence_record_refs,
            cleanup_disposition=cleanup_disposition,
            cleanup_evidence_refs=verification_records.cleanup.evidence_record_refs,
            residual_state=verification_records.cleanup.residual_state,
            verification_binding=binding,
            verification_identities=tuple(_identity(record, binding) for record in records),
        )
    )


__all__ = (
    "CleanupVerificationRecord",
    "RepeatabilityEvidenceValidator",
    "RepeatabilityRunInput",
    "RepeatabilityRunPair",
    "RepeatabilityVerificationRecords",
    "ResetVerificationRecord",
    "VariationVerificationRecord",
    "VerificationBinding",
    "VerificationDisposition",
    "assemble_repeatability_consistency_evidence",
)
