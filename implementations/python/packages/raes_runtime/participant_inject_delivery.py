"""Trusted result projection for the DSL-142 / ADR-112 composition boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from raes_contracts.contracts.inject_occurrence_outcome import InjectOccurrenceCorrelationModel
from raes_contracts.contracts.participant_inject_application import (
    ParticipantInjectApplicationModel,
    ParticipantInjectContentModel,
)
from raes_contracts.errors import InvalidInputError
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import ParticipantInjectDeliveryRuntime, RuntimeModel

from .participant_control_runtime import ParticipantControlLiveCut
from .participant_crossing_mediation import ParticipantCrossingEvidence


@dataclass(frozen=True, kw_only=True)
class ParticipantInjectResolution:
    """Owner disclosure and live order evidence, independently of world success."""

    content: ParticipantInjectContentModel
    evidence: ParticipantCrossingEvidence
    cut: ParticipantControlLiveCut


class ParticipantInjectResolver(Protocol):
    def resolve_delivery(
        self,
        delivery: ParticipantInjectDeliveryRuntime,
        application: ParticipantInjectApplicationModel,
        correlation: InjectOccurrenceCorrelationModel,
        snapshot: object,
    ) -> ParticipantInjectResolution: ...


@dataclass(frozen=True, kw_only=True)
class ParticipantInjectRuntimeBinding:
    """Explicit projection installation under original instantiated compiler context."""

    model: RuntimeModel
    resolver: ParticipantInjectResolver

    def __post_init__(self) -> None:
        if not isinstance(self.model, RuntimeModel) or self.model.realization_instance is None:
            raise TypeError("inject delivery requires retained compiler context")
        if not callable(getattr(self.resolver, "resolve_delivery", None)):
            raise TypeError("inject delivery requires an installed projection owner")
        try:
            canonical = compile_runtime_model(self.model.realization_instance)
        except InvalidInputError as exc:
            raise ValueError("inject delivery must match its original compiler context") from exc
        if canonical != self.model:
            raise ValueError("inject delivery must match its original compiler context")
        object.__setattr__(self, "model", deepcopy(self.model))
