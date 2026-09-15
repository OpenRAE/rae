"""Computed integrity checks for immutable retained research records.

These checks validate recorded joins, never parse or execute an old scenario.
The independent corpus pins fence admission to the original captures, including
invariants that cannot be proved by the frozen JSON shape contracts alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from raes_contracts.canonical import canonical_json_digest

from ._types import _PROGRESSIVE_PRODUCTION_EVIDENCE_DIGESTS, _RETAINED_PRODUCTION_EVIDENCE_DIGESTS


def _require(condition: bool, name: str) -> None:
    if not condition:
        raise ValueError(f"historical evidence invariant failed: {name}")


def _digest_join(payload: Mapping[str, Any], key: str) -> None:
    _require(payload[f"{key}_digest"] == canonical_json_digest(payload[key]), f"{key} digest join")


def _satisfiability(payload: Mapping[str, Any]) -> None:
    model = payload["normalized_model"]
    _digest_join(payload, "normalized_model")
    _digest_join(payload, "solver_configuration")
    _require(payload["source"]["byte_digest"] == model["source_digest"], "source join")
    _require(payload["authored_digest"] == model["authored_digest"], "authored join")
    if payload["witness"] is not None:
        _digest_join(payload["witness"], "snapshot")
    if payload["unsat_core"] is not None:
        ids = payload["unsat_core"]["clause_ids"]
        _require(ids == sorted(set(ids)), "core ordering")
        _require(set(ids) <= {clause["clause_id"] for clause in model["clauses"]}, "core clause join")


def _exploit_path(payload: Mapping[str, Any]) -> None:
    graph, query, configuration = (payload[key] for key in ("normalized_graph", "query", "search_configuration"))
    for key in ("normalized_graph", "query", "search_configuration"):
        _digest_join(payload, key)
    _require(payload["snapshot_digest"] == graph["snapshot_digest"], "snapshot join")
    for key in ("max_depth", "goal_check"):
        _require(query[key] == configuration[key], f"search {key} join")
    witness = payload["witness"]
    if witness is None:
        return
    _require(witness["initial_state"] == query["start_facts"], "initial state join")
    _require(witness["goal_facts"] == query["goal_facts"], "goal facts join")
    _digest_join(witness, "final_state")
    _require(len(witness["steps"]) <= query["max_depth"], "witness depth")
    transitions = {item["transition_id"]: item for item in graph["transitions"]}
    state = set(witness["initial_state"])
    for index, step in enumerate(witness["steps"]):
        _require(step["step_index"] == index, "step index")
        transition = transitions.get(step["transition_id"])
        _require(transition is not None, "transition join")
        _require(step["state_before_digest"] == canonical_json_digest(sorted(state)), "state before join")
        _require(set(transition["prerequisites"]) <= state, "transition prerequisites")
        _require(step["satisfied_prerequisites"] == transition["prerequisites"], "prerequisite join")
        _require(step["applied_effects"] == transition["effects"], "effects join")
        observations = sorted(item["observation_id"] for item in transition["observations"])
        _require(step["emitted_observations"] == observations, "observations join")
        state.update(transition["effects"])
        _require(step["state_after_digest"] == canonical_json_digest(sorted(state)), "state after join")
    _require(witness["final_state"] == sorted(state), "final state join")
    _require(set(query["goal_facts"]) <= state, "goal satisfaction")


def validate_archival_evidence_invariants(payload: Mapping[str, Any], replay_mode: object) -> None:
    """Accept only the independently pinned, shape-admitted original records."""
    if replay_mode == "satisfiability":
        _satisfiability(payload)
    else:
        _exploit_path(payload)
    _require(
        canonical_json_digest(payload)
        in _RETAINED_PRODUCTION_EVIDENCE_DIGESTS | _PROGRESSIVE_PRODUCTION_EVIDENCE_DIGESTS,
        "record is not in the retained production evidence corpus",
    )
