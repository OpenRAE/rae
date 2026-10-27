"""Disposable control indexes over immutable, versioned evaluation prefixes."""

from __future__ import annotations

from threading import RLock

from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.immutable_history import EventHistory, HistoryMap
from raes_contracts.participant_control_evaluation_history import participant_control_evaluation_from_payload

from .participant_control_causal_state import CausalAccumulator, ParticipantControlCausalState
from .participant_control_provider_state import _require_serial_state_chain, _scope_key

PROJECTION_VERSION = 1


class ControlStateProjection:
    """Select retained facts without changing their original interpretation."""

    def __init__(self, *, lock=None) -> None:
        self._lock = RLock() if lock is None else lock
        self.version = PROJECTION_VERSION
        self.history = HistoryMap("participant_control_evaluation_history", {})
        self.roots = {}
        self.local_roots = {}
        self.shared_roots = set()
        self.evaluations = {}
        self.by_origin = {}
        self.provider_chains = {}
        self.provider_tips = {}
        self.pending = {}
        self.completed = {}
        self.outcome_order = {}
        self.realized = {}

    def refresh(self, snapshot: object) -> None:
        with self._lock:
            history = snapshot.participant_control_evaluation_history
            if self.version == PROJECTION_VERSION and history is self.history:
                return
            if self.version != PROJECTION_VERSION or not _extends(self.history, history):
                rebuilt = ControlStateProjection(lock=self._lock)
                rebuilt._consume(history)
                self.__dict__.update(rebuilt.__dict__)
                return
            # A failed suffix fold cannot leave a partially updated index usable.
            try:
                self._consume(history)
            except BaseException:
                self.version = -1
                raise

    def _consume(self, history: HistoryMap) -> None:
        self._touched_provider_scopes = set()
        for participant_order, (participant, records) in enumerate(history.items()):
            start = len(self.history.get(participant, ()))
            for index in range(start, len(records)):
                evaluation = participant_control_evaluation_from_payload(records[index])
                self._apply(participant, evaluation, priority=(participant_order, index))
        for key in self._touched_provider_scopes:
            chain = self.provider_chains[key]
            _require_serial_state_chain(chain)
            self.provider_tips[key] = next(iter(set(chain.values()) - chain.keys()))
        self.history = history

    def _apply(self, participant: str, evaluation: object, *, priority) -> None:
        self._index_effect_order(participant, evaluation, priority[1])
        context = evaluation.request.context
        root = (context.run.ref, context.trigger_root)
        self.roots.setdefault(root, CausalAccumulator()).apply(evaluation, priority=priority)
        self.local_roots.setdefault((participant, *root), CausalAccumulator()).apply(evaluation)
        self.evaluations[evaluation.evaluation_id] = evaluation
        if isinstance(evaluation, ParticipantControlEvaluationV2Model):
            self.shared_roots.add(root)
            for proposal in evaluation.state_proposals:
                key = _scope_key(context, proposal.scope)
                chain = self.provider_chains.setdefault(key, {})
                retained = chain.setdefault(proposal.before, proposal.after)
                if retained != proposal.after:
                    raise ValueError("retained provider state has conflicting writers")
                # Only the scope touched by this append is revisited.
                self._touched_provider_scopes.add(key)
            if evaluation.commit.status == "committed":
                self.by_origin.setdefault(evaluation.commit.receipt.ref, {})[evaluation.evaluation_id] = evaluation
                if evaluation.continuation is None and evaluation.effect_plan.effects:
                    self.pending.setdefault(participant, {})[evaluation.evaluation_id] = evaluation
        else:
            from raes_contracts.contracts.participant_control_composition import admitted_effect_phase

            from .participant_control_effects import _realized_keys

            self.realized.setdefault(participant, {}).update(_realized_keys([evaluation]))
            if not evaluation.realizations and admitted_effect_phase(evaluation) is not None:
                self.pending.setdefault(participant, {})[evaluation.evaluation_id] = evaluation

    def _index_effect_order(self, participant, evaluation, position):
        from graphlib import TopologicalSorter

        from raes_contracts.contracts.participant_control_composition import admitted_effect_phase

        from .participant_control_effects import _ordered_requests

        if isinstance(evaluation, ParticipantControlEvaluationV2Model):
            if evaluation.commit.status != "committed" or evaluation.continuation is not None:
                return
            requests = {item.effect_id: item for item in evaluation.effect_plan.effects}
            graph = {key: set(item.predecessor_effect_ids) for key, item in requests.items()}
            ordered = [requests[key] for key in TopologicalSorter(graph).static_order()]
            kind = 0
        else:
            phase = admitted_effect_phase(evaluation)
            if evaluation.realizations or phase is None:
                return
            ordered = _ordered_requests(evaluation, phase)
            kind = 1
        order = self.outcome_order.setdefault(participant, {})
        for rank, request in enumerate(ordered):
            priority = (kind, position, rank)
            order[request.key] = min(order.get(request.key, priority), priority)

    def finish_drain(self, participant: str, drain: object) -> None:
        with self._lock:
            from .participant_control_causal_state import _admitted_effects

            completed = self.completed.setdefault(participant, {})
            completed.update(
                {key: value for key, value in drain.outcomes.items() if value.disposition in {"applied", "failed"}}
            )
            for identity, evaluation in tuple(self.pending.get(participant, {}).items()):
                effects = (
                    evaluation.effect_plan.effects
                    if isinstance(evaluation, ParticipantControlEvaluationV2Model)
                    else tuple(_admitted_effects(evaluation))
                )
                if effects and all(
                    effect.key in completed or effect.key in self.realized.get(participant, {}) for effect in effects
                ):
                    del self.pending[participant][identity]

    def causal_state(self, run: str, root: str, *, participant: str | None = None) -> ParticipantControlCausalState:
        with self._lock:
            key = (run, root)
            source = self.roots if participant is None or key in self.shared_roots else self.local_roots
            selected = key if source is self.roots else (participant, *key)
            return source.get(selected, CausalAccumulator()).state()


def _extends(previous: HistoryMap, current: HistoryMap) -> bool:
    if tuple(current)[: len(previous)] != tuple(previous):
        return False
    for participant, prefix in previous.items():
        records = current.get(participant)
        if not isinstance(records, EventHistory) or len(records) < len(prefix):
            return False
        if records.prefix_digest(len(prefix)) != prefix.prefix_digest(len(prefix)):
            return False
    return isinstance(current, HistoryMap)


def control_projection(plane: object) -> ControlStateProjection:
    with plane._operation_lock:
        projection = getattr(plane, "_control_state_projection", None)
        if projection is None:
            projection = ControlStateProjection(lock=plane._operation_lock)
            plane._control_state_projection = projection
        projection.refresh(plane._snapshot)
        return projection
