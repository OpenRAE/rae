"""Portable evaluation records and pure local consistency checks for API-424."""

from __future__ import annotations

from collections.abc import Sequence
from graphlib import TopologicalSorter
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from .._canonical import canonical_json_digest
from ..json_ingress import parse_bounded_json_object
from .base import ContractModel
from .participant_control_coordinates import (
    ControlArtifactReferenceModel,
    ControlRef,
    ParticipantControlContextModel,
    require_unique,
)
from .participant_control_effect_composition import control_effect_blockers
from .participant_control_effects import ControlEffectRequestModel
from .participant_control_results import (
    ControlCompositionModel,
    ControlEffectiveSupportModel,
    ControlMechanismResultModel,
    ControlRealizationBindingModel,
)
from .participant_control_selection import (
    ControlMechanismBindingModel,
    ControlResultSlotModel,
    ParticipantControlSelectionModel,
)


def control_digest(record: ContractModel) -> str:
    """JCS digest of the complete portable record, including explicit nulls."""
    return canonical_json_digest(record.model_dump(mode="json"))


class ParticipantControlRequestModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    selection: ParticipantControlSelectionModel
    context: ParticipantControlContextModel

    @model_validator(mode="after")
    def _admitted_scope(self) -> Self:
        selection, context = self.selection, self.context
        if selection.apparatus != context.apparatus:
            raise ValueError("participant control apparatus binding differs")
        if {state.instance_id for state in context.provider_states} != {b.instance_id for b in selection.bindings}:
            raise ValueError("participant control provider-state coverage is incomplete")
        for binding in selection.bindings:
            if binding.memory_scope != context.memory_scope:
                raise ValueError("participant control memory binding differs")
            if not any(
                (a.participant_address, a.episode_id, a.direction, a.sink_ref, a.phase_ref, a.subject_kind)
                == (
                    context.participant_address,
                    context.episode_id,
                    context.direction,
                    context.sink_ref,
                    context.phase_ref,
                    context.subject.subject_kind,
                )
                for a in binding.applicability
            ):
                raise ValueError("participant control applicability is unresolved")
        bounds = selection.bounds
        if (
            context.depth > bounds.max_depth
            or context.effects_consumed > bounds.max_effects
            or context.attempt > bounds.max_attempts
            or context.order > bounds.expires_at_order
        ):
            raise ValueError("participant control causal bounds are exhausted")
        return self


class ParticipantControlEvaluationModel(ContractModel):
    """Complete contributor record. Eligibility is not authorization or dispatch."""

    model_config = ConfigDict(frozen=True)
    schema_version: Literal["participant-control-evaluation/v1"]
    evaluation_id: ControlRef
    request: ParticipantControlRequestModel
    results: Annotated[tuple[ControlMechanismResultModel, ...], Field(max_length=256)]
    support: Annotated[tuple[ControlEffectiveSupportModel, ...], Field(max_length=64)]
    composition: ControlCompositionModel
    realizations: Annotated[tuple[ControlRealizationBindingModel, ...], Field(max_length=256)]

    @model_validator(mode="after")
    def _evaluation(self) -> Self:
        validate_evaluation_structure(self)
        return self


def _result_satisfied(result: ControlMechanismResultModel) -> bool:
    if result.status != "resolved":
        return False
    return result.payload.kind != "decision" or result.payload.disposition == "permit"


def _validate_result_binding(
    result: ControlMechanismResultModel,
    slot: ControlResultSlotModel,
    binding: ControlMechanismBindingModel,
    context_digest: str,
) -> None:
    if result.instance_id != slot.instance_id or result.binding_digest != control_digest(binding):
        raise ValueError("mechanism result does not bind the selected instance")
    if result.context_digest != context_digest:
        raise ValueError("mechanism result uses a stale or different exact context")
    if result.payload is not None and result.payload.kind != slot.kind:
        raise ValueError("mechanism result payload does not match its typed slot")


def _validate_ifc_result(
    result: ControlMechanismResultModel,
    binding: ControlMechanismBindingModel,
    context: ParticipantControlContextModel,
) -> None:
    if result.payload is None or result.payload.kind != "ifc-fact":
        return
    profiles = {profile.ref for profile in binding.profiles}
    expected = (
        "teaching-influence"
        if result.payload.domain == "teaching-influence-domain/rev1"
        else "participant-boundary-flow-policy-v1"
    )
    if expected not in profiles:
        raise ValueError("IFC fact domain is not selected by its mechanism")
    if expected == "teaching-influence" and set(result.payload.source_refs) != set(context.inputs):
        raise ValueError("teaching propagation must cover every admitted input")


def contributing_result_ids(results: Sequence[ControlMechanismResultModel]) -> tuple[str, ...]:
    """Canonical contributor order; serialization only, never a precedence."""
    return tuple(result.result_id for result in sorted(results, key=lambda r: (r.instance_id, r.slot_id)))


def _result_index(
    selection: ParticipantControlSelectionModel,
    results: Sequence[ControlMechanismResultModel],
) -> dict[str, ControlMechanismResultModel]:
    index = {result.slot_id: result for result in results}
    require_unique(tuple(result.slot_id for result in results))
    require_unique(tuple(result.result_id for result in results))
    if index.keys() != {slot.slot_id for slot in selection.slots}:
        raise ValueError("every selected slot requires an explicit result or absence record")
    return index


def _result_blockers(
    request: ParticipantControlRequestModel,
    results: Sequence[ControlMechanismResultModel],
) -> set[str]:
    selection = request.selection
    context_digest = control_digest(request.context)
    bindings = {binding.instance_id: binding for binding in selection.bindings}
    slots = {slot.slot_id: slot for slot in selection.slots}
    index = _result_index(selection, results)
    for slot_id, result in index.items():
        slot = slots[slot_id]
        binding = bindings[slot.instance_id]
        _validate_result_binding(result, slot, binding, context_digest)
        _validate_ifc_result(result, binding, request.context)
    return _mandatory_blockers(selection, index)


def _mandatory_blockers(
    selection: ParticipantControlSelectionModel, results: dict[str, ControlMechanismResultModel]
) -> set[str]:
    graph = {slot.slot_id: {dep.slot_id for dep in slot.dependencies} for slot in selection.slots}
    satisfied = {}
    for identity in TopologicalSorter(graph).static_order():
        satisfied[identity] = _result_satisfied(results[identity]) and all(satisfied[dep] for dep in graph[identity])
    blockers = set()
    for slot in selection.slots:
        slot_id = slot.slot_id
        result = results[slot_id]
        if slot.role == "mandatory" and not _result_satisfied(result):
            blockers.add("slot:" + slot_id)
        if slot.role == "mandatory" and any(not satisfied[dep.slot_id] for dep in slot.dependencies):
            blockers.add("dependency:" + slot_id)
    return blockers


# MPC-06 consequences, strongest first. This renders one exact reason for a
# composition that already blocks; it never selects a winner among mechanisms.
_DISPOSITION_PRECEDENCE = ("conflict", "stale", "unsupported", "weakened", "deny", "withhold", "failed")
_UNSATISFIED_STATUS = {
    "stale": "stale",
    "unsupported": "unsupported",
    "weakened": "weakened",
    "failed": "failed",
    "missing": "failed",
    "unknown": "failed",
}


def _result_cause(result: ControlMechanismResultModel) -> str | None:
    if result.status != "resolved":
        return _UNSATISFIED_STATUS[result.status]
    payload = result.payload
    if payload is None or payload.kind != "decision" or payload.disposition == "permit":
        return None
    # A mandatory abstain is unsatisfied, never implicit permission.
    return payload.disposition if payload.disposition in {"deny", "withhold"} else "failed"


def _support_cause(item: ControlEffectiveSupportModel) -> str:
    if item.effective_level == "unsupported":
        return "unsupported"
    if item.status != "resolved":
        return _UNSATISFIED_STATUS[item.status]
    return "weakened"


def _slot_causes(
    selection: ParticipantControlSelectionModel,
    results: dict[str, ControlMechanismResultModel],
    slot_id: str,
) -> set[str]:
    """Collect the exact unsatisfied reasons in one slot's dependency closure."""
    slots = {slot.slot_id: slot for slot in selection.slots}
    causes: set[str] = set()
    pending, seen = [slot_id], set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        cause = _result_cause(results[current])
        if cause is not None:
            causes.add(cause)
        pending.extend(dependency.slot_id for dependency in slots[current].dependencies)
    return causes


def _composition_disposition(
    request: ParticipantControlRequestModel,
    results: Sequence[ControlMechanismResultModel],
    support: Sequence[ControlEffectiveSupportModel],
    blockers: set[str],
    incumbent_gate_disposition: str,
) -> str:
    if not blockers:
        return "eligible"
    indexed = {result.slot_id: result for result in results}
    supported = {item.instance_id: item for item in support}
    causes: set[str] = set()
    for blocker in blockers:
        prefix, _, identity = blocker.partition(":")
        if prefix in {"slot", "dependency"}:
            causes |= _slot_causes(request.selection, indexed, identity)
        elif prefix == "support":
            causes.add(_support_cause(supported[identity]))
        elif prefix == "predecessor":
            # A required predecessor withholds its parent until it is realized.
            causes.add("withhold")
        elif blocker == "effect-conflict":
            causes.add("conflict")
        elif blocker == "incumbent-gates":
            causes.add(_UNSATISFIED_STATUS.get(incumbent_gate_disposition, incumbent_gate_disposition))
    return next((item for item in _DISPOSITION_PRECEDENCE if item in causes), "failed")


def _support_blockers(
    request: ParticipantControlRequestModel,
    support: Sequence[ControlEffectiveSupportModel],
) -> set[str]:
    bindings = request.selection.bindings
    index = {item.instance_id: item for item in support}
    require_unique(tuple(item.instance_id for item in support))
    if index.keys() != {binding.instance_id for binding in bindings}:
        raise ValueError("support must cover every selected instance exactly")
    blockers = set()
    for item in support:
        if item.context_digest != control_digest(request.context):
            raise ValueError("effective support is bound to a different context")
        if item.status != "resolved" or item.effective_level != "exact":
            blockers.add("support:" + item.instance_id)
    return blockers


def _evaluation_blockers(
    request: ParticipantControlRequestModel,
    results: Sequence[ControlMechanismResultModel],
    support: Sequence[ControlEffectiveSupportModel],
    realizations: Sequence[ControlRealizationBindingModel],
    incumbent_gate_disposition: str,
) -> set[str]:
    blockers = (
        _result_blockers(request, results)
        | _support_blockers(request, support)
        | control_effect_blockers(request, results, realizations)
    )
    if incumbent_gate_disposition != "permit":
        blockers.add("incumbent-gates")
    return blockers


def derive_control_composition(
    request: ParticipantControlRequestModel,
    results: Sequence[ControlMechanismResultModel],
    support: Sequence[ControlEffectiveSupportModel],
    realizations: Sequence[ControlRealizationBindingModel] = (),
    *,
    incumbent_gate_disposition: str,
    incumbent_gate_evidence: ControlArtifactReferenceModel,
) -> ControlCompositionModel:
    """Derive the exact MPC-05/MPC-06 composition for one resolved evaluation.

    This is the only supported way to build a ``ControlCompositionModel``: it
    reuses the same blocker accounting ``validate_evaluation_structure`` checks,
    so no consumer reproduces slot, dependency, support, effect-conflict or
    disposition logic of its own. It composes recorded results; it neither
    resolves a provider nor authorizes an effect.
    """
    blockers = _evaluation_blockers(request, results, support, realizations, incumbent_gate_disposition)
    return ControlCompositionModel(
        rule_revision="sem-235/rev1",
        disposition=_composition_disposition(request, results, support, blockers, incumbent_gate_disposition),
        blockers=tuple(sorted(blockers)),
        contributing_result_ids=contributing_result_ids(results),
        incumbent_gate_disposition=incumbent_gate_disposition,
        incumbent_gate_evidence=incumbent_gate_evidence,
    )


def validate_evaluation_structure(document: ParticipantControlEvaluationModel) -> None:
    blockers = _evaluation_blockers(
        document.request,
        document.results,
        document.support,
        document.realizations,
        document.composition.incumbent_gate_disposition,
    )
    if document.composition.contributing_result_ids != contributing_result_ids(document.results):
        raise ValueError("composition must preserve every contributor in canonical order")
    if tuple(sorted(blockers)) != document.composition.blockers:
        raise ValueError("composition must retain exactly every blocking reason")
    # The disposition is the canonical cause of the blockers, not merely their
    # presence: a stale mandatory result recorded as ``deny`` would misstate
    # why composition failed. A parsed or persisted record carries the same
    # guarantee as one derived at runtime.
    canonical = _composition_disposition(
        document.request,
        document.results,
        document.support,
        blockers,
        document.composition.incumbent_gate_disposition,
    )
    if document.composition.disposition != canonical:
        raise ValueError("composition disposition must be the canonical cause of its blockers")


PREDECESSOR_BLOCKER_PREFIX = "predecessor:"
SUBSEQUENT_PHASE = "subsequent"
REQUIRED_PREDECESSOR_PHASE = "required-predecessor"


def admitted_effect_phase(document: ParticipantControlEvaluationModel) -> str | None:
    """Return the effect phase this composition admits, or ``None`` for none.

    PC-09: an eligible composition admits its subsequent effects. A composition
    blocked only by required predecessors admits exactly those predecessors,
    after which its parent is reevaluated at a fresh cut. Any other blocker —
    a conflict, a stale cut, an unsupported or weakened mechanism, a denial —
    admits nothing, so a requested effect from such an evaluation is a rejected
    proposal and never an intent. One definition serves every consumer, so a
    rejected proposal cannot be admitted by one index and refused by another.
    """

    blockers = set(document.composition.blockers)
    if not blockers:
        return SUBSEQUENT_PHASE
    if all(blocker.startswith(PREDECESSOR_BLOCKER_PREFIX) for blocker in blockers):
        return REQUIRED_PREDECESSOR_PHASE
    return None


def admitted_effect_requests(
    document: ParticipantControlEvaluationModel,
) -> tuple[ControlEffectRequestModel, ...]:
    """Every effect request this composition actually admits, in record order."""

    phase = admitted_effect_phase(document)
    if phase is None:
        return ()
    return tuple(
        result.payload
        for result in document.results
        if isinstance(result.payload, ControlEffectRequestModel) and result.payload.phase == phase
    )


def parse_participant_control_evaluation(source: str | bytes) -> ParticipantControlEvaluationModel:
    """Bound ingress and expose no rejected value in public parse failures."""
    try:
        payload = parse_bounded_json_object(source, max_bytes=1_048_576, max_depth=32)
        return ParticipantControlEvaluationModel.model_validate(payload)
    except (TypeError, ValueError):
        raise ValueError("invalid participant control evaluation") from None
