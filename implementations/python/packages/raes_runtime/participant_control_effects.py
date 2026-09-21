"""RUN-320 governed dispatch of admitted participant-control effects.

PC-09/PC-11: a requested effect is neither permission nor execution. Each
admitted *subsequent* effect becomes a separately admitted operation through
the incumbent owner of its closed target kind, executed only after its parent
committed, and recorded as an append-only realization transition. A required
predecessor never reaches this path: it withholds its parent, so the parent's
composition is not eligible.

The runtime never synthesizes an effect's content. The trusted resolver returns
the incumbent operation input the owner already accepts, and the runtime
verifies that input is the exact effect the request names. There is no
universal executor, callback registry, or backend-name branch: an owner the
resolver cannot supply is reported ``unsupported`` with zero dispatch.

Whose effect it is, and how its outcome is known, is decided in
``participant_control_receipts``: the drain caller is authorized before any
committed state is read, each effect acts for the principal of the operation
that admitted it, and the scan, claims, owner submissions and realization
append all happen under one held mutation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from graphlib import TopologicalSorter

from raes_contracts.contracts.participant_control_composition import (
    ParticipantControlEvaluationModel,
    admitted_effect_phase,
)
from raes_contracts.contracts.participant_control_coordinates import (
    ControlLogicalEffectKeyModel,
)
from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel
from raes_contracts.contracts.participant_control_results import ControlRealizationBindingModel
from raes_contracts.runtime_state import OperationKind

from .control_plane_mutation import control_plane_mutation, external_control_plane_call
from .control_plane_store import ControlPlaneOperationRecord
from .participant_control_intents import ParticipantControlIntent
from .participant_control_receipts import (
    claim_effect,
    claim_outcome,
    never_dispatched,
    origin_principal,
    originating_operations,
    owner_idempotency_key,
    owner_record,
    realization,
    require_drain_authority,
)
from .participant_control_records import commit_participant_control_realization
from .participant_crossing_mediation import ParticipantCrossingEvidence

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
    """Dispatch every committed, unrealized effect claim for one participant.

    The caller is authorized before anything committed is read. It requests
    execution; it never becomes the principal an effect acts for.
    """

    binding = getattr(control_plane, "_participant_control", None)
    if binding is None:
        raise ValueError("participant control effect dispatch requires a bound participant control configuration")
    require_drain_authority(control_plane, participant_address, identity)
    # One mutation: two drains can never both observe an effect as unrealized.
    with control_plane_mutation(control_plane, OperationKind.PARTICIPANT_CONTROL):
        control_plane._reload_derived_state()
        history = control_plane._snapshot.participant_control_evaluation_history.get(participant_address, ())
        evaluations = [ParticipantControlEvaluationModel.model_validate(record) for record in history]
        origins = originating_operations(control_plane, participant_address)
        realized = _realized_keys(evaluations)
        # One outcome and one claimant per logical effect key. PC-11 allocates
        # identity once per key, so a later evaluation that re-requests a key
        # reports the first outcome and can never claim it under another origin.
        outcomes: dict[ControlLogicalEffectKeyModel, ParticipantControlEffectRealization] = {}
        claimants: dict[ControlLogicalEffectKeyModel, ControlPlaneOperationRecord | None] = {}
        for evaluation in evaluations:
            phase = admitted_effect_phase(evaluation)
            if phase is None or evaluation.realizations:
                # A realization transition records outcomes; it admits nothing.
                continue
            _dispatch_evaluation(
                control_plane,
                binding,
                evaluation,
                realized,
                outcomes,
                claimants,
                origin=origins.get(evaluation.evaluation_id),
                phase=phase,
            )
        return tuple(outcomes.values())


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
    realized: dict[ControlLogicalEffectKeyModel, ParticipantControlEffectRealization],
    outcomes: dict[ControlLogicalEffectKeyModel, ParticipantControlEffectRealization],
    claimants: dict[ControlLogicalEffectKeyModel, ControlPlaneOperationRecord | None],
    *,
    origin: ControlPlaneOperationRecord | None,
    phase: str,
) -> None:
    applied: dict[str, str] = {}
    for request in _ordered_requests(evaluation, phase):
        if request.key not in claimants:
            claimants[request.key] = origin
        if request.key not in outcomes:
            outcomes[request.key] = realized.get(request.key) or _dispatched(
                control_plane,
                binding,
                evaluation,
                claimants[request.key],
                request,
                applied,
            )
        applied[request.effect_id] = outcomes[request.key].disposition


def _dispatched(
    control_plane: object,
    binding: object,
    evaluation: ParticipantControlEvaluationModel,
    origin: ControlPlaneOperationRecord | None,
    request: ControlEffectRequestModel,
    applied: Mapping[str, str],
) -> ParticipantControlEffectRealization:
    outcome, claim = _effect_outcome(control_plane, binding, evaluation, origin, request, applied)
    if claim is not None:
        # Recorded as soon as it is known, so a predecessor's outcome is
        # durable before any dependent is dispatched on the strength of it.
        commit_participant_control_realization(control_plane, binding, evaluation, outcome, claim=claim)
    return ParticipantControlEffectRealization(
        effect_id=outcome.effect_id,
        disposition=outcome.disposition,
        receipt_ref=outcome.receipt.ref,
    )


def _withheld_dependent(
    request: ControlEffectRequestModel,
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
    evaluation: ParticipantControlEvaluationModel,
    origin: ControlPlaneOperationRecord | None,
    request: ControlEffectRequestModel,
    applied: Mapping[str, str],
) -> tuple[ControlRealizationBindingModel, ControlPlaneOperationRecord | None]:
    """Decide one effect's outcome, and the claim that carries it if any."""

    withheld = _withheld_dependent(request, applied)
    if withheld is not None:
        return withheld, None
    if origin is None:
        # No provable originating operation means no principal to act for.
        # That is reported, never silently skipped, and nothing is dispatched.
        return realization(request, _UNSUPPORTED, "unattributed." + request.effect_id), None
    operation = _effect_operation(control_plane, binding, evaluation, request)
    if operation is None:
        return realization(request, _UNSUPPORTED, "unsupported." + request.effect_id), None
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
            principal=origin_principal(control_plane, origin, request.target.participant_address),
        )
    else:
        # An earlier drain's dispatch may have begun: classify that attempt
        # from its durable records, never repeat it.
        disposition = claim_outcome(control_plane, claim.record, request)
    return realization(request, disposition, claim.record.receipt.operation_id), claim.record


def _submitted_outcome(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel,
    operation: ParticipantControlEffectOperation,
    *,
    principal: object,
) -> str:
    """Submit through the owner as the originating principal and read the result.

    The owner's durable record decides whenever one exists. With none, the
    owner stopped before claiming, so nothing began — and only the owner's own
    refusal of this request (its authority or its validity) is an outcome of
    the effect. Every input the owner sees is fixed by the admitted effect, its
    originating principal and the trusted resolver, so that refusal cannot be
    caused by whoever requested the drain. Any other error is a condition of
    the moment, not of the effect: it propagates, the claim stays open, and a
    later drain resumes.
    """

    try:
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
    evaluation: ParticipantControlEvaluationModel,
    request: ControlEffectRequestModel,
) -> ParticipantControlEffectOperation | None:
    """Resolve the incumbent operation input, or ``None`` for an unsupported owner."""

    try:
        with external_control_plane_call(control_plane):
            operation = binding.resolver.effect_operation(request, evaluation.request.context)
    except Exception:
        return None
    if not isinstance(operation, ParticipantControlEffectOperation) or operation.kind != request.target.kind:
        return None
    return operation if _binds_request(operation, request, evaluation.request.context) else None


def _binds_request(
    operation: ParticipantControlEffectOperation,
    request: ControlEffectRequestModel,
    context: object,
) -> bool:
    """The owner input must be the exact effect the admitted request names.

    Scope alone is not identity: an owner operation that merely shares this
    participant and episode proves nothing about the requested effect, yet its
    receipt would be recorded as that effect's realization. Every coordinate
    the closed target declares is bound to the owner input before submission.
    """

    target = request.target
    evidence = operation.crossing_evidence
    if not isinstance(evidence, ParticipantCrossingEvidence) or evidence.audience_scope_ref != context.audience_ref:
        return False
    if operation.kind == "inject":
        view = operation.view
        return (
            getattr(view, "participant_address", None) == target.participant_address
            and getattr(view, "episode_id", None) == target.episode_id
            and getattr(view, "view_id", None) == target.result_item_ref
            and getattr(view, "source_snapshot_ref", None) == context.state_cut.cut_ref
            and getattr(view, "visibility_projection_ref", None) == target.disclosure_ref.ref
        )
    if operation.kind == "handoff":
        intent = operation.intent
        return (
            getattr(intent, "kind", None) == "handoff"
            and getattr(intent, "episode_id", None) == target.episode_id
            and getattr(intent, "declaration_ref", None) == target.transition.ref
            and getattr(intent, "expected_state_revision", None) == target.expected_state_revision
            and getattr(intent, "completion_evidence_ref", None) == target.completion_obligation.ref
        )
    return False


def _submit(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel,
    operation: ParticipantControlEffectOperation,
    *,
    principal: object,
) -> None:
    """Submit through the incumbent owner of this closed effect kind.

    The owner re-authorizes the principal it is given and claims its own
    operation under a key derived from this effect's claim, so its durable
    record — not the value returned here — carries the outcome.
    """

    idempotency_key = owner_idempotency_key(claim)
    if operation.kind == "inject":
        control_plane.deliver_participant_directed_view(
            request.target.participant_address,
            operation.view,
            identity=principal,
            crossing_evidence=operation.crossing_evidence,
            idempotency_key=idempotency_key,
        )
        return
    control_plane.record_participant_control(
        request.target.participant_address,
        operation.intent,
        identity=principal,
        crossing_evidence=operation.crossing_evidence,
        idempotency_key=idempotency_key,
    )


__all__ = (
    "ParticipantControlEffectOperation",
    "ParticipantControlEffectRealization",
    "dispatch_participant_control_effects",
)
