"""RUN-320 exact binding from an admitted selection to installed providers.

PC-01/PC-02: the runtime receives operator- or backend-constructed provider
instances and binds them to the instance identities the admitted apparatus
selected. Nothing here discovers, imports, downloads, or names executable code,
and a present ``resolve`` method establishes neither installation, capability,
authority, nor realization — API-407 support records own that question.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from raes_backend_protocols.protocols import ParticipantControlProvider
from raes_contracts.contracts.participant_control_composition import ParticipantControlRequestModel
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
from raes_contracts.contracts.participant_control_resolution import ParticipantControlValidationContext
from raes_contracts.contracts.participant_control_results import ControlEffectiveSupportModel
from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel

from .control_plane_mutation import external_control_plane_call

PARTICIPANT_CONTROL_PROTOCOL_REVISION = "participant-control-provider/v1"


@dataclass(frozen=True)
class ParticipantControlResolution:
    """Owner-resolved admitted request, support and incumbent gate for one cut."""

    request: ParticipantControlRequestModel
    support: tuple[ControlEffectiveSupportModel, ...]
    incumbent_gate_disposition: str
    incumbent_gate_evidence: ControlArtifactReferenceModel


class ParticipantControlRuntimeResolver(Protocol):
    """Trusted owner resolution, declared like the incumbent policy resolver.

    ``resolve`` returns the admitted request for the live cut, or ``None`` when
    modular control does not apply to it. ``validation_context`` supplies the
    independently resolved owner facts API-424 checks the evaluation against;
    neither may be satisfied from provider output. ``effect_operation`` returns
    the incumbent owner input for one admitted effect, or ``None`` for an
    effect this apparatus has no owner for — declared here, like the rest of
    the protocol, rather than discovered per effect.
    """

    def resolve(self, **coordinates: object) -> ParticipantControlResolution | None: ...

    def validation_context(self, evaluation: object) -> ParticipantControlValidationContext: ...

    def effect_operation(self, request: object, context: object) -> object | None: ...


@dataclass(frozen=True)
class ParticipantControlRuntimeBinding:
    """Immutable admitted selection joined to its exact provider instances."""

    selection: ParticipantControlSelectionModel
    providers: Mapping[str, ParticipantControlProvider]
    resolver: ParticipantControlRuntimeResolver

    def __post_init__(self) -> None:
        selection = ParticipantControlSelectionModel.model_validate(self.selection.model_dump(mode="python"))
        _require_published_protocol(selection)
        _require_exact_providers(selection, self.providers)
        _require_declared_resolver(self.resolver)
        object.__setattr__(self, "selection", selection)
        object.__setattr__(self, "providers", MappingProxyType(dict(self.providers)))


def _require_published_protocol(selection: ParticipantControlSelectionModel) -> None:
    if any(binding.protocol_revision != PARTICIPANT_CONTROL_PROTOCOL_REVISION for binding in selection.bindings):
        raise ValueError("participant control selection names an unpublished provider protocol revision")


def _require_exact_providers(
    selection: ParticipantControlSelectionModel,
    providers: Mapping[str, ParticipantControlProvider],
) -> None:
    if set(providers) != {binding.instance_id for binding in selection.bindings}:
        raise ValueError("participant control providers must exactly match the admitted selection instances")
    for provider in providers.values():
        if not callable(getattr(provider, "resolve", None)):
            raise TypeError("participant control provider must implement the published resolve protocol")


def _require_declared_resolver(resolver: ParticipantControlRuntimeResolver) -> None:
    declared = ("resolve", "validation_context", "effect_operation")
    if not all(callable(getattr(resolver, name, None)) for name in declared):
        raise TypeError("participant control resolver must implement the declared runtime protocol")


def fenced_validation_context(
    control_plane: object,
    binding: ParticipantControlRuntimeBinding,
    record: object,
) -> Callable[[object], ParticipantControlValidationContext | None]:
    """Resolve the trusted context under the external-call re-entry fence.

    ``validation_context`` is operator-supplied resolver code, called while the
    runtime may hold the mutation authority. Invoked bare, it could re-enter a
    mutating runtime API that commits even when the enclosing validation then
    fails, or advance state before the caller captures its commit cut. So it
    runs under the same fence as every other resolver and provider call, and
    the validator receives the already-resolved value. A resolver failure is a
    missing context, which the sanitizing validator reports without detail.
    """

    with external_control_plane_call(control_plane):
        try:
            context = binding.resolver.validation_context(record)
        except Exception:
            context = None
    return lambda _record: context


__all__ = (
    "PARTICIPANT_CONTROL_PROTOCOL_REVISION",
    "ParticipantControlResolution",
    "ParticipantControlRuntimeBinding",
    "ParticipantControlRuntimeResolver",
    "fenced_validation_context",
)
