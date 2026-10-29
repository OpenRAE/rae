"""Freeze immutable record candidates before external publication and readback."""

from __future__ import annotations

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel, ExperimentStudyModel

from .runtime_record_decisions import ExperimentRecordPublicationDecision
from .runtime_record_versions import require_compatible_record_versions


def publish_records(experiment, bundle, archive):
    required = ("write_sources", "write_run", "read_run", "write_study", "read_study")
    if not all(callable(getattr(archive, name, None)) for name in required):
        raise TypeError("record publication requires an installed immutable archive owner")
    engine = experiment.engine
    versions = {}
    checked = {run.run_id: run for run in getattr(bundle, "validation_records", ())}

    def retain(run, status, codes=()):
        key = (run.run_id, run.run_version)
        if key in versions and versions[key].run != run:
            raise ValueError("record version conflicts with retained archival content")
        versions[key] = ExperimentRecordPublicationDecision(
            experiment_id=experiment.experiment_id,
            run=run,
            validation_status=status,
            failure_codes=codes,
        )

    for run in getattr(bundle, "retained_history", ()):
        retain(run, "not-performed")
    for run in checked.values():
        retain(run, bundle.validation_by_run[run.run_id], bundle.validation_failures.get(run.run_id, ()))
    for run in bundle.runs:
        is_checked = not checked or checked[run.run_id].run_version == run.run_version
        retain(
            run,
            bundle.validation_by_run[run.run_id] if is_checked else "not-performed",
            bundle.validation_failures.get(run.run_id, ()) if is_checked else (),
        )
    candidates = list(versions.values())
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


def _write_and_read(archive, candidate):
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
