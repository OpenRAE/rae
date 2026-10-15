"""Bounded API-424/v2 slot evaluation inside the existing crossing authority.

All policy algebra and DTO validation belong to raes_contracts. This consumer
orders admitted slots and joins owner resolution to the runtime's pinned cut.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from graphlib import TopologicalSorter
from time import monotonic
from typing import TYPE_CHECKING, TypeVar

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model, control_digest
from raes_contracts.contracts.participant_control_composition_v2 import (
    control_slot_support_failure_v2,
    validate_control_support_v2,
)
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
from raes_contracts.contracts.participant_control_evaluation_v2 import (
    ControlStateProposalV2Model,
    ParticipantControlEvaluationV2Model,
    admitted_control_effect_ids_v2,
    derive_control_composition_v2,
)
from raes_contracts.contracts.participant_control_invocation import (
    ControlInvocationV2Model,
    ControlMechanismResultV2Model,
    control_predecessors_satisfied_v2,
    normalize_optional_control_result_v2,
    validate_control_stage_result_v2,
)
from raes_contracts.contracts.participant_control_resolution import validate_participant_control_resolved_context_v2
from raes_contracts.contracts.participant_control_support_v2 import ControlSupportAssessmentV2Model
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from .control_plane_mutation import external_control_plane_call
from .control_plane_store_revision import SnapshotRevisionConflict
from .participant_control_binding import ParticipantControlResolution, ParticipantControlRuntimeBinding
from .participant_control_provider_state import require_provider_state_extension, require_retained_provider_state
from .participant_crossing_mediation import PreparedParticipantCrossing
from .participant_crossing_state_cut import control_history_head_refs

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane
    from .participant_control_orchestration import ParticipantControlOutcome

_T = TypeVar("_T")


@dataclass
class _EvaluationCut:
    plane: RuntimeControlPlane
    revision: int
    generation: int
    deadline: float

    @classmethod
    def capture(cls, plane: RuntimeControlPlane) -> _EvaluationCut:
        return cls(
            plane,
            plane._snapshot_state.revision,
            plane._execution_generation,
            monotonic() + plane._supervision.execution_ms / 1000,
        )

    def require_current(self) -> None:
        plane = self.plane
        plane._assert_runtime_owner()
        current = plane._store.load_snapshot_state()
        if (
            current.revision != self.revision
            or plane._snapshot_state.revision != self.revision
            or plane._execution_generation != self.generation
            or plane._effect_admission_stopped
            or plane._store.effect_admission_stopped()
        ):
            # Do not refresh the CAS revision and then publish an old prepared snapshot.
            raise SnapshotRevisionConflict()

    def call(self, method: Callable[..., _T], *args: object, provider: bool = False) -> _T:
        self.require_current()
        remaining = min(self.plane._supervision.admission_ms, int((self.deadline - monotonic()) * 1000))
        if remaining <= 0:
            raise TimeoutError("participant control evaluation budget exhausted")
        try:
            with external_control_plane_call(self.plane):
                return self.plane._execution_adapter.call(
                    "resolution" if provider else "control", method, *deepcopy(args), timeout_ms=remaining
                )
        finally:
            self.require_current()


def resolve_v2_outcome(
    plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    crossing: PreparedParticipantCrossing,
    sink_kind: object,
) -> ParticipantControlOutcome:
    """Resolve total coverage, evaluate stages and validate at the original cut."""
    from .participant_control_orchestration import ParticipantControlOutcome, _request_refusal

    cut = _EvaluationCut.capture(plane)
    heads = control_history_head_refs(plane._snapshot, crossing.intent.participant_address)
    try:

        def resolve():
            resolution = binding.resolver.resolve(
                snapshot=deepcopy(plane._snapshot),
                intent=deepcopy(crossing.intent),
                crossing=deepcopy(crossing),
                sink_kind=sink_kind,
                expected_history_head_refs=heads,
            )
            if not isinstance(resolution, ParticipantControlResolution):
                raise ValueError("missing admitted evaluation")
            request = ParticipantControlRequestV2Model.model_validate(resolution.request.model_dump(mode="json"))
            if type(resolution.support) is not tuple or len(resolution.support) > 256:
                raise ValueError("invalid participant control support material")
            support = tuple(
                ControlSupportAssessmentV2Model.model_validate(item.model_dump(mode="json"))
                for item in resolution.support
            )
            return ParticipantControlResolution(
                request, support, resolution.incumbent_gate_disposition, resolution.incumbent_gate_evidence
            )

        resolution = cut.call(resolve)
        request = resolution.request
        refusal = _request_refusal(plane, binding, crossing, request, sink_kind, heads)
        if refusal is not None:
            return refusal
        require_retained_provider_state(plane._snapshot, request)
        validate_control_support_v2(request, resolution.support)
        calls, results, losses = _evaluate_slots(cut, binding, request, resolution.support)
        evaluation = _compose(binding, crossing, request, resolution, calls, results, losses)
        require_provider_state_extension(plane._snapshot, evaluation)
        context = cut.call(binding.resolver.validation_context, evaluation)
        # Context validation invokes independently supplied support/owner callbacks.
        # Those callbacks retain neither a state-writer permit nor an unbounded wait.
        cut.call(lambda: validate_participant_control_resolved_context_v2(evaluation, lambda _: context))
        cut.require_current()
        return ParticipantControlOutcome(
            evaluation.composition.disposition, "control-" + evaluation.composition.disposition, evaluation
        )
    except SnapshotRevisionConflict:
        raise
    except Exception:
        return ParticipantControlOutcome("unresolved", "control-context-invalid")


def _evaluate_slots(
    cut: _EvaluationCut, binding: ParticipantControlRuntimeBinding, request: ParticipantControlRequestV2Model, support
):
    slots = {item.slot_id: item for item in request.selection.slots}
    instances = {item.instance_id: item for item in request.selection.bindings}
    applicable = set(request.applicability.applicable_slot_ids)
    graph = {
        identity: tuple(dep.slot_id for dep in slots[identity].dependencies)
        for identity in slots
        if identity in applicable
    }
    calls, results, losses = [], {}, []
    ordered = tuple(TopologicalSorter(graph).static_order())
    required = set(request.applicability.required_slot_ids)
    # Required closure is dependency-complete, so it can finish before optional
    # work. Optional identities can then never reserve a future required ID.
    ordered = tuple(identity for identity in ordered if identity in required) + tuple(
        identity for identity in ordered if identity not in required
    )
    for slot_id in ordered:
        slot = slots[slot_id]
        predecessors = tuple(results[item.slot_id] for item in slot.dependencies)
        invocation, available = _stage_invocation(cut, binding, request, slot, instances, predecessors, results)
        support_failure = control_slot_support_failure_v2(request, slot_id, support)
        if support_failure is not None:
            result = _failure(invocation, instances[slot.instance_id].evidence, support_failure)
        elif available and control_predecessors_satisfied_v2(predecessors):
            result = _stage_result(cut, binding, request, invocation, predecessors)
        else:
            result = _failure(invocation, instances[slot.instance_id].evidence, "missing")
        result, loss = _optional_result(binding, request, invocation, result, results)
        if loss is not None:
            losses.append(loss)
        calls.append(invocation)
        results[slot_id] = result
    return tuple(calls), tuple(results.values()), tuple(losses)


def _stage_invocation(cut, binding, request, slot, instances, predecessors, previous_results):
    """Construct a ready or blocked descriptor without granting a provider call."""
    slot_id = slot.slot_id
    stage = binding.stages[slot_id]
    available = True
    try:

        def resolve_projection(detached_request, identity, inputs):
            value = binding.resolver.projection(detached_request, identity, inputs)
            value = ControlArtifactReferenceModel.model_validate(value.model_dump(mode="json"))
            if value.kind != "projection":
                raise ValueError("invalid authorized projection")
            return value

        projection = cut.call(resolve_projection, request, slot_id, predecessors)
    except SnapshotRevisionConflict:
        raise
    except Exception:
        # An admitted unavailable projection describes a blocked stage; it
        # is never passed to provider code and conveys no disclosure grant.
        projection, available = stage.unavailable_projection, False
    invocation = ControlInvocationV2Model(
        invocation_id=_stage_id(request, slot_id),
        instance_id=slot.instance_id,
        requested_slot_ids=(slot_id,),
        binding_digest=control_digest(instances[slot.instance_id]),
        context_digest=control_digest(request.context),
        predecessor_inputs=tuple(
            dict(slot_id=item.slot_id, kind=dep.kind, result_id=item.result_id, result_digest=control_digest(item))
            for dep, item in zip(slot.dependencies, predecessors, strict=True)
        ),
        state_input=dict(
            scope=instances[slot.instance_id].state_scope,
            state=next(item.state for item in request.context.provider_states if item.instance_id == slot.instance_id),
            source="committed",
            predecessor_invocation_id=None,
        ),
        projection=ControlArtifactReferenceModel.model_validate(projection.model_dump(mode="json")),
    )
    if stage.state_predecessor_slot_id is not None:
        predecessor = previous_results[stage.state_predecessor_slot_id]
        if predecessor.next_provider_state is None:
            available = False
        else:
            invocation = ControlInvocationV2Model.model_validate(
                {
                    **invocation.model_dump(mode="json"),
                    "state_input": dict(
                        scope=invocation.state_input.scope,
                        state=predecessor.next_provider_state,
                        source="tentative",
                        predecessor_invocation_id=_stage_id(request, predecessor.slot_id),
                    ),
                }
            )
    return invocation, available


def _optional_result(binding, request, invocation, result, previous_results):
    """Normalize only this slot; mandatory availability is unchanged."""
    slot_id = invocation.requested_slot_ids[0]
    if slot_id in request.applicability.required_slot_ids:
        return result, None
    instances = {item.instance_id: item for item in request.selection.bindings}
    applicable = set(request.applicability.applicable_slot_ids)
    slots = {item.slot_id: item for item in request.selection.slots}
    competing = tuple(
        instances[other.instance_id].state_scope
        for other in slots.values()
        if other.slot_id != slot_id
        and other.slot_id in applicable
        and binding.stages[other.slot_id].commit_on is not None
    )
    result, loss = normalize_optional_control_result_v2(
        request,
        invocation,
        result,
        evidence=instances[invocation.instance_id].evidence[0],
        competing_state_scopes=competing,
        reserved_result_ids=frozenset(item.result_id for item in previous_results.values()),
        executable_effects_supported=False,
    )
    return result, loss


def _stage_result(
    cut: _EvaluationCut,
    binding: ParticipantControlRuntimeBinding,
    request: ParticipantControlRequestV2Model,
    invocation: ControlInvocationV2Model,
    predecessors: tuple[ControlMechanismResultV2Model, ...],
) -> ControlMechanismResultV2Model:
    admitted = next(item for item in request.selection.bindings if item.instance_id == invocation.instance_id)
    try:

        def resolve():
            returned = binding.providers[invocation.instance_id].resolve_stage(
                ControlInvocationV2Model.model_validate(invocation.model_dump(mode="json"))
            )
            # The finite protocol returns a tuple. Never consume arbitrary provider iterators.
            if type(returned) is not tuple or len(returned) > 1:
                raise ValueError("provider returned an unbounded or duplicate stage response")
            if not returned:
                return _failure(invocation, admitted.evidence, "missing")
            result = ControlMechanismResultV2Model.model_validate(returned[0].model_dump(mode="json"))
            portable = result.model_dump(mode="json")
            if not validate_realization_value(portable, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant:
                raise ValueError("provider result exceeds portable material bounds")
            validate_control_stage_result_v2(request, invocation, result, predecessors)
            if result.next_provider_state is not None and binding.stages[result.slot_id].commit_on is None:
                raise ValueError("provider has no admitted state write")
            return result

        return cut.call(resolve, provider=True)
    except SnapshotRevisionConflict:
        raise
    except Exception:
        return _failure(invocation, admitted.evidence, "failed")


def _failure(
    invocation: ControlInvocationV2Model,
    evidence: tuple[ControlArtifactReferenceModel, ...],
    status: str,
) -> ControlMechanismResultV2Model:
    return ControlMechanismResultV2Model(
        result_id="absent:" + canonical_json_digest([invocation.invocation_id, invocation.requested_slot_ids[0]]),
        slot_id=invocation.requested_slot_ids[0],
        instance_id=invocation.instance_id,
        binding_digest=invocation.binding_digest,
        context_digest=invocation.context_digest,
        invocation_digest=control_digest(invocation),
        status=status,
        payload=None,
        evidence=evidence,
        next_provider_state=None,
    )


def _compose(binding, crossing, request, resolution, calls, results, losses):
    from .participant_control_orchestration import _evaluation_id

    required = set(request.applicability.required_slot_ids)
    decisions = [
        dict(
            decision_id=item.result_id,
            disposition=item.payload.disposition,
            rule=item.payload.rule,
            reasons=item.evidence,
        )
        for item in results
        if item.slot_id in required
        and item.payload is not None
        and item.payload.kind == "decision"
        and item.payload.disposition != "abstain"
    ]
    effects = [item.payload for item in results if item.payload is not None and item.payload.kind == "effect-request"]
    plan = derive_control_effect_plan_v2(
        parent_crossing=request.context.crossing,
        decisions=decisions,
        effects=effects,
        incumbent_gate_disposition=resolution.incumbent_gate_disposition,
        realized_effect_ids=(),
        parent_applied=False,
    )
    composition = derive_control_composition_v2(request, results, resolution.support, losses, plan)
    by_slot = {item.slot_id: item for item in results}
    proposals = tuple(
        ControlStateProposalV2Model(
            invocation_id=call.invocation_id,
            scope=call.state_input.scope,
            before=call.state_input.state,
            after=by_slot[call.requested_slot_ids[0]].next_provider_state,
            commit_on=binding.stages[call.requested_slot_ids[0]].commit_on,
            predecessor_invocation_id=call.state_input.predecessor_invocation_id,
        )
        for call in calls
        if by_slot[call.requested_slot_ids[0]].next_provider_state is not None
        and (
            binding.stages[call.requested_slot_ids[0]].commit_on == "evaluation"
            or (composition.disposition == "eligible" and plan.parent_disposition == "permit")
        )
    )
    admitted = admitted_control_effect_ids_v2(composition, plan)
    return ParticipantControlEvaluationV2Model(
        schema_version="participant-control-evaluation/v2",
        evaluation_id=_evaluation_id(crossing, request),
        request=request,
        invocations=calls,
        results=results,
        support=resolution.support,
        lost_advice=losses,
        effect_plan=plan,
        state_proposals=proposals,
        composition=composition,
        commit=dict(
            expected_history_heads=request.context.expected_history_heads,
            coverage_digest=control_digest(request.applicability),
            result_digests=tuple(control_digest(item) for item in results),
            decision_digest=control_digest(plan),
            state_proposal_digests=tuple(control_digest(item) for item in proposals),
            effect_intent_digests=tuple(control_digest(item) for item in plan.effects if item.effect_id in admitted),
            effects_consumed=request.context.effects_consumed,
            status="prepared",
            receipt=None,
            dispatchable_effect_ids=(),
        ),
    )


def _stage_id(request: ParticipantControlRequestV2Model, slot_id: str) -> str:
    return "stage:" + canonical_json_digest([request.context.crossing.ref, request.context.attempt, slot_id])
