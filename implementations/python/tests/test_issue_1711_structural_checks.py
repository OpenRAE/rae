"""Issue #1711 / ADR-117 checks 4 to 6 and I10: private members, imports inside functions and hidden imports."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from raes_contracts.errors import InvalidInputError
from test_issue_1734_structural_ratchet import (
    IMPORT_CONTRACTS_PATH,
    PACKAGES,
    STRUCTURAL_BASELINE_PATH,
    FakeAnalyzer,
    FakeBase,
    FakeMembers,
    _baseline,
    _contracts,
    _policy,
    _repo,
    _rules,
    _run,
    _same_base,
)
from tools.policy.hidden_imports import analyze_hidden_imports
from tools.policy.private_members import PrivateMemberAccess, count_private_members
from tools.policy.source_index import build_source_index
from tools.policy.structural_ratchet import evaluate_structural_ratchet
from tools.python_closure_profiles import frozen_tool_command

LOADER = "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n"
DYNAMIC = "import importlib\n\nimportlib.import_module({target!r})\n"
LAZY_FACADE = (
    "import importlib\n\n"
    '{table} = {{"alpha.b": ("Thing",)}}\n\n\n'
    "def {function}(name):\n"
    "    for module in {loop}:\n"
    "        if name in {table}[module]:\n"
    "            return getattr(importlib.import_module(module), name)\n"
    "    raise AttributeError(name)\n"
)
TARGETS = {"alpha/b/__init__.py": "", "alpha/b/c.py": "", "alpha/c.py": ""}


def test_a_new_private_member_access_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": ""})

    failures = _run(repo, members=FakeMembers({("alpha.a", "_state"): 1}))

    assert _rules(failures) == ["private-member-access-new"]
    assert failures[0].path == f"{PACKAGES}/alpha/a.py"
    assert "_state" in failures[0].message


def test_a_baselined_member_access_passes_and_a_removed_one_is_stale(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": ""}, baseline=_baseline(members={"alpha.a": {"_state": 1}}))

    assert _run(repo, members=FakeMembers({("alpha.a", "_state"): 1})) == []
    assert _rules(_run(repo, members=FakeMembers())) == ["structural-baseline-stale"]


def test_a_member_baseline_cannot_grow_against_the_base_revision(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": ""})
    base = _same_base(repo)
    (repo / STRUCTURAL_BASELINE_PATH).write_text(_baseline(members={"alpha.a": {"_state": 1}}), encoding="utf-8")

    failures = _run(repo, base=base, members=FakeMembers({("alpha.a", "_state"): 1}))

    assert [(failure.rule_id, failure.message) for failure in failures] == [
        ("structural-baseline-grown", "private_member_accesses['alpha.a']['_state'] grew to 1")
    ]


def test_a_new_import_inside_a_function_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": "def f():\n    from alpha import b\n", "alpha/b.py": ""})

    failures = _run(repo)

    assert _rules(failures) == ["function-import-new"]
    assert "alpha.b" in failures[0].message


def test_a_baselined_import_inside_a_function_passes_and_a_hoisted_one_is_stale(tmp_path: Path) -> None:
    baseline = _baseline(function_imports={"alpha.a": {"alpha.b": 1}})
    inside = _repo(
        tmp_path / "in", {"alpha/a.py": "def f():\n    from alpha import b\n", "alpha/b.py": ""}, baseline=baseline
    )
    hoisted = _repo(tmp_path / "out", {"alpha/a.py": "from alpha import b\n", "alpha/b.py": ""}, baseline=baseline)

    assert _run(inside) == []
    assert _rules(_run(hoisted)) == ["structural-baseline-stale"]


def test_a_stdlib_import_and_a_lazy_export_are_not_imports_inside_functions(tmp_path: Path) -> None:
    lazy = "def __getattr__(name):\n    from alpha import b\n\n    return getattr(b, name)\n"
    repo = _repo(tmp_path, {"alpha/__init__.py": lazy, "alpha/a.py": "def f():\n    import json\n", "alpha/b.py": ""})

    assert _run(repo) == []


def test_a_dynamic_import_without_a_literal_target_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": LOADER})

    failures = _run(repo)

    assert _rules(failures) == ["dynamic-import-hidden"]
    assert failures[0].path == f"{PACKAGES}/alpha/a.py"
    assert "alpha.a.load" in failures[0].message


def test_a_reasoned_allowance_admits_a_dynamic_import_and_an_unused_one_is_stale(tmp_path: Path) -> None:
    allowance = [{"module": "alpha.a", "function": "load", "reason": "the composition root resolves a locator"}]
    used = _repo(tmp_path / "used", {"alpha/a.py": LOADER})
    unused = _repo(tmp_path / "unused", {"alpha/a.py": ""})

    assert _run(used, dynamic_import_allowlist=allowance) == []
    assert _rules(_run(unused, dynamic_import_allowlist=allowance)) == ["structural-baseline-stale"]


@pytest.mark.parametrize(
    "allowance",
    [
        "not a list",
        [{"module": "alpha.a", "function": "load"}],
        [{"module": "alpha.a", "function": "load", "reason": " "}],
        [
            {"module": "alpha.a", "function": "load", "reason": "x"},
            {"module": "alpha.a", "function": "load", "reason": "y"},
        ],
    ],
)
def test_a_malformed_allowance_fails_closed(tmp_path: Path, allowance: object) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": LOADER})

    assert _rules(_run(repo, dynamic_import_allowlist=allowance)) == ["policy-config-malformed"]


def test_a_literal_dynamic_target_joins_the_import_graph_for_the_cycle_check(tmp_path: Path) -> None:
    files = {
        "alpha/a.py": "from alpha import b\n",
        "alpha/b.py": 'import importlib\n\nimportlib.import_module("alpha.a")\n',
    }
    repo = _repo(tmp_path, files)

    failures = _run(repo, FakeAnalyzer(repo, {("alpha.a", "alpha.b")}))

    assert _rules(failures) == ["import-cycle-component-grown"]
    assert "['alpha.a', 'alpha.b']" in failures[0].message


def test_a_literal_dynamic_target_must_respect_the_module_boundaries(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": "", "beta/x.py": 'import importlib\n\nimportlib.import_module("alpha.a")\n'})

    failures = _run(repo)

    assert _rules(failures) == ["dynamic-import-boundary"]
    assert failures[0].path == f"{PACKAGES}/beta/x.py"


def test_a_lazy_export_table_names_the_targets_of_a_getattr_import(tmp_path: Path) -> None:
    facade = (
        "import importlib\n\n"
        '_LAZY_EXPORTS = {"alpha.b": ("Thing",)}\n\n\n'
        "def __getattr__(name):\n"
        "    for module, names in _LAZY_EXPORTS.items():\n"
        "        if name in names:\n"
        "            return getattr(importlib.import_module(module), name)\n"
        "    raise AttributeError(name)\n"
    )
    repo = _repo(tmp_path, {"alpha/__init__.py": facade, "alpha/b.py": "Thing = 1\n"})

    assert _run(repo) == []


def _hidden(tmp_path: Path, files: dict[str, str]) -> tuple[set[tuple[str, str]], list[tuple[str, str]]]:
    repo = _repo(tmp_path, {**TARGETS, **files})
    analysis = analyze_hidden_imports(build_source_index(repo, [PACKAGES]))
    return set(analysis.edges), [(item.module, item.function) for item in analysis.unresolved]


@pytest.mark.parametrize(
    ("source", "edges", "unresolved"),
    [
        pytest.param(
            "from importlib import import_module as load\n\n\ndef f(name):\n    return load(name)\n\n\nload('alpha.c')\n",
            {("alpha.a", "alpha.c")},
            [("alpha.a", "f")],
            id="import-alias",
        ),
        pytest.param(
            "import importlib\n\nloader = importlib.import_module\n\n\ndef f(name):\n    return loader(name)\n",
            set(),
            [("alpha.a", "f")],
            id="assignment-alias",
        ),
        pytest.param(
            "from importlib import *\n\n\ndef f(name):\n    return import_module(name)\n",
            set(),
            [("alpha.a", "f")],
            id="star-import",
        ),
        pytest.param("def f(obj, name):\n    return obj.import_module(name)\n", set(), [], id="unrelated-attribute"),
        pytest.param(
            "import importlib\n\n\ndef f(importlib, name):\n    return importlib.import_module(name)\n",
            set(),
            [],
            id="parameter-shadows-the-module",
        ),
        pytest.param(
            "import importlib\n\nimportlib.import_module('.c', 'alpha')\nimportlib.import_module('.b', __package__)\n",
            {("alpha.a", "alpha.c"), ("alpha.a", "alpha.b")},
            [],
            id="relative-with-package",
        ),
        pytest.param(
            "import importlib\n\nimportlib.import_module('.c')\n",
            set(),
            [("alpha.a", "<module>")],
            id="relative-without-package",
        ),
        pytest.param(
            "__import__('b', globals(), None, ['c'], 1)\n",
            {("alpha.a", "alpha.b"), ("alpha.a", "alpha.b.c")},
            [],
            id="dunder-import-with-level-and-fromlist",
        ),
        pytest.param(
            "__import__('b', None, None, (), 1)\n",
            set(),
            [("alpha.a", "<module>")],
            id="dunder-import-with-level-and-no-globals",
        ),
        pytest.param(
            "import importlib\n\nimportlib.__import__('alpha.b', fromlist=[name for name in 'c'])\n",
            set(),
            [("alpha.a", "<module>")],
            id="dunder-import-with-a-computed-fromlist",
        ),
        pytest.param(
            "from importlib.util import find_spec\n\nfind_spec('alpha.b.c')\n",
            {("alpha.a", "alpha.b")},
            [],
            id="find-spec-imports-the-parent",
        ),
        pytest.param(
            "import importlib\n\ngetattr(importlib, 'import_module')('alpha.c')\n",
            set(),
            [("alpha.a", "<module>")],
            id="getattr-passes-on-the-module",
        ),
        pytest.param("__builtins__.__import__('alpha.c')\n", {("alpha.a", "alpha.c")}, [], id="builtins-attribute"),
        pytest.param(
            "__builtins__['__import__']('alpha.c')\n", set(), [("alpha.a", "<module>")], id="builtins-subscript"
        ),
        pytest.param(
            "import importlib\n\n\ndef f(name, load=importlib.import_module):\n    return load(name)\n",
            set(),
            [("alpha.a", "<module>")],
            id="default-argument-passes-on-the-callable",
        ),
        pytest.param(
            "from importlib import import_module\n\nimport_module('alpha.c')\ndel import_module\n",
            {("alpha.a", "alpha.c")},
            [],
            id="deletion-after-a-call",
        ),
        pytest.param(
            "import importlib\n\nif FLAG:\n    load = importlib.import_module\nelse:\n    load = print\n\n\n"
            "def f(name):\n    return load(name)\n",
            set(),
            [("alpha.a", "f")],
            id="conditional-reassignment",
        ),
        pytest.param(
            "__import__('alpha.c')\n__import__ = None\n",
            {("alpha.a", "alpha.c")},
            [],
            id="builtin-before-a-module-binding",
        ),
        pytest.param(
            "import importlib\n\nload = other\nother = load\nload = importlib.import_module\n\n\n"
            "def f(name):\n    return other(name)\n",
            set(),
            [("alpha.a", "f")],
            id="cyclic-assignment",
        ),
    ],
)
def test_the_hidden_import_analysis_resolves_each_binding_and_fails_closed(
    tmp_path: Path, source: str, edges: set[tuple[str, str]], unresolved: list[tuple[str, str]]
) -> None:
    assert _hidden(tmp_path, {"alpha/a.py": source}) == (edges, unresolved)


def test_a_dynamic_import_callable_resolves_through_a_first_party_re_export(tmp_path: Path) -> None:
    files = {
        "alpha/tools.py": "import importlib\nfrom importlib import import_module\n",
        "alpha/a.py": (
            "from alpha import tools\nfrom alpha.tools import import_module as load\n\n\n"
            "def f(name):\n    return load(name)\n\n\n"
            "def g(name):\n    return tools.importlib.import_module(name)\n"
        ),
    }

    assert _hidden(tmp_path, files) == (set(), [("alpha.a", "f"), ("alpha.a", "g")])


@pytest.mark.parametrize(
    "files",
    [
        pytest.param(
            {
                "alpha/tools.py": "from importlib import *\n",
                "alpha/other.py": "def import_module(name):\n    return name\n",
                "alpha/a.py": (
                    "if FLAG:\n    from alpha.tools import *\nelse:\n    from alpha.other import *\n\n\n"
                    "def f(name):\n    return import_module(name)\n"
                ),
            },
            id="conditional-star-imports",
        ),
        pytest.param(
            {
                "alpha/tools.py": "from importlib import *\n",
                "alpha/relay.py": "from alpha.tools import *\n",
                "alpha/a.py": "from alpha.relay import *\n\n\ndef f(name):\n    return import_module(name)\n",
            },
            id="star-import-chain",
        ),
        pytest.param(
            {
                "alpha/tools.py": "import importlib\n\n_load = importlib.import_module\n__all__ = ['_load']\n",
                "alpha/a.py": "from alpha.tools import *\n\n\ndef f(name):\n    return _load(name)\n",
            },
            id="private-name-in-all",
        ),
    ],
)
def test_a_star_import_keeps_each_possible_import_callable(tmp_path: Path, files: dict[str, str]) -> None:
    assert _hidden(tmp_path, files) == (set(), [("alpha.a", "f")])


@pytest.mark.parametrize(
    ("facade", "unresolved"),
    [
        pytest.param(
            LAZY_FACADE.format(table="_LAZY_EXPORTS", function="__getattr__", loop="_LAZY_EXPORTS.keys()"),
            [],
            id="keys-of-the-lazy-table",
        ),
        pytest.param(
            LAZY_FACADE.format(table="_LAZY_EXPORTS", function="__getattr__", loop="_LAZY_EXPORTS")
            + "\n\n_LAZY_EXPORTS.update({'beta.x': ('Other',)})\n",
            [("alpha", "__getattr__")],
            id="table-updated",
        ),
        pytest.param(
            LAZY_FACADE.format(table="_LAZY_EXPORTS", function="__getattr__", loop="_LAZY_EXPORTS")
            + "\n\n_LAZY_EXPORTS['beta.x'] = ('Other',)\n",
            [("alpha", "__getattr__")],
            id="table-item-assigned",
        ),
        pytest.param(
            LAZY_FACADE.format(table="_LAZY_EXPORTS", function="__getattr__", loop="_LAZY_EXPORTS")
            + "\n\nglobals()['_LAZY_EXPORTS']['beta.x'] = ('Other',)\n",
            [("alpha", "__getattr__")],
            id="table-named-by-a-string",
        ),
        pytest.param(
            LAZY_FACADE.format(table="_OTHER", function="__getattr__", loop="_OTHER"),
            [("alpha", "__getattr__")],
            id="another-table",
        ),
        pytest.param(
            LAZY_FACADE.format(table="_LAZY_EXPORTS", function="load", loop="_LAZY_EXPORTS"),
            [("alpha", "load")],
            id="outside-getattr",
        ),
    ],
)
def test_only_a_getattr_loop_over_the_lazy_table_names_its_targets(
    tmp_path: Path, facade: str, unresolved: list[tuple[str, str]]
) -> None:
    edges = {("alpha", "alpha.b")} if not unresolved else set()

    assert _hidden(tmp_path, {"alpha/__init__.py": facade}) == (edges, unresolved)


def test_a_lazy_table_that_another_module_reaches_names_no_targets(tmp_path: Path) -> None:
    facade = LAZY_FACADE.format(table="_LAZY_EXPORTS", function="__getattr__", loop="_LAZY_EXPORTS")
    files = {"alpha/__init__.py": facade, "beta/x.py": "import alpha\n\nalpha._LAZY_EXPORTS['beta.y'] = ('Other',)\n"}

    assert _hidden(tmp_path, files) == (set(), [("alpha", "__getattr__")])


def test_a_dynamic_edge_inside_a_baselined_component_must_not_close_a_new_cycle(tmp_path: Path) -> None:
    files = {
        "alpha/a.py": "from alpha import b\n",
        "alpha/b.py": "from alpha import c\n",
        "alpha/c.py": 'import importlib\n\nfrom alpha import a\n\nimportlib.import_module("alpha.b")\n',
    }
    repo = _repo(
        tmp_path,
        files,
        contracts=_contracts(cycle_ignores=["alpha.c -> alpha.a"]),
        baseline=_baseline(components={"alpha": [["alpha.a", "alpha.b", "alpha.c"]]}),
    )
    imports = {("alpha.a", "alpha.b"), ("alpha.b", "alpha.c"), ("alpha.c", "alpha.a")}

    failures = _run(repo, FakeAnalyzer(repo, imports))

    assert [(failure.rule_id, failure.message) for failure in failures] == [
        (
            "dynamic-import-cycle",
            "dynamic imports close an import cycle between children of alpha: ['alpha.b', 'alpha.c']. Remove the "
            "dynamic import that closes the cycle",
        )
    ]


def _run_with_rules(repo: Path, **rules: dict[str, object]) -> list[str]:
    policy = _policy()
    for module in policy["module_boundaries"]["modules"]:
        module.update(rules.get(module["id"], {}))
    failures = evaluate_structural_ratchet(
        repo, policy, import_analyzer=FakeAnalyzer(repo), member_analyzer=FakeMembers(), base_revision=_same_base(repo)
    )
    return [f"{failure.rule_id}: {failure.message}" for failure in failures]


@pytest.mark.parametrize(
    ("target", "rule", "message"),
    [
        pytest.param(
            "beta.impl",
            {"public_import_prefixes": {"beta": ["beta.api"]}},
            "alpha may import beta only through public prefixes ['beta.api']",
            id="non-public-prefix",
        ),
        pytest.param("beta._impl", {}, "alpha must not import private/internal module path 'beta._impl'", id="private"),
        pytest.param(
            "beta.impl",
            {"forbidden_import_prefixes": ["beta.impl"]},
            "alpha must not import 'beta.impl'",
            id="forbidden-prefix",
        ),
    ],
)
def test_a_dynamic_target_meets_the_same_module_boundary_rules_as_a_static_import(
    tmp_path: Path, target: str, rule: dict[str, object], message: str
) -> None:
    files = {"alpha/a.py": DYNAMIC.format(target=target), "beta/api.py": "", "beta/impl.py": "", "beta/_impl.py": ""}
    repo = _repo(tmp_path, files)

    failures = _run_with_rules(repo, alpha=rule)

    assert len(failures) == 1
    assert failures[0].startswith(f"dynamic-import-boundary: alpha.a loads {target} dynamically: ")
    assert message in failures[0]


def test_a_dynamic_target_must_follow_the_package_layer_order(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": "", "beta/x.py": DYNAMIC.format(target="alpha.a")})

    failures = _run_with_rules(repo, beta={"allowed_top_level_imports": ["alpha"]})

    assert failures == [
        "dynamic-import-boundary: beta.x loads alpha.a dynamically, but the package layers do not let beta import alpha"
    ]


def test_a_new_family_is_adopted_only_within_the_findings_of_the_base_source(tmp_path: Path) -> None:
    base_source = _repo(tmp_path / "base", {"alpha/a.py": "def f():\n    from alpha import b\n", "alpha/b.py": ""})
    base = FakeBase(
        {
            IMPORT_CONTRACTS_PATH: _contracts(),
            STRUCTURAL_BASELINE_PATH: _baseline(families=False),
        },
        source=base_source,
    )
    same = _repo(
        tmp_path / "same",
        {"alpha/a.py": "def f():\n    from alpha import b\n", "alpha/b.py": ""},
        baseline=_baseline(function_imports={"alpha.a": {"alpha.b": 1}}),
    )
    more = _repo(
        tmp_path / "more",
        {"alpha/a.py": "def f():\n    from alpha import b\n", "alpha/b.py": "def g():\n    from alpha import a\n"},
        baseline=_baseline(function_imports={"alpha.a": {"alpha.b": 1}, "alpha.b": {"alpha.a": 1}}),
    )

    assert _run(same, base=base) == []
    failures = _run(more, base=base)
    assert [(failure.rule_id, failure.message) for failure in failures] == [
        (
            "structural-baseline-grown",
            "function_imports adopts 2 findings, but the base revision source has 1; adoption must not add "
            "findings (ADR-117 I10)",
        )
    ]


def test_the_current_baseline_must_record_each_counted_family(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {}, baseline=_baseline(families=False))
    base = _same_base(repo)
    base.source = repo

    messages = [failure.message for failure in _run(repo, base=base)]

    assert "the baseline must record private_member_accesses (ADR-117 check private_member_accesses)" in messages
    assert "the baseline must record function_imports (ADR-117 check function_imports)" in messages


def _report(repo: Path, *diagnostics: dict[str, object]) -> str:
    return json.dumps(list(diagnostics))


def _diagnostic(repo: Path, rel_path: str, member: str, code: str = "SLF001") -> dict[str, object]:
    return {
        "code": code,
        "message": f"Private member accessed: `{member}`",
        "filename": str(repo / PACKAGES / rel_path),
    }


def test_a_ruff_report_counts_each_finding_by_module_and_member(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": ""})
    index = build_source_index(repo, [PACKAGES])
    report = _report(repo, _diagnostic(repo, "alpha/a.py", "_x"), _diagnostic(repo, "alpha/a.py", "_x"))

    assert count_private_members(report, repo, index) == Counter({PrivateMemberAccess("alpha.a", "_x"): 2})


@pytest.mark.parametrize(
    "case",
    ["not json", "not a list", "other rule", "unknown file", "outside file", "other message"],
)
def test_an_unexpected_ruff_report_fails_closed(tmp_path: Path, case: str) -> None:
    repo = _repo(tmp_path, {"alpha/a.py": ""})
    index = build_source_index(repo, [PACKAGES])
    reports = {
        "not json": "{",
        "not a list": "{}",
        "other rule": _report(repo, _diagnostic(repo, "alpha/a.py", "_x", code="F401")),
        "unknown file": _report(repo, _diagnostic(repo, "alpha/missing.py", "_x")),
        "outside file": json.dumps(
            [{"code": "SLF001", "message": "Private member accessed: `_x`", "filename": "/elsewhere/a.py"}]
        ),
        "other message": json.dumps(
            [{"code": "SLF001", "message": "something else", "filename": str(repo / PACKAGES / "alpha/a.py")}]
        ),
    }

    with pytest.raises(InvalidInputError):
        count_private_members(reports[case], repo, index)


_MEMBERS = """
import json, sys
from pathlib import Path
from tools.policy.private_members import analyze_private_members
from tools.policy.source_index import build_source_index
root = Path(sys.argv[1])
index = build_source_index(root, ["pkgs"])
analysis = analyze_private_members(root, index)
print(json.dumps(sorted([item.module, item.member, count] for item, count in analysis.counts.items())))
"""


@pytest.mark.integration
def test_the_locked_ruff_reports_access_to_another_objects_private_member(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (
        "class Box:\n"
        "    def __init__(self):\n"
        "        self._value = 1\n\n"
        "    def same(self, other):\n"
        "        return self._value + other._value\n"
    )
    package = tmp_path / "pkgs" / "fix1711"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "box.py").write_text(source, encoding="utf-8")

    completed = subprocess.run(
        frozen_tool_command(repo_root, "python", "-c", _MEMBERS, str(tmp_path)),
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == [["fix1711.box", "_value", 1]]
