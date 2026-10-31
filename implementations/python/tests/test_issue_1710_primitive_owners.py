"""Each shared primitive has one owner module in the packages (issue #1710, ADR-118).

The scan reads every package source file. A finding outside the owner module
means a local copy came back. ``tools/`` and ``implementations/formal/`` are out
of this scope until their own refactor chunk.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

PACKAGES = Path(__file__).resolve().parents[1] / "packages"
OWNERS = {
    "wall-clock read": "raes_contracts/timestamps.py",
    "SHA-256 construction": "raes_contracts/digests.py",
    "JSON Pointer token escape": "raes_contracts/json_pointer.py",
    "sorted compact json.dumps": "raes_contracts/json_serialization.py",
    "RFC 8785 serialization": "raes_contracts/_canonical.py",
}


def _attribute_call(node: ast.AST, owner: str, name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == owner
    )


def _replace_pair(node: ast.AST) -> tuple[str, str] | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "replace"
        and len(node.args) == 2
        and all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args)
    ):
        return node.args[0].value, node.args[1].value
    return None


def _wall_clock_read(node: ast.AST) -> bool:
    return _attribute_call(node, "datetime", "now") or _attribute_call(node, "datetime", "utcnow")


def _sha256_construction(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "sha256" and isinstance(node.value, ast.Name):
        return node.value.id == "hashlib"
    if isinstance(node, ast.ImportFrom) and node.module == "hashlib":
        return any(alias.name == "sha256" for alias in node.names)
    if _attribute_call(node, "hashlib", "new") and node.args:
        first = node.args[0]
        return isinstance(first, ast.Constant) and str(first.value).lower() == "sha256"
    return False


def _pointer_escape(node: ast.AST) -> bool:
    outer = _replace_pair(node)
    if outer is None:
        return False
    inner = _replace_pair(node.func.value)
    return (inner, outer) in {((("~", "~0")), ("/", "~1")), (("~1", "/"), ("~0", "~"))}


def _sorted_compact_dumps(node: ast.AST) -> bool:
    if not _attribute_call(node, "json", "dumps"):
        return False
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in node.keywords}
    return keywords.get("sort_keys") == "True" and keywords.get("separators") in {"(',', ':')", '(",", ":")'}


def _rfc8785_serialization(node: ast.AST) -> bool:
    return _attribute_call(node, "rfc8785", "dumps")


CHECKS: dict[str, Callable[[ast.AST], bool]] = {
    "wall-clock read": _wall_clock_read,
    "SHA-256 construction": _sha256_construction,
    "JSON Pointer token escape": _pointer_escape,
    "sorted compact json.dumps": _sorted_compact_dumps,
    "RFC 8785 serialization": _rfc8785_serialization,
}


def _findings(primitive: str) -> Iterator[str]:
    check = CHECKS[primitive]
    for path in sorted(PACKAGES.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if check(node):
                yield f"{path.relative_to(PACKAGES).as_posix()}:{node.lineno}"


@pytest.mark.parametrize("primitive", sorted(CHECKS))
def test_each_primitive_appears_only_in_its_owner_module(primitive):
    owner = OWNERS[primitive]
    findings = list(_findings(primitive))
    assert any(finding.startswith(f"{owner}:") for finding in findings), f"the scan no longer finds {owner}"
    copies = [finding for finding in findings if not finding.startswith(f"{owner}:")]
    assert copies == [], f"{primitive} outside {owner}: {copies}"


@pytest.mark.parametrize(
    ("source", "primitive"),
    [
        ("from datetime import UTC, datetime\nnow = datetime.now(UTC)\n", "wall-clock read"),
        ("import hashlib\ndigest = hashlib.sha256(b'').hexdigest()\n", "SHA-256 construction"),
        ("from hashlib import sha256\n", "SHA-256 construction"),
        ("import hashlib\ndigest = hashlib.new('SHA256')\n", "SHA-256 construction"),
        ("token = value.replace('~', '~0').replace('/', '~1')\n", "JSON Pointer token escape"),
        ('token = value.replace("~1", "/").replace("~0", "~")\n', "JSON Pointer token escape"),
        ('import json\ntext = json.dumps(value, sort_keys=True, separators=(",", ":"))\n', "sorted compact json.dumps"),
        ("import rfc8785\ndata = rfc8785.dumps(value)\n", "RFC 8785 serialization"),
    ],
)
def test_each_check_recognizes_a_local_copy(source, primitive):
    tree = ast.parse(source)
    assert any(CHECKS[primitive](node) for node in ast.walk(tree))


@pytest.mark.parametrize(
    "source",
    [
        "import hashlib\ndigest = hashlib.new(algorithm)\n",
        "deadline = workflow.now()\n",
        "import json\ntext = json.dumps(value, indent=2, sort_keys=True)\n",
        "token = value.replace('~', '-')\n",
    ],
)
def test_checks_ignore_other_uses(source):
    tree = ast.parse(source)
    assert not any(check(node) for check in CHECKS.values() for node in ast.walk(tree))
