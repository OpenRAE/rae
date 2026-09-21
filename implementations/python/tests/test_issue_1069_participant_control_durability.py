"""Issue #1069 durability, replay and concurrency for composed control state.

Both supported stores preserve the exact contribution, composition and effect
history within their own supported lifetimes: the durable local (P1) store
carries it across a restart with retained deduplication, while the in-memory
(P0) store discards it with the process, exactly as API-404 declares.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from participant_control_runtime_fixtures import control_binding
from participant_crossing_fixtures import (
    PARTICIPANT,
    StaticCrossingResolver,
    action_plane,
    admit,
    policy_capable_target,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore

_CARRIER = "participant_control_evaluation_history"


def _target():
    return policy_capable_target("participant_ingress_admission", "participant_modular_control")


def _plane(*, store=None, binding=None, resolver=None):
    return action_plane(
        resolver or StaticCrossingResolver(),
        target=_target(),
        store=store,
        participant_control=binding or control_binding(),
    )


def _evaluations(plane) -> list[dict]:
    return list(plane.snapshot.participant_control_evaluation_history.get(PARTICIPANT, ()))


@pytest.mark.parametrize(
    "make_store", [lambda _p: InMemoryControlPlaneStore(), lambda p: LocalControlPlaneStore(p / "cp")]
)
def test_both_stores_preserve_the_exact_composition_history(make_store, tmp_path: Path):
    plane = _plane(store=make_store(tmp_path / "compose"))

    admit(plane, idempotency_key="durable-compose")

    evaluations = _evaluations(plane)
    assert len(evaluations) == 1
    assert evaluations[0]["composition"]["disposition"] == "eligible"
    assert [result["slot_id"] for result in evaluations[0]["results"]] == ["fact", "rule"]


def test_a_local_store_restart_replays_the_exact_history(tmp_path: Path):
    store_path = tmp_path / "control-plane"
    # The same trusted resolver is re-supplied after restart, as an operator
    # re-admitting the run would do; restart revalidates the retained history.
    resolver = StaticCrossingResolver()
    first = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver)
    admit(first, idempotency_key="durable-restart")
    committed = _evaluations(first)
    crossings = dict(first.snapshot.participant_crossing_history)
    first.close()

    second = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver)

    assert _evaluations(second) == committed
    assert dict(second.snapshot.participant_crossing_history) == crossings


def test_a_restarted_local_store_retains_its_idempotent_claim(tmp_path: Path):
    store_path = tmp_path / "control-plane"
    resolver = StaticCrossingResolver()
    first = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver)
    receipt = admit(first, idempotency_key="durable-replay")
    first.close()

    second = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver)
    replayed = admit(second, idempotency_key="durable-replay")

    assert replayed.operation_id == receipt.operation_id
    assert len(_evaluations(second)) == 1


def test_an_in_memory_store_claims_nothing_beyond_its_process_lifetime(tmp_path: Path):
    """P0 keeps no durable state, so a fresh plane starts with no history."""

    first = _plane(store=InMemoryControlPlaneStore())
    admit(first, idempotency_key="ephemeral")
    assert len(_evaluations(first)) == 1

    second = _plane(store=InMemoryControlPlaneStore())

    assert _evaluations(second) == []


def test_a_second_concurrent_owner_cannot_write_the_committed_history(tmp_path: Path):
    """One durable owner at a time: a rival owner is refused, not merged."""

    store_path = tmp_path / "cp"
    owner = _plane(store=LocalControlPlaneStore(store_path))
    admit(owner, idempotency_key="sole-owner")

    second_store = LocalControlPlaneStore(store_path)
    with pytest.raises(RuntimeError, match="already has a runtime owner"):
        _plane(store=second_store)

    assert len(_evaluations(owner)) == 1


def test_a_stale_expected_head_refuses_a_second_commit(tmp_path: Path):
    """The evaluation carrier joins the expected-head cut the store enforces."""

    from raes_runtime.control_plane_store_history import require_expected_history_heads

    plane = _plane(store=LocalControlPlaneStore(tmp_path / "cp"))
    stale_heads = {f"{_CARRIER}:{PARTICIPANT}": None}
    admit(plane, idempotency_key="stale-head")

    with pytest.raises(ValueError, match="history head"):
        require_expected_history_heads(plane.snapshot, stale_heads)


def test_a_second_evaluation_cannot_re_spend_a_consumed_root_budget(tmp_path: Path):
    """PC-12 budgets are durable: an under-declared context is refused."""

    from participant_control_runtime_fixtures import ForgetfulConsumptionResolver

    plane = _plane(store=LocalControlPlaneStore(tmp_path / "cp"))
    admit(plane, idempotency_key="budget-first")
    assert _evaluations(plane)[0]["composition"]["disposition"] == "eligible"

    binding = plane._participant_control
    forgetful = ForgetfulConsumptionResolver(payload=binding.resolver.payload, providers=binding.resolver.providers)
    object.__setattr__(binding, "resolver", forgetful)
    receipt = admit(plane, idempotency_key="budget-second")

    # The under-declared context is refused before composition, so no second
    # evaluation is recorded and the operation fails closed.
    assert len(_evaluations(plane)) == 1
    assert plane.get_operation(receipt.operation_id).state.value == "failed"
    assert plane.audit_log()[-1].details["control_disposition"] == "stale"


def test_the_causal_fold_reports_what_a_root_already_consumed():
    from participant_control_runtime_fixtures import control_binding as _binding
    from raes_runtime.participant_control_causal_state import causal_state_from_history

    plane = _plane(binding=_binding())
    admit(plane, idempotency_key="budget-fold")
    evaluation = _evaluations(plane)[0]
    context = evaluation["request"]["context"]

    state = causal_state_from_history(
        _evaluations(plane),
        run_ref=context["run"]["ref"],
        trigger_root=context["trigger_root"],
    )

    assert state.effects_consumed == 1
    assert set(state.firings) == {("hint-followup", "rev1")}


def test_a_root_that_resolved_no_effect_still_consumes_its_attempt(tmp_path: Path):
    """PC-12 bounds the causal root, not one request.

    An evaluation spends an attempt whether or not it resolves an effect, so a
    root cannot be re-resolved indefinitely by declaring ``attempt=1`` on each
    fresh crossing.
    """

    from participant_control_runtime_fixtures import control_binding, fact_only_payload

    plane = _plane(store=LocalControlPlaneStore(tmp_path / "cp"), binding=control_binding(fact_only_payload()))
    admit(plane, idempotency_key="attempt-first")
    first = _evaluations(plane)
    assert len(first) == 1
    assert first[0]["request"]["context"]["attempt"] == 1
    assert not [result for result in first[0]["results"] if result["payload"]["kind"] == "effect-request"]

    admit(plane, idempotency_key="attempt-second")

    # The second evaluation under this root declares a fresh attempt.
    assert [item["request"]["context"]["attempt"] for item in _evaluations(plane)] == [1, 2]


def test_a_re_declared_attempt_is_refused_after_a_restart(tmp_path: Path):
    """The retained attempt survives the process that observed it."""

    from participant_control_runtime_fixtures import ForgetfulConsumptionResolver, control_binding

    store_path = tmp_path / "cp"
    resolver = StaticCrossingResolver()
    plane = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver)
    admit(plane, idempotency_key="attempt-restart-first")
    plane.close()

    restarted = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver, binding=control_binding())
    binding = restarted._participant_control
    forgetful = ForgetfulConsumptionResolver(payload=binding.resolver.payload, providers=binding.resolver.providers)
    object.__setattr__(binding, "resolver", forgetful)
    receipt = admit(restarted, idempotency_key="attempt-restart-second")

    assert len(_evaluations(restarted)) == 1
    assert restarted.get_operation(receipt.operation_id).state.value == "failed"


def test_the_causal_fold_reports_the_attempts_a_root_already_spent():
    from participant_control_runtime_fixtures import control_binding as _binding
    from raes_runtime.participant_control_causal_state import causal_state_from_history

    plane = _plane(binding=_binding())
    admit(plane, idempotency_key="attempt-fold")
    evaluation = _evaluations(plane)[0]
    context = evaluation["request"]["context"]

    state = causal_state_from_history(
        _evaluations(plane),
        run_ref=context["run"]["ref"],
        trigger_root=context["trigger_root"],
    )

    assert state.attempts == context["attempt"]
    assert state.next_attempt == context["attempt"] + 1


def test_a_rejected_proposal_never_consumes_the_roots_effect_budget(tmp_path: Path):
    """Contributor order cannot decide what a later context must retain.

    A conflicted composition admits nothing, so neither conflicting payload
    becomes a retained claim — whichever order the contributors arrived in.
    """

    from participant_control_runtime_fixtures import conflicting_effect_payload, control_binding
    from raes_runtime.participant_control_causal_state import causal_state_from_history

    folds = []
    for reverse in (False, True):
        plane = _plane(
            store=LocalControlPlaneStore(tmp_path / f"cp-{reverse}"),
            binding=control_binding(conflicting_effect_payload()),
        )
        for provider in plane._participant_control.resolver.providers:
            provider.reverse = reverse
        admit(plane, idempotency_key="conflict-budget")
        evaluation = _evaluations(plane)[0]
        assert evaluation["composition"]["disposition"] == "conflict"
        context = evaluation["request"]["context"]
        state = causal_state_from_history(
            _evaluations(plane),
            run_ref=context["run"]["ref"],
            trigger_root=context["trigger_root"],
        )
        folds.append((state.effects_consumed, sorted(state.firings)))
        plane.close()

    # No claim either way, so the fold does not depend on arrival order.
    assert folds[0] == folds[1] == (0, [])


def _downgrade_to_schema_5(store_path: Path) -> None:
    """Rewrite a store as a pre-carrier build left it: schema 5, no carrier."""

    import sqlite3

    from raes_runtime.control_plane_store_local_codec import decode_payload, encode_payload

    connection = sqlite3.connect(store_path / "control-plane.sqlite3")
    try:
        encoded, digest = connection.execute(
            "SELECT payload, digest FROM state WHERE key='runtime-snapshot'"
        ).fetchone()
        payload = decode_payload(encoded, digest, kind="runtime snapshot")
        payload.pop(_CARRIER)
        encoded, digest = encode_payload(payload)
        connection.execute(
            "UPDATE state SET payload=?, digest=? WHERE key='runtime-snapshot'",
            (encoded, digest),
        )
        connection.execute("UPDATE metadata SET value='5' WHERE key='schema-version'")
        connection.commit()
    finally:
        connection.close()


def _stored_schema_and_carrier(store_path: Path) -> tuple[str, bool]:
    import sqlite3

    from raes_runtime.control_plane_store_local_codec import decode_payload

    connection = sqlite3.connect(store_path / "control-plane.sqlite3")
    try:
        (version,) = connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone()
        encoded, digest = connection.execute(
            "SELECT payload, digest FROM state WHERE key='runtime-snapshot'"
        ).fetchone()
        return version, _CARRIER in decode_payload(encoded, digest, kind="runtime snapshot")
    finally:
        connection.close()


def test_upgrading_a_pre_carrier_store_records_the_carrier_explicitly(tmp_path: Path):
    """No pre-schema-6 build can have written a modular evaluation.

    So the upgrade records the missing carrier as authoritatively empty, and
    from then on every openable store carries it explicitly — an older build
    refuses the store instead of re-serializing it without the carrier.
    """

    from raes_runtime.control_plane_store_record_migration import LOCAL_OPERATION_SCHEMA_VERSION

    store_path = tmp_path / "cp"
    resolver = StaticCrossingResolver()
    plane = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver)
    admit(plane, idempotency_key="pre-carrier-history")
    crossings = dict(plane.snapshot.participant_crossing_history)
    plane.close()
    _downgrade_to_schema_5(store_path)
    assert _stored_schema_and_carrier(store_path) == ("5", False)

    upgraded = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=resolver,
        store=LocalControlPlaneStore(store_path),
        enforce_final_sink_flow_control=False,
    )
    upgraded.close()

    assert _stored_schema_and_carrier(store_path) == (LOCAL_OPERATION_SCHEMA_VERSION, True)
    assert LOCAL_OPERATION_SCHEMA_VERSION == "6"
    assert crossings  # the participant history the upgrade preserved


def test_an_upgraded_store_starts_modular_control_and_restarts_cleanly(tmp_path: Path):
    """Migrate, initialize modular control, restart: every step succeeds."""

    store_path = tmp_path / "cp"
    resolver = StaticCrossingResolver()
    binding = control_binding()
    plane = action_plane(resolver, target=_target(), store=LocalControlPlaneStore(store_path))
    plane.close()
    _downgrade_to_schema_5(store_path)

    modular = _plane(store=LocalControlPlaneStore(store_path), resolver=resolver, binding=binding)
    admit(modular, idempotency_key="post-upgrade-control")
    committed = _evaluations(modular)
    assert len(committed) == 1
    modular.close()

    restarted = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=resolver,
        store=LocalControlPlaneStore(store_path),
        enforce_final_sink_flow_control=False,
        participant_control=binding,
    )
    assert _evaluations(restarted) == committed
    restarted.close()


def test_a_store_newer_than_this_build_is_refused_rather_than_rewritten(tmp_path: Path):
    """The downgrade guard: an unknown schema is never re-serialized."""

    import sqlite3

    store_path = tmp_path / "cp"
    plane = _plane(store=LocalControlPlaneStore(store_path))
    plane.close()
    connection = sqlite3.connect(store_path / "control-plane.sqlite3")
    connection.execute("UPDATE metadata SET value='7' WHERE key='schema-version'")
    connection.commit()
    connection.close()

    newer_store = LocalControlPlaneStore(store_path)
    with pytest.raises(ValueError, match="unsupported local control-plane database schema"):
        _plane(store=newer_store)


def test_committed_consumption_is_a_watermark_not_a_claim_count():
    """PC-12: a spent budget stays spent even when no claim is retained for it."""

    from participant_control_runtime_fixtures import (
        _rebound_context_digests,
        control_binding,
        fact_only_payload,
    )
    from raes_contracts.contracts.participant_control_composition import ParticipantControlRequestModel
    from raes_runtime.participant_control_causal_state import (
        causal_state_from_history,
        declares_retained_consumption,
    )

    plane = _plane(binding=control_binding(fact_only_payload()))
    admit(plane, idempotency_key="watermark")
    committed = _evaluations(plane)[0]
    # A committed context that declares consumption beyond its retained claims.
    committed["request"]["context"]["effects_consumed"] = 2  # the whole admitted budget
    _rebound_context_digests(committed)
    context = committed["request"]["context"]

    state = causal_state_from_history([committed], run_ref=context["run"]["ref"], trigger_root=context["trigger_root"])

    assert state.claims == {}
    assert state.effects_consumed == 2
    replenished = ParticipantControlRequestModel.model_validate(
        {**committed["request"], "context": {**context, "effects_consumed": 0, "attempt": 2}}
    ).context
    assert declares_retained_consumption(replenished, state) is False
