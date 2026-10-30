"""Issue #1734 / ADR-117: the structural checks with real Git and the real grimp/import-linter tooling."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from raes_contracts.errors import OperationalError
from tools.policy.structural_baseline import GitBaseRevision
from tools.python_closure_profiles import frozen_tool_command

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.integration

_ANALYZE = """
import json, sys
from pathlib import Path
from tools.policy.import_graph import analyze_imports
root, config, *packages = sys.argv[1:]
analysis = analyze_imports([Path(root)], Path(config), root_packages=packages, exclude_type_checking_imports=True)
print(json.dumps({
    "imports": sorted(analysis.imports),
    "contracts": {result.contract_id: [result.status, list(result.details)] for result in analysis.contracts},
    "versions": dict(analysis.versions),
}))
"""

_RATCHET = """
import sys
from pathlib import Path
from tools.policy.repo_policy import load_policy
from tools.policy.structural_ratchet import evaluate_structural_ratchet
repo = Path(sys.argv[1])
failures = evaluate_structural_ratchet(repo, load_policy(repo), base_rev="HEAD")
print("\\n".join(failure.render() for failure in failures))
sys.exit(1 if failures else 0)
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _tooling_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        frozen_tool_command(REPO_ROOT, "python", *args), cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def _write(root: Path, files: dict[str, str]) -> None:
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _contracts(cycle_ignores: list[str], layer_ignores: list[str]) -> str:
    return (
        "[tool.importlinter]\n"
        'root_packages = ["fixhigh1734", "fixlow1734"]\n'
        "include_external_packages = false\n"
        "exclude_type_checking_imports = true\n\n"
        "[[tool.importlinter.contracts]]\n"
        'id = "raes-package-layers"\nname = "layers"\ntype = "layers"\n'
        'layers = ["fixhigh1734", "fixlow1734"]\n'
        'unmatched_ignore_imports_alerting = "error"\n'
        f"ignore_imports = {json.dumps(layer_ignores)}\n\n"
        "[[tool.importlinter.contracts]]\n"
        'id = "raes-sibling-cycles"\nname = "cycles"\ntype = "acyclic_siblings"\n'
        'ancestors = ["fixhigh1734", "fixlow1734"]\ndepth = 10\n'
        'unmatched_ignore_imports_alerting = "error"\n'
        f"ignore_imports = {json.dumps(cycle_ignores)}\n"
    )


def _analyze(tmp_path: Path, files: dict[str, str], cycle_ignores: list[str], layer_ignores: list[str]) -> dict:
    root = tmp_path / "src"
    _write(root, {"fixhigh1734/__init__.py": "", "fixlow1734/__init__.py": "", **files})
    config = tmp_path / "import_contracts.toml"
    config.write_text(_contracts(cycle_ignores, layer_ignores), encoding="utf-8")
    completed = _tooling_python("-c", _ANALYZE, str(root), str(config), "fixhigh1734", "fixlow1734")
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_a_cycle_through_an_import_inside_a_function_breaks_the_sibling_contract(tmp_path: Path) -> None:
    result = _analyze(
        tmp_path,
        {
            "fixhigh1734/a.py": "from fixhigh1734 import b\n",
            "fixhigh1734/b.py": "def later():\n    from fixhigh1734 import a\n    return a\n",
        },
        [],
        [],
    )

    assert ["fixhigh1734.b", "fixhigh1734.a"] in result["imports"]
    assert result["contracts"]["raes-sibling-cycles"][0] == "broken"
    assert result["contracts"]["raes-package-layers"] == ["kept", []]
    assert result["versions"] == {"grimp": "3.18", "import-linter": "2.15"}


def test_type_checking_imports_are_excluded_and_ignored_imports_keep_the_contract(tmp_path: Path) -> None:
    result = _analyze(
        tmp_path,
        {
            "fixhigh1734/a.py": "from fixhigh1734 import b\n",
            "fixhigh1734/b.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from fixhigh1734 import a\n",
            "fixhigh1734/c.py": "from fixhigh1734 import d\n",
            "fixhigh1734/d.py": "from fixhigh1734 import c\n",
        },
        ["fixhigh1734.c -> fixhigh1734.d"],
        [],
    )

    assert ["fixhigh1734.b", "fixhigh1734.a"] not in result["imports"]
    assert result["contracts"]["raes-sibling-cycles"] == ["kept", []]


def test_an_upward_import_breaks_the_layers_contract_and_an_unmatched_ignore_is_reported(tmp_path: Path) -> None:
    result = _analyze(
        tmp_path,
        {"fixlow1734/up.py": "import fixhigh1734\n"},
        ["fixhigh1734.ghost -> fixlow1734"],
        [],
    )

    assert result["contracts"]["raes-package-layers"][0] == "broken"
    assert any("fixlow1734.up" in line for line in result["contracts"]["raes-package-layers"][1])
    assert result["contracts"]["raes-sibling-cycles"][0] == "unmatched-ignores"


def test_the_committed_baselines_match_the_repository_through_the_real_analyzers() -> None:
    completed = _tooling_python("-c", _RATCHET, str(REPO_ROOT))

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_the_git_base_reader_reads_the_base_revision_and_detects_package_changes(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "config", "user.name", "Tests")
    _write(tmp_path, {"pkgs/alpha/__init__.py": "", "tools/policy/structural_baseline.json": "{}\n"})
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = GitBaseRevision(tmp_path, "HEAD")

    assert base.read("tools/policy/structural_baseline.json") == "{}\n"
    assert base.read("tools/policy/import_contracts.toml") is None
    assert not base.sources_changed(["pkgs"])

    (tmp_path / "pkgs" / "alpha" / "new.py").write_text("", encoding="utf-8")
    assert base.sources_changed(["pkgs"])
    (tmp_path / "pkgs" / "alpha" / "new.py").unlink()
    (tmp_path / "pkgs" / "alpha" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    assert base.sources_changed(["pkgs"])

    missing_revision = GitBaseRevision(tmp_path, "no-such-revision")
    with pytest.raises(OperationalError, match="not a commit"):
        missing_revision.read("tools/policy/structural_baseline.json")
