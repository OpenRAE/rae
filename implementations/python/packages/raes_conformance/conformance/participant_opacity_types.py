"""Participant-opacity probe vocabulary.

The declarative half of the probe family: the closed observation transcript,
the case and point records a harness fills in, the backend readback record, and
the harness protocol. A harness contributes inputs, the transcript the backend
reports, and a backend state commitment. It contributes no expected
transcript, realization owner, provenance digest, or verdict: the runner in
``participant_opacity_probes`` derives each of those from what it executes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Protocol

from raes_runtime.registry import RuntimeTarget

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ParticipantOpacityRealizationOwner(StrEnum):
    """Who the runner observed realizing the measured relation for a case."""

    DECLARATION_ONLY = "declaration-only"
    RUNTIME_MEDIATED = "runtime-mediated"
    BACKEND_NATIVE = "backend-native"


class ParticipantOpacityEvidenceOrigin(StrEnum):
    """Whether a case rests on runner-measured execution or on supplied transcripts."""

    DECLARATION = "declaration"
    SYNTHETIC_MODEL = "synthetic-model"
    OBSERVED_EXECUTION = "observed-execution"


@dataclass(frozen=True)
class ParticipantOpacityProbeObservation:
    """Closed, non-secret observation transcript for one possible point."""

    decision: str
    failure: str
    action_availability: str
    delivery: str
    omission: str
    retry: str
    logical_timing: str
    logical_order: str
    policy_release_effect: str
    external_effect: str
    payload_released: bool


OBSERVATION_FIELDS = tuple(field.name for field in fields(ParticipantOpacityProbeObservation))


@dataclass(frozen=True)
class ParticipantOpacityReadbackRequest:
    """Runner-issued collection that binds one readback to one execution phase.

    ``collection_id`` is a fresh runner nonce, so a cached response from another
    run, case, point, or phase cannot satisfy a later collection.
    """

    collection_id: str
    case_name: str
    point_ref: str
    phase: str


@dataclass(frozen=True)
class ParticipantOpacityBackendReadback:
    """Backend-owned state commitment answering exactly one runner-issued collection."""

    request: ParticipantOpacityReadbackRequest
    source_ref: str
    state_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, ParticipantOpacityReadbackRequest):
            raise ValueError("backend readback must answer a runner-issued collection request")
        if not isinstance(self.source_ref, str) or not self.source_ref:
            raise ValueError("backend readback must name its backend state source")
        if not isinstance(self.state_digest, str) or _DIGEST.fullmatch(self.state_digest) is None:
            raise ValueError("backend readback must be a sha256 state digest")


@dataclass(frozen=True)
class ParticipantOpacityProbePoint:
    """One possible point materialized by an exact-cut crossing policy resolver."""

    point_ref: str
    resolver: object


@dataclass(frozen=True)
class ParticipantOpacityProbeCase:
    """Typed backend-specific inputs; no expected transcript, owner, or verdict."""

    name: str
    profile_id: str
    profile_revision: str
    profile_digest: str
    protected_point: ParticipantOpacityProbePoint
    complement_point: ParticipantOpacityProbePoint
    participant_address: str
    episode_id: str
    behavior: object
    admission_request: object
    identity: object
    crossing_evidence: object
    idempotency_key: str
    environment_digest: str
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    explicit_non_claims: tuple[str, ...]
    behavior_specifications: Mapping[str, object] | None = None
    enforce_final_sink_flow_control: bool = True

    def __post_init__(self) -> None:
        if self.protected_point.point_ref == self.complement_point.point_ref:
            raise ValueError("probe points must name two distinct possible points")
        if not self.idempotency_key:
            raise ValueError("probe idempotency key must be non-empty")
        if _DIGEST.fullmatch(self.environment_digest) is None:
            raise ValueError("probe environment digest must be a sha256 digest")

    @property
    def points(self) -> tuple[ParticipantOpacityProbePoint, ParticipantOpacityProbePoint]:
        return (self.protected_point, self.complement_point)


class ParticipantOpacityProbeHarness(Protocol):
    """Backend setup, reporting, and readback adapter used by the generic runner."""

    probe_set_digest: str

    def cases(self, target: RuntimeTarget) -> tuple[ParticipantOpacityProbeCase, ...]: ...

    def reported_observation(
        self,
        target: RuntimeTarget,
        case: ParticipantOpacityProbeCase,
        point_ref: str,
    ) -> ParticipantOpacityProbeObservation: ...

    def backend_readback(
        self,
        target: RuntimeTarget,
        case: ParticipantOpacityProbeCase,
        request: ParticipantOpacityReadbackRequest,
    ) -> ParticipantOpacityBackendReadback: ...


__all__ = [
    "OBSERVATION_FIELDS",
    "ParticipantOpacityBackendReadback",
    "ParticipantOpacityEvidenceOrigin",
    "ParticipantOpacityProbeCase",
    "ParticipantOpacityProbeHarness",
    "ParticipantOpacityProbeObservation",
    "ParticipantOpacityProbePoint",
    "ParticipantOpacityReadbackRequest",
    "ParticipantOpacityRealizationOwner",
]
