"""RUN-320 exact binding from an admitted selection to installed providers.

PC-01/PC-02: the runtime receives operator- or backend-constructed provider
instances and binds them to the instance identities the admitted apparatus
selected. Nothing here discovers, imports, downloads, or names executable code,
and a present ``resolve`` method establishes neither installation, capability,
authority, nor realization — API-407 support records own that question.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

from raes_backend_protocols.protocols import ParticipantControlProvider, ParticipantControlProviderV2
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import schema_bundle
from raes_contracts.contracts.participant_control_applicability import (
    ParticipantControlRequestV2Model,
    ParticipantControlSelectionV2Model,
)
from raes_contracts.contracts.participant_control_composition import ParticipantControlRequestModel
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel, require_kind
from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model
from raes_contracts.contracts.participant_control_resolution import (
    ParticipantControlValidationContext,
    ParticipantControlValidationContextV2,
)
from raes_contracts.contracts.participant_control_results import ControlEffectiveSupportModel
from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel
from raes_contracts.contracts.participant_control_support_v2 import ControlSupportAssessmentV2Model
from raes_contracts.errors import InvalidInputError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger

from .control_plane_mutation import external_control_plane_call
from .control_plane_store_revision import SnapshotRevisionConflict

_LOGGER = get_logger(__name__)
_CONTEXT_FAILED = "participant control resolver validation context failed"

PARTICIPANT_CONTROL_PROTOCOL_REVISION = "participant-control-provider/v1"


@dataclass(frozen=True)
class ParticipantControlResolution:
    """Owner-resolved admitted request, support and incumbent gate for one cut."""

    request: ParticipantControlRequestModel | ParticipantControlRequestV2Model
    support: tuple[ControlEffectiveSupportModel, ...] | tuple[ControlSupportAssessmentV2Model, ...]
    incumbent_gate_disposition: str
    incumbent_gate_evidence: ControlArtifactReferenceModel


class ParticipantControlRuntimeResolver(Protocol):
    """Trusted owner resolution, declared like the incumbent policy resolver.

    ``resolve`` returns the admitted request for the live cut, or ``None`` when
    modular control does not apply to it. ``validation_context`` supplies the
    independently resolved owner facts API-424 checks the evaluation against;
    neither may be satisfied from provider output. It is called for retained
    evaluations as well as fresh ones: resolve the original admitted inputs
    and current effect approval. ``effect_operation`` returns
    the incumbent owner input for one admitted effect, or ``None`` for an
    effect this apparatus has no owner for — declared here, like the rest of
    the protocol, rather than discovered per effect.
    """

    def resolve(self, **coordinates: object) -> ParticipantControlResolution | None: ...

    def validation_context(
        self, evaluation: object
    ) -> ParticipantControlValidationContext | ParticipantControlValidationContextV2: ...

    def effect_operation(self, request: object, context: object) -> object | None: ...


class ParticipantControlRuntimeResolverV2(ParticipantControlRuntimeResolver, Protocol):
    """Trusted disclosure owner for one exact content-addressed projection.

    Before returning a projection, independently validate the supplied predecessor
    results and authorize disclosure to this slot. The installed provider's
    scoped content resolver must resolve that reference to those exact detached
    inputs. Failure supplies no projection or provider invocation.
    """

    def projection(
        self,
        request: ParticipantControlRequestV2Model,
        slot_id: str,
        predecessors: tuple[ControlMechanismResultV2Model, ...],
    ) -> ControlArtifactReferenceModel: ...


@dataclass(frozen=True, kw_only=True)
class ParticipantControlStageBinding:
    """Operator-admitted state policy for one v2 slot, never provider claims."""

    unavailable_projection: ControlArtifactReferenceModel
    commit_on: Literal["evaluation", "parent-release"] | None = None
    state_predecessor_slot_id: str | None = None

    def __post_init__(self) -> None:
        projection = ControlArtifactReferenceModel.model_validate(self.unavailable_projection.model_dump(mode="json"))
        require_kind(projection, "projection")
        object.__setattr__(self, "unavailable_projection", projection)
        if self.commit_on not in {None, "evaluation", "parent-release"}:
            raise ValueError("invalid participant control state commit condition")


@dataclass(frozen=True)
class ParticipantControlRuntimeBinding:
    """Immutable admitted selection joined to its exact provider instances."""

    selection: ParticipantControlSelectionModel | ParticipantControlSelectionV2Model
    providers: Mapping[str, ParticipantControlProvider | ParticipantControlProviderV2]
    resolver: ParticipantControlRuntimeResolver | ParticipantControlRuntimeResolverV2
    stages: Mapping[str, ParticipantControlStageBinding] | None = None
    contract_digests: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        model = (
            ParticipantControlSelectionV2Model
            if isinstance(self.selection, ParticipantControlSelectionV2Model)
            else ParticipantControlSelectionModel
        )
        selection = model.model_validate(self.selection.model_dump(mode="python"))
        _require_published_protocol(selection)
        _require_exact_providers(selection, self.providers)
        _require_declared_resolver(self.resolver)
        object.__setattr__(self, "selection", selection)
        object.__setattr__(self, "providers", MappingProxyType(dict(self.providers)))
        if isinstance(selection, ParticipantControlSelectionV2Model):
            self._require_v2_inputs(selection)
        elif self.stages is not None or self.contract_digests is not None:
            raise ValueError("v2 participant control options require explicit v2 selection")

    def _require_v2_inputs(self, selection: ParticipantControlSelectionV2Model) -> None:
        contracts = ("participant-control-selection-v2", "participant-control-evaluation-v2")
        expected = {name: canonical_json_digest(schema_bundle()[name]) for name in contracts}
        if self.contract_digests != expected:
            raise ValueError("participant control v2 requires exact published contract content pins")
        slots = {item.slot_id: item for item in selection.slots}
        if self.stages is None or self.stages.keys() != slots.keys():
            raise ValueError("participant control v2 requires every admitted stage policy")
        for identity, stage in self.stages.items():
            if type(stage) is not ParticipantControlStageBinding:
                raise TypeError("participant control stage policy must use its typed binding")
            predecessor = stage.state_predecessor_slot_id
            if predecessor is not None and (
                predecessor not in {dep.slot_id for dep in slots[identity].dependencies}
                or slots[predecessor].instance_id != slots[identity].instance_id
            ):
                raise ValueError("tentative state must name a same-instance declared input predecessor")
        if not callable(getattr(self.resolver, "projection", None)):
            raise TypeError("participant control v2 requires a scoped projection resolver")
        object.__setattr__(self, "stages", MappingProxyType(dict(self.stages)))
        object.__setattr__(self, "contract_digests", MappingProxyType(dict(expected)))


def _require_published_protocol(selection: ParticipantControlSelectionModel) -> None:
    revision = (
        "participant-control-provider/v2"
        if isinstance(selection, ParticipantControlSelectionV2Model)
        else PARTICIPANT_CONTROL_PROTOCOL_REVISION
    )
    if any(binding.protocol_revision != revision for binding in selection.bindings):
        raise ValueError("participant control selection names an unpublished provider protocol revision")


def _require_exact_providers(
    selection: ParticipantControlSelectionModel,
    providers: Mapping[str, ParticipantControlProvider],
) -> None:
    if set(providers) != {binding.instance_id for binding in selection.bindings}:
        raise ValueError("participant control providers must exactly match the admitted selection instances")
    method = "resolve_stage" if isinstance(selection, ParticipantControlSelectionV2Model) else "resolve"
    for provider in providers.values():
        if not callable(getattr(provider, method, None)):
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
        # Isolation: the operator-supplied resolver failed; the context is missing.
        except Exception as exc:
            _LOGGER.exception(_CONTEXT_FAILED, exc_info=foreign_failure_record(exc))
            context = None
    return lambda _record: context


def resolve_v2_request(
    plane: object,
    cut: object,
    binding: ParticipantControlRuntimeBinding,
    crossing: object,
    sink_kind: object,
    heads: tuple[str, ...],
) -> ParticipantControlResolution | None:
    """Resolve and revalidate the admitted v2 request at the cut, or ``None`` after one failure record."""

    def resolve() -> ParticipantControlResolution:
        resolution = binding.resolver.resolve(
            snapshot=deepcopy(plane._snapshot),
            intent=deepcopy(crossing.intent),
            crossing=deepcopy(crossing),
            sink_kind=sink_kind,
            expected_history_head_refs=heads,
        )
        if not isinstance(resolution, ParticipantControlResolution):
            raise InvalidInputError("missing admitted evaluation")
        request = ParticipantControlRequestV2Model.model_validate(resolution.request.model_dump(mode="json"))
        if type(resolution.support) is not tuple or len(resolution.support) > 256:
            raise InvalidInputError("invalid participant control support material")
        support = tuple(
            ControlSupportAssessmentV2Model.model_validate(item.model_dump(mode="json")) for item in resolution.support
        )
        return ParticipantControlResolution(
            request, support, resolution.incumbent_gate_disposition, resolution.incumbent_gate_evidence
        )

    try:
        return cut.call(resolve)
    except SnapshotRevisionConflict:
        raise
    # Isolation: the operator-supplied resolver failed or returned a request that does not revalidate.
    except Exception as exc:
        _LOGGER.exception(
            "participant control v2 resolver failed; control is unresolved", exc_info=foreign_failure_record(exc)
        )
        return None


def resolve_control_context[T](resolve: Callable[[], T]) -> T | None:
    """Return the trusted context that ``resolve`` builds, or ``None`` after one failure record.

    ``resolve`` calls the operator-supplied ``validation_context`` and reads the
    context it returns. A stale cut is not a resolver failure, so it propagates.
    """

    try:
        return resolve()
    except SnapshotRevisionConflict:
        raise
    # Isolation: the operator-supplied resolver or the context that it returned failed.
    except Exception as exc:
        _LOGGER.exception(_CONTEXT_FAILED, exc_info=foreign_failure_record(exc))
        return None


def control_context_admits(validate: Callable[[], None]) -> bool:
    """Run the published validation of a resolved context; ``False`` when it does not admit.

    The published validation isolates the host callbacks in the context and logs
    their failures, so its ``ValueError`` refusal needs no second record here.
    """

    try:
        validate()
    except SnapshotRevisionConflict:
        raise
    except ValueError:
        return False
    # The cut, the budget or the runtime owner check failed in RAES code; it keeps its normal traceback.
    except RaesError:
        _LOGGER.exception("participant control context validation did not complete")
        return False
    return True


__all__ = (
    "PARTICIPANT_CONTROL_PROTOCOL_REVISION",
    "ParticipantControlResolution",
    "ParticipantControlRuntimeBinding",
    "ParticipantControlRuntimeResolver",
    "ParticipantControlRuntimeResolverV2",
    "ParticipantControlStageBinding",
    "control_context_admits",
    "fenced_validation_context",
    "resolve_control_context",
    "resolve_v2_request",
)
