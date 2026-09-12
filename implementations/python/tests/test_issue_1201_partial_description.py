"""Executable design checks, not production SDL conformance claims."""

import json
from dataclasses import replace
from itertools import product

import pytest
from implementations.python.research.description_lifecycle import report_choice
from implementations.python.research.partial_description import (
    ABSENT,
    NO_WITNESS,
    Atom,
    Field,
    Record,
    Scope,
    accepts,
    choose,
    denotation,
    effective_posture,
    normalize,
    resolve_reference,
)


def atom(value):
    return Atom((value,))


def record(**fields):
    return Record(tuple(Field(name, rule) for name, rule in fields.items()))


def test_inherited_open_does_not_weaken_an_exact_sibling():
    request = record(os=atom("Kali"), software=record(nmap=record(version=atom("7.95"))))
    good = {"os": "Kali", "software": {"nmap": {"version": "7.95"}, "curl": {"version": "8"}}}
    wrong = {**good, "os": "Debian"}
    scopes = (Scope((), "open"),)
    assert choose((request,), (wrong, good), scopes=scopes) == good
    assert choose((request,), (wrong,), scopes=scopes) is NO_WITNESS
    assert accepts(request, good)  # valid description is independent of permission
    assert choose((request,), (good,), scopes=()) is NO_WITNESS
    assert effective_posture(("software", "curl", "version"), scopes, "closed") == "open"


def test_optional_presence_is_conditional_and_absence_is_not_unknown():
    optional = Record((Field("nmap", record(version=atom("7.95")), "optional"),))
    assert accepts(optional, {})
    assert accepts(optional, {"nmap": {"version": "7.95"}})
    assert not accepts(optional, {"nmap": {"version": "7.94"}})
    forbidden = Record((Field("nmap", record(), "absent"),))
    assert accepts(forbidden, {})
    assert not accepts(forbidden, {"nmap": {}})
    assert not accepts(record(nmap=record()), {})
    assert ABSENT is not None


def test_closure_names_a_universe_and_does_not_close_the_machine():
    software = Record((Field("nmap", record()),), closed=True, universe="modeled-software/v1")
    request = record(software=software)
    assert accepts(request, {"software": {"nmap": {}}, "incidental_dependencies": {"libc": "6"}})
    assert not accepts(request, {"software": {"nmap": {}, "curl": {}}})
    unnamed_closure = replace(software, universe=None)
    with pytest.raises(ValueError, match="closure-universe-required"):
        accepts(unnamed_closure, {"nmap": {}})


def test_one_supported_witness_does_not_prove_universal_support():
    request = record(os=Atom(("Kali", "Debian")))
    universe = ({"os": "Kali"}, {"os": "Debian"}, {"os": "Windows"})
    requested = denotation((request,), universe)
    offered = denotation((record(os=atom("Kali")),), universe)
    assert requested == frozenset({0, 1})
    assert offered == frozenset({0})
    assert not requested <= offered
    assert choose((request,), (universe[0],)) == universe[0]
    impossible = (request, record(os=atom("Windows")))
    assert denotation(impossible, universe) <= offered  # vacuous universal truth
    assert choose(impossible, universe) is NO_WITNESS  # never operational success


def test_conjunction_algebra_and_normalization_over_an_exhaustive_small_universe():
    universe = tuple({"x": x, "y": y} for x, y in product(range(3), repeat=2))
    rules = (record(x=Atom((0, 1))), record(y=Atom((1, 2))), record(x=atom(1)))
    for a, b, c in product(rules, repeat=3):
        da, db, dc = (denotation((rule,), universe) for rule in (a, b, c))
        assert denotation((a, b), universe) == da & db == denotation((b, a), universe)
        assert denotation((a, a), universe) == da
        assert denotation((a, b, c), universe) == (da & db) & dc == da & (db & dc)
        assert denotation((a, b, c), universe) <= denotation((a, b), universe) <= da
        assert denotation((normalize(a),), universe) == da
    assert normalize(record(y=atom(2), x=atom(1))) == normalize(record(x=atom(1), y=atom(2)))


def test_defaults_are_lexical_not_conjunction_or_input_order():
    scopes = (Scope((), "open"), Scope(("a",), "closed"), Scope(("a", "b"), None))
    assert effective_posture(("a", "b", "c"), scopes, "closed") == "closed"
    assert effective_posture(("sibling",), tuple(reversed(scopes)), "closed") == "open"
    assert effective_posture(("a", "b"), (), "open") == "open"
    duplicate_scopes = (Scope((), "open"), Scope((), "closed"))
    with pytest.raises(ValueError, match="duplicate-scope"):
        effective_posture((), duplicate_scopes, "closed")


def test_stable_identity_duplicate_rejection_and_typed_atoms():
    rule = record(alpha=atom(1), beta=atom(2))
    assert accepts(rule, {"beta": 2, "alpha": 1})
    assert not accepts(rule, {"alpha": 2, "beta": 1})
    assert not accepts(atom(1), True)
    duplicate_identity = Record((Field("same", atom(1)), Field("same", atom(2))))
    with pytest.raises(ValueError, match="duplicate-identity"):
        accepts(duplicate_identity, {})


def test_cycles_missing_references_and_budgets_are_not_empty_sets():
    leaf = atom("ok")
    assert resolve_reference("a", {"a": "b", "b": leaf}) == leaf
    with pytest.raises(ValueError, match="reference-cycle"):
        resolve_reference("a", {"a": "b", "b": "a"})
    with pytest.raises(ValueError, match="unknown-reference"):
        resolve_reference("a", {})
    with pytest.raises(ValueError, match="limit-exceeded"):
        resolve_reference("a", {"a": "b", "b": leaf}, limit=1)
    deep = record(a=record(b=atom(1)))
    with pytest.raises(ValueError, match="limit-exceeded"):
        accepts(deep, {"a": {"b": 1}}, limit=2)
    with pytest.raises(ValueError, match="limit-exceeded"):
        denotation((leaf,), ("ok", "no"), limit=1)


def test_conjoined_explicit_fields_authorize_each_other_without_opening_extras():
    rules = (record(x=atom(1)), record(y=atom(2)))
    assert choose(rules, ({"x": 1, "y": 2},)) == {"x": 1, "y": 2}
    assert choose(rules, ({"x": 1, "y": 2, "z": 3},)) is NO_WITNESS


def test_scope_applies_inside_an_undeclared_descendant():
    scopes = (Scope((), "open"), Scope(("runtime", "files"), "closed"))
    assert choose((record(),), ({"runtime": {"files": {"added": "x"}}},), scopes=scopes) is NO_WITNESS


def test_five_linux_boxes_are_exactly_five_with_one_open_scope():
    box = record(family=atom("Linux"))
    request = record(nodes=Record(tuple(Field(f"box{i}", box) for i in range(5)), True, "requested-nodes/v1"))
    realized = {"nodes": {f"box{i}": {"family": "Linux", "distribution": "Debian", "release": "13"} for i in range(5)}}
    assert choose((request,), (realized,), scopes=(Scope((), "open"),)) == realized
    report = report_choice(realized, tuple(("nodes", f"box{i}", "distribution") for i in range(5)))
    assert report.basis == "backend-selected"
    assert len(report.facts) == 5
    assert all(fact.value == "Debian" for fact in report.facts)
    assert not accepts(request, {"nodes": {**realized["nodes"], "sixth": {"family": "Linux"}}})
    assert not accepts(request, {"nodes": dict(list(realized["nodes"].items())[:4])})


def test_kali_ladder_software_presence_and_private_acquisition():
    presence = record(os=atom("Kali"))
    nmap = record(software=record(nmap=record(name=atom("nmap"), version=atom("7.95"))))
    refined = record(
        release=atom("2026.3"),
        software=Record(
            (Field("curl", record(name=atom("curl"))), Field("optional", record(version=atom("1")), "optional"))
        ),
        configuration=record(one=atom(True), two=atom(2), three=atom("three")),
    )
    selected = {
        "os": "Kali",
        "release": "2026.3",
        "software": {"nmap": {"name": "nmap", "version": "7.95"}, "curl": {"name": "curl", "version": "8"}},
        "configuration": {"one": True, "two": 2, "three": "three", "incidental": 4},
    }
    for rules in ((presence,), (presence, nmap), (presence, nmap, refined)):
        assert choose(rules, (selected,), scopes=(Scope((), "open"),)) == selected
    backend_internal_route = "private-offline-cache"
    acquisition_offers = {backend_internal_route: ({**selected, "internal_route": backend_internal_route},)}
    witness = choose((presence, nmap), acquisition_offers[backend_internal_route], scopes=(Scope((), "open"),))
    assert witness["internal_route"] == backend_internal_route
    report = report_choice(witness, (("os",), ("software", "nmap", "version")))
    assert tuple(fact.value for fact in report.facts) == ("Kali", "7.95")
    assert backend_internal_route not in str(report)
    private = replace(
        record(repository=record(identity=atom("private-mirror"), revision=atom(3))),
        profile="urn:example:repo@1:sha256-fixture",
    )
    request = record(acquisition=private)
    realization = {"acquisition": {"repository": {"identity": "private-mirror", "revision": 3}}}
    with pytest.raises(ValueError, match="unsupported-semantics"):
        choose((request,), (realization,))
    assert choose((request,), (realization,), supported_profiles=frozenset({private.profile})) == realization
    realization["acquisition"]["repository"]["revision"] = 4
    assert choose((request,), (realization,), supported_profiles=frozenset({private.profile})) is NO_WITNESS


def test_non_cyber_typed_domain_uses_the_same_recursive_relation():
    greenhouse = record(crop=atom("tomato"), temperature=Atom((18, 19, 20)), irrigation=record(enabled=atom(True)))
    candidate = {"crop": "tomato", "temperature": 19, "irrigation": {"enabled": True, "supplier": "private"}}
    assert choose((greenhouse,), (candidate,), scopes=(Scope((), "open"),)) == candidate
    assert not accepts(greenhouse, {**candidate, "temperature": 21})


def test_world_round_trip_and_domain_budget_preserve_type_sensitive_meaning():
    worlds = ({"value": True}, {"value": 1}, {"value": None}, {"value": "1"})
    rule = record(value=atom(True))
    assert (
        denotation((rule,), worlds)
        == denotation((normalize(rule),), tuple(json.loads(json.dumps(worlds))))
        == frozenset({0})
    )
    assert normalize(normalize(rule)) == normalize(rule)
    oversized_domain = Atom((0, 1, 2))
    with pytest.raises(ValueError, match="limit-exceeded"):
        accepts(oversized_domain, 2, limit=8)


def test_null_witness_is_distinct_from_no_supported_choice():
    assert choose((Atom((None,)),), (None,)) != choose((Atom((None,)),), ("wrong",))
