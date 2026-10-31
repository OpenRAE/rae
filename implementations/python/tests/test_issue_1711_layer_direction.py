"""The package dependency rule of ADR-121 (issue #1711).

``raes_contracts`` is the lowest package and imports no first-party package, in
any scope. ``raes`` imports only ``raes_contracts``. The static scan includes
imports inside functions and under ``TYPE_CHECKING``. The cold-import test
proves that loading every ``raes_contracts`` module loads no higher package.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

PACKAGES = Path(__file__).resolve().parents[1] / "packages"
FIRST_PARTY = frozenset(path.name for path in PACKAGES.iterdir() if (path / "__init__.py").is_file())
ALLOWED_FIRST_PARTY = {
    "raes_contracts": frozenset(),
    "raes": frozenset({"raes_contracts"}),
}


def _module_name(path: Path) -> str:
    parts = path.relative_to(PACKAGES).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _absolute_imports(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def _foreign_first_party_imports(package: str) -> list[str]:
    findings = []
    for path in sorted((PACKAGES / package).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for line, imported in _absolute_imports(tree):
            top_level = imported.split(".", 1)[0]
            if top_level in FIRST_PARTY and top_level != package and top_level not in ALLOWED_FIRST_PARTY[package]:
                findings.append(f"{_module_name(path)}:{line} imports {imported}")
    return findings


@pytest.mark.parametrize("package", sorted(ALLOWED_FIRST_PARTY))
def test_package_imports_only_lower_packages_in_every_scope(package: str) -> None:
    assert _foreign_first_party_imports(package) == []


def test_loading_every_contracts_module_loads_no_higher_package() -> None:
    modules = sorted(_module_name(path) for path in (PACKAGES / "raes_contracts").rglob("*.py"))
    script = (
        "import importlib, json, sys\n"
        f"for name in {modules!r}:\n"
        "    importlib.import_module(name)\n"
        "loaded = sorted({name.split('.', 1)[0] for name in sys.modules} & set(json.loads(sys.argv[1])))\n"
        "print(json.dumps(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, json.dumps(sorted(FIRST_PARTY))],
        capture_output=True,
        check=True,
        cwd=PACKAGES,
        text=True,
    )
    assert json.loads(result.stdout) == ["raes_contracts"]
