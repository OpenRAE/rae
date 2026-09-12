"""Content-backed post-run evidence satisfaction validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO

from ._evidence_content_validation import _validate_artifact_content
from .contracts import (
    ExperimentArtifactRefModel,
    ExperimentCaptureRequirementModel,
    ExperimentCaptureSpecModel,
    ExperimentCaptureWindowModel,
    ExperimentEvidenceRecordModel,
    ExperimentEvidenceReferenceModel,
    ExperimentRunModel,
    ExperimentTaskModel,
    validate_experiment_run_structure_against_task,
)
from .contracts.base import _parse_rfc3339_datetime


@dataclass(frozen=True)
class _ValidatedEvidenceBinding:
    """A requirement-to-record-to-artifact relation created only after proof."""

    requirement_id: str
    record: ExperimentEvidenceRecordModel
    artifact: ExperimentArtifactRefModel


def _artifact_for_record(
    run: ExperimentRunModel,
    record: ExperimentEvidenceRecordModel,
) -> ExperimentArtifactRefModel:
    raw_content = record.raw_content
    candidates = []
    if raw_content.artifact_ref is not None:
        candidates = [
            artifact
            for artifact in run.evidence_artifacts
            if artifact.artifact_id == raw_content.artifact_ref.artifact_id
        ]
    elif raw_content.content_uri is not None and raw_content.content_checksum is not None:
        candidates = [
            artifact
            for artifact in run.evidence_artifacts
            if artifact.uri == raw_content.content_uri
            and artifact.checksum.algorithm == raw_content.content_checksum.algorithm
            and artifact.checksum.value.casefold() == raw_content.content_checksum.value.casefold()
        ]
    if len(candidates) != 1:
        raise ValueError("evidence record must resolve to exactly one emitted run artifact")
    if raw_content.artifact_ref is not None and raw_content.artifact_ref != candidates[0]:
        raise ValueError("evidence record artifact_ref does not match the emitted run artifact")
    return candidates[0]


def _validate_record_binding(
    *,
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    capture_spec: ExperimentCaptureSpecModel,
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
) -> None:
    _validate_record_capture_identity(capture_spec, requirement, record)
    _validate_record_execution_identity(task, run, record)
    _validate_record_window(run, capture_spec, requirement, record)
    _validate_record_disclosure(requirement, record)
    _validate_record_source(requirement, record)


def _validate_record_capture_identity(
    capture_spec: ExperimentCaptureSpecModel,
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
) -> None:
    if (
        record.capture_spec_ref.ref_id != capture_spec.capture_spec_id
        or record.capture_spec_ref.ref_version != capture_spec.spec_version
    ):
        raise ValueError("evidence record capture_spec_ref does not match the supplied capture spec")
    if record.capture_requirement_ref != requirement.requirement_id:
        raise ValueError("evidence record capture_requirement_ref does not match the capture requirement")
    if record.output_contract != requirement.output_contract:
        raise ValueError("evidence record output_contract does not match the admitted capture requirement")
    if record.evidence_kind != requirement.capture_kind:
        raise ValueError("evidence record kind does not match the capture requirement")


def _validate_record_execution_identity(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    record: ExperimentEvidenceRecordModel,
) -> None:
    if record.run_ref.ref_id != run.run_id or (
        record.run_ref.ref_version is not None and record.run_ref.ref_version != run.run_version
    ):
        raise ValueError("evidence record run_ref does not match the experiment run")
    if record.task_ref is not None and (
        record.task_ref.ref_id != task.task_id or record.task_ref.ref_version != task.task_version
    ):
        raise ValueError("evidence record task_ref does not match the experiment task")


def _resolve_capture_window(
    capture_spec: ExperimentCaptureSpecModel,
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
) -> ExperimentCaptureWindowModel:
    if record.capture_window_ref not in requirement.window_refs:
        raise ValueError("evidence record capture window does not match the capture requirement")
    matching_windows = [
        window for window in capture_spec.capture_windows if window.window_id == record.capture_window_ref
    ]
    if len(matching_windows) != 1:
        raise ValueError("evidence record capture window must resolve exactly in the supplied capture spec")
    return matching_windows[0]


def _capture_window_bounds(
    run: ExperimentRunModel,
    window: ExperimentCaptureWindowModel,
) -> tuple[datetime | None, datetime | None]:
    starts_at, ends_at = _explicit_capture_window_bounds(window)
    if window.window_kind in {"run", "task"}:
        starts_at, ends_at = _run_bounded_capture_window(run, starts_at, ends_at)
    elif window.window_kind == "interval" and (starts_at is None or ends_at is None):
        raise ValueError("interval capture window timing cannot be proved without both bounds")
    elif starts_at is None and ends_at is None:
        raise ValueError("capture window timing cannot be proved from the supplied evidence")
    return starts_at, ends_at


def _run_bounded_capture_window(
    run: ExperimentRunModel,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> tuple[datetime, datetime]:
    run_starts_at = _parse_rfc3339_datetime("started_at", run.started_at)
    run_ends_at = _parse_rfc3339_datetime("ended_at", run.ended_at)
    bounded_start = max(value for value in (starts_at, run_starts_at) if value is not None)
    bounded_end = min(value for value in (ends_at, run_ends_at) if value is not None)
    return bounded_start, bounded_end


def _explicit_capture_window_bounds(
    window: ExperimentCaptureWindowModel,
) -> tuple[datetime | None, datetime | None]:
    starts_at = _parse_rfc3339_datetime("starts_at", window.starts_at) if window.starts_at is not None else None
    ends_at = _parse_rfc3339_datetime("ends_at", window.ends_at) if window.ends_at is not None else None
    return starts_at, ends_at


def _validate_record_window(
    run: ExperimentRunModel,
    capture_spec: ExperimentCaptureSpecModel,
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
) -> None:
    window = _resolve_capture_window(capture_spec, requirement, record)
    captured_at = _parse_rfc3339_datetime("captured_at", record.captured_at)
    starts_at, ends_at = _capture_window_bounds(run, window)
    if starts_at is not None and captured_at < starts_at:
        raise ValueError("evidence was captured before the admitted capture window")
    if ends_at is not None and captured_at > ends_at:
        raise ValueError("evidence was captured after the admitted capture window")


def _validate_record_disclosure(
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
) -> None:
    if record.sensitivity != requirement.sensitivity:
        raise ValueError("evidence record sensitivity does not match the capture requirement")
    _validate_redaction_state(requirement, record)
    if record.redaction_policy != requirement.redaction_policy:
        raise ValueError("evidence record redaction policy does not match the capture requirement")
    if record.redaction_policy is not None:
        raise ValueError("the governed redaction policy has no content verifier")
    if record.raw_content.loss_disclosure is not None and record.redaction_state == "none":
        raise ValueError("lossy evidence cannot satisfy a required complete capture")


def _validate_redaction_state(
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
) -> None:
    if record.redaction_state == "withheld":
        raise ValueError("withheld evidence cannot satisfy a required capture")
    requires_redaction = requirement.redaction_policy is not None or requirement.sensitivity == "redacted"
    expected_redaction_state = "redacted" if requires_redaction else "none"
    if record.redaction_state != expected_redaction_state:
        if requires_redaction:
            raise ValueError("required evidence redaction policy was not applied")
        raise ValueError("redacted evidence is not permitted by the capture requirement")


def _validate_record_source(
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
) -> None:
    required_source = requirement.channel_ref
    if not any(
        source.ref_kind == required_source.ref_kind
        and source.ref_id == required_source.ref_id
        and (required_source.ref_version is None or source.ref_version == required_source.ref_version)
        for source in record.source_refs
    ):
        raise ValueError("evidence record source does not match the admitted measurement channel")


def _binding_satisfies_reference(
    binding: _ValidatedEvidenceBinding,
    reference: ExperimentEvidenceReferenceModel,
) -> bool:
    if reference.ref_version is not None and reference.ref_version != binding.record.record_version:
        return False
    if reference.ref_digest is not None:
        artifact_digest = f"{binding.artifact.checksum.algorithm}:{binding.artifact.checksum.value}"
        if artifact_digest.casefold() != reference.ref_digest.casefold():
            return False
    return reference.ref_path is None or binding.artifact.uri == reference.ref_path


def _validate_task_evidence_bindings(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    bindings: Mapping[str, _ValidatedEvidenceBinding],
) -> None:
    missing_observations = sorted(
        reference.ref_id
        for reference in task.evaluation_protocol.observation_requirements
        if (binding := bindings.get(reference.ref_id)) is None or not _binding_satisfies_reference(binding, reference)
    )
    if missing_observations:
        raise ValueError(
            "validated evidence bindings do not satisfy task observation requirements: "
            + ", ".join(missing_observations)
        )

    missing_metric_evidence: list[str] = []
    for result_id, result in run.result_summaries.items():
        result_artifact_ids = {reference.ref_id for reference in result.evidence_refs}
        metric = task.evaluation_protocol.metric_definitions[result.metric_id]
        for reference in metric.evidence_requirements:
            binding = bindings.get(reference.ref_id)
            if (
                binding is None
                or binding.artifact.artifact_id not in result_artifact_ids
                or not _binding_satisfies_reference(binding, reference)
            ):
                missing_metric_evidence.append(f"{result_id}:{reference.ref_id}")
    if missing_metric_evidence:
        raise ValueError(
            "run result evidence_refs do not resolve to validated metric evidence bindings: "
            + ", ".join(sorted(missing_metric_evidence))
        )


def validate_experiment_run_evidence(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    *,
    capture_specs: Mapping[str, ExperimentCaptureSpecModel],
    evidence_records: Mapping[str, ExperimentEvidenceRecordModel],
    artifact_readers: Mapping[str, BinaryIO],
) -> tuple[ExperimentEvidenceReferenceModel, ...]:
    """Prove task/run evidence claims against exact records and emitted bytes.

    The caller acquires immutable byte streams.  This validator never fetches
    artifact URIs, searches host paths, or treats adapter-authored reference
    identifiers and summaries as evidence.
    """

    validate_experiment_run_structure_against_task(task, run)
    _validate_supplied_evidence_sets(run, capture_specs, evidence_records)
    requirements, records_by_requirement = _index_capture_evidence(capture_specs, evidence_records)
    _validate_task_requirement_ids(task, requirements)
    validated_bindings = _validate_evidence_bindings(
        task,
        run,
        requirements,
        records_by_requirement,
        artifact_readers,
    )
    _validate_task_evidence_bindings(task, run, validated_bindings)
    return tuple(_binding_reference(binding) for binding in validated_bindings.values())


def _validate_supplied_evidence_sets(
    run: ExperimentRunModel,
    capture_specs: Mapping[str, ExperimentCaptureSpecModel],
    evidence_records: Mapping[str, ExperimentEvidenceRecordModel],
) -> None:
    referenced_specs = {(reference.ref_id, reference.ref_version) for reference in run.traceability.capture_spec_refs}
    supplied_specs = {(spec.capture_spec_id, spec.spec_version) for spec in capture_specs.values()}
    if referenced_specs != supplied_specs:
        raise ValueError("run capture_spec_refs must resolve exactly to supplied capture specs")
    referenced_records = {
        (reference.ref_id, reference.ref_version) for reference in run.traceability.evidence_record_refs
    }
    supplied_records = {(record.evidence_record_id, record.record_version) for record in evidence_records.values()}
    if referenced_records != supplied_records:
        raise ValueError("run evidence_record_refs must resolve exactly to supplied evidence records")


def _index_capture_evidence(
    capture_specs: Mapping[str, ExperimentCaptureSpecModel],
    evidence_records: Mapping[str, ExperimentEvidenceRecordModel],
) -> tuple[
    dict[str, tuple[ExperimentCaptureSpecModel, ExperimentCaptureRequirementModel]],
    dict[tuple[str, str], list[ExperimentEvidenceRecordModel]],
]:
    records_by_requirement: dict[tuple[str, str], list[ExperimentEvidenceRecordModel]] = {}
    requirements: dict[str, tuple[ExperimentCaptureSpecModel, ExperimentCaptureRequirementModel]] = {}
    for capture_spec in capture_specs.values():
        for requirement_id, requirement in capture_spec.capture_requirements.items():
            if requirement_id in requirements:
                raise ValueError("capture requirement ids must be unambiguous across supplied capture specs")
            requirements[requirement_id] = (capture_spec, requirement)
    for record in evidence_records.values():
        key = (record.capture_spec_ref.ref_id, record.capture_requirement_ref)
        records_by_requirement.setdefault(key, []).append(record)
    valid_requirement_keys = {
        (capture_spec.capture_spec_id, requirement_id) for requirement_id, (capture_spec, _) in requirements.items()
    }
    if not set(records_by_requirement).issubset(valid_requirement_keys):
        raise ValueError("evidence records must resolve to admitted capture requirements")
    return requirements, records_by_requirement


def _validate_task_requirement_ids(
    task: ExperimentTaskModel,
    requirements: Mapping[str, tuple[ExperimentCaptureSpecModel, ExperimentCaptureRequirementModel]],
) -> None:
    task_requirement_ids = {reference.ref_id for reference in task.evaluation_protocol.observation_requirements} | {
        reference.ref_id
        for metric in task.evaluation_protocol.metric_definitions.values()
        for reference in metric.evidence_requirements
    }
    unresolved = sorted(task_requirement_ids - set(requirements))
    if unresolved:
        raise ValueError("task evidence requirements do not resolve to capture requirements: " + ", ".join(unresolved))


def _validate_evidence_bindings(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    requirements: Mapping[str, tuple[ExperimentCaptureSpecModel, ExperimentCaptureRequirementModel]],
    records_by_requirement: Mapping[tuple[str, str], list[ExperimentEvidenceRecordModel]],
    artifact_readers: Mapping[str, BinaryIO],
) -> dict[str, _ValidatedEvidenceBinding]:
    validated_bindings: dict[str, _ValidatedEvidenceBinding] = {}
    for requirement_id in sorted(requirements):
        capture_spec, requirement = requirements[requirement_id]
        records = records_by_requirement.get((capture_spec.capture_spec_id, requirement_id), [])
        if len(records) != 1:
            raise ValueError(f"capture requirement {requirement_id!r} must resolve to exactly one evidence record")
        record = records[0]
        _validate_record_binding(
            task=task,
            run=run,
            capture_spec=capture_spec,
            requirement=requirement,
            record=record,
        )
        artifact = _artifact_for_record(run, record)
        _validate_artifact_content(requirement, record, artifact, artifact_readers.get(artifact.artifact_id))
        validated_bindings[requirement_id] = _ValidatedEvidenceBinding(
            requirement_id=requirement_id,
            record=record,
            artifact=artifact,
        )
    return validated_bindings


def _binding_reference(binding: _ValidatedEvidenceBinding) -> ExperimentEvidenceReferenceModel:
    return ExperimentEvidenceReferenceModel(
        ref_kind="evidence",
        ref_id=binding.requirement_id,
        ref_version=binding.record.record_version,
        ref_digest=f"{binding.artifact.checksum.algorithm}:{binding.artifact.checksum.value}",
        ref_path=binding.artifact.uri,
    )


__all__ = ["validate_experiment_run_evidence"]
