"""Finite SEM-234 witnesses; these tests do not execute mixed backends."""

from dataclasses import replace
from itertools import permutations, product

import pytest
import sem234_mixed_composition_model as model
from sem230_information_flow_model import Crossing, CrossingKind, Label, ProjectionPolicyDecision
from sem234_mixed_composition_model import (
    Component,
    Context,
    Edge,
    Phase,
    Plan,
    Scope,
    admit,
)

SCOPES = (
    Scope("participant.alice", "participant-runtime", frozenset({"act"})),
    Scope("action.alice.inspect", "action-family", frozenset({"act"})),
    Scope("nodes.target", "controlled-scope", frozenset({"target"})),
    Scope("observations.status", "observation-source", frozenset({"observe"})),
    Scope("crossings.status", "crossing-boundary", frozenset({"cross"})),
)
PINS = frozenset(
    (kind, f"{kind}:one", "rev1", "digest:one")
    for kind in ("adapter", "authority", "mapping", "policy", "release", "time", "failure", "observer")
)
ATOMS = frozenset({"act", "target", "observe", "cross"})
SIM = Component("apparatus:a", "simulation", "clock:a", ATOMS, 2, frozenset({"conformance:a"}))
EMU = Component("apparatus:b", "emulation-or-operational", "clock:b", ATOMS, 2, frozenset({"conformance:b"}))
EDGE = Edge("apparatus:a", "apparatus:b", "crossings.status", PINS, ("clock:a", "clock:b"))
ALLOCATIONS = (
    ("participant.alice", "apparatus:a"),
    ("nodes.target", "apparatus:b"),
    ("observations.status", "apparatus:b"),
    ("crossings.status", "apparatus:b"),
)
PHASE = Phase("phase:0", frozenset({SIM.ref, EMU.ref}), ALLOCATIONS, (EDGE,), (EDGE.key,))
PLAN = Plan(
    "scenario:one",
    "policy:one",
    "plan:one",
    "entry:one",
    "run:one",
    "simultaneous-mixed-realization",
    (SIM.ref, EMU.ref),
    (PHASE,),
    ATOMS,
)
CONTEXT = Context(SCOPES, (SIM, EMU), PINS, ((next(pin for pin in PINS if pin[0] == "time"), ("clock:a", "clock:b")),))


def test_mixed_admission_resolves_all_five_scope_kinds_without_backend_name_inference():
    assert admit(PLAN, CONTEXT) == ()
    action_allocation = replace(PHASE, allocations=(("action.alice.inspect", SIM.ref), *ALLOCATIONS[1:]))
    assert admit(replace(PLAN, phases=(action_allocation,)), CONTEXT) == ()
    misleading_name = replace(SIM, ref="emulator-brand")
    changed_phase = replace(
        PHASE,
        members=frozenset({misleading_name.ref, EMU.ref}),
        allocations=(("participant.alice", misleading_name.ref), *ALLOCATIONS[1:]),
        edges=(replace(EDGE, source=misleading_name.ref),),
        exchanges=((misleading_name.ref, EMU.ref, EDGE.scope),),
    )
    renamed = replace(PLAN, components=(misleading_name.ref, EMU.ref), phases=(changed_phase,))
    assert admit(renamed, replace(CONTEXT, components=(misleading_name, EMU))) == ()
    unclassified = replace(SIM, form="unknown")
    assert "realization-form" in admit(PLAN, replace(CONTEXT, components=(unclassified, EMU)))


def test_alternative_realizations_keep_scenario_policy_but_have_separate_run_identities():
    for component in (SIM, EMU):
        phase = Phase(
            "phase:0", frozenset({component.ref}), tuple((scope, component.ref) for scope, _ in ALLOCATIONS), (), ()
        )
        alternative = replace(
            PLAN,
            mode="alternative-realization",
            components=(component.ref,),
            phases=(phase,),
            entry=f"entry:{component.ref}",
            run=f"run:{component.ref}",
        )
        assert admit(alternative, CONTEXT) == ()
        assert (alternative.scenario, alternative.policy) == (PLAN.scenario, PLAN.policy)
        assert alternative.run != PLAN.run


def test_mixed_forms_require_allocated_providers_not_merely_listed_members():
    assert admit(PLAN, CONTEXT) == ()
    single_provider = replace(
        PHASE, allocations=tuple((scope, SIM.ref) for scope, _ in ALLOCATIONS), edges=(), exchanges=()
    )
    assert "mixed-forms" in admit(replace(PLAN, phases=(single_provider,)), CONTEXT)
    same_form = replace(EMU, form=SIM.form)
    assert "mixed-forms" in admit(PLAN, replace(CONTEXT, components=(SIM, same_form)))


@pytest.mark.parametrize("kind", sorted(pin[0] for pin in PINS))
def test_every_edge_binding_must_resolve_at_its_exact_revision_and_digest(kind):
    pin = next(pin for pin in PINS if pin[0] == kind)
    for replacement in (None, (pin[0], pin[1], "stale", pin[3]), (pin[0], pin[1], pin[2], "wrong")):
        pins = (PINS - {pin}) | ({replacement} if replacement else set())
        broken = replace(PHASE, edges=(replace(EDGE, pins=frozenset(pins)),))
        assert "edge-binding" in admit(replace(PLAN, phases=(broken,)), CONTEXT)


def test_missing_reverse_or_wrong_clock_mapping_does_not_admit_an_exchange():
    for edges in ((), (replace(EDGE, source=EMU.ref, destination=SIM.ref),)):
        assert "exchange-edge" in admit(replace(PLAN, phases=(replace(PHASE, edges=edges),)), CONTEXT)
    wrong = replace(EDGE, clocks=("clock:b", "clock:a"))
    assert "clock-mapping" in admit(replace(PLAN, phases=(replace(PHASE, edges=(wrong,)),)), CONTEXT)


def test_cross_kind_overlap_and_inactive_or_unadmitted_providers_are_rejected():
    overlap = replace(PHASE, allocations=(*ALLOCATIONS, ("action.alice.inspect", EMU.ref)))
    assert "competing-providers" in admit(replace(PLAN, phases=(overlap,)), CONTEXT)
    inactive = replace(PHASE, members=frozenset({SIM.ref}))
    assert "inactive-provider" in admit(replace(PLAN, phases=(inactive,)), CONTEXT)
    fallback = replace(PHASE, allocations=(("participant.alice", "apparatus:late"), *ALLOCATIONS[1:]))
    assert "inactive-provider" in admit(replace(PLAN, phases=(fallback,)), CONTEXT)
    late = replace(PHASE, members=PHASE.members | {"apparatus:late"})
    assert "unadmitted-member" in admit(replace(PLAN, phases=(late,)), CONTEXT)


def test_missing_required_effect_or_provider_support_is_not_borrowed_from_a_peer():
    missing = replace(PHASE, allocations=ALLOCATIONS[1:])
    assert "incomplete-allocation" in admit(replace(PLAN, phases=(missing,)), CONTEXT)
    unsupported = replace(SIM, supported=ATOMS - {"act"})
    assert "unsupported-effect" in admit(PLAN, replace(CONTEXT, components=(unsupported, EMU)))
    unverified = replace(SIM, evidence=frozenset())
    assert "support-evidence" in admit(PLAN, replace(CONTEXT, components=(unverified, EMU)))


def test_axes_are_independent_and_allocation_is_order_independent():
    for loop, world, membership in product(
        ("open-loop", "closed-loop"), ("closed-world", "bounded-open-world"), ("fixed", "pre-admitted-dynamic")
    ):
        assert admit(replace(PLAN, loop=loop, world=world, membership=membership), CONTEXT) == ()
    assert "axes" in admit(replace(PLAN, world="open"), CONTEXT)
    for allocations in permutations(ALLOCATIONS):
        assert admit(replace(PLAN, phases=(replace(PHASE, allocations=allocations),)), CONTEXT) == ()


def test_graph_bounds_refuse_instead_of_truncating_and_unknown_scopes_do_not_match_prefixes():
    assert "work-limit" in admit(PLAN, CONTEXT, limit=1)
    unknown = replace(PHASE, allocations=(("participant.alice.extra", SIM.ref), *ALLOCATIONS[1:]))
    assert "unresolved-scope" in admit(replace(PLAN, phases=(unknown,)), CONTEXT)


def _state(plan=PLAN):
    return model.State(
        plan,
        0,
        model.Cut(
            "cut:0",
            "alice",
            "episode:1",
            "operator",
            "authority:one",
            "rev1",
            "capability:1",
            0,
            ("control:0", "crossing:0"),
        ),
    )


def _delivery(state, **changes):
    crossing = Crossing(
        "alice",
        "participant:alice",
        1,
        CrossingKind.DISCLOSURE,
        Label.DISCLOSURE,
        "status",
        "ready",
        "rev1",
        "decision:0",
        state.cut.ref,
        True,
        True,
        True,
        True,
        False,
        True,
        True,
    )
    policy = ProjectionPolicyDecision(
        "policy:one", "rev1", "decision:0", state.cut.ref, frozenset({"status"}), frozenset()
    )
    args = dict(
        edge_key=EDGE.key,
        expected=state.cut,
        crossings=(crossing,),
        policies=(policy,),
        emitted=frozenset({"status"}),
        before="event:0",
        after="event:1",
        order=frozenset({("event:0", "event:1")}),
        action=True,
        action_admitted=True,
        committed=True,
        result="delivered",
    )
    args.update(changes)
    return model.deliver(state, CONTEXT, **args)


def test_authorization_precedes_routing_and_metadata_is_projected_with_payload():
    state = _state()
    result, outcome = _delivery(state)
    assert outcome == "delivered"
    assert result.effects == (EDGE.key,)
    assert result.knowledge == frozenset({"status"})
    refused, outcome = _delivery(state, emitted=frozenset({"status", "secret-membership"}))
    assert outcome == "projection-widened"
    assert refused.effects == () and refused.knowledge == state.knowledge
    assert refused.history == ("projection-widened",)


@pytest.mark.parametrize("empty_output", [False, True])
@pytest.mark.parametrize("mutation", ["missing", "policy_id", "revision", "decision_cut_ref"])
def test_delivery_requires_exact_policy_decision_even_without_output(mutation, empty_output):
    state = _state()
    policy = ProjectionPolicyDecision(
        state.plan.policy, state.cut.policy_revision, "decision:0", state.cut.ref, frozenset({"status"}), frozenset()
    )
    policies = () if mutation == "missing" else (replace(policy, **{mutation: "wrong"}),)
    output = {"crossings": (), "emitted": frozenset()} if empty_output else {}
    refused, outcome = _delivery(state, policies=policies, **output)
    assert outcome == "policy-binding"
    assert refused.effects == state.effects
    assert refused.knowledge == state.knowledge
    assert refused.history == (*state.history, "policy-binding")
    # Empty output is legal only when an exact decision still authorizes the cut.
    admitted, outcome = _delivery(state, policies=(policy,), **output)
    assert outcome == "delivered"
    assert admitted.effects == (EDGE.key,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("controller", "previous-controller"),
        ("authority", "old-authority"),
        ("policy_revision", "old-policy"),
        ("capability", "old-support"),
        ("revision", 99),
        ("heads", ("old-control", "old-crossing")),
        ("participant", "bob"),
        ("episode", "episode:old"),
        ("order_ref", "order:old"),
    ],
)
def test_every_stale_cut_coordinate_prevents_effects(field, value):
    state = _state()
    result, outcome = _delivery(state, expected=replace(state.cut, **{field: value}))
    assert outcome == "stale"
    assert result.effects == () and result.knowledge == frozenset()


def test_revocation_open_loop_and_action_denial_cannot_be_overridden_by_provider():
    state = _state()
    revoked = replace(state, cut=replace(state.cut, authority_status="revoked"))
    assert _delivery(revoked)[1] == "inactive-authority"
    open_loop = _state(replace(PLAN, loop="open-loop"))
    assert _delivery(open_loop)[1] == "open-loop-actuation"
    assert _delivery(open_loop, action=False)[1] == "delivered"
    assert _delivery(state, action_admitted=False)[1] == "action-denied"


def test_partial_order_needs_the_required_comparison_and_no_timestamp_tiebreak():
    state = _state()
    incomparable = frozenset({("event:0", "concurrent"), ("event:1", "concurrent")})
    denied, outcome = _delivery(state, order=incomparable)
    assert outcome == "unresolved-order" and denied.effects == ()
    # A partial relation is sufficient for this comparison, without ordering every pair.
    partial = frozenset({("event:0", "event:1"), ("unrelated", "other")})
    assert _delivery(state, order=partial)[1] == "delivered"
    contradictory = frozenset({("event:0", "event:1"), ("event:1", "event:0")})
    assert _delivery(state, order=contradictory)[1] == "invalid-order"


def test_commit_and_attempt_are_not_delivery_and_failed_store_cannot_promise_history():
    state = _state()
    failed_commit, outcome = _delivery(state, committed=False)
    assert outcome == "commit-failed" and failed_commit == state
    for result in ("failed", "unknown"):
        attempted, outcome = _delivery(state, result=result)
        assert outcome == result and attempted.effects == (EDGE.key,)
        assert attempted.knowledge == frozenset()
    delivered, _ = _delivery(state)
    replay, outcome = _delivery(delivered, expected=state.cut)
    assert outcome == "stale" and replay.effects == delivered.effects
    assert replay.knowledge == delivered.knowledge


def _phased_plan():
    next_phase = Phase("phase:1", frozenset({SIM.ref}), tuple((scope, SIM.ref) for scope, _ in ALLOCATIONS), (), ())
    return replace(
        PLAN,
        phases=(PHASE, next_phase),
        membership="pre-admitted-dynamic",
        transitions=(("phase:0", "phase:1", "trigger:advance"),),
    )


def test_phase_commit_preserves_trial_identity_controller_and_prior_knowledge():
    state, _ = _delivery(_state(_phased_plan()))
    result, outcome = model.advance(state, CONTEXT, expected=state.cut, trigger="trigger:advance", committed=True)
    assert outcome == "phase-committed" and result.phase == 1
    assert dict(result.plan.phases[result.phase].allocations)["nodes.target"] == SIM.ref
    assert EMU.ref not in result.plan.phases[result.phase].members
    assert result.plan == state.plan
    assert result.cut.controller == state.cut.controller
    assert result.knowledge == state.knowledge and result.effects == state.effects
    assert result.history[:-1] == state.history
    assert result.cut.revision == state.cut.revision + 1
    stale, outcome = model.advance(result, CONTEXT, expected=state.cut, trigger="trigger:advance", committed=True)
    assert outcome == "stale" and stale.phase == result.phase


def test_phases_cannot_activate_unadmitted_members_or_skip_pending_work():
    state = _state(_phased_plan())
    for trigger, committed, pending, reason in (
        ("trigger:unknown", True, (), "unadmitted-trigger"),
        ("trigger:advance", False, (), "commit-failed"),
        ("trigger:advance", True, ("attempt:pending",), "in-flight"),
    ):
        initial = replace(state, pending=pending)
        result, outcome = model.advance(initial, CONTEXT, expected=initial.cut, trigger=trigger, committed=committed)
        assert outcome == reason and result.phase == 0 and result.effects == ()
    invalid_phase = replace(PHASE, ref="phase:1", members=PHASE.members | {"late"})
    invalid = _state(replace(state.plan, phases=(PHASE, invalid_phase)))
    assert (
        model.advance(invalid, CONTEXT, expected=invalid.cut, trigger="trigger:advance", committed=True)[1]
        == "invalid-plan"
    )


def test_inter_trial_lineage_requires_new_entry_run_and_fixed_scenario_policy():
    target = replace(PLAN, plan="plan:two", entry="entry:two", run="run:two")
    assert model.link_trials(PLAN, target, CONTEXT) == (PLAN.entry, PLAN.run, target.entry, target.run)
    for invalid in (PLAN, replace(target, scenario="different"), replace(target, policy="different")):
        with pytest.raises(ValueError, match="trial-lineage"):
            model.link_trials(PLAN, invalid, CONTEXT)


def test_delegated_abstract_completion_and_reporting_use_existing_description_owners():
    from implementations.python.research.description_lifecycle import Demand, capture, report_choice
    from implementations.python.research.partial_description import NO_WITNESS, Atom, Field, Record, choose, denotation
    from implementations.python.research.partial_description import Scope as OpenScope

    request = Record((Field("action", Atom(("inspect",))),))
    concrete = {"action": "inspect", "internal": "private-route"}
    wrong = {"action": "attack", "internal": "private-route"}
    selected = choose((request,), (wrong, concrete), scopes=(OpenScope((), "open"),))
    assert selected == concrete
    assert choose((request,), (wrong,), scopes=(OpenScope((), "open"),)) is NO_WITNESS
    assert report_choice(selected, (("action",),)).facts[0].value == "inspect"
    assert tuple(f.path for f in report_choice(selected, (("action",),)).facts) == (("action",),)
    # A complete abstract action needs no machine or internal implementation recipe.
    abstract = {"action": "inspect"}
    assert choose((request,), (abstract,)) == abstract
    universe = (abstract, concrete)
    offered_rule = Record((Field("internal", Atom(("private-route",))),))
    requested = denotation((request,), universe)
    offered = denotation((offered_rule,), universe)
    assert requested == frozenset({0, 1}) and offered == frozenset({1})
    assert not requested <= offered
    calls = []
    key = (("participant",), "actions")

    def producer():
        calls.append("collect")
        return ("inspect",)

    result = capture((Demand((), "none", forbid_experimental=True),), {key: producer}, {key})
    assert calls == [] and result.collected == () and result.exported == ()
    selected_demand = Demand((), "exhaustive", ("actions",), retain=True)
    result = capture((selected_demand,), {key: producer}, {key})
    assert calls == ["collect"] and result.collected and result.retained and result.exported == ()


def test_resolved_policy_and_authority_cannot_be_borrowed_from_another_edge_cut():
    state = _state()
    other_policy = ProjectionPolicyDecision(
        "policy:other", "rev1", "decision:0", state.cut.ref, frozenset({"status"}), frozenset()
    )
    assert _delivery(state, policies=(other_policy,))[1] == "policy-binding"
    other_authority = replace(state, cut=replace(state.cut, authority="authority:other"))
    assert _delivery(other_authority)[1] == "authority-binding"


def test_explicit_loss_never_silently_changes_the_original_required_obligations():
    lossy = replace(EDGE, loss=frozenset({"timing:coarsened"}))
    plan = replace(PLAN, phases=(replace(PHASE, edges=(lossy,)),))
    assert "unadmitted-loss" in admit(plan, CONTEXT)
    assert admit(replace(plan, allowed_loss=lossy.loss), CONTEXT) == ()
    # Declaring loss still cannot make a missing required comparison true.
    state = _state(replace(plan, allowed_loss=lossy.loss))
    assert _delivery(state, order=frozenset())[1] == "unresolved-order"


def test_controller_cardinality_and_revision_are_explicit_not_provider_counts():
    state = _state()
    for invalid in ("", ("operator", "joint")):
        invalid_state = replace(state, cut=replace(state.cut, controller=invalid))
        assert _delivery(invalid_state)[1] == "controller-authority"
    assert "profile-revision" in admit(replace(PLAN, authority_revision="sem-234/rev2"), CONTEXT)


def test_federated_label_alone_does_not_establish_distinct_leaf_forms():
    nested = replace(EMU, form="federated-composition")
    assert "nested-profile-required" in admit(PLAN, replace(CONTEXT, components=(SIM, nested)))
