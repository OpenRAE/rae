"""Faults must be reachable, deliberate, reversible and independently inspectable."""

from dataclasses import replace

import pytest
from implementations.formal.participant_crossing import concrete
from implementations.formal.participant_crossing.aut import parse_aut, render_aut


def test_required_faults_have_exact_reversible_deltas() -> None:
    from implementations.formal.participant_crossing.counterexample_mutations import build_mutations, validate_delta

    baseline = concrete.build()
    original = render_aut(baseline)
    cases = build_mutations()
    assert {case.case_id for case in cases} == {
        "hidden-denial",
        "hidden-observation",
        "hidden-divergence",
        "removed-delivery",
        "later-cut-replay",
    }
    for case in cases:
        validate_delta(baseline, case)
        assert case.graph.states[: len(baseline.states)] == baseline.states
        assert set(case.graph.edges) - set(case.added) | set(case.removed) == set(baseline.edges)
        assert case.location in case.reachable
        assert case.added or case.removed
        parse_aut(render_aut(case.graph))
    assert render_aut(concrete.build()) == original


def test_later_cut_fault_preserves_request_input_and_retained_cut() -> None:
    from implementations.formal.participant_crossing.counterexample_mutations import build_mutations

    case = next(case for case in build_mutations() if case.case_id == "later-cut-replay")
    origin = case.graph.states[case.location]
    assert origin.cut == "p1" and origin.intent == ("request-0", "plain", "p0", "later-cut")
    assert origin.last == ("request-0", "p0", "permit")
    for index in {target for _, _, target in case.added}:
        state = case.graph.states[index]
        assert (state.cut, state.intent, state.last) == (origin.cut, origin.intent, origin.last)
    assert {label for _, label, _ in case.added} == {
        "crossing.decision.permit",
        "crossing.delivery",
        "crossing.observation",
    }


def test_undeclared_and_empty_deltas_are_refused() -> None:
    from implementations.formal.participant_crossing.counterexample_mutations import build_mutations, validate_delta

    baseline = concrete.build()
    case = build_mutations()[0]
    with pytest.raises(ValueError, match="invalid mutation delta"):
        validate_delta(baseline, replace(case, added=(), removed=()))
    changed = replace(case.graph, edges=case.graph.edges + ((baseline.initial, "internal.validate", baseline.initial),))
    with pytest.raises(ValueError, match="invalid mutation delta"):
        validate_delta(baseline, replace(case, graph=changed))
    with pytest.raises(ValueError, match="invalid mutation delta"):
        validate_delta(baseline, replace(case, location=len(baseline.states) + 5))


def test_removed_delivery_is_structural_deadlock_and_observation_stays_visible() -> None:
    from implementations.formal.participant_crossing.counterexample_mutations import build_mutations

    cases = {case.case_id: case for case in build_mutations()}
    removed = cases["removed-delivery"]
    assert not any(source == removed.location for source, _, _ in removed.graph.edges)
    observation = cases["hidden-observation"]
    assert observation.removed[0][1] == "crossing.observation"
    assert any(
        state.phase == "terminal" and any(source == i for source, _, _ in concrete.build().edges)
        for i, state in enumerate(concrete.build().states)
    )


def test_error_and_native_tau_are_not_hidden_by_the_carrier() -> None:
    for label in ("tau", "crossing.error", "payload.secret"):
        with pytest.raises(ValueError):
            parse_aut(f'des (0, 1, 1)\n(0,"{label}",0)\n'.encode())
