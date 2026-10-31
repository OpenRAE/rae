"""Internal assembled evidence types for bounded repeatability-consistency.

These types support ASR-514 determinism, stability, and replay-consistency
verification. One comparison is a single binary baseline-to-repetition pair
under the exact ``canonical-artifact-identity`` relation; a larger set of
repeated runs composes as several pairwise cases.

Trust boundary: ``compare_repeatability_consistency`` and
``assemble_repeatability_consistency_evidence`` are a trusted-composition-only
surface, invoked by code that already owns the validator authority and the case.
The module-owned assembly token is integrity defense-in-depth - it detects
accidental or unsealed construction - not an access-control boundary against a
caller that is already trusted to drive the comparator. Each evidence reference
is bound to the digest-verified run's declared evidence set (see
``repeatability_evidence``); content authenticity of an individual evidence
record remains owned by the platform evidence provenance layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from raes_contracts.canonical import canonical_json_digest

from .verification_authority import (
    VerificationBinding,
    VerificationDisposition,
    VerificationRecordIdentity,
)

_ASSEMBLY_TOKEN = object()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str):
        return False
    prefix, _, hexpart = value.partition(":")
    return prefix == "sha256" and len(hexpart) == 64 and all(character in "0123456789abcdef" for character in hexpart)


class ProjectionOutcome(str, Enum):
    """Support status of one side's admitted projected outcome."""

    DECIDED = "decided"
    INDETERMINATE = "indeterminate"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RepetitionProjection:
    """One side's projected outcome derived by the admitted validator.

    A decided projection carries the canonical digest of the projected artifact
    under the declared observation projection and the run-bound evidence it
    resolved through. An indeterminate or unsupported projection carries no
    digest, so it can never be read as an equal or unequal outcome.
    """

    run_ref: str
    outcome: ProjectionOutcome
    projected_digest: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_ref, str) or not self.run_ref.strip():
            raise ValueError("run_ref must be non-empty")
        if not isinstance(self.outcome, ProjectionOutcome):
            raise ValueError("outcome must be a ProjectionOutcome")
        if self.outcome is ProjectionOutcome.DECIDED:
            if not _is_sha256(self.projected_digest):
                raise ValueError("a decided projection must carry a sha256 projected_digest")
            if not self.evidence_refs:
                raise ValueError("a decided projection must carry run-bound evidence_refs")
        elif self.projected_digest is not None:
            raise ValueError("an undecided projection must not carry a projected_digest")


@dataclass(frozen=True, init=False)
class RepeatabilityConsistencyEvidence:
    """Evidence assembled only from validator-derived, run-bound artifacts."""

    case_digest: str
    baseline_artifact_ref: str
    baseline_projection: RepetitionProjection
    repetition_artifact_ref: str
    repetition_projection: RepetitionProjection
    variation_disposition: VerificationDisposition
    unmatched_dimension_refs: tuple[str, ...]
    reset_disposition: VerificationDisposition
    reset_evidence_refs: tuple[str, ...]
    cleanup_disposition: VerificationDisposition
    cleanup_evidence_refs: tuple[str, ...]
    residual_state: tuple[str, ...]
    verification_binding: VerificationBinding
    verification_identities: tuple[VerificationRecordIdentity, ...]
    _assembly_token: object = field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("use assemble_repeatability_consistency_evidence() to construct comparison evidence")

    def _has_authentic_assembly(self) -> bool:
        return self._assembly_token is _ASSEMBLY_TOKEN


def _new_repeatability_consistency_evidence(
    parts: _RepeatabilityConsistencyEvidenceParts,
) -> RepeatabilityConsistencyEvidence:
    """Construct one module-sealed evidence value for the trusted assembler."""

    instance = object.__new__(RepeatabilityConsistencyEvidence)
    for field_name in RepeatabilityConsistencyEvidence.__dataclass_fields__:
        value = _ASSEMBLY_TOKEN if field_name == "_assembly_token" else getattr(parts, field_name)
        object.__setattr__(instance, field_name, value)
    return instance


@dataclass(frozen=True)
class _RepeatabilityConsistencyEvidenceParts:
    """Typed content passed across the private assembly boundary."""

    case_digest: str
    baseline_artifact_ref: str
    baseline_projection: RepetitionProjection
    repetition_artifact_ref: str
    repetition_projection: RepetitionProjection
    variation_disposition: VerificationDisposition
    unmatched_dimension_refs: tuple[str, ...]
    reset_disposition: VerificationDisposition
    reset_evidence_refs: tuple[str, ...]
    cleanup_disposition: VerificationDisposition
    cleanup_evidence_refs: tuple[str, ...]
    residual_state: tuple[str, ...]
    verification_binding: VerificationBinding
    verification_identities: tuple[VerificationRecordIdentity, ...]


# canonical_json_digest re-exported for the trusted assembler's identity digests.
__all__ = (
    "ProjectionOutcome",
    "RepeatabilityConsistencyEvidence",
    "RepetitionProjection",
    "canonical_json_digest",
)
