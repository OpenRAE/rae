"""Join added accounting to an exact scientific artifact without moving its proof."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel

from .runtime_record_decisions import ExperimentRecordPublicationDecision
from .runtime_trial_decisions import TrialArchiveCandidateDecision, TrialArchiveDecision

if TYPE_CHECKING:
    from .runtime_decisions import RuntimeDecision

CanonicalRuns = tuple[tuple[ExperimentRunModel, int], ...]


def canonical_archival_runs(records: Iterable[RuntimeDecision], experiment_id: str) -> dict[str, CanonicalRuns]:
    result = {}
    for item in records:
        if getattr(item, "experiment_id", None) != experiment_id:
            continue
        if isinstance(item, (TrialArchiveCandidateDecision, TrialArchiveDecision)):
            run, priority = item.run, 2
        elif isinstance(item, ExperimentRecordPublicationDecision) and item.run is not None:
            run, priority = item.run, int(item.validation_status == "passed")
            if run.record_state != "archival" or any(
                ref.ref_kind == "run" and ref.ref_id == run.run_id and ref.ref_digest for ref in run.derived_from_refs
            ):
                continue
        else:
            continue
        versions = result.setdefault(run.run_id, {})
        prior, old_priority = versions.get(run.run_version, (run, priority))
        if prior != run:
            raise ValueError("canonical archival run has conflicting retained versions")
        versions[run.run_version] = (run, max(priority, old_priority))
    return {run_id: tuple(versions.values()) for run_id, versions in result.items()}


def accounting_validation_record(
    run: ExperimentRunModel, candidates: CanonicalRuns | None
) -> tuple[ExperimentRunModel, ExperimentRunModel]:
    canonical = _matching_scientific_record(run, candidates)
    if canonical is None:
        return run, run
    payload = run.model_dump(mode="json")
    payload["derived_from_refs"].append(
        {
            "ref_kind": "run",
            "ref_id": canonical.run_id,
            "ref_version": canonical.run_version,
            "ref_digest": canonical_json_digest(canonical.model_dump(mode="json")),
        }
    )
    return ExperimentRunModel.model_validate(payload), canonical


def _matching_scientific_record(run: ExperimentRunModel, candidates: CanonicalRuns | None) -> ExperimentRunModel | None:
    if not candidates or any(run.run_version == candidate.run_version for candidate, _ in candidates):
        return None
    if run.record_state != "archival" or run.execution_accounting is None:
        return None
    # Changed scientific facts or ambiguous originals require proof at the new version.
    excluded = {"run_version", "execution_accounting"}
    facts = run.model_dump(mode="json", exclude=excluded)
    matches = [
        (candidate, priority)
        for candidate, priority in candidates
        if candidate.record_state == "archival" and facts == candidate.model_dump(mode="json", exclude=excluded)
    ]
    preferred = []
    if matches:
        priority = max(rank for _, rank in matches)
        preferred = [candidate for candidate, rank in matches if rank == priority]
    return preferred[0] if len(preferred) == 1 else None
