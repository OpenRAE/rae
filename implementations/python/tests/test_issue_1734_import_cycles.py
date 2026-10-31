"""Issue #1734 / ADR-117: sibling projection, cyclic components and the layer agreement with ADR-036."""

from __future__ import annotations

import pytest
from raes_contracts.errors import InvalidInputError
from tools.policy.import_cycles import (
    Layer,
    SiblingEdge,
    cyclic_components,
    is_cyclic_import,
    layer_disagreements,
    parse_layers,
    sibling_edge,
)


@pytest.mark.parametrize(
    ("importer", "imported", "expected"),
    [
        ("a.x", "a.y", SiblingEdge("a", "a.x", "a.y")),
        ("a.x.deep", "a.y.other", SiblingEdge("a", "a.x", "a.y")),
        ("a.p.one", "a.p.two", SiblingEdge("a.p", "a.p.one", "a.p.two")),
        ("a.x", "a", None),
        ("a", "a.x", None),
        ("a.p.one", "a.p", None),
        ("a.x", "b.y", None),
        ("a.x", "a.x", None),
    ],
)
def test_each_import_projects_onto_one_sibling_pair(importer: str, imported: str, expected: SiblingEdge | None) -> None:
    assert sibling_edge(importer, imported) == expected


def test_components_hold_only_siblings_that_reach_each_other() -> None:
    imports = {
        ("a.x", "a.y"),
        ("a.y.deep", "a.x"),
        ("a.y", "a.z"),
        ("a.p.one", "a.p.two"),
        ("a.p.two", "a.p.one"),
        ("b.m", "b.n"),
    }

    assert cyclic_components(imports, depth=10) == {
        "a": (("a.x", "a.y"),),
        "a.p": (("a.p.one", "a.p.two"),),
    }


def test_depth_limits_the_packages_whose_children_are_checked() -> None:
    imports = {("a.p.one", "a.p.two"), ("a.p.two", "a.p.one")}

    assert cyclic_components(imports, depth=0) == {}
    assert cyclic_components(imports, depth=1) == {"a.p": (("a.p.one", "a.p.two"),)}


def test_a_new_return_path_through_an_existing_edge_extends_the_component() -> None:
    before = {("a.x", "a.y"), ("a.y", "a.x"), ("a.y", "a.z")}
    after = {("a.x", "a.y"), ("a.y", "a.z"), ("a.z", "a.x")}

    assert cyclic_components(before, depth=10) == {"a": (("a.x", "a.y"),)}
    assert cyclic_components(after, depth=10) == {"a": (("a.x", "a.y", "a.z"),)}


def test_components_of_a_long_chain_do_not_depend_on_recursion_depth() -> None:
    count = 5000
    imports = {(f"a.m{index}", f"a.m{index + 1}") for index in range(count)} | {(f"a.m{count}", "a.m0")}

    components = cyclic_components(imports, depth=10)

    assert len(components["a"][0]) == count + 1


def test_an_import_is_cyclic_only_when_its_siblings_share_a_component() -> None:
    components = {"a": (("a.x", "a.y"),)}

    assert is_cyclic_import(("a.x.deep", "a.y"), components)
    assert not is_cyclic_import(("a.x", "a.z"), components)
    assert not is_cyclic_import(("a.x", "b.y"), components)


def test_layers_parse_independent_and_non_independent_layers() -> None:
    assert parse_layers(["top", "left | right", "low : lower", "base"]) == (
        Layer(("top",), independent=True),
        Layer(("left", "right"), independent=True),
        Layer(("low", "lower"), independent=False),
        Layer(("base",), independent=True),
    )


@pytest.mark.parametrize("entry", ["", "a | b : c", "a |", " : b"])
def test_malformed_layer_entries_are_refused(entry: str) -> None:
    with pytest.raises(InvalidInputError):
        parse_layers(["top", entry])


ALLOWED = {
    "cli": frozenset({"core", "contracts", "conformance"}),
    "conformance": frozenset({"core", "contracts", "cli"}),
    "core": frozenset({"contracts"}),
    "contracts": frozenset({"core"}),
    "ops": frozenset({"contracts"}),
}


def test_layers_that_follow_the_allowed_imports_agree() -> None:
    layers = parse_layers(["cli", "conformance", "core | ops", "contracts"])

    assert layer_disagreements(layers, ALLOWED) == []


def test_layers_may_order_a_mutual_allowance_but_not_forbid_a_one_way_allowance() -> None:
    reversed_one_way = parse_layers(["cli", "conformance", "contracts", "core | ops"])
    independent_but_allowed = parse_layers(["cli | conformance", "core | ops", "contracts"])

    assert layer_disagreements(reversed_one_way, ALLOWED) == [
        "layers place 'contracts' above 'ops', but ADR-036 allows 'ops' to import 'contracts' and not the reverse"
    ]
    assert layer_disagreements(independent_but_allowed, ALLOWED) == [
        "layers make 'cli' and 'conformance' independent, but ADR-036 allows 'cli' to import 'conformance'",
        "layers make 'conformance' and 'cli' independent, but ADR-036 allows 'conformance' to import 'cli'",
    ]


def test_layers_must_name_each_package_exactly_once() -> None:
    missing = parse_layers(["cli", "conformance", "core", "contracts"])
    extra = parse_layers(["cli", "conformance", "core | ops", "contracts", "ghost"])
    twice = parse_layers(["cli", "conformance", "core | ops", "contracts", "cli"])

    assert layer_disagreements(missing, ALLOWED) == ["layers do not name package 'ops'"]
    assert layer_disagreements(extra, ALLOWED) == ["layers name 'ghost', which is not a package"]
    assert layer_disagreements(twice, ALLOWED) == ["layers name 'cli' more than once"]
