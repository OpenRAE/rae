"""Scoped state derived only from atomically retained API-424/v2 evaluations."""

from __future__ import annotations

import itertools

from raes_contracts.contracts.participant_control_applicability import (
    ControlStateScopeV2Model,
    ParticipantControlRequestV2Model,
)
from raes_contracts.contracts.participant_control_coordinates import (
    ControlArtifactReferenceModel,
    ParticipantControlContextModel,
)
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.participant_control_evaluation_history import participant_control_evaluation_from_payload
from raes_contracts.runtime_state import RuntimeSnapshot

_StateKey = tuple[str, ControlStateScopeV2Model, str | None, str | None]


def _scope_key(context: ParticipantControlContextModel, scope: ControlStateScopeV2Model) -> _StateKey:
    return (
        context.run.ref,
        scope,
        context.participant_address if scope.sharing != "run" else None,
        context.episode_id if scope.sharing == "episode" else None,
    )


def _state_chains(
    snapshot: RuntimeSnapshot,
    extra: tuple[ParticipantControlEvaluationV2Model, ...] = (),
) -> dict[_StateKey, dict[ControlArtifactReferenceModel, ControlArtifactReferenceModel]]:
    chains = {}
    records = (payload for history in snapshot.participant_control_evaluation_history.values() for payload in history)
    for evaluation in itertools.chain(map(participant_control_evaluation_from_payload, records), extra):
        if not isinstance(evaluation, ParticipantControlEvaluationV2Model):
            continue
        for proposal in evaluation.state_proposals:
            key = _scope_key(evaluation.request.context, proposal.scope)
            chain = chains.setdefault(key, {})
            previous = chain.setdefault(proposal.before, proposal.after)
            if previous != proposal.after:
                raise ValueError("retained provider state has conflicting writers")
    for chain in chains.values():
        _require_serial_state_chain(chain)
    return chains


def _require_serial_state_chain(chain: dict[ControlArtifactReferenceModel, ControlArtifactReferenceModel]) -> None:
    if len(set(chain.values())) != len(chain) or len(set(chain.values()) - chain.keys()) != 1:
        raise ValueError("retained provider state has a fork or cycle")
    root = set(chain) - set(chain.values())
    if len(root) != 1:
        raise ValueError("retained provider state has no unique predecessor")
    state = next(iter(root))
    seen = set()
    while state in chain:
        if state in seen:
            raise ValueError("retained provider state has a cycle")
        seen.add(state)
        state = chain[state]
    if len(seen) != len(chain):
        raise ValueError("retained provider state has disconnected versions")


def require_provider_state_extension(
    snapshot: RuntimeSnapshot, evaluation: ParticipantControlEvaluationV2Model, *, projection: object | None = None
) -> None:
    """Validate the proposed extension before its atomic history append."""
    if projection is None:
        _state_chains(snapshot, (evaluation,))
        return
    proposed = {}
    for proposal in evaluation.state_proposals:
        key = _scope_key(evaluation.request.context, proposal.scope)
        chain = proposed.setdefault(key, dict(projection.provider_chains.get(key, {})))
        previous = chain.setdefault(proposal.before, proposal.after)
        if previous != proposal.after:
            raise ValueError("retained provider state has conflicting writers")
    for chain in proposed.values():
        _require_serial_state_chain(chain)


def require_retained_provider_state(
    snapshot: RuntimeSnapshot, request: ParticipantControlRequestV2Model, *, projection: object | None = None
) -> None:
    """Match every shared read version against the retained transaction chain.

    All scopes live in this snapshot; the caller retains its original global
    revision CAS across evaluation. Cross-store sharing is not supported.
    """
    chains = _state_chains(snapshot) if projection is None else projection.provider_chains
    for binding in request.selection.bindings:
        state = next(
            (item.state for item in request.context.provider_states if item.instance_id == binding.instance_id), None
        )
        if state is None:
            continue
        chain = chains.get(_scope_key(request.context, binding.state_scope), {})
        if chain:
            tips = set(chain.values()) - chain.keys()
            if len(tips) != 1 or state not in tips:
                raise ValueError("participant control provider state is stale or conflicting")
