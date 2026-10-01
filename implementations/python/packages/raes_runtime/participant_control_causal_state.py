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
from raes_contracts.contracts.participant_control_coordinates import (
    ControlLogicalEffectKeyModel,
    ControlPriorEffectClaimModel,
    ParticipantControlContextModel,
)
from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel


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
    consumed = 0
    for record in history:
        evaluation = ParticipantControlEvaluationModel.model_validate(record)
        context = evaluation.request.context
        if (context.run.ref, context.trigger_root) != (run_ref, trigger_root):
            continue
        # API-424 lets a context's consumption exceed its retained claims, so
        # the count is a watermark of its own, not the number of claims: what
        # the context declared already spent, plus the keys it newly admitted.
        # A maximum rather than a sum, so a replayed key and a realization
        # transition — which repeats its evaluation's context — add nothing.
        declared = {claim.key for claim in context.prior_effect_claims}
        admitted = {effect.key for effect in _admitted_effects(evaluation)} - declared
        consumed = max(consumed, context.effects_consumed + len(admitted))
        # A realization transition records the outcome of an evaluation that
        # already spent its attempt; counting it again would double-charge.
        if not evaluation.realizations:
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
