"""ADR-112 inject trigger requests and claimed occurrences; neither executes an effect."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..addressing import CompiledAddress
from ..canonical import canonical_json_digest
from ..operation_lifecycle import OperationAdmissionContext, OperationKind
from ..versions import INJECT_OCCURRENCE_SCHEMA_VERSION, INJECT_TRIGGER_REQUEST_SCHEMA_VERSION
from .backend_operation import (
    OperationArtifactReferenceModel,
    OperationContractModel,
    OperationIdentifier,
    OperationPositive,
)

_MAX_CLAIMS = 1024
_CLAIM_CONFLICT = "inject trigger retry conflicts with the original claim"


def _require_family(address: str, family: str) -> None:
    if not address.startswith(f"orchestration.{family}."):
        raise ValueError(f"inject trigger requires a compiled orchestration {family} address")


def _require_binding_of(inject: str, binding: str) -> None:
    """A compiled node binding renders as ``orchestration.inject-binding.<node>.<inject>``."""

    prefix = "orchestration.inject-binding."
    if binding.startswith(prefix) and not binding.endswith("." + inject.removeprefix("orchestration.inject.")):
        raise ValueError("inject trigger bindings must belong to the requested inject")


class InjectTargetBindingModel(OperationContractModel):
    """One selected concrete realization instance; entity names never select hosts."""

    binding: CompiledAddress
    instance: OperationIdentifier
    revision: OperationIdentifier


class InjectIndependentPlacementModel(OperationContractModel):
    """Direct request through an admitted independent binding; no schedule is invented."""

    kind: Literal["independent"] = "independent"


class InjectEventPlacementModel(OperationContractModel):
    """Event-anchored request; the event's precondition assertions remain binding."""

    kind: Literal["event"] = "event"
    event: CompiledAddress

    @model_validator(mode="after")
    def _event(self) -> Self:
        _require_family(self.event, "event")
        return self


class InjectSchedulePlacementModel(OperationContractModel):
    """One uniquely identified schedule slot, claimable at most once in its run."""

    kind: Literal["schedule"] = "schedule"
    event: CompiledAddress
    script: CompiledAddress
    story: CompiledAddress | None = None
    slot: OperationIdentifier

    @model_validator(mode="after")
    def _schedule(self) -> Self:
        _require_family(self.event, "event")
        _require_family(self.script, "script")
        if self.story is not None:
            _require_family(self.story, "story")
        return self


InjectPlacement = Annotated[
    InjectIndependentPlacementModel | InjectEventPlacementModel | InjectSchedulePlacementModel,
    Field(discriminator="kind"),
]


class InjectTriggerRequestModel(OperationContractModel):
    """A caller's selection within admitted intent; acceptance is not an effect."""

    schema_version: Literal[INJECT_TRIGGER_REQUEST_SCHEMA_VERSION] = INJECT_TRIGGER_REQUEST_SCHEMA_VERSION
    request_key: OperationIdentifier
    occurrence_id: OperationIdentifier
    target_scope: OperationIdentifier
    run_scope: OperationIdentifier
    plan: OperationArtifactReferenceModel
    inject: CompiledAddress
    bindings: tuple[InjectTargetBindingModel, ...] = Field(min_length=1, max_length=256)
    placement: InjectPlacement
    input_ref: OperationArtifactReferenceModel | None = None
    expected_head: OperationIdentifier

    @model_validator(mode="after")
    def _selection(self) -> Self:
        _require_family(self.inject, "inject")
        if self.plan.contract_id != "orchestration-plan-v1":
            raise ValueError("inject trigger must pin its compiled orchestration plan")
        for binding in self.bindings:
            _require_binding_of(self.inject, binding.binding)
        instances = [(binding.binding, binding.instance) for binding in self.bindings]
        if len(instances) != len(set(instances)):
            raise ValueError("inject trigger cannot select one realization instance twice")
        return self


class InjectOrderModel(OperationContractModel):
    """Trusted ordering-authority token; neither arrival order nor a clock tick."""

    scope: OperationIdentifier
    predecessor: OperationIdentifier
    position: OperationPositive


class InjectOccurrenceModel(OperationContractModel):
    """Atomic claim of one occurrence under exact admitted pins; not dispatch or outcome."""

    schema_version: Literal[INJECT_OCCURRENCE_SCHEMA_VERSION] = INJECT_OCCURRENCE_SCHEMA_VERSION
    operation_id: OperationIdentifier
    request: InjectTriggerRequestModel
    admission: OperationAdmissionContext
    admission_evidence: tuple[OperationArtifactReferenceModel, ...] = Field(min_length=1, max_length=64)
    store_revision: OperationIdentifier
    order: InjectOrderModel
    scenario: OperationArtifactReferenceModel
    source: OperationArtifactReferenceModel
    realization: OperationArtifactReferenceModel
    evidence_requirements: tuple[OperationArtifactReferenceModel, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _claim(self) -> Self:
        request, admission = self.request, self.admission
        if admission.operation_kind is not OperationKind.ORCHESTRATION:
            raise ValueError("inject occurrences are admitted as orchestration operations")
        if (admission.target_scope, admission.run_scope) != (request.target_scope, request.run_scope):
            raise ValueError("inject occurrence admission must bind the requested target and run")
        if (self.order.scope, self.order.predecessor) != (request.run_scope, request.expected_head):
            raise ValueError("inject order must follow the requested run head without rebasing")
        identities = [request.request_key, request.occurrence_id, self.operation_id, *_slot(self)]
        if len(identities) != len(set(identities)):
            raise ValueError("request key, occurrence, operation and slot identities must stay distinct")
        return self


def _slot(occurrence: InjectOccurrenceModel) -> tuple[str, ...]:
    placement = occurrence.request.placement
    return (placement.slot,) if isinstance(placement, InjectSchedulePlacementModel) else ()


def inject_trigger_request_digest(request: InjectTriggerRequestModel) -> str:
    return canonical_json_digest(request.model_dump(mode="json"))


def inject_occurrence_digest(occurrence: InjectOccurrenceModel) -> str:
    return canonical_json_digest(occurrence.model_dump(mode="json"))


def inject_retry_key(occurrence: InjectOccurrenceModel) -> tuple[str, str, str]:
    """Return the ADR-104 scoped retry identity: actor, operation kind and client key."""

    admission = occurrence.admission
    return admission.actor_id, admission.operation_kind.value, occurrence.request.request_key


def require_inject_trigger_retry(
    occurrence: InjectOccurrenceModel, request: InjectTriggerRequestModel, *, actor_id: str
) -> InjectOccurrenceModel:
    """Return the original claim for an exact retry; never admit, rebase or dispatch again.

    Callers authorize receipt access before any lookup, so a conflict reveals no
    other actor's claim. Changed content under the same key is a conflict.
    """

    if (actor_id, request.request_key) != (occurrence.admission.actor_id, occurrence.request.request_key):
        raise ValueError(_CLAIM_CONFLICT)
    if inject_trigger_request_digest(request) != inject_trigger_request_digest(occurrence.request):
        raise ValueError(_CLAIM_CONFLICT)
    return occurrence


def validate_inject_occurrence_claims(occurrences: Sequence[InjectOccurrenceModel]) -> None:
    """Reject reuse of a retry key, occurrence, operation, schedule slot or order position."""

    if len(occurrences) > _MAX_CLAIMS:
        raise ValueError("inject occurrence claim set exceeds its bound")
    if len({(item.request.target_scope, item.request.run_scope) for item in occurrences}) > 1:
        raise ValueError("inject occurrence claims must share one target/run store")
    claims = {
        "retry key": [inject_retry_key(item) for item in occurrences],
        "occurrence": [item.request.occurrence_id for item in occurrences],
        "operation": [item.operation_id for item in occurrences],
        "order position": [item.order.position for item in occurrences],
        "schedule slot": [slot for item in occurrences for slot in _slot(item)],
    }
    for label, values in claims.items():
        if len(values) != len(set(values)):
            raise ValueError(f"inject occurrence {label} is already claimed")
