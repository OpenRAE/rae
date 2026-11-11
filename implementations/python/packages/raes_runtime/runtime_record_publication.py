"""Freeze immutable record candidates before external publication and readback."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel, ExperimentStudyModel

from .runtime_record_decisions import ExperimentRecordPublicationDecision
from .runtime_record_versions import require_compatible_record_versions

if TYPE_CHECKING:
    from .experiment_records import ExperimentRecordArchive, ExperimentRecordBundle
    from .runtime_experiment import RuntimeExperiment


def publish_records(
    experiment: RuntimeExperiment, bundle: ExperimentRecordBundle, archive: ExperimentRecordArchive
) -> None:
    _require_archive_owner(archive)
    engine = experiment.engine
    candidates = _run_candidates(experiment.experiment_id, bundle)
    if bundle.study is not None:
        candidates.append(
            ExperimentRecordPublicationDecision(
                experiment_id=experiment.experiment_id,
                study=bundle.study,
                validation_status=bundle.study_validation,
                failure_codes=() if bundle.study_validation == "passed" else ("study-validation-failed",),
            )
        )
    retained = engine._store.load_runtime_decisions()
    require_compatible_record_versions(
        retained,
        experiment.experiment_id,
        (item.run if item.run is not None else item.study for item in candidates),
    )
    for candidate in candidates:
        engine._store.claim_runtime_decision(candidate)
    # Source writes append individually identified artifacts, never replace history.
    for source in bundle.sources:
        engine._execution_adapter.call("store", archive.write_sources, source, timeout_ms=engine._supervision.commit_ms)
    retained = engine._store.load_runtime_decisions()
    pending = [
        item
        for item in retained
        if isinstance(item, ExperimentRecordPublicationDecision)
        and item.experiment_id == experiment.experiment_id
        and item.state == "candidate"
    ]
    # Runs precede studies, including candidates retained after a lost acknowledgement.
    for candidate in sorted(pending, key=lambda item: item.study is not None):
        engine._execution_adapter.call(
            "store", _write_and_read, archive, candidate, timeout_ms=engine._supervision.commit_ms
        )
        engine._store.claim_runtime_decision(candidate.model_copy(update={"state": "published"}))


def _require_archive_owner(archive: ExperimentRecordArchive) -> None:
    required = ("write_sources", "write_run", "read_run", "write_study", "read_study")
    if not all(callable(getattr(archive, name, None)) for name in required):
        raise TypeError("record publication requires an installed immutable archive owner")


def _run_candidates(experiment_id: str, bundle: ExperimentRecordBundle) -> list[ExperimentRecordPublicationDecision]:
    versions: dict[tuple[str, str], ExperimentRecordPublicationDecision] = {}
    checked = {run.run_id: run for run in bundle.validation_records}
    for run in bundle.retained_history:
        _retain_candidate(
            versions,
            ExperimentRecordPublicationDecision(
                experiment_id=experiment_id, run=run, validation_status="not-performed"
            ),
        )
    for run in checked.values():
        _retain_candidate(versions, _run_candidate(experiment_id, bundle, run, is_checked=True))
    for run in bundle.runs:
        is_checked = not checked or checked[run.run_id].run_version == run.run_version
        _retain_candidate(versions, _run_candidate(experiment_id, bundle, run, is_checked=is_checked))
    return list(versions.values())


def _run_candidate(
    experiment_id: str, bundle: ExperimentRecordBundle, run: ExperimentRunModel, *, is_checked: bool
) -> ExperimentRecordPublicationDecision:
    return ExperimentRecordPublicationDecision(
        experiment_id=experiment_id,
        run=run,
        validation_status=bundle.validation_by_run[run.run_id] if is_checked else "not-performed",
        failure_codes=bundle.validation_failures.get(run.run_id, ()) if is_checked else (),
    )


def _retain_candidate(
    versions: dict[tuple[str, str], ExperimentRecordPublicationDecision],
    candidate: ExperimentRecordPublicationDecision,
) -> None:
    key = (candidate.run.run_id, candidate.run.run_version)
    if key in versions and versions[key].run != candidate.run:
        raise ValueError("record version conflicts with retained archival content")
    versions[key] = candidate


def _write_and_read(archive: ExperimentRecordArchive, candidate: ExperimentRecordPublicationDecision) -> None:
    subject = candidate.run if candidate.run is not None else candidate.study
    expected = canonical_json_digest(subject.model_dump(mode="json"))
    if candidate.run is not None:
        archive.write_run(subject.model_copy(deep=True))
        observed = archive.read_run(subject.run_id, subject.run_version)
        observed = ExperimentRunModel.model_validate(observed.model_dump(mode="json", warnings=False))
    else:
        archive.write_study(subject.model_copy(deep=True))
        observed = archive.read_study(subject.study_id, subject.study_version)
        observed = ExperimentStudyModel.model_validate(observed.model_dump(mode="json", warnings=False))
    if canonical_json_digest(observed.model_dump(mode="json")) != expected:
        raise ValueError("archive readback differs from the frozen record candidate")
