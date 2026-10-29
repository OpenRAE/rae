"""Typed participant action precondition/effect/failure models (SEM-211)."""

from enum import Enum

from pydantic import Field, field_validator, model_validator

from ._base import SDLModel


class ParticipantPreconditionClass(str, Enum):
    """SEM-211 precondition classes for participant action applicability."""

    AUTHORITY = "authority"
    CAPABILITY = "capability"
    TARGET = "target"
    KNOWLEDGE = "knowledge"
    RESOURCE = "resource"
    TEMPORAL = "temporal"
    INTERACTION = "interaction"
    REALIZATION = "realization"


class ParticipantEffectClass(str, Enum):
    """SEM-211 effect classes for participant action results."""

    INTENDED_EFFECT = "intended_effect"
    SIDE_EFFECT = "side_effect"
    OBSERVATION_EFFECT = "observation_effect"
    VISIBILITY_EFFECT = "visibility_effect"
    DETECTION_EFFECT = "detection_effect"
    EVIDENCE_EFFECT = "evidence_effect"
    NO_EFFECT = "no_effect"
    UNKNOWN_EFFECT = "unknown_effect"


class ParticipantFailureClass(str, Enum):
    """SEM-211 portable failure classes for participant action attempts."""

    PRECONDITION_UNSATISFIED = "precondition_unsatisfied"
    UNSUPPORTED_ACTION = "unsupported_action"
    TARGET_UNAVAILABLE = "target_unavailable"
    AUTHORITY_DENIED = "authority_denied"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"
    CONTENTION_LOST = "contention_lost"
    PARTIAL_SUCCESS = "partial_success"
    UNSAFE_WITHHELD = "unsafe_withheld"
    BACKEND_ERROR = "backend_error"
    UNKNOWN = "unknown"


class ParticipantActionPrecondition(SDLModel):
    """Typed SEM-211 applicability precondition on an action contract."""

    precondition_id: str
    precondition_class: ParticipantPreconditionClass
    description: str
    support_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("precondition_id", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant action precondition fields must be non-empty")
        return value

    @field_validator("support_refs", "evidence_refs")
    @classmethod
    def _require_non_empty_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant action precondition refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("participant action precondition refs must be unique")
        return values


class ParticipantActionEffect(SDLModel):
    """Typed SEM-211 effect declaration on an action contract."""

    effect_id: str
    effect_class: ParticipantEffectClass
    description: str
    target_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("effect_id", "description")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant action effect fields must be non-empty")
        return value

    @field_validator("target_refs", "evidence_refs")
    @classmethod
    def _require_non_empty_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant action effect refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("participant action effect refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_effect_evidence(self) -> ParticipantActionEffect:
        if self.effect_class not in {ParticipantEffectClass.NO_EFFECT, ParticipantEffectClass.UNKNOWN_EFFECT}:
            if not self.target_refs and not self.evidence_refs:
                raise ValueError(f"{self.effect_class.value} effects require target_refs or evidence_refs")
        return self


class ParticipantBackendFailureMapping(SDLModel):
    """Mapping from a backend diagnostic code to a portable SEM-211 failure."""

    backend_error_code: str
    failure_class: ParticipantFailureClass
    diagnostic: str

    @field_validator("backend_error_code", "diagnostic")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant backend failure mapping fields must be non-empty")
        return value
