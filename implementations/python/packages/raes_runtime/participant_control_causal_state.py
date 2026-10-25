"""RUN-320 causal state folded from the committed evaluation history.

PC-12 gives every admitted root finite depth, effect, fan-out, firing and
attempt budgets, and PC-11 keeps one logical claim per effect key. Those
budgets are durable: a single evaluation validating its own bounds proves
nothing if the next evaluation under the same root may again declare zero
consumption and no retained claims.

This module folds the committed history for one participant and causal root
into the consumption the next admitted context must declare. The runtime
refuses a context that under-declares it, so a claim consumes budget exactly
once and a replayed key is recognised rather than re-admitted.

Resolution attempts are folded the same way and for the same reason. An
evaluation that resolves no effect still spends an attempt; if attempts were
only bounded per request, a root could be re-resolved without limit by
declaring ``attempt=1`` on every fresh crossing. An attempt is spent by making
the evaluation, so it is counted whether or not the composition admitted
anything; a *claim*, by contrast, is only ever folded from an admitted intent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from raes_contracts.contracts.participant_control_composition import (
    ParticipantControlEvaluationModel,
    admitted_effect_requests,
    control_digest,
)
from raes_contracts.contracts.participant_control_composition_v2 import admitted_control_effect_ids_v2
from raes_contracts.contracts.participant_control_coordinates import (
    ControlLogicalEffectKeyModel,
    ControlPriorEffectClaimModel,
    ParticipantControlContextModel,
)
from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.participant_control_evaluation_history import participant_control_evaluation_from_payload


@dataclass(frozen=True)
class ParticipantControlCausalState:
    """Consumption one causal root has already retained in committed history."""

    claims: Mapping[ControlLogicalEffectKeyModel, ControlPriorEffectClaimModel]
    firings: Mapping[tuple[str, str], frozenset[str]]
    attempts: int = 0
    effects_consumed: int = 0

    @property
    def next_attempt(self) -> int:
        """The lowest attempt an admitted context may still declare."""

        return self.attempts + 1


def root_has_shared_consumption(
    history: Sequence[Mapping[str, object]],
    *,
    run_ref: str,
    trigger_root: str,
) -> bool:
    """A root's explicit v2 sharing survives later binding/participant changes."""
    for payload in history:
        if payload.get("schema_version") != "participant-control-evaluation/v2":
            continue
        context = participant_control_evaluation_from_payload(payload).request.context
        if (context.run.ref, context.trigger_root) == (run_ref, trigger_root):
            return True
    return False


def causal_state_from_history(
    history: Sequence[Mapping[str, object]],
    *,
    run_ref: str,
    trigger_root: str,
) -> ParticipantControlCausalState:
    """Fold every retained claim this run and causal root already consumed."""

    claims: dict[ControlLogicalEffectKeyModel, ControlPriorEffectClaimModel] = {}
    firings: dict[tuple[str, str], set[str]] = {}
    attempts = 0
    watermarks: dict[frozenset[ControlLogicalEffectKeyModel], int] = {}
    admitted_keys: set[ControlLogicalEffectKeyModel] = set()
    for record in history:
        evaluation = participant_control_evaluation_from_payload(record)
        context = evaluation.request.context
        if (context.run.ref, context.trigger_root) != (run_ref, trigger_root):
            continue
        # Each watermark already covers its declared claims. Add every unique
        # admission outside that set, including interleaved continuations.
        # Shared participant histories need not be globally ordered.
        declared = frozenset(claim.key for claim in context.prior_effect_claims)
        watermarks[declared] = max(watermarks.get(declared, 0), context.effects_consumed)
        admitted_keys.update({effect.key for effect in _admitted_effects(evaluation)} - declared)
        # A realization transition records the outcome of an evaluation that
        # already spent its attempt; counting it again would double-charge.
        if isinstance(evaluation, ParticipantControlEvaluationV2Model) or not evaluation.realizations:
            attempts = max(attempts, context.attempt)
        _fold_retained(context, claims, firings)
        for effect in _admitted_effects(evaluation):
            claims.setdefault(
                effect.key,
                ControlPriorEffectClaimModel(
                    effect_id=effect.effect_id,
                    key=effect.key,
                    content_digest=control_digest(effect),
                ),
            )
            firings.setdefault((effect.key.rule_id, effect.key.rule_revision), set()).add(effect.key.firing_epoch)
    consumed = max((count + len(admitted_keys - declared) for declared, count in watermarks.items()), default=0)
    return ParticipantControlCausalState(
        claims=claims,
        firings={rule: frozenset(epochs) for rule, epochs in firings.items()},
        attempts=attempts,
        effects_consumed=max(consumed, len(claims)),
    )


def _fold_retained(
    context: ParticipantControlContextModel,
    claims: dict[ControlLogicalEffectKeyModel, ControlPriorEffectClaimModel],
    firings: dict[tuple[str, str], set[str]],
) -> None:
    for claim in context.prior_effect_claims:
        claims.setdefault(claim.key, claim)
    for state in context.rule_firings:
        firings.setdefault((state.rule_id, state.rule_revision), set()).update(state.firing_epochs)


def _admitted_effects(evaluation: ParticipantControlEvaluationModel) -> Iterable[ControlEffectRequestModel]:
    """Only an admitted intent consumes budget; a rejected proposal never did.

    API-424 decides what a composition admits, so a conflicted or otherwise
    blocked evaluation contributes no claim here. Otherwise contributor order
    would pick which of two conflicting payloads a later context must retain,
    and a proposal nobody admitted would spend the root's effect budget.
    """

    if isinstance(evaluation, ParticipantControlEvaluationV2Model):
        admitted = admitted_control_effect_ids_v2(evaluation.composition, evaluation.effect_plan)
        return tuple(item for item in evaluation.effect_plan.effects if item.effect_id in admitted)
    return admitted_effect_requests(evaluation)


def declares_retained_consumption(
    context: ParticipantControlContextModel,
    state: ParticipantControlCausalState,
) -> bool:
    """Require the admitted context to carry everything the root already spent.

    The context may declare more than the committed history proves — a
    resolver knows its own in-flight claims — but never less: under-declaring
    is how a second evaluation would re-spend an exhausted budget or re-admit
    an already claimed effect key.
    """

    # Every committed evaluation under this root spent an attempt, whether or
    # not it resolved an effect, so the next one must declare a fresh number.
    # PC-12's ``max_attempts`` then bounds the root, not a single request.
    return (
        _declares_retained_claims(context, state)
        and _declares_retained_firings(context, state)
        and context.effects_consumed >= state.effects_consumed
        and context.attempt >= state.next_attempt
    )


def validate_incremental_effect_admission(plane, evaluation):
    """Check a continuation against all work this shared root already admitted."""
    from raes_contracts.contracts.participant_control_continuation import (
        validate_participant_control_incremental_admission_v2,
    )

    context = evaluation.request.context
    state = causal_state_from_history(
        tuple(item for history in plane._snapshot.participant_control_evaluation_history.values() for item in history),
        run_ref=context.run.ref,
        trigger_root=context.trigger_root,
    )
    current = ParticipantControlContextModel.model_validate(
        {
            **context.model_dump(mode="json"),
            "effects_consumed": state.effects_consumed,
            "prior_effect_claims": [claim.model_dump(mode="json") for claim in state.claims.values()],
            "rule_firings": [
                {"rule_id": key[0], "rule_revision": key[1], "firing_epochs": sorted(epochs)}
                for key, epochs in state.firings.items()
            ],
        }
    )
    validate_participant_control_incremental_admission_v2(evaluation, current)


def _declares_retained_claims(context: ParticipantControlContextModel, state: ParticipantControlCausalState) -> bool:
    declared = {claim.key: claim for claim in context.prior_effect_claims}
    return all(
        (current := declared.get(key)) is not None
        and current.effect_id == retained.effect_id
        and current.content_digest == retained.content_digest
        for key, retained in state.claims.items()
    )


def _declares_retained_firings(context: ParticipantControlContextModel, state: ParticipantControlCausalState) -> bool:
    declared = {(item.rule_id, item.rule_revision): set(item.firing_epochs) for item in context.rule_firings}
    # A retained epoch the context leaves undeclared is an under-declaration.
    return all(not (epochs - declared.get(rule, set())) for rule, epochs in state.firings.items())


__all__ = (
    "ParticipantControlCausalState",
    "causal_state_from_history",
    "declares_retained_consumption",
)
