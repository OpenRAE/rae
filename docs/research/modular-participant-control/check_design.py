"""Finite design falsification for ADR-108; not a runtime/provider implementation.

Run directly with Python. The model deliberately excludes actual provider
execution, schemas, stores, network delivery and backend instrumentation.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, replace
from itertools import permutations, product
from pathlib import Path


@dataclass(frozen=True)
class Slot:
    name: str
    mandatory: bool
    outcome: str


def blockers(slots: tuple[Slot, ...], incumbent_permit: bool) -> frozenset[str]:
    """PC-05/06 projection: mandatory facts/decisions and the incumbent gate."""
    reasons = {s.name for s in slots if s.mandatory and s.outcome not in {"permit", "fact"}}
    if not incumbent_permit:
        reasons.add("incumbent")
    return frozenset(reasons)


@dataclass(frozen=True)
class Effect:
    """One stable logical key, one root budget unit, durable dispatch marker."""

    phase: str = "absent"
    budget: int = 1
    calls: int = 0
    content: str | None = None
    history: tuple[str, ...] = ()


def step(state: Effect, event: str) -> Effect:
    """PC-10/11 finite abstraction; failed admission/commit never invokes."""
    phase = state.phase
    if event == "claim" and phase == "absent" and state.budget:
        return replace(state, phase="committed", budget=0, content="inject-A", history=(*state.history, "claim"))
    if event == "dispatch" and phase == "committed":
        return replace(state, phase="dispatching", calls=state.calls + 1, history=(*state.history, "dispatch"))
    if event == "observed" and phase in {"dispatching", "indeterminate"}:
        return replace(state, phase="applied", history=(*state.history, "observed"))
    if event == "crash" and phase == "dispatching":
        return replace(state, phase="indeterminate", history=(*state.history, "unknown"))
    # Deny, stale cut, failed commit and same-key replay have no effect.
    # Changed content under the existing key conflicts without replacing it.
    return state


class DesignChecks(unittest.TestCase):
    def test_all_result_orders_and_advisory_roles(self) -> None:
        outcomes = (
            "permit",
            "fact",
            "deny",
            "withhold",
            "abstain",
            "missing",
            "unknown",
            "unsupported",
            "stale",
            "failed",
            "weakened",
        )
        for values in product(outcomes, repeat=3):
            for roles in product((False, True), repeat=3):
                slots = tuple(Slot(str(i), roles[i], values[i]) for i in range(3))
                expected = blockers(slots, True)
                for order in permutations(slots):
                    self.assertEqual(blockers(order, True), expected)
                self.assertIn("incumbent", blockers(slots, False))
                if any(s.mandatory and s.outcome not in {"permit", "fact"} for s in slots):
                    self.assertTrue(expected)
                # Adding a mandatory denial cannot make the parent releasable.
                self.assertTrue(blockers((*slots, Slot("veto", True, "deny")), True))

    def test_observation_fact_is_not_a_decision_grant(self) -> None:
        observation = (Slot("tracking", True, "fact"), Slot("monitor", False, "deny"))
        self.assertFalse(blockers(observation, True))
        self.assertTrue(blockers(observation, False))
        self.assertTrue(blockers((*observation, Slot("sink", True, "deny")), True))
        self.assertTrue(blockers((Slot("tracking", True, "unknown"),), True))

    def test_finite_ifc_join_laws_and_opaque_memory(self) -> None:
        domain = tuple(
            frozenset(x for x, selected in zip(("hint", "example"), bits, strict=True) if selected)
            for bits in product((False, True), repeat=2)
        )
        for a, b, c in product(domain, repeat=3):
            self.assertIn(a | b, domain)
            self.assertEqual(a | a, a)
            self.assertEqual(a | b, b | a)
            self.assertEqual((a | b) | c, a | (b | c))
            self.assertLessEqual(a, a | b)
            if a <= b:
                self.assertLessEqual(a | c, b | c)
        observation, memory = frozenset({"hint"}), frozenset({"example"})
        self.assertEqual(observation | memory, frozenset({"hint", "example"}))
        # Counterexample to discarding memory on reset: the derivation loses an input.
        self.assertNotEqual(observation, observation | memory)

    def test_crash_retry_and_failed_commit_schedules(self) -> None:
        events = (
            "claim",
            "dispatch",
            "observed",
            "crash",
            "deny",
            "stale",
            "failed-commit",
            "replay",
            "changed-content",
        )
        frontier = {Effect()}
        seen = set(frontier)
        for _depth in range(7):
            successors = set()
            for state, event in product(frontier, events):
                new = step(state, event)
                self.assertLessEqual(new.calls, 1)
                self.assertIn(new.budget, (0, 1))
                self.assertEqual(new.history[: len(state.history)], state.history)
                if new.calls:
                    self.assertEqual(new.content, "inject-A")
                    self.assertEqual(new.budget, 0)
                    self.assertEqual(new.history[0], "claim")
                if state.phase == "indeterminate" and event != "observed":
                    self.assertEqual(new, state)
                if event in {"deny", "stale", "failed-commit", "changed-content"}:
                    self.assertEqual(new, state)
                successors.add(new)
            frontier = successors - seen
            seen |= successors
        self.assertEqual({s.phase for s in seen}, {"absent", "committed", "dispatching", "indeterminate", "applied"})
        self.assertFalse(any(step(Effect(), e).calls for e in events))

    def test_trigger_cycle_is_finite_and_retry_cannot_reset_root(self) -> None:
        # A -> B -> A inject cycle. Every new key consumes root budget; replay
        # reuses its key. Explore both events, rather than assuming one ordering.
        for root_limit, depth_limit in product(range(4), repeat=2):
            states = {(0, 0, frozenset())}
            for _ in range(8):
                next_states = set(states)
                for used, depth, keys in states:
                    # Retry, handoff and restart leave root accounting unchanged.
                    next_states.add((used, depth, keys))
                    if used < root_limit and depth < depth_limit:
                        key = ("root", "A" if depth % 2 == 0 else "B", depth)
                        next_states.add((used + 1, depth + 1, keys | {key}))
                states = next_states
            self.assertTrue(
                all(used == len(keys) and used <= root_limit and depth <= depth_limit for used, depth, keys in states)
            )
            self.assertEqual(max(used for used, _, _ in states), min(root_limit, depth_limit))

    def test_delivery_dependencies_and_independent_backend_selection(self) -> None:
        graph = json.loads(Path(__file__).with_name("delivery.json").read_text())
        nodes = {n["id"]: n for n in graph["nodes"]}
        self.assertEqual(len(nodes), len(graph["nodes"]))
        self.assertEqual(len(nodes), 15)  # architecture plus all 14 delivery nodes
        visited, visiting = set(), set()

        def visit(key: str) -> None:
            self.assertNotIn(key, visiting, f"cycle at {key}")
            if key in visited:
                return
            visiting.add(key)
            node = nodes[key]
            dependencies = (
                node["requires_all"] + sum(node["requires_any"], []) + node.get("requires_for_adversarial_claims", [])
            )
            for dependency in dependencies:
                self.assertIn(dependency, nodes)
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for key in nodes:
            visit(key)
        evaluation = nodes["OpenRAE/rae#1007"]
        alternatives = set(evaluation["requires_any"][0])
        self.assertEqual(alternatives, {"OpenRAE/lilrae#22", "Brad-Edwards/shifter#1969"})
        for backend in alternatives:
            completed = set(evaluation["requires_all"]) | {backend}
            self.assertTrue(all(completed.intersection(group) for group in evaluation["requires_any"]))
        self.assertFalse(set(evaluation["requires_all"]).intersection(alternatives))
        # Cross-repo UIDs explicitly reference RAES records, all of which must exist.
        repo = Path(__file__).resolve().parents[3]
        for node in nodes.values():
            for uid in node["requirements"]:
                path = repo / "docs" / "requirements" / uid / "requirement.md"
                self.assertTrue(path.is_file(), f"missing authority {uid}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
