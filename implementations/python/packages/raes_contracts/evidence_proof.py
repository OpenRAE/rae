"""Immutable process-local results of the emitted-evidence validation boundary.

These results have no wire decoder or public constructor. Recompute them from
content at ingress; reference metadata cannot restore validation authority.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import InitVar, dataclass, field
from typing import TYPE_CHECKING

from .canonical import canonical_json_digest

_EVIDENCE_VALIDATION_KEY = object()

if TYPE_CHECKING:
    from .contracts.experiment_apparatus import ExperimentTaskModel
    from .contracts.experiment_references import ExperimentReferenceModel
    from .contracts.experiment_run import ExperimentRunModel


@dataclass(frozen=True, slots=True)
class ValidatedEvidenceBinding:
    """Immutable identity facts from a fully validated requirement/artifact join."""

    requirement_id: str
    capture_spec_id: str
    capture_spec_version: str
    record_id: str
    record_version: str
    output_contract: str
    artifact_id: str
    artifact_digest: str
    artifact_path: str = field(repr=False)
    _validation_key: InitVar[object]

    def __post_init__(self, _validation_key: object) -> None:
        if _validation_key is not _EVIDENCE_VALIDATION_KEY:
            raise TypeError("evidence binding requires content validation")

    def _matches(self, reference: ExperimentReferenceModel) -> bool:
        return (
            reference.ref_kind == "evidence"
            and reference.ref_id == self.requirement_id
            and (reference.ref_version is None or reference.ref_version == self.record_version)
            and (reference.ref_digest is None or reference.ref_digest.casefold() == self.artifact_digest.casefold())
            and (reference.ref_path is None or reference.ref_path == self.artifact_path)
        )


@dataclass(frozen=True, slots=True, init=False)
class ValidatedRunEvidence:
    """Content proof bound to the exact validated task and run, not their ids alone."""

    bindings: tuple[ValidatedEvidenceBinding, ...]
    task_digest: str
    run_digest: str

    def __init__(self) -> None:
        raise TypeError("evidence proof requires content validation")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("evidence proofs cannot be serialized; repeat content validation")

    def require_context(self, task: ExperimentTaskModel, run: ExperimentRunModel) -> None:
        """Reject use after either validated input has changed."""

        self.require_run(run)
        if canonical_json_digest(task.model_dump(mode="json")) != self.task_digest:
            raise ValueError("validated evidence proof does not match the supplied task")

    def require_run(self, run: ExperimentRunModel) -> None:
        if canonical_json_digest(run.model_dump(mode="json")) != self.run_digest:
            raise ValueError("validated evidence proof does not match the supplied run")

    def satisfies(
        self,
        run: ExperimentRunModel,
        reference: ExperimentReferenceModel,
        *,
        artifact_ids: Collection[str] | None = None,
    ) -> bool:
        """Match a consumer's relation only against content-proven bindings."""

        self.require_run(run)
        return any(
            binding._matches(reference) and (artifact_ids is None or binding.artifact_id in artifact_ids)
            for binding in self.bindings
        )


def _mint_validated_run_evidence(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    bindings: tuple[ValidatedEvidenceBinding, ...],
) -> ValidatedRunEvidence:
    """Internal final step of evidence_satisfaction; never a reference decoder."""

    proof = object.__new__(ValidatedRunEvidence)
    object.__setattr__(proof, "bindings", bindings)
    object.__setattr__(proof, "task_digest", canonical_json_digest(task.model_dump(mode="json")))
    object.__setattr__(proof, "run_digest", canonical_json_digest(run.model_dump(mode="json")))
    return proof


__all__ = ["ValidatedEvidenceBinding", "ValidatedRunEvidence"]
