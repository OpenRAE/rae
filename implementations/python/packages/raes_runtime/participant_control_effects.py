"""Dispatch governed effects through their separately admitted operation owners.

The drain caller is authorized before committed state is read. Effects retain
originating principals, logical claims and causal budgets. V1 and v2 records
keep their recorded interpretations; required predecessors, parent outcomes
and independent consequences use their respective contract-owned rules.
An admitted intent, an owner submission and an observed effect remain distinct.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING

from raes_contracts.contracts import InjectTriggerRequestModel
from raes_contracts.contracts.participant_control_composition import (
    ParticipantControlEvaluationModel,
    admitted_effect_phase,
)
from raes_contracts.contracts.participant_control_coordinates import (
    ControlLogicalEffectKeyModel,
)
from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model
from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.contracts.participant_control_results import ControlRealizationBindingModel
from raes_contracts.contracts.participant_inject_application import ParticipantInjectApplicationModel
from raes_contracts.runtime_state import OperationKind

from .control_plane_mutation import control_plane_mutation, external_control_plane_call
from .control_plane_store import ControlPlaneOperationRecord
from .participant_control_intents import ParticipantControlIntent
from .participant_control_receipts import (
    claim_effect,
    claim_outcome,
    never_dispatched,
    origin_principal,
    owner_record,
    realization,
    require_drain_authority,
)
from .participant_control_records import commit_participant_control_realization
from .participant_crossing_mediation import ParticipantCrossingEvidence

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane
    from .control_plane_security import ControlPlaneIdentity
    from .participant_control_binding import ParticipantControlRuntimeBinding

_APPLIED = "applied"
_WITHHELD = "withheld"
_FAILED = "failed"
_INDETERMINATE = "indeterminate"
_UNSUPPORTED = "unsupported"
# Only an owner's recorded outcome is durable. A withhold or an unsupported
# owner is an ordering or availability fact recomputed on every drain, and an
# uncertain outcome stays open on its claim for the incumbent recovery path.
_RECORDED = frozenset({_APPLIED, _FAILED})


@dataclass(frozen=True)
class ParticipantControlEffectOperation:
    """One incumbent operation input the owner of this effect kind accepts.

    The crossing evidence is part of that input. It names the audience the
    owner's crossing is decided for, so it comes from the trusted resolver with
    the rest of the owner input — never from whoever requests the drain.
    """

    kind: str
    view: object | None = None
    intent: ParticipantControlIntent | None = None
    crossing_evidence: ParticipantCrossingEvidence | None = None
    inject_application: ParticipantInjectApplicationModel | None = None
    inject_request: InjectTriggerRequestModel | None = None
    participant_address: str | None = None


@dataclass(frozen=True)
class ParticipantControlEffectRealization:
    """Bounded, value-independent outcome of one dispatched effect."""

    effect_id: str
    disposition: str
    receipt_ref: str


def dispatch_participant_control_effects(
    control_plane: object,
    participant_address: str,
    *,
    identity: object,
) -> tuple[ParticipantControlEffectRealization, ...]:
    """Dispatch a governed pass, prioritizing committed cancellation work.

    The caller is authorized before anything committed is read. It requests
    execution; it never becomes the principal an effect acts for.
    """

    binding = getattr(control_plane, "_participant_control", None)
    if binding is None:
        raise ValueError("participant control effect dispatch requires a bound participant control configuration")
    require_drain_authority(control_plane, participant_address, identity)
    from .participant_control_effect_drain import has_pending_cancellation

    drain = _DrainState(realized={})
    cancellation_pending = has_pending_cancellation(control_plane, participant_address)
    if cancellation_pending:
        with (
            control_plane._mutation_authority.supervision(),
            control_plane_mutation(control_plane, OperationKind.PARTICIPANT_CONTROL),
        ):
            _drain_pass(control_plane, binding, participant_address, drain, cancellation_only=True)
            drain.cancellations.update(drain.outcomes)
    ordinary = ExitStack()
    try:
        ordinary.enter_context(control_plane_mutation(control_plane, OperationKind.PARTICIPANT_CONTROL))
    except TimeoutError:
        if cancellation_pending:
            return _ordered_outcomes(control_plane, participant_address, drain)
        raise
    with ordinary:
        _drain_pass(control_plane, binding, participant_address, drain)
    return _ordered_outcomes(control_plane, participant_address, drain)


def _ordered_outcomes(plane, participant, drain):
    from .participant_control_projection import control_projection

    order = control_projection(plane).outcome_order.get(participant, {})
    keys = sorted(drain.outcomes, key=lambda key: (key not in drain.cancellations, order[key]))
    return tuple(drain.outcomes[key] for key in keys)


def _drain_pass(
    control_plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    participant_address: str,
    drain: _DrainState,
    *,
    cancellation_only: bool = False,
) -> None:
    from .participant_control_effect_drain import dispatch_v2_effects
    from .participant_control_projection import control_projection

    control_plane._reload_derived_state()
    projection = control_projection(control_plane)
    retained = tuple(projection.pending.get(participant_address, {}).values())
    evaluations = [record for record in retained if isinstance(record, ParticipantControlEvaluationModel)]
    from .participant_control_operation_index import operation_index

    origins = operation_index(control_plane).origins
    if not cancellation_only:
        drain.outcomes.update(projection.completed.get(participant_address, {}))
    drain.realized.update(projection.realized.get(participant_address, {}))
    dispatch_v2_effects(control_plane, binding, retained, drain, cancellation_only=cancellation_only)
    if not cancellation_only:
        for evaluation in evaluations:
            phase = admitted_effect_phase(evaluation)
            if phase is not None and not evaluation.realizations:
                _dispatch_evaluation(
                    control_plane,
                    binding,
                    evaluation,
                    drain,
                    origin=origins.get((participant_address, evaluation.evaluation_id)),
                    phase=phase,
                )
    control_projection(control_plane).finish_drain(participant_address, drain)


@dataclass
class _DrainState:
    """One outcome and one claimant per logical effect key, for one drain.

    PC-11 allocates identity once per key, so a later evaluation that
    re-requests a key reports the first outcome and can never claim it under
    another origin.
    """

    realized: dict[ControlLogicalEffectKeyModel, ParticipantControlEffectRealization]
    outcomes: dict[ControlLogicalEffectKeyModel, ParticipantControlEffectRealization] = field(default_factory=dict)
    claimants: dict[ControlLogicalEffectKeyModel, ControlPlaneOperationRecord | None] = field(default_factory=dict)
    cancellations: set[ControlLogicalEffectKeyModel] = field(default_factory=set)


def _realized_keys(
    evaluations: list[ParticipantControlEvaluationModel],
) -> dict[ControlLogicalEffectKeyModel, ParticipantControlEffectRealization]:
    """Index the recorded outcome of every logical key already realized.

    A realization is resolved against the request in *its own* evaluation. A
    shared effect-id table across evaluations would be last-writer-wins, so a
    later — possibly rejected — reuse of an effect id under a different logical
    key could reassign an earlier applied receipt to that other key.
    """

    realized: dict[ControlLogicalEffectKeyModel, ParticipantControlEffectRealization] = {}
    for evaluation in evaluations:
        requests = {
            result.payload.effect_id: result.payload
            for result in evaluation.results
            if isinstance(result.payload, ControlEffectRequestModel)
        }
        for retained in evaluation.realizations:
            request = requests.get(retained.effect_id)
            if request is not None and retained.disposition in _RECORDED:
                realized[request.key] = ParticipantControlEffectRealization(
                    effect_id=retained.effect_id,
                    disposition=retained.disposition,
                    receipt_ref=retained.receipt.ref,
                )
    return realized


def _ordered_requests(
    evaluation: ParticipantControlEvaluationModel,
    phase: str,
) -> list[ControlEffectRequestModel]:
    """Order this phase's requests so a predecessor is always reached first.

    Record order is serialization, never execution order: PC-07 declares the
    causal order through ``predecessor_effect_ids`` and the composition already
    rejected a cycle, so a stable topological walk is the admitted order.
    """

    requests = {
        result.payload.effect_id: result.payload
        for result in evaluation.results
        if isinstance(result.payload, ControlEffectRequestModel)
    }
    graph = {identity: set(request.predecessor_effect_ids) & requests.keys() for identity, request in requests.items()}
    ordered = [requests[identity] for identity in TopologicalSorter(graph).static_order()]
    return [request for request in ordered if request.phase == phase]


def _dispatch_evaluation(
    control_plane: object,
    binding: object,
    evaluation: ParticipantControlEvaluationModel,
    drain: _DrainState,
    *,
    origin: ControlPlaneOperationRecord | None,
    phase: str,
) -> None:
    applied: dict[str, str] = {}
    for request in _ordered_requests(evaluation, phase):
        if request.key not in drain.claimants:
            drain.claimants[request.key] = origin
        if request.key not in drain.outcomes:
            drain.outcomes[request.key] = drain.realized.get(request.key) or _dispatched(
                control_plane,
                binding,
                evaluation,
                drain.claimants[request.key],
                request,
                applied,
            )
        applied[request.effect_id] = drain.outcomes[request.key].disposition


def _dispatched(
    control_plane: object,
    binding: object,
    evaluation: ParticipantControlEvaluationModel | ParticipantControlEvaluationV2Model,
    origin: ControlPlaneOperationRecord | None,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    applied: Mapping[str, str],
) -> ParticipantControlEffectRealization:
    outcome, claim = _effect_outcome(control_plane, binding, evaluation, origin, request, applied)
    if claim is not None:
        # Recorded as soon as it is known, so a predecessor's outcome is
        # durable before any dependent is dispatched on the strength of it.
        if isinstance(evaluation, ParticipantControlEvaluationV2Model):
            from .participant_control_effect_evidence import commit_effect_outcome

            owner = owner_record(control_plane, claim, request)
            if owner is not None:
                outcome = outcome.model_copy(
                    update={"receipt": outcome.receipt.model_copy(update={"ref": owner.receipt.operation_id})}
                )
            commit_effect_outcome(control_plane, evaluation, outcome, claim)
        else:
            commit_participant_control_realization(control_plane, binding, evaluation, outcome, claim=claim)
    return ParticipantControlEffectRealization(
        effect_id=outcome.effect_id,
        disposition=outcome.disposition,
        receipt_ref=outcome.receipt.ref,
    )


def _withheld_dependent(
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    applied: Mapping[str, str],
) -> ControlRealizationBindingModel | None:
    """Withhold an effect whose declared predecessor was not applied.

    A dependent runs only after its predecessor is realized; a failed,
    unsupported or indeterminate predecessor leaves it withheld rather than
    dispatched out of its admitted order. A withhold is an ordering decision,
    so it is recomputed on every drain and never recorded as an outcome: once
    the predecessor applies, the dependent is simply admitted.
    """

    unsatisfied = [
        identity for identity in request.predecessor_effect_ids if applied.get(identity, _UNSUPPORTED) != _APPLIED
    ]
    if not unsatisfied:
        return None
    return realization(request, _WITHHELD, "withheld." + request.effect_id)


def _effect_outcome(
    control_plane: object,
    binding: object,
    evaluation: ParticipantControlEvaluationModel | ParticipantControlEvaluationV2Model,
    origin: ControlPlaneOperationRecord | None,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    applied: Mapping[str, str],
) -> tuple[ControlRealizationBindingModel, ControlPlaneOperationRecord | None]:
    """Decide one effect's outcome, and the claim that carries it if any."""

    withheld = _withheld_dependent(request, applied)
    operation = None
    if withheld is None and origin is not None:
        if isinstance(request, ControlEffectRequestV2Model):
            from .participant_control_effect_owners import prepare_v2_effect_dispatch

            prepared = prepare_v2_effect_dispatch(control_plane, binding, evaluation, origin, request)
            if prepared is not None:
                return prepared
        operation = _effect_operation(control_plane, binding, evaluation, request)
    if operation is None:
        # No provable originating operation means no principal to act for, and
        # no owner input means no owner: both are reported, never silently
        # skipped, and nothing is claimed or dispatched.
        reason = "unattributed." if origin is None else "unsupported."
        return withheld or realization(request, _UNSUPPORTED, reason + request.effect_id), None
    return _claimed_outcome(control_plane, origin, request, operation)


def _claimed_outcome(
    control_plane: object,
    origin: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    operation: ParticipantControlEffectOperation,
) -> tuple[ControlRealizationBindingModel, ControlPlaneOperationRecord | None]:
    claim = claim_effect(control_plane, origin, request)
    if claim is None:
        # The store refused because this claim identity already holds a
        # *different* request. That record is provably not this effect's, so
        # it is never read as an outcome, and nothing is dispatched.
        return realization(request, _FAILED, "claim-conflict." + request.effect_id), None
    if claim.fresh or never_dispatched(control_plane, claim.record, request):
        disposition = _submitted_outcome(
            control_plane,
            claim.record,
            request,
            operation,
            principal=origin_principal(
                control_plane, origin, getattr(request.target, "participant_address", operation.participant_address)
            ),
        )
    else:
        # An earlier drain's dispatch may have begun: classify that attempt
        # from its durable records, never repeat it.
        from .participant_control_effect_owners import resume_owned_effect

        resume_owned_effect(control_plane, claim.record, request)
        disposition = claim_outcome(control_plane, claim.record, request)
    return realization(request, disposition, claim.record.receipt.operation_id), claim.record


def _submitted_outcome(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    operation: ParticipantControlEffectOperation,
    *,
    principal: object,
) -> str:
    """Submit through the owner as the originating principal and read the result.

    A recorded owner decides the outcome. Without one, an admission refusal
    fails this fixed request; other errors propagate and leave recovery open.
    """

    try:
        from .control_plane_operation_context import effect_operation_parent

        with effect_operation_parent(claim.receipt.operation_id):
            _submit(control_plane, claim, request, operation, principal=principal)
    except Exception as error:
        if owner_record(control_plane, claim, request) is None:
            if isinstance(error, (PermissionError, ValueError)):
                return _FAILED
            raise
    return claim_outcome(control_plane, claim, request)


def _effect_operation(
    control_plane: object,
    binding: object,
    evaluation: ParticipantControlEvaluationModel | ParticipantControlEvaluationV2Model,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
) -> ParticipantControlEffectOperation | None:
    """Resolve the incumbent operation input, or ``None`` for an unsupported owner."""

    try:
        if isinstance(evaluation, ParticipantControlEvaluationV2Model):
            from .participant_control_evaluation_v2 import _EvaluationCut

            operation = _EvaluationCut.capture(control_plane).call(
                binding.resolver.effect_operation, request, evaluation.request.context
            )
        else:
            with external_control_plane_call(control_plane):
                operation = binding.resolver.effect_operation(request, evaluation.request.context)
    except Exception:
        return None
    if not isinstance(operation, ParticipantControlEffectOperation) or operation.kind != request.target.kind:
        return None
    if isinstance(request, ControlEffectRequestV2Model):
        from .participant_control_effect_owners import supports_effect_operation

        origin = control_plane._operations.get(evaluation.commit.receipt.ref)
        supported = supports_effect_operation(control_plane, request, operation, evaluation.request.context, origin)
    else:
        supported = _binds_request(operation, request, evaluation.request.context)
    return operation if supported else None


def _binds_request(
    operation: ParticipantControlEffectOperation,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    context: object,
) -> bool:
    """The owner input must be the exact effect the admitted request names.

    Scope alone is not identity: an owner operation that merely shares this
    participant and episode proves nothing about the requested effect, yet its
    receipt would be recorded as that effect's realization. Every coordinate
    the closed target declares is bound to the owner input before submission.
    """

    if isinstance(request, ControlEffectRequestV2Model) and operation.kind in {"inject", "interrupt"}:
        from .participant_control_effect_owners import binds_owned_effect

        return binds_owned_effect(operation, request, context)
    evidence = operation.crossing_evidence
    if not isinstance(evidence, ParticipantCrossingEvidence):
        return False
    from .participant_control_effect_owners import owner_input_bindings

    bound = owner_input_bindings(operation.kind)
    return (
        bound is not None
        and evidence.audience_scope_ref == context.audience_ref
        and all(actual == expected for actual, expected in bound(operation, request.target, context))
    )


def _submit(
    control_plane: RuntimeControlPlane,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    operation: ParticipantControlEffectOperation,
    *,
    principal: ControlPlaneIdentity,
) -> None:
    from .participant_control_effect_owners import submit_effect_operation

    submit_effect_operation(control_plane, claim, request, operation, principal=principal)


__all__ = (
    "ParticipantControlEffectOperation",
    "ParticipantControlEffectRealization",
    "dispatch_participant_control_effects",
)
