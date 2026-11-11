"""Join analysis agrees with bounded path enumeration and rejects state leakage."""

import itertools

import pytest
from raes_contracts.workflow.semantics import workflow_join_states


def _paths_to_terminals(graph, node, join):
    if node == join or not graph[node]:
        return [(node,)]
    return [(node, *path) for successor in graph[node] for path in _paths_to_terminals(graph, successor, join)]


def test_join_analysis_matches_all_small_dag_paths():
    nodes = ("a", "b", "c", "j", "end")
    edges = tuple(itertools.combinations(nodes, 2))
    for edge_mask in range(1 << len(edges)):
        graph = {node: [] for node in nodes}
        for bit, (source, target) in enumerate(edges):
            if edge_mask >> bit & 1:
                graph[source].append(target)
        observable = frozenset({"a", "c", "end"})
        expected = {}
        for node in nodes:
            paths = _paths_to_terminals(graph, node, "j")
            if all(path[-1] == "j" for path in paths):
                expected[node] = frozenset.intersection(*(frozenset(path[:-1]) & observable for path in paths))
        assert workflow_join_states(graph, join_step="j", observable_steps=observable) == expected


def test_join_boundary_excludes_its_continuation_state():
    graph = {"a": ["j"], "j": ["later"], "later": []}
    assert workflow_join_states(graph, join_step="j", observable_steps={"a", "later"}) == {
        "a": frozenset({"a"}),
        "j": frozenset(),
    }


def test_nonconvergent_branch_has_no_guaranteed_state():
    graph = {"choice": ["a", "escape"], "a": ["j"], "escape": [], "j": []}
    states = workflow_join_states(graph, join_step="j", observable_steps={"a", "escape"})
    assert "choice" not in states
    assert "escape" not in states


def test_decision_merge_retains_only_guaranteed_state():
    graph = {"choice": ["a", "b"], "a": ["common"], "b": ["common"], "common": ["j"], "j": []}
    states = workflow_join_states(graph, join_step="j", observable_steps={"a", "b", "common"})
    assert states["choice"] == frozenset({"common"})


def test_cyclic_graph_is_refused():
    with pytest.raises(ValueError, match="acyclic"):
        workflow_join_states({"a": ["a", "j"], "j": []}, join_step="j", observable_steps={"a"})


def test_missing_join_is_refused():
    with pytest.raises(ValueError, match="join must name a graph step"):
        workflow_join_states({"a": []}, join_step="j", observable_steps={"a"})
