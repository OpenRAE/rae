"""Typed provider/v2 invocation inputs and result binding for API-424."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel, PrefixedDigestString
from .participant_control_applicability import (
    ControlMechanismBindingV2Model,
    ControlResultSlotV2Model,
    ControlStateScopeV2Model,
    ParticipantControlRequestV2Model,
    control_digest,
)
from .participant_control_coordinates import (
    Artifacts,
    ControlArtifactReferenceModel,
    ControlRef,
    Evidence,
    ResultKind,
    require_kind,
    require_unique,
)
from .participant_control_decisions_v2 import ControlEffectRequestV2Model
from .participant_control_results import (
    ControlAdvisoryModel,
    ControlDecisionModel,
    ControlIFCFact,
    ControlMechanismResultModel,
)

ControlResultPayloadV2 = Annotated[
    ControlIFCFact | ControlDecisionModel | ControlAdvisoryModel | ControlEffectRequestV2Model,
    Field(discriminator="kind"),
]


class ControlPredecessorInputV2Model(ContractModel):
    """Content-bound reference to one detached, typed predecessor result."""

    model_config = ConfigDict(frozen=True)
    slot_id: ControlRef
    kind: ResultKind
    result_id: ControlRef
    result_digest: PrefixedDigestString


class ControlStateInputV2Model(ContractModel):
    model_config = ConfigDict(frozen=True)
    scope: ControlStateScopeV2Model
    state: ControlArtifactReferenceModel
    source: Literal["committed", "tentative"]
    predecessor_invocation_id: ControlRef | None

    @model_validator(mode="after")
    def _source(self) -> Self:
        require_kind(self.state, "provider-state")
        if (self.source == "tentative") != (self.predecessor_invocation_id is not None):
            raise ValueError("tentative state requires its exact predecessor invocation")
        return self


class ControlInvocationV2Model(ContractModel):
    """One slot/stage call with immutable, disclosure-authorized inputs."""

    model_config = ConfigDict(frozen=True)
    invocation_id: ControlRef
    instance_id: ControlRef
    requested_slot_ids: Annotated[tuple[ControlRef, ...], Field(min_length=1, max_length=256)]
    binding_digest: PrefixedDigestString
    context_digest: PrefixedDigestString
    predecessor_inputs: Annotated[tuple[ControlPredecessorInputV2Model, ...], Field(max_length=256)]
    state_input: ControlStateInputV2Model
    projection: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _identities(self) -> Self:
        require_unique(self.requested_slot_ids)
        require_unique(tuple(item.slot_id for item in self.predecessor_inputs))
        require_kind(self.projection, "projection")
        return self


class ControlMechanismResultV2Model(ControlMechanismResultModel):
    """A typed output bound to the complete invocation input identity."""

    invocation_digest: PrefixedDigestString
    payload: ControlResultPayloadV2 | None
    rule_outcome: Literal["not-triggered"] | None = None
    evaluated_basis: Artifacts = ()

    @model_validator(mode="after")
    def _resolved_payload(self) -> Self:
        if self.rule_outcome == "not-triggered":
            if self.status != "resolved" or self.payload is not None or not self.evaluated_basis:
                raise ValueError("not-triggered rule must be resolved with an evaluated basis and no effect")
        elif (self.status == "resolved") != (self.payload is not None):
            raise ValueError("only a resolved mechanism result carries a typed payload")
        if self.evaluated_basis and self.rule_outcome != "not-triggered":
            raise ValueError("evaluated false-trigger basis needs the not-triggered outcome")
        if self.next_provider_state is not None:
            require_kind(self.next_provider_state, "provider-state")
            if self.status != "resolved":
                raise ValueError("unresolved results cannot propose provider state")
        return self


class ControlLostAdviceV2Model(ContractModel):
    """Safe, bounded evidence for a discarded optional contribution."""

    model_config = ConfigDict(frozen=True)
    slot_id: ControlRef
    reason: Literal["malformed", "missing", "unknown", "stale", "failed", "weakened", "unsupported", "conflict"]
    evidence: Evidence


def normalize_optional_result_failure_v2(
    request: ParticipantControlRequestV2Model,
    invocation: ControlInvocationV2Model,
    raw_result: object,
    *,
    result_id: str,
    evidence: ControlArtifactReferenceModel | dict,
) -> tuple[ControlMechanismResultV2Model, ControlLostAdviceV2Model]:
    """Discard one rejected optional output without exposing provider text.

    The caller must already have isolated the invocation. This function never
    catches an evaluation-wide failure or converts a required input to advice.
    """

    if len(invocation.requested_slot_ids) != 1:
        raise ValueError("optional failure normalization requires one slot")
    slot_id = invocation.requested_slot_ids[0]
    if slot_id not in request.applicability.applicable_slot_ids:
        raise ValueError("optional failure slot is not applicable")
    if slot_id in request.applicability.required_slot_ids:
        raise ValueError("mandatory participant control result cannot be normalized as optional")
    try:
        ControlMechanismResultV2Model.model_validate(raw_result)
    except (TypeError, ValueError):
        pass
    else:
        raise ValueError("optional result is already structurally valid")
    evidence = ControlArtifactReferenceModel.model_validate(evidence)
    require_kind(evidence, "evidence")
    result = ControlMechanismResultV2Model(
        result_id=result_id,
        slot_id=slot_id,
        instance_id=invocation.instance_id,
        binding_digest=invocation.binding_digest,
        context_digest=invocation.context_digest,
        invocation_digest=control_digest(invocation),
        status="failed",
        payload=None,
        evidence=(evidence,),
        next_provider_state=None,
    )
    loss = ControlLostAdviceV2Model(slot_id=slot_id, reason="malformed", evidence=(evidence,))
    return result, loss


def _satisfied(result: ControlMechanismResultV2Model) -> bool:
    if result.status != "resolved":
        return False
    payload = result.payload
    return result.rule_outcome == "not-triggered" or (
        payload is not None and (payload.kind != "decision" or payload.disposition == "permit")
    )


def validate_control_invocations_v2(
    request: ParticipantControlRequestV2Model,
    invocations: tuple[ControlInvocationV2Model, ...] | list[ControlInvocationV2Model | dict],
    results: tuple[ControlMechanismResultV2Model, ...] | list[ControlMechanismResultV2Model | dict],
) -> None:
    """Check the exact slot DAG and predecessor/state input bindings.

    This local check cannot attest that a provider actually consumed its input;
    installation and trusted disclosure resolution remain separate gates.
    """

    calls = tuple(ControlInvocationV2Model.model_validate(item) for item in invocations)
    outputs = tuple(ControlMechanismResultV2Model.model_validate(item) for item in results)
    require_unique(tuple(call.invocation_id for call in calls))
    require_unique(tuple(result.result_id for result in outputs))
    require_unique(tuple(result.slot_id for result in outputs))
    slots = {slot.slot_id: slot for slot in request.selection.slots}
    bindings = {binding.instance_id: binding for binding in request.selection.bindings}
    by_slot: dict[str, ControlInvocationV2Model] = {}
    for call in calls:
        for slot_id in call.requested_slot_ids:
            if slot_id in by_slot:
                raise ValueError("participant control slot has duplicate invocations")
            by_slot[slot_id] = call
    expected = set(request.applicability.applicable_slot_ids)
    if by_slot.keys() != expected or {item.slot_id for item in outputs} != expected:
        raise ValueError("participant control invocation or result coverage is incomplete")
    result_by_slot = {result.slot_id: result for result in outputs}
    cut_digest = control_digest(request.context)
    for call in calls:
        binding = _validate_call_identity(call, bindings.get(call.instance_id), cut_digest)
        _validate_call_state(call, binding, request, calls, outputs)
        _validate_call_predecessors(call, slots, result_by_slot)
        _validate_call_results(call, slots, result_by_slot)


def _validate_call_identity(
    call: ControlInvocationV2Model, binding: ControlMechanismBindingV2Model | None, cut_digest: str
) -> ControlMechanismBindingV2Model:
    if binding is None or call.binding_digest != control_digest(binding) or call.context_digest != cut_digest:
        raise ValueError("participant control invocation differs from the admitted binding or cut")
    if call.state_input.scope != binding.state_scope:
        raise ValueError("participant control invocation state scope differs")
    return binding


def _validate_call_state(
    call: ControlInvocationV2Model,
    binding: ControlMechanismBindingV2Model,
    request: ParticipantControlRequestV2Model,
    calls: tuple[ControlInvocationV2Model, ...],
    outputs: tuple[ControlMechanismResultV2Model, ...],
) -> None:
    if call.state_input.source == "committed":
        states = {state.instance_id: state.state for state in request.context.provider_states}
        if call.state_input.state != states.get(call.instance_id):
            raise ValueError("participant control invocation state version differs")
        return
    predecessor = next(
        (item for item in calls if item.invocation_id == call.state_input.predecessor_invocation_id), None
    )
    if predecessor is None or predecessor.instance_id != binding.instance_id:
        raise ValueError("participant control tentative state predecessor is absent")
    proposals = {
        result.next_provider_state
        for result in outputs
        if result.slot_id in predecessor.requested_slot_ids and result.next_provider_state is not None
    }
    if proposals != {call.state_input.state}:
        raise ValueError("participant control tentative state does not bind a predecessor proposal")


def _validate_call_predecessors(
    call: ControlInvocationV2Model,
    slots: dict[str, ControlResultSlotV2Model],
    result_by_slot: dict[str, ControlMechanismResultV2Model],
) -> None:
    declared = {dep.slot_id: dep.kind for slot_id in call.requested_slot_ids for dep in slots[slot_id].dependencies}
    if declared.keys() & set(call.requested_slot_ids):
        raise ValueError("participant control predecessor cannot be produced in the same invocation")
    supplied = {item.slot_id: item for item in call.predecessor_inputs}
    if supplied.keys() != declared.keys():
        raise ValueError("participant control predecessor input coverage is incomplete")
    for slot_id, item in supplied.items():
        _validate_predecessor_input(call, item, declared[slot_id], result_by_slot)


def _validate_predecessor_input(
    call: ControlInvocationV2Model,
    item: ControlPredecessorInputV2Model,
    declared_kind: str,
    result_by_slot: dict[str, ControlMechanismResultV2Model],
) -> None:
    predecessor = result_by_slot.get(item.slot_id)
    if (
        predecessor is None
        or item.kind != declared_kind
        or predecessor.result_id != item.result_id
        or control_digest(predecessor) != item.result_digest
    ):
        raise ValueError("participant control predecessor result identity or type differs")
    if not _satisfied(predecessor) and any(
        result_by_slot[slot_id].status == "resolved" for slot_id in call.requested_slot_ids
    ):
        raise ValueError("participant control unsatisfied predecessor cannot feed a resolved result")


def _validate_call_results(
    call: ControlInvocationV2Model,
    slots: dict[str, ControlResultSlotV2Model],
    result_by_slot: dict[str, ControlMechanismResultV2Model],
) -> None:
    for slot_id in call.requested_slot_ids:
        slot = slots[slot_id]
        result = result_by_slot[slot_id]
        _validate_call_result_identity(call, slot, result)
        if result.rule_outcome == "not-triggered" and slot.kind != "effect-request":
            raise ValueError("not-triggered result requires a rule/effect slot")
        if result.payload is not None and result.payload.kind != slot.kind:
            raise ValueError("participant control result does not match its typed slot")


def _validate_call_result_identity(
    call: ControlInvocationV2Model, slot: ControlResultSlotV2Model, result: ControlMechanismResultV2Model
) -> None:
    if (
        slot.instance_id != call.instance_id
        or result.instance_id != call.instance_id
        or result.binding_digest != call.binding_digest
        or result.context_digest != call.context_digest
        or result.invocation_digest != control_digest(call)
    ):
        raise ValueError("participant control result differs from its exact invocation")
