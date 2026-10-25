"""Validate continuation of an immutable admitted effect graph at its own cut."""

from .participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from .participant_control_resolution import (
    ParticipantControlValidationContextV2,
    _validate_admitted_v2_identity,
    _validate_inject,
    _validate_v2_effect_authority,
    _validate_v2_receipts,
    _validate_v2_results_and_support,
)


def validate_participant_control_incremental_admission_v2(record, current_context):
    """Apply the existing limits to newly admitted keys at current consumption."""
    from .participant_control_composition_v2 import admitted_control_effect_ids_v2
    from .participant_control_effect_composition import _retained_claims, _validate_effect_bounds

    admitted = admitted_control_effect_ids_v2(record.composition, record.effect_plan)
    effects = {effect for effect in record.effect_plan.effects if effect.effect_id in admitted}
    blockers = set()
    new_keys = _retained_claims(effects, current_context, blockers)
    if blockers:
        raise ValueError("continuation conflicts with current committed claims")
    _validate_effect_bounds(effects, new_keys, current_context, record.request.selection.bounds)


def validate_participant_control_effect_dispatch_v2(record, effect, context):
    """Resolve one pending effect's current authority without granting siblings."""
    from .participant_control_applicability import control_digest
    from .participant_control_effects import ControlInjectEffectModel

    try:
        record = ParticipantControlEvaluationV2Model.model_validate(record.model_dump(mode="python"))
        if (
            record.commit.status != "committed"
            or effect not in record.effect_plan.effects
            or effect.effect_id not in record.commit.dispatchable_effect_ids
        ):
            raise ValueError("effect has no committed dispatch permission")
        _validate_admitted_v2_identity(record, context)
        _validate_v2_results_and_support(record, context)
        if context.authorized_effects.get(control_digest(effect)) != record.request.context:
            raise ValueError("effect authority is no longer resolved")
        if isinstance(effect.target, ControlInjectEffectModel):
            _validate_inject(effect.target, record.request.context, context)
    except Exception:
        raise ValueError("participant control current effect authority validation failed") from None


def validate_participant_control_continuation_v2(record, source, context):
    """Credit exact same-cut owner outcomes without re-evaluating provider work.

    This is a continuation of the source transaction, not a fresh evaluation:
    no request, result, state proposal, effect identity, or budget may change.
    The caller independently resolves every credited committed intent/outcome.
    Fresh evaluations retain their stricter monotonic consumption validation.
    """
    try:
        source = ParticipantControlEvaluationV2Model.model_validate(source.model_dump(mode="python"))
        record = ParticipantControlEvaluationV2Model.model_validate(record.model_dump(mode="python"))
        if not isinstance(context, ParticipantControlValidationContextV2) or source.commit.status != "committed":
            raise ValueError("missing committed source or trusted context")
        continuation = record.continuation
        if (
            source.continuation is not None
            or continuation is None
            or continuation.source_evaluation_id != source.evaluation_id
            or continuation.source_commit_receipt != source.commit.receipt
        ):
            raise ValueError("continuation differs from its exact original source")
        effects = {item.effect_id: item for item in source.effect_plan.effects}
        from .participant_control_applicability import control_digest

        if {item.effect_id for item in continuation.realized_claims} != set(record.effect_plan.realized_effect_ids):
            raise ValueError("continuation claims differ from credited outcomes")
        for claim in continuation.realized_claims:
            effect = effects[claim.effect_id]
            if (claim.key, claim.content_digest) != (effect.key, control_digest(effect)):
                raise ValueError("continuation claim differs from exact committed intent")
        for field in ("request", "invocations", "results", "support", "lost_advice", "state_proposals"):
            if getattr(source, field) != getattr(record, field):
                raise ValueError("continuation changed an immutable evaluation input")
        for field in ("effects", "decisions", "incumbent_gate_disposition"):
            if getattr(source.effect_plan, field) != getattr(record.effect_plan, field):
                raise ValueError("continuation changed its committed effect graph")
        _validate_admitted_v2_identity(record, context)
        _validate_v2_results_and_support(record, context)
        _validate_v2_effect_authority(record, context, same_cut=True)
        _validate_v2_receipts(record, context)
    except Exception:
        raise ValueError("participant control trusted continuation validation failed") from None
