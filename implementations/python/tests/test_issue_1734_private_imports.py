"""Issue #1734 / ADR-117: static source index and the private-import check."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest
from raes_contracts.errors import InvalidInputError
from tools.policy.private_imports import PrivateImport, collect_private_imports, is_private_name
from tools.policy.source_index import build_source_index

ROOT = "src"


def _write(repo: Path, rel_path: str, text: str = "") -> None:
    path = repo / ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(repo: Path) -> Counter[PrivateImport]:
    return collect_private_imports(build_source_index(repo, [ROOT]))


def _package(repo: Path, files: dict[str, str]) -> None:
    for rel_path, text in files.items():
        _write(repo, rel_path, text)


def test_index_names_modules_and_packages_and_skips_non_package_directories(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/one.py": "",
            "alpha/sub/__init__.py": "",
            "alpha/sub/two.py": "",
            "alpha/data/script.py": "",
            "notpkg/loose.py": "",
        },
    )

    index = build_source_index(tmp_path, [ROOT])

    assert index.root_packages == ("alpha",)
    assert sorted(index.modules) == ["alpha", "alpha.one", "alpha.sub", "alpha.sub.two"]
    assert index.modules["alpha.sub"].is_package
    assert index.modules["alpha.one"].rel_path == "src/alpha/one.py"
    assert index.max_package_depth == 1


def test_index_refuses_a_source_file_that_resolves_outside_the_repository(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    _package(tmp_path, {"alpha/__init__.py": ""})
    os.symlink(outside, tmp_path / ROOT / "alpha" / "escape.py")

    with pytest.raises(InvalidInputError, match="outside the repository"):
        build_source_index(tmp_path, [ROOT])


def test_index_refuses_a_symlinked_package_directory(tmp_path: Path) -> None:
    _package(tmp_path, {"alpha/__init__.py": "", "beta/__init__.py": ""})
    os.symlink(tmp_path / ROOT / "beta", tmp_path / ROOT / "alpha" / "linked")

    with pytest.raises(InvalidInputError, match="symbolic link"):
        build_source_index(tmp_path, [ROOT])


def test_index_refuses_an_unsafe_or_missing_coverage_root(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="coverage root"):
        build_source_index(tmp_path, ["../elsewhere"])
    with pytest.raises(InvalidInputError, match="coverage root"):
        build_source_index(tmp_path, ["missing"])


def test_index_refuses_invalid_python_source(tmp_path: Path) -> None:
    _package(tmp_path, {"alpha/__init__.py": "def broken(:\n"})

    with pytest.raises(InvalidInputError, match="not valid Python source"):
        build_source_index(tmp_path, [ROOT])


@pytest.mark.parametrize(
    ("name", "private"),
    [
        ("_helper", True),
        ("__mangled", True),
        ("_", True),
        ("__all__", False),
        ("__future__", False),
        ("__init__", False),
        ("public", False),
    ],
)
def test_private_name_rule_exempts_only_special_names(name: str, private: bool) -> None:
    assert is_private_name(name) is private


def test_private_name_from_another_module_is_a_finding_in_every_import_form(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/owner.py": "_helper = 1\n_other = 2\n",
            "alpha/user.py": (
                "from typing import TYPE_CHECKING\n"
                "from alpha.owner import _helper as renamed\n"
                "from .owner import _other\n"
                "if TYPE_CHECKING:\n"
                "    from alpha.owner import _helper\n"
                "def later():\n"
                "    from alpha import owner\n"
                "    from alpha.owner import _other\n"
                "    return owner\n"
            ),
        },
    )

    assert _findings(tmp_path) == Counter(
        {
            PrivateImport("alpha.user", "alpha.owner._helper"): 2,
            PrivateImport("alpha.user", "alpha.owner._other"): 2,
        }
    )


def test_private_module_is_private_to_its_parent_package(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": "from ._impl import public\nfrom . import _impl\n",
            "alpha/_impl.py": "public = 1\n_hidden = 2\n",
            "alpha/peer.py": "from alpha._impl import public\nimport alpha._impl\n",
            "alpha/inner/__init__.py": "from .._impl import public\n",
            "beta/__init__.py": "from alpha._impl import public\nimport alpha._impl as impl\nfrom alpha import _impl\n",
        },
    )

    assert _findings(tmp_path) == Counter(
        {
            PrivateImport("beta", "alpha._impl.public"): 1,
            PrivateImport("beta", "alpha._impl"): 2,
        }
    )


def test_private_name_from_own_package_init_is_a_finding_but_own_module_is_not(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": "_shared = 1\nfrom . import _shared as again\n",
            "alpha/child.py": "from . import _shared\n",
        },
    )

    assert _findings(tmp_path) == Counter({PrivateImport("alpha.child", "alpha._shared"): 1})


def test_all_does_not_bless_a_private_name_and_star_imports_report_listed_private_names(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/owner.py": "__all__ = ['visible', '_listed']\nvisible = 1\n_listed = 2\n",
            "alpha/user.py": "from alpha.owner import _listed\nfrom alpha.owner import *\n",
            "alpha/plain.py": "visible = 1\n",
            "alpha/star.py": "from alpha.plain import *\n",
        },
    )

    assert _findings(tmp_path) == Counter({PrivateImport("alpha.user", "alpha.owner._listed"): 2})


@pytest.mark.parametrize(
    "exporter",
    [
        "__all__ = []\n__all__ = ['_secret']\n_secret = 1\n",
        "__all__ = []\n__all__ += ['_secret']\n_secret = 1\n",
        "__all__ = ['visible']\n__all__.extend(['_secret'])\n_secret = 1\nvisible = 2\n",
        "__all__ = ['visible']\n__all__.append('_secret')\n_secret = 1\nvisible = 2\n",
        "__all__ = ['visible']\nEXPORTS = __all__\nEXPORTS += ['_secret']\n_secret = 1\nvisible = 2\n",
    ],
)
def test_star_exports_follow_every_later_update_of_all(tmp_path: Path, exporter: str) -> None:
    _package(
        tmp_path,
        {"alpha/__init__.py": "", "alpha/owner.py": exporter, "alpha/user.py": "from alpha.owner import *\n"},
    )

    assert _findings(tmp_path) == Counter({PrivateImport("alpha.user", "alpha.owner._secret"): 1})


def test_star_exports_follow_a_reassignment_that_drops_a_private_name(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/owner.py": (
                "__all__ = ['_old']\n__all__ = ['visible']\nEXPORTS = __all__\nEXPORTS = ['_other']\nvisible = 1\n"
            ),
            "alpha/user.py": "from alpha.owner import *\n",
        },
    )

    assert _findings(tmp_path) == Counter()


@pytest.mark.parametrize(
    "exporter",
    [
        "__all__ = ['a']\n__all__.remove('a')\n",
        "__all__ = ['a']\nif True:\n    __all__ += ['_b']\n",
        "__all__ = ['a']\ndef grow():\n    global __all__\n    __all__ = ['_b']\n",
        "__all__ = ['a']\n__all__ = __all__ + ['_b']\n",
        "__all__ = ['a']\nregister(__all__)\n",
    ],
)
def test_star_exports_fail_closed_on_an_unsupported_update_of_all(tmp_path: Path, exporter: str) -> None:
    _package(
        tmp_path,
        {"alpha/__init__.py": "", "alpha/owner.py": exporter, "alpha/user.py": "from alpha.owner import *\n"},
    )

    with pytest.raises(InvalidInputError, match="__all__"):
        _findings(tmp_path)


def test_star_import_from_a_module_with_dynamic_all_fails_closed(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": "",
            "alpha/owner.py": "__all__ = sorted(['b', 'a'])\n",
            "alpha/user.py": "from alpha.owner import *\n",
        },
    )

    with pytest.raises(InvalidInputError, match="__all__"):
        _findings(tmp_path)


def test_external_private_names_and_modules_are_findings_and_future_is_not(tmp_path: Path) -> None:
    _package(
        tmp_path,
        {
            "alpha/__init__.py": (
                "from __future__ import annotations\n"
                "from _thread import RLock\n"
                "from typing import _SpecialForm\n"
                "import os.path\n"
            ),
        },
    )

    assert _findings(tmp_path) == Counter(
        {
            PrivateImport("alpha", "_thread.RLock"): 1,
            PrivateImport("alpha", "typing._SpecialForm"): 1,
        }
    )


def test_relative_import_above_the_top_level_package_fails_closed(tmp_path: Path) -> None:
    _package(tmp_path, {"alpha/__init__.py": "", "alpha/one.py": "from ... import thing\n"})

    with pytest.raises(InvalidInputError, match="above the top-level package"):
        _findings(tmp_path)
