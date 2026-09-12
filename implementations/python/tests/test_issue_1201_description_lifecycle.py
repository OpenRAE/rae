"""Finite lifecycle and cross-axis acceptance examples for design review."""

import pytest
from implementations.python.research.description_lifecycle import (
    Demand,
    Fact,
    abstract_run,
    assess,
    capture,
    promote,
    report_choice,
    version_domain,
)
from implementations.python.research.partial_description import NO_WITNESS, Atom, Field, Record, Scope, accepts, choose


def test_version_relations_are_named_and_do_not_use_lexicographic_order():
    versions = ("7.9.0", "7.10.0", "7.11.0")
    assert version_domain(versions, lower="7.9.0", lower_closed=False).values == ("7.10.0", "7.11.0")
    assert version_domain(versions, upper="7.10.0", upper_closed=False).values == ("7.9.0",)
    assert version_domain(versions, lower="7.10.0", upper="7.10.0").values == ("7.10.0",)
    with pytest.raises(ValueError, match="incomparable-version"):
        version_domain(("7.10.0-apt1",), lower="7.9.0")
    with pytest.raises(ValueError, match="unsupported-version-relation"):
        version_domain(versions, relation="universal-semver")


def test_partial_capture_keeps_unknown_redacted_absence_and_contradiction_separate():
    request = Record((Field("os", Atom(("Kali",))), Field("version", Atom(("1",)))))
    universe = ({"os": "Kali", "version": "1"}, {"os": "Kali", "version": "2"}, {"os": "Debian"})
    facts = (Fact(("os",), "known", "Kali"), Fact(("version",), "unknown"))
    assert assess((request,), facts, universe) == "unresolved"
    assert assess((request,), (Fact(("version",), "redacted"),), universe) == "unresolved"
    assert assess((request,), (Fact(("version",), "absent"),), universe) == "violated"
    assert assess((request,), (Fact(("version",), "known", "1"),), universe) == "satisfied-in-finite-universe"
    contradictory = (Fact(("os",), "known", "Kali"), Fact(("os",), "known", "Debian"))
    assert assess((request,), contradictory, universe) == "contradictory-or-unrepresented"
    invalid_facts = (Fact(("version",), "redacted", "hidden"),)
    with pytest.raises(ValueError, match="knowledge-value-forbidden"):
        assess((request,), invalid_facts, universe)
    assert promote(facts, (("os",),)) == Record((Field("os", Atom(("Kali",))),))
    with pytest.raises(ValueError, match="promotion-needs-known-fact"):
        promote(facts, (("version",),))
    assert facts[1].state == "unknown"  # neither promotion nor assessment rewrites facts


def test_requested_choice_report_is_not_a_measurement_or_full_inventory():
    selection = {"os": "Kali", "internal_route": "private-cache", "software": {"nmap": "7.95"}}
    report = report_choice(selection, (("os",), ("software", "nmap")))
    assert report.basis == "backend-selected"
    assert report.facts == (Fact(("os",), "known", "Kali"), Fact(("software", "nmap"), "known", "7.95"))
    assert "private-cache" not in str(report)
    assert report_choice(selection, ()).facts == ()
    assert selection["internal_route"] == "private-cache"


def test_detailed_filesystem_no_data_does_not_invoke_a_collector():
    request = Record(
        (
            Field("image", Atom(("sha256:fixture",))),
            Field("files", Record((Field("config", Atom(("exact-content",))),), True, "modeled-files/v1")),
        )
    )
    selected = {"image": "sha256:fixture", "files": {"config": "exact-content"}}
    assert choose((request,), (selected,)) == selected
    key = (("node",), "filesystem-trace")

    def forbidden_collector():
        pytest.fail("no-data scope must reject collection before producer invocation")

    result = capture((Demand((), "none", forbid_experimental=True),), {key: forbidden_collector}, frozenset({key}))
    assert result.collected == result.retained == result.exported == ()


def test_mixed_component_demands_and_explicit_retention_export():
    packets = (("links", "observed"), "packets")
    ops = (("nodes", "operational"), "health")
    silent = (("nodes", "silent"), "trace")
    called = []

    def producer(key):
        def run():
            called.append(key)
            return ("event",)

        return run

    demands = (
        Demand((), "operational"),
        Demand(packets[0], "selected", ("packets",), retain=True, export=False),
        Demand(ops[0], "inherit"),
        Demand(silent[0], "none", forbid_experimental=True),
    )
    result = capture(
        demands,
        {key: producer(key) for key in (packets, ops, silent)},
        frozenset({packets, ops, silent}),
        operational=frozenset({ops}),
    )
    assert called == [packets, ops]
    assert tuple(item[0] for item in result.collected) == (packets,)
    assert result.retained == result.collected
    assert result.exported == ()
    assert result.operational_count == 1


def test_unsupported_capture_and_prohibition_conflicts_fail_before_any_collection():
    key = (("node",), "packets")

    def forbidden_collector():
        pytest.fail("admission must precede every producer")

    requested = (Demand((), "selected", ("packets",)),)
    unsupported = frozenset()
    supported = frozenset({key})
    conflicting = (Demand((), "none", forbid_experimental=True), Demand(("node",), "selected", ("packets",)))
    forbidden = (Demand((), "none", forbidden=("packets",)),)
    with pytest.raises(ValueError, match="unsupported-capture"):
        capture(requested, {key: forbidden_collector}, unsupported)
    with pytest.raises(ValueError, match="policy-conflict"):
        capture(
            conflicting,
            {key: forbidden_collector},
            supported,
        )
    with pytest.raises(ValueError, match="policy-conflict"):
        capture(
            forbidden,
            {key: forbidden_collector},
            supported,
            operational=supported,
        )


def test_abstract_two_computers_three_actions_execute_without_concrete_inventory():
    # Each computer can increment, send its counter, or receive the peer's value.
    schedule = (
        ("a", "increment"),
        ("a", "send"),
        ("b", "receive"),
        ("b", "increment"),
        ("b", "send"),
        ("a", "receive"),
    )
    assert abstract_run(schedule) == ({"a": 2, "b": 2}, ())
    state, trace = abstract_run(schedule, record_trace=True)
    assert state == {"a": 2, "b": 2}
    assert len(trace) == 6
    assert all(set(event) == {"actor", "action", "before", "after"} for event in trace)
    key = (("abstract",), "actions")
    result = capture(
        (Demand((), "exhaustive", ("actions",), retain=False, export=True),), {key: lambda: trace}, frozenset({key})
    )
    assert result.exported == result.collected == ((key, trace),)
    assert result.retained == ()
    with pytest.raises(ValueError, match="action-not-enabled"):
        abstract_run((("a", "receive"),))
    with pytest.raises(ValueError, match="unknown-action"):
        abstract_run((("a", "install-os"),))
    with pytest.raises(ValueError, match="limit-exceeded"):
        abstract_run(schedule, limit=2)


def test_source_and_model_budgets_include_direct_input_shapes():
    oversized_atom = Atom(("x" * 4097,))
    integer_atom = Atom((1,))
    non_leaf_facts = (Fact((), "known", {"x": True}),)
    with pytest.raises(ValueError, match="limit-exceeded"):
        accepts(oversized_atom, "short")
    with pytest.raises(ValueError, match="limit-exceeded"):
        accepts(integer_atom, 1 << 300)
    with pytest.raises(ValueError, match="fact-needs-leaf"):
        assess((), non_leaf_facts, ({"x": 1},))


def test_knowledge_never_grants_backend_discretion():
    request = Record((Field("os", Atom(("Kali",))),))
    candidate = {"os": "Kali", "extra": "unrequested"}
    assert accepts(request, candidate)
    assert assess((request,), (Fact(("extra",), "unknown"),), (candidate,)) == "satisfied-in-finite-universe"
    assert choose((request,), (candidate,)) is NO_WITNESS
    assert choose((request,), (candidate,), scopes=(Scope((), "open"),)) == candidate
