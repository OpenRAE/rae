"""Finite semantic witnesses for sem-235/rev1, not provider conformance."""

from dataclasses import replace
from itertools import permutations, product

import pytest
import sem235_modular_control_model as model


def test_teaching_domain_join_laws_memory_and_fresh_derivation():
    domain = tuple(
        frozenset(t for t, bit in zip(model.TOKENS, bits, strict=True) if bit)
        for bits in product((False, True), repeat=2)
    )
    for a, b, c in product(domain, repeat=3):
        assert model.join(a, b) in domain
        assert model.join(a, a) == a
        assert model.join(a, b) == model.join(b, a)
        assert model.join(model.join(a, b), c) == model.join(a, model.join(b, c))
        assert a <= model.join(a, b)
        if a <= b:
            assert model.join(a, c) <= model.join(b, c)
    hint = model.Influence("hint", frozenset({"coached-hint"}))
    memory = model.Influence("memory", frozenset({"worked-example"}))
    proposal = model.derive("proposal", (hint, memory))
    assert proposal.labels == frozenset(model.TOKENS)
    assert proposal.ancestors == frozenset({"hint", "memory"})
    assert model.derive("next-episode", (proposal,)).labels == proposal.labels
    assert model.derive("unknown", (hint, replace(memory, labels=None))).labels is None
    with pytest.raises(ValueError, match="fresh"):
        model.derive("hint", (proposal,))
    unknown_token = frozenset({"trusted"})
    empty = frozenset()
    with pytest.raises(ValueError, match="domain"):
        model.join(unknown_token, empty)
    wrong_revision = replace(hint, revision="sem-233/rev1")
    with pytest.raises(ValueError, match="revision"):
        model.derive("new", (wrong_revision,))


@pytest.mark.parametrize("status", ("missing", "unknown", "unsupported", "stale", "failed", "weakened"))
def test_mandatory_failure_cannot_be_overridden_by_advice(status):
    slots = (
        model.Slot("flow", "fact"),
        model.Slot("budget", "decision"),
        model.Slot("monitor", "advice", mandatory=False),
    )
    results = (
        model.Result("flow", "fact", status=status),
        model.Result("budget", "decision", payload="permit"),
        model.Result("monitor", "advice", payload="permit"),
    )
    for order in permutations(results):
        assert model.compose(slots, order, cut="K0") == (f"flow:{status}",)


def test_fact_slot_and_permission_slot_are_not_interchangeable():
    fact = model.Slot("flow", "fact")
    decision = model.Slot("sink", "decision")
    assert model.compose((fact,), (model.Result("flow", "fact"),), cut="K0") == ()
    assert model.compose((fact,), (), cut="K0") == ("flow:missing",)
    assert model.compose((decision,), (model.Result("sink", "fact"),), cut="K0") == ("sink:kind",)
    assert model.compose((decision,), (model.Result("sink", "decision", payload="abstain"),), cut="K0")
    assert model.compose((), (), cut="K0", incumbent=False) == ("incumbent",)
    assert model.compose((fact,), (model.Result("flow", "fact", cut="K1"),), cut="K0") == ("flow:stale",)


def test_dependency_admission_and_all_blocking_reasons():
    slots = (model.Slot("flow", "fact"), model.Slot("rule", "decision", dependencies=("flow",)))
    results = (model.Result("flow", "fact", status="unknown"), model.Result("rule", "decision", payload="permit"))
    assert model.compose(slots, results, cut="K0") == ("flow:unknown", "rule:dependency")
    for invalid in (
        (model.Slot("a", "fact", dependencies=("a",)),),
        (model.Slot("a", "fact", dependencies=("absent",)),),
        (model.Slot("a", "advice", mandatory=False), model.Slot("b", "decision", dependencies=("a",))),
        (model.Slot("a", "fact"), model.Slot("a", "decision")),
    ):
        with pytest.raises(ValueError):
            model.compose(invalid, (), cut="K0")


def test_effect_conflicts_are_order_independent_and_delay_intersects():
    route = model.Request("route-a", "route", "P", "left")
    other = replace(route, rule="route-b", target="right")
    for pair in permutations((route, other)):
        assert model.effect_plan(pair) == ("conflict",)
    transform = model.Request("edit-a", "transform", "P", "participant", content="edit:1")
    mask = replace(transform, rule="mask-b", kind="mask", content="mask:2")
    assert model.effect_plan((transform, mask), order=frozenset({("edit-a", "mask-b")})) == ("conflict",)
    assert model.effect_plan((route, route)) == ()
    assert model.effect_plan((route, replace(route, content="changed"))) == ("key-conflict",)
    delay = model.Request("delay-a", "delay", "P", "participant", window=(10, 20))
    assert model.delay_window((delay, replace(delay, rule="delay-b", window=(15, 25)))) == (15, 20)
    assert model.effect_plan((delay, replace(delay, rule="delay-b", window=(21, 25)))) == ("conflict",)
    assert model.effect_plan((replace(delay, window=(20, 10)),)) == ("invalid-window",)
    assert model.effect_plan((delay, replace(delay, rule="delay-b", clock="other"))) == ("conflict",)


@pytest.mark.parametrize("kind", ("transform", "mask", "route", "handoff"))
def test_distinct_matching_effects_still_require_order(kind):
    first = model.Request("rule-a", kind, "P", "participant")
    second = replace(first, rule="rule-b")
    for pair in permutations((first, second)):
        assert model.effect_plan(pair) == ("conflict",)
        assert model.effect_plan(pair, order=frozenset({("rule-a", "rule-b")})) == ()
    assert model.effect_plan((first, first)) == ()


def test_lifecycle_order_and_explicit_independence():
    stop = model.Request("stop", "shutdown", "P", "participant")
    inject = model.Request("hint", "inject", "P", "participant")
    assert model.effect_plan((stop, inject)) == ("conflict",)
    assert model.effect_plan((stop, inject), order=frozenset({("stop", "hint")})) == ("conflict",)
    assert model.effect_plan((stop, inject), order=frozenset({("hint", "stop")})) == ()
    other = replace(inject, rule="other", subject="Q", target="supervisor")
    assert model.effect_plan((inject, other)) == ("conflict",)
    assert model.effect_plan((inject, other), independent=frozenset({frozenset({"hint", "other"})})) == ()
    assert model.effect_plan((inject, other), order=frozenset({("hint", "other"), ("other", "hint")})) == (
        "invalid-order",
    )
    assert model.effect_plan((replace(inject, kind="callback"),)) == ("unsupported",)


def test_fresh_inject_identity_commit_replay_and_external_uncertainty():
    state = model.State()
    request = model.Request("followup", "inject", "P", "participant", content="prompt:reflection")
    for denied in (dict(allowed=False), dict(current="K1"), dict(committed=False)):
        after, outcome = model.claim(state, request, **denied)
        assert after == state
        assert outcome != "committed"
    state, outcome = model.claim(state, request)
    assert outcome == "committed"
    identity = state.claims[0].identity
    assert identity != request.subject
    assert model.claim(state, request) == (state, "committed")
    assert model.claim(state, replace(request, content="different")) == (state, "key-conflict")
    assert model.dispatch(state, identity, fenced=False)[0] == state
    assert model.dispatch(state, identity, allowed=False)[0] == state
    assert model.dispatch(state, identity, expected="K0", current="K1")[0] == state
    state, _ = model.dispatch(state, identity)
    assert state.calls == (identity,)
    state = model.observe(state, identity, "indeterminate")
    assert model.dispatch(state, identity)[0] == state
    state = model.observe(state, identity, "applied")
    assert model.dispatch(state, identity) == (state, "applied")
    assert state.calls == (identity,)


def test_causal_budget_depth_rule_limits_and_fresh_proposal_reentry():
    request = model.Request("followup", "inject", "P", "participant")
    for total, depth, per_rule in product(range(3), repeat=3):
        state = model.State(limit=total, depth_limit=depth, rule_limit=per_rule)
        parent = None
        for epoch in range(4):
            state, _ = model.claim(state, replace(request, epoch=epoch, parent=parent))
            if state.claims:
                parent = state.claims[-1].identity
        assert len(state.claims) == min(total, depth, per_rule)
        if state.claims:
            assert model.claim(state, state.claims[0].request)[0] == state
    transformed = model.derive("P2", (model.Influence("P", frozenset(model.TOKENS)),))
    assert transformed.ref == "P2"
    assert transformed.labels == frozenset(model.TOKENS)
    assert model.compose(
        (model.Slot("sink", "decision"),), (model.Result("sink", "decision", payload="deny"),), cut="K0"
    )
    state, _ = model.claim(model.State(), replace(request, kind="transform", subject="P2"), allowed=False)
    assert not state.claims
    assert not state.calls


def test_teaching_influence_requests_an_independently_governed_inject():
    proposal = model.derive(
        "P", (model.Influence("H", frozenset({"coached-hint"})), model.Influence("M", frozenset({"worked-example"})))
    )
    slots = (model.Slot("ifc", "fact"), model.Slot("budget", "decision"))
    results = (model.Result("ifc", "fact"), model.Result("budget", "decision", payload="permit"))
    assert model.compose(slots, results, cut="K0") == ()
    assert "coached-hint" in proposal.labels
    request = model.Request("hint-followup/1", "inject", proposal.ref, "student", content="reflection")
    # The trigger source and its control dependency both contribute influence.
    state, _ = model.claim(model.State(), request, expected="K1", current="K1")
    injected = model.derive(state.claims[0].identity, (proposal, model.Influence("reflection", frozenset())))
    assert injected.labels == proposal.labels
    state, _ = model.dispatch(state, state.claims[0].identity, expected="K1", current="K1")
    assert len(state.calls) == 1


def test_known_adversarial_observation_retains_security_influence_and_triggers_inject():
    from sem233_boundary_flow_model import FlowGateState, FlowProfile, FlowValue, SinkPolicy, derive, may_flow_at_sink

    profile = FlowProfile(
        "participant-boundary-flow-policy-v1",
        "rev1",
        "sem-233/rev1",
        frozenset({"hidden-condition", "conf:deny-unresolved"}),
        frozenset({"attacker-influence", "int:deny-unresolved"}),
    )
    source = FlowValue(
        "A",
        profile.label(integrity={"attacker-influence"}),
        frozenset({"source:A"}),
        frozenset({"attacker:A"}),
        "subject",
        "episode",
        "exposure",
        "rev1",
        "K0",
    )
    observation = SinkPolicy(
        "observation",
        "subject",
        profile.profile_id,
        profile.profile_revision,
        "exposure",
        "rev1",
        "K0",
        frozenset(),
        frozenset({"attacker-influence"}),
    )
    assert may_flow_at_sink(profile, source, observation, FlowGateState.allowing())
    proposal = derive(
        profile,
        result_ref="P",
        inputs=(source,),
        participant_ref="subject",
        episode_ref="episode",
        policy_ref="exposure",
        policy_revision="rev1",
        state_cut_ref="K0",
    )
    assert proposal.label.integrity == source.label.integrity
    assert not may_flow_at_sink(
        profile, proposal, replace(observation, satisfied_integrity=frozenset()), FlowGateState.allowing()
    )
    assert not may_flow_at_sink(profile, source.without_label(), observation, FlowGateState.allowing())
    request = model.Request("adversarial-exposure/1", "inject", "P", "supervisor", content="evaluator-prompt")
    state, _ = model.claim(model.State(), request, expected="K1", current="K1")
    identity = state.claims[0].identity
    prompt = replace(
        source,
        value_ref="prompt",
        label=profile.label(confidentiality={"hidden-condition"}),
        provenance_refs=frozenset({"source:prompt"}),
        influence_refs=frozenset({"prompt:influence"}),
    )
    injected = derive(
        profile,
        result_ref=identity,
        inputs=(proposal, prompt),
        participant_ref="supervisor",
        episode_ref="episode",
        policy_ref="supervisor-only",
        policy_revision="rev1",
        state_cut_ref="K1",
    )
    inject_sink = replace(
        observation,
        sink_ref="inject",
        destination_ref="supervisor",
        policy_ref="supervisor-only",
        state_cut_ref="K1",
        satisfied_confidentiality=frozenset({"hidden-condition"}),
    )
    assert injected.label.integrity == proposal.label.integrity
    assert may_flow_at_sink(profile, injected, inject_sink, FlowGateState.allowing())
    assert not may_flow_at_sink(
        profile, injected, replace(inject_sink, satisfied_confidentiality=frozenset()), FlowGateState.allowing()
    )
    # The exact supervisor audience is an independent gate, not source endorsement.
    assert model.dispatch(state, identity, allowed=False)[0].calls == ()
    state, _ = model.dispatch(state, identity, expected="K1", current="K1")
    assert state.calls == (identity,)


def test_inject_audience_and_policy_cut_use_incumbent_projection():
    from sem230_information_flow_model import Crossing, CrossingKind, Label, ProjectionPolicyDecision, project_history

    policy = ProjectionPolicyDecision("projection", "rev1", "decision:1", "K1", frozenset({"I"}), frozenset())
    crossing = Crossing(
        "supervisor",
        "supervisor",
        1,
        CrossingKind.DISCLOSURE,
        Label.INTERVENTION,
        "I",
        "evaluator-prompt",
        "rev1",
        "decision:1",
        "K1",
        True,
        True,
        True,
        True,
        False,
        True,
        True,
    )
    assert project_history((crossing,), (policy,), participant="supervisor", audience="supervisor") == (
        (1, "I", "evaluator-prompt"),
    )
    assert project_history((crossing,), (policy,), participant="subject", audience="subject") == ()
    assert (
        project_history(
            (replace(crossing, decision_cut_ref="K2"),), (policy,), participant="supervisor", audience="supervisor"
        )
        == ()
    )


def test_model_refuses_unrepresented_multiple_effect_slots_per_rule():
    request = model.Request("rule", "inject", "P", "participant")
    assert model.effect_plan((request, replace(request, slot=1))) == ("unsupported",)


@pytest.mark.parametrize("kind", ("permit", "deny", "withhold"))
def test_disposition_cannot_be_dispatched_as_an_occurrence(kind):
    state, result = model.claim(model.State(), model.Request("decision", kind, "P", "participant"))
    assert result == "refused"
    assert not state.claims
    assert not state.calls


@pytest.mark.parametrize("payload", ("permit", "deny", "withhold", "abstain"))
def test_optional_advice_has_no_direct_grant_or_veto(payload):
    slots = (model.Slot("sink", "decision"), model.Slot("monitor", "advice", mandatory=False))
    advice = model.Result("monitor", "advice", payload=payload)
    for decision in ("permit", "deny", "withhold", "abstain"):
        results = (model.Result("sink", "decision", payload=decision), advice)
        expected = () if decision == "permit" else (f"sink:{decision}",)
        assert model.compose(slots, results, cut="K0") == expected
        assert model.compose(slots, results[:1], cut="K0") == expected
