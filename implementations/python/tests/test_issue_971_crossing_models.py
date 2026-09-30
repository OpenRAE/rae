"""Complete single-operation crossing models, independently constructed."""

from dataclasses import replace

import pytest
from implementations.formal.participant_crossing import abstract, concrete


def finish(module, state):
    labels = []
    visited = set()
    while state.phase != "terminal":
        assert state not in visited, "crossing must make finite progress"
        visited.add(state)
        edges = module.successors(state)
        assert len(edges) == 1
        label, state = edges[0]
        labels.append(label)
    return labels, state


@pytest.mark.parametrize("module", [abstract, concrete])
@pytest.mark.parametrize("cut", ["p0", "p1"])
@pytest.mark.parametrize("input_class", ["plain", "transform", "declassify", "unsupported", "forbidden"])
def test_policy_sequences_and_replay(module, cut, input_class):
    start = replace(module.INITIAL, cut=cut)
    requests = [(label, target) for label, target in module.successors(start) if label == "crossing.request"]
    offered = next(target for _, target in requests if target.intent[1] == input_class)
    labels, terminal = finish(module, offered)
    visible = [label for label in labels if not label.startswith("internal.")]
    if input_class == "unsupported":
        expected = ["crossing.decision.unsupported"]
    elif input_class == "forbidden" or (input_class == "declassify" and cut == "p0"):
        expected = ["crossing.decision.deny"]
    else:
        expected = ["crossing.decision.permit"]
        if input_class != "plain":
            expected.append(f"crossing.{input_class}")
        expected.extend(["crossing.delivery", "crossing.observation"])
    assert visible == expected
    assert terminal.last == ("request-0", cut, terminal.decision)
    replay = next(target for label, target in module.successors(terminal) if label == "crossing.request")
    replay_labels, repeated = finish(module, replay)
    assert [label for label in replay_labels if not label.startswith("internal.")] == expected
    assert repeated.last == terminal.last
    if module is concrete:
        assert terminal.head == repeated.head == "h1"
        assert "internal.atomic-commit" not in replay_labels
    if cut == "p0":
        advanced = next(target for label, target in module.successors(terminal) if label == "policy.cut.advance")
        stale = next(target for label, target in module.successors(advanced) if label == "crossing.request")
        rejected_labels, rejected = finish(module, stale)
        assert [label for label in rejected_labels if not label.startswith("internal.")] == ["crossing.replay.reject"]
        assert rejected.last == terminal.last
        if module is concrete:
            assert rejected.head == terminal.head


@pytest.mark.parametrize("module", [abstract, concrete])
def test_exhaustive_reachable_closure(module):
    graph = module.build()
    assert graph.states[graph.initial] == module.INITIAL
    assert len(graph.states) == len(set(graph.states))
    index = {state: i for i, state in enumerate(graph.states)}
    expected = {
        (index[state], label, index[target]) for state in graph.states for label, target in module.successors(state)
    }
    assert set(graph.edges) == expected
    reachable = {graph.initial}
    while True:
        expanded = reachable | {target for source, _, target in graph.edges if source in reachable}
        if expanded == reachable:
            break
        reachable = expanded
    assert reachable == set(range(len(graph.states)))
    assert all(module.successors(state) for state in graph.states)
    assert module.build() == graph


def test_atomic_refusal_and_hidden_progress():
    graph = concrete.build()
    for source, label, target in graph.edges:
        before, after = graph.states[source], graph.states[target]
        if label.startswith("internal."):
            assert concrete.internal_rank(before) > concrete.internal_rank(after)
        if before.head != after.head:
            assert label == "internal.atomic-commit"
            assert before.head == "h0"
            assert after.head == "h1"
            assert before.last is None
            assert after.last is not None
        if before.phase == "preparing-record" and before.intent[3] == "fresh":
            assert before.head == "h0"
            assert before.last is None


@pytest.mark.parametrize("module", [abstract, concrete])
def test_resource_limit_fails_instead_of_returning_partial_graph(module):
    with pytest.raises(ValueError, match="resource limit"):
        module.build(max_states=1)


@pytest.mark.parametrize("module", [abstract, concrete])
def test_transition_enumeration_order_does_not_change_export(module, monkeypatch):
    expected = module.build()
    original = module.successors
    monkeypatch.setattr(module, "successors", lambda state: list(reversed(original(state))))
    assert module.build() == expected
