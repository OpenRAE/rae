"""Trusted evidence assembly for bounded necessity comparison."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Protocol

from raes_contracts.contracts import (
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentTaskModel,
    PropositionTruthResultModel,
    validate_experiment_run_against_task,
)
from raes_contracts.satisfiability import canonical_contract_digest

from .necessity_types import (
    BoundedButForEvidence,
    VerificationBinding,
    VerificationDisposition,
    VerificationRecordIdentity,
    _BoundedButForEvidenceParts,
    _new_bounded_but_for_evidence,
)
from .necessity_validation import (
    BoundedButForCase,
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
    record: InterventionVerificationRecord | MatchingVerificationRecord | CleanupVerificationRecord,
) -> None:
    _require_text(record.record_id, "record_id")
    _require_text(record.record_version, "record_version")
    _require_unique_text(record.evidence_record_refs, "evidence_record_refs")
    if not record.evidence_record_refs:
        raise ValueError("evidence_record_refs must not be empty")


@dataclass(frozen=True)
class InterventionVerificationRecord:
    """Run-bound inputs from which an admitted adapter verifies intervention."""

    record_id: str
    record_version: str
    world_id: str
    run_ref: str
    intervention_ref: str
    intervention_version: str
    evidence_record_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_record_header(self)
        for field_name in ("world_id", "run_ref", "intervention_ref", "intervention_version"):
            _require_text(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class MatchingVerificationRecord:
    """Run-bound inputs from which an admitted adapter verifies matching."""

    record_id: str
    record_version: str
    baseline_world_id: str
    baseline_run_ref: str
    counterfactual_world_id: str
    counterfactual_run_ref: str
    policy_id: str
    policy_version: str
    observed_difference_refs: tuple[str, ...]
    evidence_record_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_record_header(self)
        for field_name in (
            "baseline_world_id",
            "baseline_run_ref",
            "counterfactual_world_id",
            "counterfactual_run_ref",
            "policy_id",
            "policy_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_unique_text(self.observed_difference_refs, "observed_difference_refs")


@dataclass(frozen=True)
class CleanupVerificationRecord:
    """Run-bound inputs from which an admitted adapter verifies cleanup."""

    record_id: str
    record_version: str
    world_id: str
    run_ref: str
    subject_ref: str
    residual_state: tuple[str, ...]
    evidence_record_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_record_header(self)
        for field_name in ("world_id", "run_ref", "subject_ref"):
            _require_text(getattr(self, field_name), field_name)
        _require_unique_text(self.residual_state, "residual_state")


@dataclass(frozen=True)
class NecessityRunPair:
    """Typed baseline and counterfactual task/run inputs."""

    baseline_task: ExperimentTaskModel
    baseline_run: ExperimentRunModel
    counterfactual_task: ExperimentTaskModel
    counterfactual_run: ExperimentRunModel
    baseline_evidence: ExperimentRunEvidenceInputs | None = None
    counterfactual_evidence: ExperimentRunEvidenceInputs | None = None


@dataclass(frozen=True)
class NecessityVerificationRecords:
    """The three run-bound verification inputs for one comparison."""

    intervention: InterventionVerificationRecord
    matching: MatchingVerificationRecord
    cleanup: CleanupVerificationRecord

    def as_tuple(
        self,
    ) -> tuple[InterventionVerificationRecord, MatchingVerificationRecord, CleanupVerificationRecord]:
        """Return the records in canonical comparison order."""

        return (self.intervention, self.matching, self.cleanup)


class NecessityEvidenceValidator(Protocol):
    """Host-owned adapter admitted by the case's exact executable binding."""

    binding: VerificationBinding

    def derive_truth(
        self,
        *,
        role: str,
        case: BoundedButForCase,
        run: ExperimentRunModel,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> PropositionTruthResultModel: ...

    def verify_intervention(
        self,
        *,
        case: BoundedButForCase,
        record: InterventionVerificationRecord,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> VerificationDisposition: ...

    def verify_matching(
        self,
        *,
        case: BoundedButForCase,
        record: MatchingVerificationRecord,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> VerificationDisposition: ...

    def verify_cleanup(
        self,
        *,
        case: BoundedButForCase,
        record: CleanupVerificationRecord,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> VerificationDisposition: ...


def _run_ref(run: ExperimentRunModel) -> str:
    return f"experiment-run:{run.run_id}@{run.run_version}"


def _snapshot_ref(run: ExperimentRunModel) -> str:
    snapshot = run.scenario_snapshot_ref
    return f"scenario-snapshot:{snapshot.ref_id}@{snapshot.ref_version}"


def _validate_world(
    case: BoundedButForCase,
    role: str,
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    evidence: ExperimentRunEvidenceInputs | None,
) -> None:
    try:
        validate_experiment_run_against_task(task, run, evidence=evidence)
    except ValueError as exc:
        raise ValueError(f"{role} task/run validation failed") from exc
    world = case.baseline_world if role == "baseline" else case.counterfactual_world
    snapshot = run.scenario_snapshot_ref
    if (
        world.run_ref != _run_ref(run)
        or world.run_digest != canonical_contract_digest(run)
        or world.subject_ref != _snapshot_ref(run)
        or world.subject_digest != snapshot.ref_digest
    ):
        raise ValueError(f"{role} world does not match the validated task, run, and scenario snapshot")


def _run_evidence_refs(run: ExperimentRunModel) -> set[tuple[str, str | None]]:
    return {(reference.ref_id, reference.ref_version) for reference in run.traceability.evidence_record_refs}


def _record_matches_run(record: ExperimentEvidenceRecordModel, run: ExperimentRunModel) -> bool:
    return (
        record.run_ref.ref_kind == "run"
        and record.run_ref.ref_id == run.run_id
        and record.run_ref.ref_version == run.run_version
        and (record.evidence_record_id, record.record_version) in _run_evidence_refs(run)
    )


def _validate_truth_evidence(
    role: str,
    truth: PropositionTruthResultModel,
    run: ExperimentRunModel,
    evidence_by_id: dict[str, ExperimentEvidenceRecordModel],
) -> None:
    for evidence_ref in truth.evidence_refs:
        record = evidence_by_id.get(evidence_ref)
        if record is None or not _record_matches_run(record, run):
            raise ValueError(f"{role} truth evidence must resolve through its exact run and traceability")


def _validate_verification_evidence(
    label: str,
    refs: tuple[str, ...],
    run: ExperimentRunModel,
    evidence_by_id: dict[str, ExperimentEvidenceRecordModel],
) -> None:
    for evidence_ref in refs:
        record = evidence_by_id.get(evidence_ref)
        if record is None or not _record_matches_run(record, run):
            raise ValueError(f"{label} evidence must resolve through the counterfactual run and traceability")


def _require_join(label: str, joins: tuple[tuple[str, str], ...]) -> None:
    if any(actual != expected for actual, expected in joins):
        raise ValueError(f"{label} verification does not match the admitted case")


def _validate_verification_joins(case: BoundedButForCase, records: NecessityVerificationRecords) -> None:
    intervention, matching, cleanup = records.as_tuple()
    _require_join(
        "intervention",
        (
            (intervention.world_id, case.counterfactual_world.world_id),
            (intervention.run_ref, case.counterfactual_world.run_ref),
            (intervention.intervention_ref, case.intervention_ref),
            (intervention.intervention_version, case.intervention_version),
        ),
    )
    _require_join(
        "matching",
        (
            (matching.baseline_world_id, case.baseline_world.world_id),
            (matching.baseline_run_ref, case.baseline_world.run_ref),
            (matching.counterfactual_world_id, case.counterfactual_world.world_id),
            (matching.counterfactual_run_ref, case.counterfactual_world.run_ref),
            (matching.policy_id, case.matching_policy.policy_id),
            (matching.policy_version, case.matching_policy.policy_version),
        ),
    )
    _require_join(
        "cleanup",
        (
            (cleanup.world_id, case.counterfactual_world.world_id),
            (cleanup.run_ref, case.counterfactual_world.run_ref),
            (cleanup.subject_ref, case.counterfactual_world.subject_ref),
        ),
    )


def _record_digest(
    record: InterventionVerificationRecord | MatchingVerificationRecord | CleanupVerificationRecord,
) -> str:
    payload = {
        "record_kind": type(record).__name__,
        **asdict(record),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _identity(
    record: InterventionVerificationRecord | MatchingVerificationRecord | CleanupVerificationRecord,
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


def assemble_bounded_but_for_evidence(
    case: BoundedButForCase,
    *,
    runs: NecessityRunPair,
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    verification_records: NecessityVerificationRecords,
    validator: NecessityEvidenceValidator,
) -> BoundedButForEvidence:
    """Invoke the admitted adapter and assemble evidence after every join passes."""

    _validate_world(case, "baseline", runs.baseline_task, runs.baseline_run, runs.baseline_evidence)
    _validate_world(
        case,
        "counterfactual",
        runs.counterfactual_task,
        runs.counterfactual_run,
        runs.counterfactual_evidence,
    )
    binding = getattr(validator, "binding", None)
    if not isinstance(binding, VerificationBinding) or binding != case.verification_authority:
        raise ValueError("validator binding does not match the authority admitted by the case")
    evidence_by_id = {record.evidence_record_id: record for record in evidence_records}
    if len(evidence_by_id) != len(evidence_records):
        raise ValueError("evidence_records must use unique evidence_record_id values")
    baseline_truth = validator.derive_truth(
        role="baseline",
        case=case,
        run=runs.baseline_run,
        evidence_records=evidence_records,
    )
    counterfactual_truth = validator.derive_truth(
        role="counterfactual",
        case=case,
        run=runs.counterfactual_run,
        evidence_records=evidence_records,
    )
    if not isinstance(baseline_truth, PropositionTruthResultModel) or not isinstance(
        counterfactual_truth, PropositionTruthResultModel
    ):
        raise ValueError("validator must derive typed PropositionTruthResultModel values")
    _validate_truth_evidence("baseline", baseline_truth, runs.baseline_run, evidence_by_id)
    _validate_truth_evidence("counterfactual", counterfactual_truth, runs.counterfactual_run, evidence_by_id)
    _validate_verification_joins(case, verification_records)
    for label, record in zip(
        ("intervention verification", "matching verification", "cleanup verification"),
        verification_records.as_tuple(),
        strict=True,
    ):
        _validate_verification_evidence(
            label,
            record.evidence_record_refs,
            runs.counterfactual_run,
            evidence_by_id,
        )

    intervention_disposition = validator.verify_intervention(
        case=case,
        record=verification_records.intervention,
        evidence_records=evidence_records,
    )
    matching_disposition = validator.verify_matching(
        case=case,
        record=verification_records.matching,
        evidence_records=evidence_records,
    )
    cleanup_disposition = validator.verify_cleanup(
        case=case,
        record=verification_records.cleanup,
        evidence_records=evidence_records,
    )
    dispositions = (
        intervention_disposition,
        matching_disposition,
        cleanup_disposition,
    )
    if any(not isinstance(disposition, VerificationDisposition) for disposition in dispositions):
        raise ValueError("validator methods must return VerificationDisposition values")

    permitted = set(case.matching_policy.permitted_difference_refs)
    observed = set(verification_records.matching.observed_difference_refs)
    unmatched = tuple(sorted(observed.symmetric_difference(permitted)))
    records = verification_records.as_tuple()
    record_ids = [record.record_id for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("verification records must use unique record_id values")
    return _new_bounded_but_for_evidence(
        _BoundedButForEvidenceParts(
            case_digest=case.digest,
            baseline_world_id=case.baseline_world.world_id,
            baseline_run_ref=case.baseline_world.run_ref,
            baseline_truth=baseline_truth,
            counterfactual_world_id=case.counterfactual_world.world_id,
            counterfactual_run_ref=case.counterfactual_world.run_ref,
            counterfactual_truth=counterfactual_truth,
            intervention_disposition=intervention_disposition,
            intervention_evidence_refs=verification_records.intervention.evidence_record_refs,
            matching_disposition=matching_disposition,
            unmatched_dimension_refs=unmatched,
            cleanup_disposition=cleanup_disposition,
            cleanup_evidence_refs=verification_records.cleanup.evidence_record_refs,
            residual_state=verification_records.cleanup.residual_state,
            verification_binding=binding,
            verification_identities=tuple(_identity(record, binding) for record in records),
        )
    )


__all__ = (
    "CleanupVerificationRecord",
    "InterventionVerificationRecord",
    "MatchingVerificationRecord",
    "NecessityEvidenceValidator",
    "NecessityRunPair",
    "NecessityVerificationRecords",
    "VerificationBinding",
    "VerificationDisposition",
    "assemble_bounded_but_for_evidence",
)
