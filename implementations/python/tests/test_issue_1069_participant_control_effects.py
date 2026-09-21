"""Issue #1069 governed dispatch of admitted participant-control effects.

A requested effect is not a permission and a commit is not a dispatch: each
admitted subsequent effect is a separately admitted operation through its
incumbent owner, executed only after its parent committed, idempotent on its
logical effect key, and recorded as an append-only realization transition.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from participant_control_runtime_fixtures import (
    INSTANCE,
    SyntheticControlProvider,
    control_binding,
    dependent_effects_payload,
    handoff_effect_payload,
    required_predecessor_payload,
)
from participant_crossing_fixtures import (
    PARTICIPANT,
    StaticCrossingResolver,
    action_plane,
    admit,
    control_specification,
    identity,
    policy_capable_target,
)
from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel
from raes_contracts.runtime_state import OperationKind, OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_mutation import control_plane_mutation
from raes_runtime.participant_control_receipts import effect_idempotency_key
from raes_runtime.participant_control_records import commit_participant_control_realization


def _instrument_backend(target: object) -> dict[str, int]:
    """Count real participant backend invocations at the effect boundary."""

    runtime = target.participant_runtime
    assert runtime is not None
    original = runtime.admit_action
    counter = {"calls": 0}

    def tracked(*args: object, **kwargs: object):
        counter["calls"] += 1
        return original(*args, **kwargs)

    runtime.admit_action = tracked  # type: ignore[method-assign]
    return counter


def _target(*features: str):
    return policy_capable_target(
        "participant_ingress_admission",
        "participant_modular_control",
        "participant_directed_inject_delivery",
        "participant_egress_projection",
        "participant_intervention",
        "participant_transformation",
        *features,
    )


def _plane(binding, *, target=None, store=None):
    return action_plane(
        StaticCrossingResolver(),
        target=target or _target(),
        store=store,
        participant_control=binding,
    )


def _origin():
    """The principal that causes the effect: bound to control *and* the audience.

    An effect acts for the principal of the operation that admitted it, so an
    inject can only apply if that principal may disclose to the audience.
    """

    return identity(audience_bound=True)


def _dispatch(plane):
    """Dispatch as an operator bound to both the control subject and audience."""

    return plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity(audience_bound=True))


def _deliveries(plane) -> set[str]:
    return {
        record["occurrence"]["decision_id"]
        for record in plane.snapshot.participant_crossing_history[PARTICIPANT]
        if record["occurrence"]["interaction_kind"] == "participant-inject-delivery"
        and record["occurrence"].get("decision_id")
    }


def _history(plane) -> list[dict]:
    return list(plane.snapshot.participant_control_evaluation_history.get(PARTICIPANT, ()))


def _effect_claims(plane) -> list:
    """Every runtime effect claim: kind participant-control, keyed by the logical effect."""

    from raes_contracts.runtime_state import OperationKind

    return [
        record
        for record in plane._store.load_records().values()
        if record.idempotency_key.startswith("control-effect:")
        and record.status.context.operation_kind is OperationKind.PARTICIPANT_CONTROL
    ]


def _origin_and_request(plane, slot_id: str = "rule"):
    """The committed evaluation's originating operation and one effect request."""

    from raes_runtime.participant_control_receipts import originating_operations

    evaluation = ParticipantControlEvaluationModel.model_validate(
        next(item for item in _history(plane) if ":realization:" not in item["evaluation_id"])
    )
    origin = originating_operations(plane, PARTICIPANT)[evaluation.evaluation_id]
    request = next(result.payload for result in evaluation.results if result.slot_id == slot_id)
    return origin, request


def _force_indeterminate(plane):
    """Claim the owner operation, then fail before establishing its outcome.

    This is the crash window between an owner claiming its operation and
    committing a terminal state: the dispatch may have begun, and nothing
    durable says whether it did.
    """

    from raes_contracts.runtime_state import OperationKind

    original = plane.deliver_participant_directed_view
    claimed: dict[str, object] = {}

    def interrupted(*args: object, **kwargs: object):
        del args
        claimed["record"] = _claim_in_owner_scope(
            plane,
            operation_kind=OperationKind.PARTICIPANT_CROSSING,
            operation_id="owner-attempt-1",
            state=OperationState.RUNNING,
            key=kwargs["idempotency_key"],
        )
        raise RuntimeError("owner interrupted after claiming its operation")

    plane.deliver_participant_directed_view = interrupted  # type: ignore[method-assign]

    def restore() -> None:
        plane.deliver_participant_directed_view = original  # type: ignore[method-assign]

    return restore


def _resolve_owner_operation(plane) -> None:
    """Establish the terminal state startup recovery would have observed."""

    record = plane._store.load_records()["owner-attempt-1"]
    plane._store.save_record(replace(record, status=replace(record.status, state=OperationState.SUCCEEDED)))


def _recommit_last_realization(plane) -> None:
    """Replay the realization writer with the outcome already committed."""

    from raes_runtime.participant_control_receipts import claim_effect

    binding = plane._participant_control
    history = _history(plane)
    transition = ParticipantControlEvaluationModel.model_validate(
        next(item for item in reversed(history) if ":realization:" in item["evaluation_id"])
    )
    causal = ParticipantControlEvaluationModel.model_validate(
        next(item for item in history if ":realization:" not in item["evaluation_id"])
    )
    origin, request = _origin_and_request(plane)
    with control_plane_mutation(plane, OperationKind.PARTICIPANT_CONTROL):
        claim = claim_effect(plane, origin, request)
        commit_participant_control_realization(
            plane,
            binding,
            causal,
            transition.realizations[0],
            claim=claim.record,
        )


def test_ifc_resolved_influence_triggers_a_governed_inject():
    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-inject")

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["applied"]
    assert realizations[0].effect_id == "effect-1"
    delivered = plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert any(record["occurrence"]["interaction_kind"] == "participant-inject-delivery" for record in delivered)


def test_ifc_resolved_influence_triggers_a_non_inject_handoff_effect():
    specification = control_specification()
    plane = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=StaticCrossingResolver(),
        behavior_specifications={specification.address: specification},
        participant_control=control_binding(handoff_effect_payload()),
        enforce_final_sink_flow_control=False,
    )
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    admit(plane, control_identity=_origin(), idempotency_key="effect-handoff")

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["applied"]
    assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1


def test_realizations_append_a_transition_rather_than_rewriting_the_evaluation():
    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-append")
    before = _history(plane)

    _dispatch(plane)

    after = _history(plane)
    assert after[0] == before[0]
    assert after[0]["realizations"] == []
    assert after[-1]["realizations"][0]["disposition"] == "applied"
    assert after[-1]["evaluation_id"] != before[0]["evaluation_id"]


def test_replaying_a_claimed_key_returns_its_receipt_without_a_second_effect():
    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-replay")

    first = _dispatch(plane)
    committed = len(_history(plane))
    delivered = _deliveries(plane)
    second = _dispatch(plane)

    assert [item.receipt_ref for item in second] == [item.receipt_ref for item in first]
    assert len(_history(plane)) == committed
    assert _deliveries(plane) == delivered


def test_a_non_eligible_composition_dispatches_nothing():
    providers = {INSTANCE: SyntheticControlProvider(omits_slot="fact")}
    plane = _plane(control_binding(providers=providers))
    admit(plane, control_identity=_origin(), idempotency_key="effect-blocked")

    assert _dispatch(plane) == ()
    assert plane.snapshot.participant_control_history == {}


def test_an_unsupported_effect_owner_records_unsupported_with_zero_dispatch():
    plane = _plane(control_binding(), target=_target())
    admit(plane, control_identity=_origin(), idempotency_key="effect-unsupported")
    plane._participant_control.resolver.effect_operations = False

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["unsupported"]
    assert not any(
        record["occurrence"]["interaction_kind"] == "participant-inject-delivery"
        for record in plane.snapshot.participant_crossing_history[PARTICIPANT]
    )


def test_an_owner_input_that_does_not_bind_the_request_is_never_dispatched():
    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-mismatch")
    plane._participant_control.resolver.effect_participant = "participant.behavior.other-agent"

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["unsupported"]
    assert _history(plane)[0]["composition"]["disposition"] == "eligible"


def test_a_refused_owner_operation_records_failed_without_a_parent_rollback():
    """The owner declares no inject delivery, so its gate refuses the effect."""

    refusing = policy_capable_target(
        "participant_ingress_admission",
        "participant_modular_control",
        "participant_egress_projection",
        "participant_transformation",
    )
    plane = _plane(control_binding(), target=refusing)
    admit(plane, control_identity=_origin(), idempotency_key="effect-refused")

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["failed"]
    assert _history(plane)[0]["composition"]["disposition"] == "eligible"


def _effect_key(plane) -> str:
    from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel

    evaluation = ParticipantControlEvaluationModel.model_validate(_history(plane)[0])
    request = next(result.payload for result in evaluation.results if result.slot_id == "rule")
    return effect_idempotency_key(request)


def _claim_in_owner_scope(plane, *, operation_kind, operation_id, state, key=None, actor_id=None):
    """Claim one record under a chosen claim scope, as that owner would.

    The store's claim identity is ``(actor, operation kind, key)``, so a test
    that wants to stand in for an effect's own prior attempt must claim in the
    dispatching actor's scope, and one that wants a foreign record must not.
    """

    from raes_contracts.runtime_state import OperationKind
    from raes_runtime.control_plane_operation_context import operation_actor_scope

    incumbent = next(iter(plane._store.load_records().values()))
    assert isinstance(operation_kind, OperationKind)
    actor = actor_id or operation_actor_scope(identity(audience_bound=True))[0]
    context = incumbent.receipt.context.model_copy(update={"operation_kind": operation_kind, "actor_id": actor})
    claimed = replace(
        incumbent,
        idempotency_key=key or _effect_key(plane),
        receipt=replace(incumbent.receipt, operation_id=operation_id, context=context),
        status=replace(
            incumbent.status,
            operation_id=operation_id,
            context=context,
            state=state,
            diagnostics=[],
            changed_addresses=[],
        ),
    )
    running = replace(claimed, status=replace(claimed.status, state=OperationState.RUNNING))
    plane._claim_record(running)
    if state is not OperationState.RUNNING:
        plane._store.save_record(claimed)
    return claimed


def test_a_claimed_but_undispatched_effect_resumes_exactly_once():
    """PC-11: a committed-but-undispatched key resumes on durable proof.

    Owners claim write-ahead under a key only the effect's claim derives, so an
    open claim with no owner record proves dispatch never began. The
    may-have-begun case — an owner record that is not terminal — stays
    indeterminate and is covered by the reconciliation tests.
    """

    from raes_runtime.participant_control_receipts import claim_effect

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-undispatched")
    origin, request = _origin_and_request(plane)
    with control_plane_mutation(plane, OperationKind.PARTICIPANT_CONTROL):
        assert claim_effect(plane, origin, request).fresh  # interrupted before any submission

    first = _dispatch(plane)
    second = _dispatch(plane)

    assert [item.disposition for item in first] == ["applied"]
    assert second == first
    assert len(_deliveries(plane)) == 1
    assert len(_effect_claims(plane)) == 1


def test_a_record_outside_the_owner_claim_scope_never_answers_for_an_effect():
    """A co-located operation must not stand in as an effect's outcome.

    The store's claim identity is ``(actor, operation kind, key)``. A record
    that merely reuses this effect's client key under a different operation
    kind is not this effect's claim, so it can neither report the effect as
    applied nor satisfy a dependent's prerequisite.
    """

    from raes_contracts.runtime_state import OperationKind

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-foreign-scope")
    # A permitted operation of another kind, succeeded, reusing the effect key.
    _claim_in_owner_scope(
        plane,
        operation_kind=OperationKind.PARTICIPANT_ACTION,
        operation_id="foreign-attempt-1",
        state=OperationState.SUCCEEDED,
    )

    realizations = _dispatch(plane)

    # The foreign record is ignored: the effect runs through its own owner.
    assert [item.disposition for item in realizations] == ["applied"]
    assert len(_deliveries(plane)) == 1
    assert "foreign-attempt-1" not in {item.receipt_ref for item in realizations}


def test_a_dependent_is_not_satisfied_by_a_foreign_record_for_its_predecessor():
    """A forged prerequisite must never authorize a dependent effect."""

    from raes_contracts.runtime_state import OperationKind

    plane = _plane(control_binding(dependent_effects_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-foreign-predecessor")
    plane._participant_control.resolver.effect_operations = False
    _claim_in_owner_scope(
        plane,
        operation_kind=OperationKind.PARTICIPANT_ACTION,
        operation_id="foreign-predecessor-1",
        state=OperationState.SUCCEEDED,
    )

    realizations = _dispatch(plane)

    by_id = {item.effect_id: item.disposition for item in realizations}
    assert by_id["effect-1"] == "unsupported"
    assert by_id["effect-2"] == "withheld"


def test_a_restarted_runtime_returns_the_applied_receipt_without_redelivery(tmp_path):
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    store_path = tmp_path / "cp"
    resolver = StaticCrossingResolver()
    first = action_plane(
        resolver,
        target=_target(),
        store=LocalControlPlaneStore(store_path),
        participant_control=control_binding(),
    )
    admit(first, control_identity=_origin(), idempotency_key="effect-restart")
    applied = _dispatch(first)
    delivered = _deliveries(first)
    first.close()

    second = action_plane(
        resolver,
        target=_target(),
        store=LocalControlPlaneStore(store_path),
        participant_control=control_binding(),
    )
    resumed = _dispatch(second)

    assert [item.disposition for item in resumed] == [item.disposition for item in applied] == ["applied"]
    assert _deliveries(second) == delivered


def test_an_owner_recorded_refusal_is_never_reported_as_applied():
    """An accepted receipt is admission; the durable status is the outcome."""

    specification = control_specification()
    plane = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=StaticCrossingResolver(),
        behavior_specifications={specification.address: specification},
        # The admitted effect names a state revision the owner will reject, so
        # the owner admits the operation and records it FAILED.
        participant_control=control_binding(handoff_effect_payload(expected_state_revision=99)),
        enforce_final_sink_flow_control=False,
    )
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    admit(plane, control_identity=_origin(), idempotency_key="effect-owner-refusal")

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["failed"]
    recorded = plane.snapshot.participant_control_history.get(PARTICIPANT, ())
    assert all(event["occurrence"].get("disposition") != "applied" for event in recorded)


def test_effects_dispatch_in_their_declared_causal_order():
    """Record order is serialization; predecessor_effect_ids is the order."""

    plane = _plane(control_binding(dependent_effects_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-ordered")

    realizations = _dispatch(plane)

    assert [item.effect_id for item in realizations] == ["effect-1", "effect-2"]
    assert [item.disposition for item in realizations] == ["applied", "unsupported"]


def test_a_dependent_is_withheld_when_its_predecessor_did_not_apply():
    plane = _plane(control_binding(dependent_effects_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-withheld")
    plane._participant_control.resolver.effect_operations = False

    realizations = _dispatch(plane)

    by_id = {item.effect_id: item.disposition for item in realizations}
    assert by_id["effect-1"] == "unsupported"
    assert by_id["effect-2"] == "withheld"


def test_a_required_predecessor_is_admitted_while_its_parent_stays_withheld():
    """PC-11: the parent withholds, the predecessor runs as its own operation."""

    target = _target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(required_predecessor_payload()), target=target)

    admit(plane, control_identity=_origin(), idempotency_key="effect-predecessor")

    evaluation = _history(plane)[0]
    assert evaluation["composition"]["disposition"] == "withhold"
    assert counter["calls"] == 0  # the withheld parent performed no effect

    realizations = _dispatch(plane)

    by_id = {item.effect_id: item.disposition for item in realizations}
    assert by_id["effect-2"] in {"applied", "unsupported"}
    assert "effect-1" not in by_id  # the subsequent effect waits for a fresh cut


def test_dispatch_requires_a_bound_participant_control_configuration():
    plane = action_plane(StaticCrossingResolver(), target=_target())
    with pytest.raises(ValueError, match="participant control"):
        _dispatch(plane)


def test_an_inject_owner_input_with_a_different_lineage_is_never_dispatched():
    """Scope is not identity: a view that is not this inject's result is refused."""

    target = _target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(), target=target)
    admit(plane, control_identity=_origin(), idempotency_key="effect-inject-lineage")
    plane._participant_control.resolver.effect_inject_lineage = "participant-inject-view:other"
    before = counter["calls"]

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["unsupported"]
    assert counter["calls"] == before  # no owner operation beyond the admission
    assert _deliveries(plane) == set()


def test_a_handoff_owner_input_with_a_different_declaration_is_never_dispatched():
    plane = _plane(control_binding(handoff_effect_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-handoff-declaration")
    plane._participant_control.resolver.effect_declaration_ref = (
        "participant.behavior-specification.controlled.control-transition.override"
    )

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["unsupported"]
    assert plane.snapshot.participant_control_history.get(PARTICIPANT, ()) == ()


def test_a_handoff_owner_input_with_a_different_state_revision_is_never_dispatched():
    plane = _plane(control_binding(handoff_effect_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-handoff-revision")
    plane._participant_control.resolver.effect_state_revision = 99

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["unsupported"]
    assert plane.snapshot.participant_control_history.get(PARTICIPANT, ()) == ()


def test_an_uncertain_realization_is_reconciled_once_its_owner_resolves():
    """An open claim is resolved by the owner operation it submitted."""

    plane = _plane(control_binding(dependent_effects_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-indeterminate")
    restore = _force_indeterminate(plane)

    uncertain = _dispatch(plane)
    restore()

    by_id = {item.effect_id: item.disposition for item in uncertain}
    assert by_id["effect-1"] == "indeterminate"
    assert by_id["effect-2"] == "withheld"

    _resolve_owner_operation(plane)
    reconciled = _dispatch(plane)

    by_id = {item.effect_id: item.disposition for item in reconciled}
    assert by_id["effect-1"] == "applied"
    # Only the known outcome is recorded, on the effect's own claim, and the
    # external action was never repeated on the reconciling pass.
    transitions = [item for item in _history(plane) if ":realization:" in item["evaluation_id"]]
    assert [item["realizations"][0]["effect_id"] for item in transitions][0] == "effect-1"
    assert "owner-attempt-1" not in _deliveries(plane)


def test_an_overlapping_dispatch_of_the_same_outcome_is_recognised_as_a_replay():
    """A second drain resolves the same claim and neither repeats nor re-records."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-replay")

    first = _dispatch(plane)
    committed = [item["evaluation_id"] for item in _history(plane) if ":realization:" in item["evaluation_id"]]
    second = _dispatch(plane)
    _recommit_last_realization(plane)

    assert [item.disposition for item in first] == ["applied"]
    assert second == first
    assert len(_deliveries(plane)) == 1
    assert [item["evaluation_id"] for item in _history(plane) if ":realization:" in item["evaluation_id"]] == committed


def test_a_foreign_record_under_the_effect_claim_never_reports_applied():
    """A different request holding this effect's claim identity is refused, never read.

    The store validates a replay against the claim's content, so a record that
    merely reuses the effect key under the originating actor conflicts instead
    of standing in for the effect.
    """

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-foreign-same-scope")
    _claim_in_owner_scope(
        plane,
        operation_kind=OperationKind.PARTICIPANT_CONTROL,
        operation_id="unrelated-success-1",
        state=OperationState.SUCCEEDED,
    )

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["failed"]
    assert [item.receipt_ref for item in realizations] == ["claim-conflict.effect-1"]
    assert _deliveries(plane) == set()


def test_a_dependent_is_never_authorized_by_an_unrelated_succeeded_record():
    """A forged prerequisite authorizes nothing, so no dependent runs on it."""

    plane = _plane(control_binding(dependent_effects_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-foreign-same-scope-dependent")
    _claim_in_owner_scope(
        plane,
        operation_kind=OperationKind.PARTICIPANT_CONTROL,
        operation_id="unrelated-success-2",
        state=OperationState.SUCCEEDED,
    )

    realizations = _dispatch(plane)

    by_id = {item.effect_id: item.disposition for item in realizations}
    assert by_id["effect-1"] == "failed"
    assert by_id["effect-2"] == "withheld"
    assert _deliveries(plane) == set()


def test_an_owner_refusal_before_its_claim_fails_on_the_effects_own_claim():
    """An owner that refuses before claiming began nothing; no other record answers."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-owner-refused-early")
    original = plane.deliver_participant_directed_view

    def refusing(*args: object, **kwargs: object):
        del args, kwargs
        raise ValueError("owner refused before claiming")

    plane.deliver_participant_directed_view = refusing  # type: ignore[method-assign]
    try:
        realizations = _dispatch(plane)
    finally:
        plane.deliver_participant_directed_view = original  # type: ignore[method-assign]

    (claim,) = _effect_claims(plane)
    assert [item.disposition for item in realizations] == ["failed"]
    assert [item.receipt_ref for item in realizations] == [claim.receipt.operation_id]
    assert claim.status.state is OperationState.FAILED
    assert _deliveries(plane) == set()


def test_a_withheld_dependent_runs_once_its_predecessor_is_reconciled():
    """A withhold is an ordering decision, never a terminal outcome."""

    plane = _plane(control_binding(dependent_effects_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-dependent-resume")
    restore = _force_indeterminate(plane)

    uncertain = _dispatch(plane)
    restore()

    by_id = {item.effect_id: item.disposition for item in uncertain}
    assert by_id["effect-1"] == "indeterminate"
    assert by_id["effect-2"] == "withheld"

    _resolve_owner_operation(plane)
    resumed = _dispatch(plane)

    by_id = {item.effect_id: item.disposition for item in resumed}
    assert by_id["effect-1"] == "applied"
    # The dependent is no longer stranded behind its recovered predecessor.
    assert by_id["effect-2"] != "withheld"


def test_a_rejected_evaluation_never_claims_or_realizes_its_proposals():
    """A conflicted composition admits nothing, so it indexes nothing."""

    from participant_control_runtime_fixtures import conflicting_effect_payload
    from raes_contracts.contracts.participant_control_composition import (
        ParticipantControlEvaluationModel,
        admitted_effect_phase,
        admitted_effect_requests,
    )

    plane = _plane(control_binding(conflicting_effect_payload()))
    admit(plane, control_identity=_origin(), idempotency_key="effect-rejected-proposal")

    evaluation = ParticipantControlEvaluationModel.model_validate(_history(plane)[0])
    assert evaluation.composition.disposition == "conflict"
    assert admitted_effect_phase(evaluation) is None
    assert admitted_effect_requests(evaluation) == ()

    realizations = _dispatch(plane)

    assert realizations == ()
    assert _deliveries(plane) == set()


def test_an_interrupted_outcome_commit_is_never_repeated_or_lost(tmp_path):
    """The claim close and the realization append are one commit.

    An interruption after the owner acted but before that commit leaves the
    effect's claim open. Restart hands it to the incumbent recovery lifecycle,
    and the effect's outcome is still read from the owner record its own claim
    submitted — never re-dispatched, and never lost.
    """

    from raes_runtime.control_plane_recovery import (
        IndeterminateResolutionDisposition,
        resolve_indeterminate_operation,
        unresolved_indeterminate_operation_ids,
    )
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    store_path = tmp_path / "cp"
    resolver = StaticCrossingResolver()
    # The same trusted binding is re-supplied after restart, as an operator
    # re-admitting the run would do.
    binding = control_binding()
    plane = action_plane(
        resolver,
        target=_target(),
        store=LocalControlPlaneStore(store_path),
        participant_control=binding,
    )
    admit(plane, control_identity=_origin(), idempotency_key="effect-partial-commit")
    store = plane._store
    original = store.commit_participant_transition

    def interrupted(*args: object, **kwargs: object):
        record = kwargs.get("record")
        if record is not None and record.idempotency_key.startswith("control-effect:"):
            raise RuntimeError("durable write interrupted after the owner acted")
        return original(*args, **kwargs)

    store.commit_participant_transition = interrupted  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="interrupted"):
        _dispatch(plane)
    plane.close()

    restarted = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=resolver,
        store=LocalControlPlaneStore(store_path),
        enforce_final_sink_flow_control=False,
        participant_control=binding,
    )
    (claim,) = _effect_claims(restarted)
    # Recovery classified the open claim; nothing was recorded for it.
    assert claim.receipt.operation_id in unresolved_indeterminate_operation_ids(restarted)
    assert [item for item in _history(restarted) if ":realization:" in item["evaluation_id"]] == []

    # While the recovery barrier stands, a drain never reports the outcome as
    # recorded: the incumbent refusal propagates instead.
    with pytest.raises(RuntimeError, match="indeterminate operation requires resolution"):
        _dispatch(restarted)
    assert [item for item in _history(restarted) if ":realization:" in item["evaluation_id"]] == []

    resolve_indeterminate_operation(
        restarted,
        claim.receipt.operation_id,
        disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
        idempotency_key="resolve-interrupted-effect",
        identity=identity(audience_bound=True),
    )
    assert unresolved_indeterminate_operation_ids(restarted) == ()

    realizations = _dispatch(restarted)

    assert [item.disposition for item in realizations] == ["applied"]
    assert [item.receipt_ref for item in realizations] == [claim.receipt.operation_id]
    assert len(_deliveries(restarted)) == 1
    # The proven outcome is now durable, under a record linked to the claim...
    (transition,) = [item for item in _history(restarted) if ":realization:" in item["evaluation_id"]]
    assert [entry["disposition"] for entry in transition["realizations"]] == ["applied"]
    carriers = [
        record
        for record in restarted._store.load_records().values()
        if record.status.context.parent_operation_id == claim.receipt.operation_id
        and record.status.context.operation_kind is OperationKind.PARTICIPANT_CONTROL
    ]
    assert [record.status.state for record in carriers] == [OperationState.SUCCEEDED]
    # ...a later drain reads it from history, and subsequent work is admitted.
    assert _dispatch(restarted) == realizations
    receipt = admit(restarted, control_identity=_origin(), idempotency_key="effect-after-recovery")
    assert restarted.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED


def test_a_reused_effect_identity_never_reassigns_another_keys_receipt():
    """A realization resolves against the request in its own evaluation.

    A shared effect-id table across evaluations would be last-writer-wins, so
    a later reuse of an effect id under a different logical key could rebind an
    earlier applied receipt to that other key.
    """

    import json

    from participant_control_contract_fixtures import evaluation_payload
    from raes_runtime.participant_control_effects import _realized_keys

    first = ParticipantControlEvaluationModel.model_validate(
        _applied_evaluation(evaluation_payload(), receipt="owner-applied-1")
    )
    reused = json.loads(json.dumps(evaluation_payload()))
    # The same effect id under a different logical key, with its own outcome.
    request = next(item for item in reused["results"] if item["slot_id"] == "rule")["payload"]
    request["key"] = {**request["key"], "firing_epoch": "epoch-2"}
    second = ParticipantControlEvaluationModel.model_validate(
        _applied_evaluation(reused, receipt="owner-failed-2", disposition="failed")
    )

    realized = _realized_keys([first, second])

    by_key = {key.firing_epoch: value for key, value in realized.items()}
    assert by_key[first.results[1].payload.key.firing_epoch].receipt_ref == "owner-applied-1"
    assert by_key[first.results[1].payload.key.firing_epoch].disposition == "applied"
    assert by_key["epoch-2"].receipt_ref == "owner-failed-2"
    assert by_key["epoch-2"].disposition == "failed"


def _applied_evaluation(payload: dict, *, receipt: str, disposition: str = "applied") -> dict:
    """Attach one realization for the payload's own effect request."""

    from participant_control_contract_fixtures import ref

    request = next(item for item in payload["results"] if item["slot_id"] == "rule")["payload"]
    payload["realizations"] = [
        {
            "effect_id": request["effect_id"],
            "disposition": disposition,
            "receipt": {**ref(receipt, "receipt")},
            "evidence": [request["evidence"][0]],
        }
    ]
    return payload


def _principal(name: str, *, participant: str = PARTICIPANT, audience: bool = True, control: bool = True):
    """A distinct authenticated principal with chosen bindings."""

    from participant_crossing_fixtures import AUDIENCE, CONTROLLER
    from raes_runtime.control_plane_security import (
        ControlPlaneIdentity,
        ControlPlaneRole,
        ParticipantAudienceSubjectBinding,
        ParticipantControlSubjectBinding,
    )

    return ControlPlaneIdentity(
        identity=name,
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name="stub",
        participant_control_subjects=(
            (ParticipantControlSubjectBinding(participant_address=participant, controller_ref=CONTROLLER),)
            if control
            else ()
        ),
        participant_audience_subjects=(
            (ParticipantAudienceSubjectBinding(participant_address=participant, audience_scope_ref=AUDIENCE),)
            if audience
            else ()
        ),
    )


@pytest.mark.parametrize(
    "caller",
    [
        None,
        "not-an-identity",
        "other-participant",
    ],
)
def test_an_unauthorized_drain_is_refused_before_reading_committed_state(caller):
    """The drain caller is authorized first, so it can read and record nothing."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-unauthorized-drain")
    before = _history(plane)
    identity_value = {
        None: None,
        "not-an-identity": "operator.red",
        "other-participant": _principal("operator.green", participant="participant.behavior.blue-agent"),
    }[caller]

    with pytest.raises(PermissionError, match="participant control effect dispatch"):
        plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity_value)

    assert _history(plane) == before
    assert _effect_claims(plane) == []
    assert _deliveries(plane) == set()
    refused = [event for event in plane.audit_log() if event.action == "dispatch_participant_control_effects"]
    assert [event.allowed for event in refused] == [False]


def test_a_refused_drain_cannot_suppress_the_effect_for_an_authorized_one():
    """Nothing caller-dependent is persisted, so a later authorized drain proceeds."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-poison-attempt")
    with pytest.raises(PermissionError):
        plane.dispatch_participant_control_effects(
            PARTICIPANT,
            identity=_principal("operator.green", participant="participant.behavior.blue-agent"),
        )

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["applied"]
    assert len(_deliveries(plane)) == 1


def test_a_privileged_drain_cannot_perform_an_effect_its_origin_could_not():
    """Confused deputy: the effect acts for the principal that caused it.

    A principal bound only to control causes an eligible inject it could not
    itself disclose. An audience-bound drainer requests execution, but the
    owner authorizes the originating principal, which refuses — the drainer's
    own authority never substitutes for it.
    """

    plane = _plane(control_binding())
    control_only = _principal("operator.red", audience=False)
    admit(plane, control_identity=control_only, idempotency_key="effect-confused-deputy")

    first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=_principal("operator.privileged"))

    assert [item.disposition for item in first] == ["failed"]
    assert _deliveries(plane) == set()
    # The refusal belongs to the fixed origin, so every drain meets it identically.
    second = plane.dispatch_participant_control_effects(PARTICIPANT, identity=_principal("operator.other"))
    assert second == first


def test_effect_operations_are_attributed_to_the_originating_operation():
    """The claim retains the origin's actor and scopes and names it as parent."""

    from raes_runtime.participant_control_receipts import originating_operations

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-attribution")
    evaluation_id = _history(plane)[0]["evaluation_id"]
    origin = originating_operations(plane, PARTICIPANT)[evaluation_id]

    plane.dispatch_participant_control_effects(PARTICIPANT, identity=_principal("operator.drainer"))

    (claim,) = _effect_claims(plane)
    context = claim.status.context
    assert context.actor_id == origin.status.context.actor_id != "operator.drainer"
    assert context.authorization_scope == origin.status.context.authorization_scope
    assert context.parent_operation_id == origin.receipt.operation_id
    # The outcome's operation and its actor-bound audit belong to the origin;
    # the drain caller appears only on the audited drain request.
    recorded = next(event for event in plane.audit_log() if event.action == "record_participant_control_realization")
    assert recorded.identity == origin.status.context.actor_id
    assert recorded.operation_id == claim.receipt.operation_id
    drained = next(event for event in plane.audit_log() if event.action == "dispatch_participant_control_effects")
    assert (drained.identity, drained.allowed) == ("operator.drainer", True)


def test_different_drainers_resolve_one_claim_and_execute_once():
    """The claim identity is the origin's, so a second drainer cannot re-execute."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-two-drainers")

    first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=_principal("operator.one"))
    second = plane.dispatch_participant_control_effects(PARTICIPANT, identity=_principal("operator.two"))

    assert first == second
    assert [item.disposition for item in first] == ["applied"]
    assert len(_deliveries(plane)) == 1
    assert len(_effect_claims(plane)) == 1


def test_concurrent_drains_never_both_observe_an_effect_as_unrealized():
    """The scan, claim, submission and record happen under one held mutation."""

    import threading

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-concurrent")
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []

    def drain(name: str) -> None:
        try:
            barrier.wait()
            results.append(plane.dispatch_participant_control_effects(PARTICIPANT, identity=_principal(name)))
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    threads = [threading.Thread(target=drain, args=(name,)) for name in ("operator.left", "operator.right")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(results) == 2 and results[0] == results[1]
    assert [item.disposition for item in results[0]] == ["applied"]
    assert len(_deliveries(plane)) == 1
    assert len(_effect_claims(plane)) == 1
    assert len([item for item in _history(plane) if ":realization:" in item["evaluation_id"]]) == 1


def test_a_read_only_role_cannot_drain_effects():
    """Draining mutates, so it needs a mutating role, as crossing ingress does."""

    from dataclasses import replace as _replace

    from raes_runtime.control_plane_security import ControlPlaneRole

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-auditor-drain")
    auditor = _replace(_principal("auditor.one"), roles=frozenset({ControlPlaneRole.AUDITOR}))

    with pytest.raises(PermissionError, match="caller-forbidden"):
        plane.dispatch_participant_control_effects(PARTICIPANT, identity=auditor)

    assert _effect_claims(plane) == []


def test_a_transient_owner_error_is_not_an_outcome_of_the_effect():
    """Only the owner's own refusal fails an effect; a passing condition does not."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-transient")
    original = plane.deliver_participant_directed_view

    def unavailable(*args: object, **kwargs: object):
        del args, kwargs
        raise RuntimeError("store momentarily unavailable")

    plane.deliver_participant_directed_view = unavailable  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="momentarily unavailable"):
        _dispatch(plane)
    plane.deliver_participant_directed_view = original  # type: ignore[method-assign]

    # Nothing was recorded against the effect, and its claim stayed open.
    assert [item for item in _history(plane) if ":realization:" in item["evaluation_id"]] == []
    assert [claim.status.state for claim in _effect_claims(plane)] == [OperationState.RUNNING]

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["applied"]
    assert len(_deliveries(plane)) == 1
    assert len(_effect_claims(plane)) == 1


def test_one_logical_key_has_one_claimant_across_evaluations():
    """PC-11 allocates identity once per key, whoever re-requests it later."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-key-first")
    admit(plane, control_identity=_principal("operator.second"), idempotency_key="effect-key-second")
    admissions = [item for item in _history(plane) if ":realization:" not in item["evaluation_id"]]
    assert len(admissions) == 2

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["applied"]
    (claim,) = _effect_claims(plane)
    assert claim.status.context.actor_id == _origin().identity
    assert len(_deliveries(plane)) == 1


def test_an_effect_with_no_provable_origin_is_reported_and_never_dispatched():
    from raes_runtime.participant_control_effects import _effect_outcome

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-unattributed")
    evaluation = ParticipantControlEvaluationModel.model_validate(_history(plane)[0])
    _origin_record, request = _origin_and_request(plane)

    outcome, claim = _effect_outcome(plane, plane._participant_control, evaluation, None, request, {})

    assert (outcome.disposition, outcome.receipt.ref, claim) == ("unsupported", "unattributed.effect-1", None)
    assert _effect_claims(plane) == []
    assert _deliveries(plane) == set()


def test_another_actors_record_under_the_owner_key_never_answers_for_the_effect():
    """The owner key is derivable, so the owner record resolves in its claim scope.

    In the window where an effect is claimed but not yet submitted, another
    actor that learned the claim's identity files a succeeded operation of the
    owner's kind under the derived owner key. It is outside the owner's claim
    scope — the owner is always submitted as the originating principal — so it
    neither reports the effect applied nor blocks the real dispatch.
    """

    from raes_runtime.participant_control_receipts import claim_effect, owner_idempotency_key

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-owner-key-forgery")
    origin, request = _origin_and_request(plane)
    with control_plane_mutation(plane, OperationKind.PARTICIPANT_CONTROL):
        claim = claim_effect(plane, origin, request).record
    _claim_in_owner_scope(
        plane,
        operation_kind=OperationKind.PARTICIPANT_CROSSING,
        operation_id="forged-owner-1",
        state=OperationState.SUCCEEDED,
        key=owner_idempotency_key(claim),
        actor_id="operator.attacker",
    )

    realizations = _dispatch(plane)

    assert [item.disposition for item in realizations] == ["applied"]
    assert len(_deliveries(plane)) == 1  # the real owner ran; the forgery answered nothing


def test_a_drain_caller_supplies_nothing_the_owner_sees():
    """An audience-only drain cannot fail a supervisory handoff it has no authority over.

    The owner's evidence comes from the trusted resolver with the rest of the
    owner input, so the caller has nothing to omit or distort: its drain runs
    the handoff as the originating principal, exactly as any other drain would.
    """

    specification = control_specification()
    plane = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=StaticCrossingResolver(),
        behavior_specifications={specification.address: specification},
        participant_control=control_binding(handoff_effect_payload()),
        enforce_final_sink_flow_control=False,
    )
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    admit(plane, control_identity=_origin(), idempotency_key="effect-audience-only-drain")

    realizations = plane.dispatch_participant_control_effects(
        PARTICIPANT, identity=_principal("operator.audience-only", control=False)
    )

    assert [item.disposition for item in realizations] == ["applied"]


def test_owner_evidence_the_resolver_does_not_supply_is_unsupported_not_failed():
    """Missing owner input is an availability fact: nothing claimed, nothing recorded."""

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-no-evidence")
    plane._participant_control.resolver.effect_evidence = False

    first = _dispatch(plane)

    assert [item.disposition for item in first] == ["unsupported"]
    assert _effect_claims(plane) == []
    assert [item for item in _history(plane) if ":realization:" in item["evaluation_id"]] == []

    plane._participant_control.resolver.effect_evidence = True
    assert [item.disposition for item in _dispatch(plane)] == ["applied"]
    assert len(_deliveries(plane)) == 1


def test_owner_evidence_for_another_audience_never_reaches_the_owner():
    from participant_control_runtime_fixtures import _effect_evidence

    plane = _plane(control_binding())
    admit(plane, control_identity=_origin(), idempotency_key="effect-wrong-audience")
    resolver = plane._participant_control.resolver
    original = resolver.effect_operation

    def elsewhere(request, context):
        operation = original(request, context)
        evidence_elsewhere = _effect_evidence(context).model_copy(update={"audience_scope_ref": "audience:elsewhere"})
        return replace(operation, crossing_evidence=evidence_elsewhere)

    resolver.effect_operation = elsewhere  # type: ignore[method-assign]

    assert [item.disposition for item in _dispatch(plane)] == ["unsupported"]
    assert _deliveries(plane) == set()
