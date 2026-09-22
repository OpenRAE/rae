"""Executable counterexamples for the #1352 semantic decision, not conformance."""

from dataclasses import FrozenInstanceError, replace
from itertools import permutations, product

import control_applicability_model as m
import pytest
from sem235_modular_control_model import Result, Slot


def fact(node, predecessors, cut):
    return Result(node.slot.ref, node.slot.kind, cut=cut)


def required(*slots, sink="in"):
    return (m.Obligation("profile", frozenset({sink}), slots),)


def test_disjoint_sinks_preserve_apparatus_and_account_for_every_obligation():
    nodes = (m.Node(Slot("ingress", "fact")), m.Node(Slot("egress", "fact"), sinks=frozenset({"out"})))
    obligations = (*required("ingress"), m.Obligation("output-profile", frozenset({"out"}), ("egress",)))
    for sink, active, inactive in (("in", "ingress", "output-profile"), ("out", "egress", "profile")):
        result = m.evaluate(nodes, obligations, fact, sink=sink)
        assert result.apparatus == nodes
        assert result.applicable == (active,)
        assert result.inapplicable == (inactive,)
        assert not result.blockers


def test_missing_and_unresolved_coverage_never_become_empty_success():
    assert m.evaluate((), required("missing"), fact).blockers == ("coverage:profile",)
    assert m.evaluate((), required(), fact).blockers == ("coverage:profile",)
    unknown = (m.Obligation("profile", None, ()),)
    assert m.evaluate((), unknown, fact).blockers == ("applicability:profile",)
    node = m.Node(Slot("f", "fact"), sinks=None)
    assert m.evaluate((node,), required("f"), fact).blockers
    assert not m.evaluate((), required(sink="out"), fact).blockers
    assert m.evaluate((), (), fact, incumbent=False).blockers == ("incumbent",)


def test_slot_invocation_carries_fresh_immutable_predecessors_back_to_provider_a():
    nodes = (
        m.Node(Slot("fact", "fact")),
        m.Node(Slot("assessment", "advice", False, ("fact",)), provider="B"),
        m.Node(Slot("rule", "decision", True, ("assessment",))),
    )
    for ordering in permutations(nodes):
        calls = []

        def resolve(node, predecessors, cut, calls=calls):
            calls.append((node.provider, node.slot.ref))
            if node.slot.ref == "fact":
                assert predecessors == ()
                return Result("fact", "fact", cut=cut, payload="influence")
            assert len(predecessors) == 1
            with pytest.raises(FrozenInstanceError):
                predecessors[0].payload = "changed"
            if node.slot.ref == "assessment":
                assert predecessors[0].payload == "influence"
                return Result("assessment", "advice", cut=cut, payload="deny")
            assert predecessors[0].payload == "deny"
            # Advice availability is required; its negative opinion is not a veto.
            return Result("rule", "decision", cut=cut, payload="permit")

        result = m.evaluate(ordering, required("rule"), resolve)
        assert calls == [("A", "fact"), ("B", "assessment"), ("A", "rule")]
        assert result.required == frozenset({"fact", "assessment", "rule"})
        assert not result.blockers


@pytest.mark.parametrize("failure", ("missing", "failed", "stale", "wrong-slot", "wrong-kind", "exception"))
def test_optional_failures_are_isolated_but_required_dependencies_block(failure):
    advice = m.Node(Slot("advice", "advice", False))

    def resolve(node, predecessors, cut):
        if node.slot.ref == "consumer":
            pytest.fail("consumer must not run without its required input")
        if failure == "exception":
            raise ValueError("private rejected payload")
        if failure == "missing":
            return None
        if failure == "wrong-slot":
            return Result("forged", "advice")
        if failure == "wrong-kind":
            return Result("advice", "decision", payload="deny")
        return Result("advice", "advice", status="failed" if failure == "failed" else "resolved", cut="K1")

    optional = m.evaluate((advice,), (), resolve)
    assert not optional.blockers
    assert optional.lost
    assert "private" not in repr(optional)
    consumer = m.Node(Slot("consumer", "decision", True, ("advice",)))
    mandatory = m.evaluate((advice, consumer), required("consumer"), resolve)
    assert mandatory.blockers
    assert {r.slot for r in mandatory.results} == {"advice", "consumer"}


@pytest.mark.parametrize(
    "loss,limit,accepted", ((0, 0, True), (1, 2, True), (2, 1, False), (1, 0, False), (None, 2, False))
)
def test_support_must_satisfy_the_admitted_constraint(loss, limit, accepted):
    node = m.Node(Slot("f", "fact"), loss=loss, allowed_loss=limit)
    assert (not m.evaluate((node,), required("f"), fact).blockers) is accepted
    optional = replace(node, slot=Slot("f", "advice", False))
    assert not m.evaluate((optional,), (), fact).blockers


def test_false_trigger_is_explicit_and_not_a_missing_mandatory_result():
    node = m.Node(Slot("rule", "request"))

    def resolved(node, predecessors, cut):
        return Result(node.slot.ref, "request", cut=cut, payload="not-triggered")

    assert not m.evaluate((node,), required("rule"), resolved).blockers
    assert m.evaluate((node,), required("rule"), lambda n, p, k: None).blockers


def test_slot_graph_rejects_cycles_unknown_edges_and_duplicate_slots():
    invalid = (
        (m.Node(Slot("a", "fact", dependencies=("a",))),),
        (m.Node(Slot("a", "fact", dependencies=("absent",))),),
        (m.Node(Slot("a", "fact")), m.Node(Slot("a", "fact"))),
    )
    for nodes in invalid:
        with pytest.raises(ValueError):
            m.evaluate(nodes, (), fact)


@pytest.mark.parametrize(
    "decision,phase", tuple(product(("deny", "withhold"), ("predecessor", "subsequent", "independent")))
)
def test_parent_decision_cannot_be_weakened_by_phase(decision, phase):
    legacy_target = m.Effect("parent-decision", decision, "parent", phase)
    assert m.effect_decision(("permit",), (legacy_target,))[0] == decision
    assert m.effect_decision((decision,), (m.Effect("prerequisite", phase="predecessor"),))[0] == decision


def test_independent_audit_has_its_own_authority_and_never_releases_denied_parent():
    audit = m.Effect("audit")
    assert m.effect_decision(("deny",), (audit,)) == ("deny", ("audit",))
    for refused in (
        replace(audit, authorized=False),
        replace(audit, supported=False),
        replace(audit, accepts=frozenset()),
    ):
        assert m.effect_decision(("deny",), (refused,)) == ("deny", ())
    assert m.effect_decision(("permit",), (), incumbent=False)[0] != "permit"


def test_prerequisite_requires_fresh_parent_evaluation_and_success_consequence_waits():
    prerequisite = m.Effect("review", phase="predecessor")
    after = m.Effect("followup", phase="subsequent")
    assert m.effect_decision(("permit",), (prerequisite, after)) == ("withhold", ("review",))
    assert m.effect_decision(("permit",), (prerequisite, after), applied=frozenset({"review"})) == ("permit", ())
    assert m.effect_decision(("permit",), (after,), applied=frozenset({"parent"})) == ("permit", ("followup",))
    assert m.effect_decision(("deny",), (prerequisite,), applied=frozenset({"review"}))[0] == "deny"
    assert m.effect_decision(("permit",), (replace(prerequisite, supported=False),))[0] == "withhold"


def test_combined_parent_effect_graph_rejects_phase_cycles():
    for effects in (
        (m.Effect("review", phase="predecessor", predecessors=("parent",)),),
        (m.Effect("review", phase="predecessor", predecessors=("after",)), m.Effect("after", phase="subsequent")),
        (m.Effect("audit", predecessors=("unknown",)),),
    ):
        with pytest.raises(ValueError):
            m.effect_decision(("permit",), effects)


def test_atomic_commit_includes_scoped_state_decision_and_intent_or_nothing():
    initial = m.State(cells=(("participant:A", 0), ("participant:B", 0)))
    writes = (m.Write("participant:A", 0, 1), m.Write("participant:B", 0, 2, "release"))
    after, status = m.commit(initial, 0, "permit", writes, ("audit",))
    assert status == "committed"
    assert after == m.State(1, (("participant:A", 1), ("participant:B", 2)), ("permit",), ("audit",))
    denied, _ = m.commit(initial, 0, "deny", writes, ("audit",))
    assert denied.cells == (("participant:A", 1), ("participant:B", 0))
    assert denied.history == ("deny",)
    assert denied.intents == ("audit",)
    assert m.commit(initial, 0, "permit", writes, succeeds=False)[0] == initial
    assert m.commit(after, 0, "permit", writes)[0] == after
    competing = (m.Write("participant:A", 0, 1), m.Write("participant:A", 0, 2))
    for order in permutations(competing):
        assert m.commit(initial, 0, "permit", order) == (initial, "state-conflict")
    assert m.commit(initial, 0, "permit", (m.Write("unknown-scope", 0, 1),))[0] == initial
