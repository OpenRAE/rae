"""Share immutable artifact version ownership across all runtime archive paths."""

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel

from .runtime_record_decisions import ExperimentRecordPublicationDecision
from .runtime_trial_decisions import TrialArchiveCandidateDecision, TrialArchiveDecision, TrialReplacementDecision


def _retain(versions, artifact):
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


def retained_record_versions(records, experiment_id):
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


def require_compatible_record_versions(records, experiment_id, artifacts, *, known_versions=None):
    versions = retained_record_versions(records, experiment_id) if known_versions is None else known_versions
    for artifact in artifacts:
        _retain(versions, artifact)
