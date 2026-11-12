"""Multi-operation semantics, complete finite closure and bounded failure cases."""

import importlib

import pytest


@pytest.fixture(params=["multi_abstract", "multi_concrete"])
def model(request):
    return importlib.import_module(f"implementations.formal.participant_crossing.{request.param}")


def request_operation(model, state, slot, item="plain", body="original", mode="fresh"):
    return next(
        target
        for label, target in model.successors(state)
        if label == f"crossing.request.{mode}.{'ab'[slot]}" and target.intent == (slot, item, body, mode)
    )


def finish(model, state, response="observe"):
    labels = []
    seen = set()
    while state.phase != "idle":
        assert state not in seen
        seen.add(state)
        edges = model.successors(state)
        if len(edges) > 1:
            prefix = "crossing.result." if response == "observe" else "crossing.outcome.unknown."
            label, state = next(edge for edge in edges if edge[0].startswith(prefix))
        else:
            assert len(edges) == 1
            label, state = edges[0]
        labels.append(label)
    return labels, state


def fresh(model, state, slot, item="plain", response="observe"):
    return finish(model, request_operation(model, state, slot, item), response)


def test_a_retry_a_b_retry_a_and_no_second_effect(model):
    _, a = fresh(model, model.INITIAL, 0)
    labels, replayed = finish(model, request_operation(model, a, 0, mode="retry"))
    assert [label for label in labels if not label.startswith("internal.")] == ["crossing.result.permit.a"]
    assert replayed.ledger == a.ledger
    assert replayed.head == a.head == 1
    assert replayed.effects == a.effects == 1
    assert "internal.atomic-commit" not in labels
    _, b = fresh(model, replayed, 1)
    assert b.cut == a.cut == "p0"
    assert b.head == 2
    assert b.effects == 2
    assert len(b.ledger) == 2
    labels, rejected = finish(model, request_operation(model, b, 0, mode="retry"))
    assert [label for label in labels if not label.startswith("internal.")] == ["crossing.replay.reject.a"]
    assert rejected.ledger == b.ledger
    assert rejected.effects == b.effects
    assert any(label == "crossing.status.completed.a" for label, _ in model.successors(rejected))
    assert not any("request.fresh" in label for label, _ in model.successors(rejected))


@pytest.mark.parametrize("item,body", [("transform", "original"), ("plain", "changed")])
def test_conflicting_input_preserves_original_result(model, item, body):
    _, state = fresh(model, model.INITIAL, 0)
    labels, rejected = finish(model, request_operation(model, state, 0, item, body, "retry"))
    assert "crossing.replay.reject.a" in labels
    assert rejected.ledger == state.ledger
    assert rejected.head == state.head
    assert rejected.effects == state.effects


def test_operation_count_does_not_replace_history_or_policy(model):
    _, a = fresh(model, model.INITIAL, 0)
    _, b = fresh(model, a, 1, "unresolved")
    assert len(b.ledger) == 2
    assert b.head == a.head == 1
    labels, replay = finish(model, request_operation(model, b, 0, mode="retry"))
    assert "crossing.result.permit.a" in labels
    advanced = next(target for label, target in model.successors(replay) if label == "policy.cut.advance")
    labels, rejected = finish(model, request_operation(model, advanced, 0, mode="retry"))
    assert "crossing.replay.reject.a" in labels
    assert rejected.ledger == advanced.ledger
    # The unresolved-policy request has no resolved policy coordinate.
    labels, repeated = finish(model, request_operation(model, rejected, 1, "unresolved", mode="retry"))
    assert "crossing.result.unresolved.b" in labels
    assert repeated.head == 1


def test_unknown_reply_restart_and_fresh_key_duplicate_risk(model):
    labels, unknown = fresh(model, model.INITIAL, 0, response="unknown")
    assert "crossing.outcome.unknown.a" in labels
    assert unknown.known == 0
    restarted = next(target for label, target in model.successors(unknown) if label == "runtime.restart")
    assert restarted.ledger == unknown.ledger
    assert restarted.effects == 1
    labels, observed = finish(model, request_operation(model, restarted, 0, mode="retry"))
    assert "crossing.result.permit.a" in labels
    assert observed.known == 1
    assert observed.effects == 1
    assert observed.ledger == unknown.ledger
    _, duplicated = fresh(model, restarted, 1)
    assert duplicated.effects == 2


def test_lost_retry_reply_can_be_recovered_without_another_effect(model):
    _, unknown = fresh(model, model.INITIAL, 0, response="unknown")
    labels, still_unknown = finish(model, request_operation(model, unknown, 0, mode="retry"), response="unknown")
    assert "crossing.outcome.unknown.a" in labels
    assert still_unknown.known == 0
    assert still_unknown.ledger == unknown.ledger
    assert still_unknown.effects == 1
    labels, known = finish(model, request_operation(model, still_unknown, 0, mode="retry"))
    assert "crossing.result.permit.a" in labels
    assert known.effects == 1
    assert known.known == 1


def test_complete_closure_and_resource_failure(model):
    graph = model.build()
    assert graph.states[graph.initial] == model.INITIAL
    index = {state: ordinal for ordinal, state in enumerate(graph.states)}
    assert len(index) == len(graph.states)
    assert set(graph.edges) == {
        (ordinal, label, index[target])
        for ordinal, state in enumerate(graph.states)
        for label, target in model.successors(state)
    }
    assert all(model.successors(state) for state in graph.states)
    assert max(state.head for state in graph.states) == 2
    assert max(len(state.ledger) for state in graph.states) == 2
    assert model.build() == graph
    with pytest.raises(ValueError, match="resource limit"):
        model.build(max_states=1)


@pytest.mark.parametrize("cut", ["p0", "p1"])
@pytest.mark.parametrize("item", ["plain", "transform", "declassify", "unsupported", "forbidden", "unresolved"])
def test_every_fresh_outcome_and_repeated_retry(model, cut, item):
    from dataclasses import replace

    labels, completed = fresh(model, replace(model.INITIAL, cut=cut), 0, item)
    outcome = {
        "plain": "permit",
        "transform": "transform",
        "declassify": "declassify" if cut == "p1" else "deny",
        "unsupported": "unsupported",
        "forbidden": "deny",
        "unresolved": "unresolved",
    }[item]
    assert completed.ledger[0][5] == outcome
    assert labels[-1] == f"crossing.result.{outcome}.a"
    assert completed.head == (outcome != "unresolved")
    assert completed.effects == (outcome in {"permit", "transform", "declassify"})
    for _ in range(3):
        labels, repeated = finish(model, request_operation(model, completed, 0, item, mode="retry"))
        assert [label for label in labels if not label.startswith("internal.")] == [f"crossing.result.{outcome}.a"]
        assert repeated.ledger == completed.ledger
        assert repeated.effects == completed.effects
        completed = repeated


def test_hidden_progress_and_atomic_fresh_commits():
    from implementations.formal.participant_crossing import multi_concrete

    graph = multi_concrete.build()
    for source, label, target in graph.edges:
        before, after = graph.states[source], graph.states[target]
        if label.startswith("internal."):
            assert multi_concrete.internal_rank(before) > multi_concrete.internal_rank(after)
        if before.ledger != after.ledger:
            assert label == "internal.atomic-commit"
            assert before.intent[3] == "fresh"
            assert len(after.ledger) == len(before.ledger) + 1
        if before.effects != after.effects:
            assert label.startswith("crossing.delivery.")
            assert after.effects == before.effects + 1
        if before.head != after.head:
            assert label == "internal.atomic-commit"
            assert after.head == before.head + 1
