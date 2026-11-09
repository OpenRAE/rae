"""Issue #1734 / ADR-117: static count of repository ancestors for each class."""

from __future__ import annotations

from pathlib import Path

from tools.policy.class_ancestry import analyze_class_ancestry
from tools.policy.source_index import build_source_index

ROOT = "src"


def _ancestry(repo: Path, files: dict[str, str]):
    for rel_path, text in files.items():
        path = repo / ROOT / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return analyze_class_ancestry(build_source_index(repo, [ROOT]))


def _chain(length: int) -> str:
    lines = ["class C0:\n    pass\n"]
    lines.extend(f"class C{index}(C{index - 1}):\n    pass\n" for index in range(1, length + 1))
    return "".join(lines)


def test_count_is_the_number_of_distinct_repository_ancestors(tmp_path: Path) -> None:
    result = _ancestry(tmp_path, {"alpha/__init__.py": "", "alpha/chain.py": _chain(8)})

    assert result.unresolved == ()
    assert result.counts["alpha.chain:C7"] == 7
    assert result.counts["alpha.chain:C8"] == 8
    assert result.counts["alpha.chain:C0"] == 0


def test_diamond_ancestor_counts_once(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/shapes.py": (
                "class Base:\n    pass\n"
                "class Left(Base):\n    pass\n"
                "class Right(Base):\n    pass\n"
                "class Bottom(Left, Right):\n    pass\n"
            ),
        },
    )

    assert result.counts["alpha.shapes:Bottom"] == 3


def test_external_and_builtin_ancestors_are_not_counted(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/loader.py": (
                "import yaml\n"
                "from collections import namedtuple\n"
                "from typing import Generic, TypeVar\n"
                "T = TypeVar('T')\n"
                "class Loader(yaml.SafeLoader):\n    pass\n"
                "class Error(ValueError):\n    pass\n"
                "class Box(Generic[T]):\n    pass\n"
                "class Pair(namedtuple('Pair', 'a b')):\n    pass\n"
                "class Mine(Loader, metaclass=type):\n    pass\n"
            ),
        },
    )

    assert result.unresolved == ()
    assert result.counts["alpha.loader:Loader"] == 0
    assert result.counts["alpha.loader:Error"] == 0
    assert result.counts["alpha.loader:Box"] == 0
    assert result.counts["alpha.loader:Pair"] == 0
    assert result.counts["alpha.loader:Mine"] == 1


def test_resolution_follows_relative_imports_aliases_reexports_stars_and_generics(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "from .core.base import Root as PublicRoot\n",
            "alpha/core/__init__.py": "",
            "alpha/core/base.py": (
                "from typing import Generic, TypeVar\n"
                "T = TypeVar('T')\n"
                "class Root(Generic[T]):\n    pass\n"
                "Alias = Root\n"
                "type Kind = Root\n"
            ),
            "alpha/core/stars.py": "from .base import *\n",
            "alpha/user.py": (
                "import alpha.core.base as base_module\n"
                "import alpha\n"
                "from alpha import PublicRoot\n"
                "from .core.stars import Root as Starred\n"
                "from .core import base\n"
                "class A(PublicRoot[int]):\n    pass\n"
                "class B(base_module.Alias):\n    pass\n"
                "class C(alpha.core.base.Root):\n    pass\n"
                "class D(Starred, base.Root):\n    pass\n"
                "class E(base.Kind):\n    pass\n"
            ),
        },
    )

    assert result.unresolved == ()
    for name in ("A", "B", "C", "D", "E"):
        assert result.counts[f"alpha.user:{name}"] == 1, name


def test_nested_and_local_classes_resolve_in_their_enclosing_scopes(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/nested.py": (
                "class Base:\n    pass\n"
                "class Outer:\n"
                "    class Inner(Base):\n        pass\n"
                "    class Deeper(Inner):\n        pass\n"
                "def factory():\n"
                "    class Local(Outer.Inner):\n        pass\n"
                "    return Local\n"
            ),
        },
    )

    assert result.unresolved == ()
    assert result.counts["alpha.nested:Outer.Deeper"] == 2
    assert result.counts["alpha.nested:factory.<locals>.Local"] == 2


def test_compound_statements_and_rebinding_use_the_binding_in_force_at_definition(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/base.py": "class Thing:\n    pass\n",
            "alpha/cond.py": (
                "try:\n"
                "    from yaml import CSafeLoader as Loader\n"
                "except ImportError:\n"
                "    from yaml import SafeLoader as Loader\n"
                "from .base import Thing\n"
                "if True:\n"
                "    class Inside(Thing):\n        pass\n"
                "class Thing(Thing):\n    pass\n"
                "class After(Thing):\n    pass\n"
                "class Fast(Loader):\n    pass\n"
            ),
        },
    )

    assert result.unresolved == ()
    assert result.counts["alpha.cond:Inside"] == 1
    assert result.counts["alpha.cond:Thing"] == 1
    assert result.counts["alpha.cond:After"] == 2
    assert result.counts["alpha.cond:Fast"] == 0


def test_nested_classes_use_the_module_binding_in_force_when_their_body_runs(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/chain.py": _chain(7),
            "alpha/nested.py": (
                "from .chain import C7 as Base\n"
                "class Outer:\n"
                "    Alias = Base\n"
                "    class Child(Base):\n        pass\n"
                "    class FromAlias(Alias):\n        pass\n"
                "def later():\n"
                "    class Late(Base):\n        pass\n"
                "    return Late\n"
                "Base = object\n"
            ),
        },
    )

    assert result.unresolved == ()
    assert result.counts["alpha.nested:Outer.Child"] == 8
    assert result.counts["alpha.nested:Outer.FromAlias"] == 8
    # A function body runs after the module, so it sees the final module binding.
    assert result.counts["alpha.nested:later.<locals>.Late"] == 0


def test_same_class_name_in_two_modules_keeps_separate_identities(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/one.py": "class Base:\n    pass\nclass Thing(Base):\n    pass\n",
            "alpha/two.py": "from .one import Thing as Parent\nclass Thing(Parent):\n    pass\n",
        },
    )

    assert result.counts["alpha.one:Thing"] == 1
    assert result.counts["alpha.two:Thing"] == 2


def test_unresolved_repository_base_is_reported_not_counted_as_zero(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/factory.py": "def make_base():\n    return object\nclass Base:\n    pass\n",
            "alpha/user.py": (
                "from .factory import make_base, Missing\n"
                "from . import factory\n"
                "class FromCall(make_base()):\n    pass\n"
                "class FromMissing(Missing):\n    pass\n"
                "class FromFunction(factory.make_base):\n    pass\n"
                "class FromUnknown(undefined_name):\n    pass\n"
            ),
        },
    )

    unresolved = {(item.class_id, item.base) for item in result.unresolved}
    assert unresolved == {
        ("alpha.user:FromCall", "make_base()"),
        ("alpha.user:FromMissing", "Missing"),
        ("alpha.user:FromFunction", "factory.make_base"),
        ("alpha.user:FromUnknown", "undefined_name"),
    }
    assert all(item.rel_path == "src/alpha/user.py" for item in result.unresolved)


def test_inheritance_and_alias_cycles_are_bounded_and_reported(tmp_path: Path) -> None:
    result = _ancestry(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/loop.py": ("class A(B):\n    pass\nclass B(A):\n    pass\nX = Y\nY = X\nclass C(X):\n    pass\n"),
        },
    )

    assert {item.class_id for item in result.unresolved} >= {"alpha.loop:A", "alpha.loop:C"}
