"""Share immutable artifact version ownership across all runtime archive paths."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel, ExperimentStudyModel

from .runtime_record_decisions import ExperimentRecordPublicationDecision
from .runtime_trial_decisions import TrialArchiveCandidateDecision, TrialArchiveDecision, TrialReplacementDecision

if TYPE_CHECKING:
    from .runtime_decisions import RuntimeDecision

RecordArtifact = ExperimentRunModel | ExperimentStudyModel
RecordVersions = dict[tuple[str, str, str], RecordArtifact]


def _retain(versions: RecordVersions, artifact: RecordArtifact) -> None:
    identity = (
        ("run", artifact.run_id, artifact.run_version)
        if isinstance(artifact, ExperimentRunModel)
        else ("study", artifact.study_id, artifact.study_version)
    )
    prior = versions.setdefault(identity, artifact)
    if prior is artifact:
        return
    if canonical_json_digest(prior.model_dump(mode="json")) != canonical_json_digest(artifact.model_dump(mode="json")):
        raise ValueError("record version conflicts with retained archival content")


def retained_record_versions(records: Iterable[RuntimeDecision], experiment_id: str) -> RecordVersions:
    versions = {}
    for item in records:
        if getattr(item, "experiment_id", None) != experiment_id:
            continue
        if isinstance(item, (TrialArchiveCandidateDecision, TrialArchiveDecision)):
            artifacts = (item.run,)
        elif isinstance(item, TrialReplacementDecision):
            artifacts = (item.parent_run, item.superseded_run)
        elif isinstance(item, ExperimentRecordPublicationDecision):
            artifacts = (item.run if item.run is not None else item.study,)
        else:
            continue
        for artifact in artifacts:
            _retain(versions, artifact)
    return versions


def require_compatible_record_versions(
    records: Iterable[RuntimeDecision],
    experiment_id: str,
    artifacts: Iterable[RecordArtifact],
    *,
    known_versions: RecordVersions | None = None,
) -> None:
    versions = retained_record_versions(records, experiment_id) if known_versions is None else known_versions
    for artifact in artifacts:
        _retain(versions, artifact)
