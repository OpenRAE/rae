"""Runtime reference recorders preserve verdicts, provenance and input ownership."""

from __future__ import annotations

import ast
import copy
import importlib
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
from raes.runtime_capabilities import RuntimeProcessIdentity

ROOT = Path(__file__).resolve().parents[3]
POINTER = "#/$defs/RuntimeProcessIdentity"


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[ModuleType, Path]:
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    module = importlib.import_module("tools.parity_sdl_constructors")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "reference_revision", lambda: "a" * 40)
    monkeypatch.setattr(module, "reference_definitions", lambda _model: {POINTER: RuntimeProcessIdentity})
    directory = tmp_path / "implementations/go/contract/admission/testdata"
    directory.mkdir(parents=True)
    manifest = {
        "reference": "a" * 40,
        "models": {POINTER: RuntimeProcessIdentity.__module__ + "." + RuntimeProcessIdentity.__name__},
        "baselines": {POINTER: {"name": "worker"}},
        "case_files": ["runtime-constructors-000.json"],
        "case_count": 3,
    }
    document = {
        "reference": "a" * 40,
        "cases": [
            {"name": "default-selector", "pointer": POINTER, "accepted": True},
            {"name": "explicit-selector", "pointer": POINTER, "accepted": True, "data": {"pid": 2}},
            {
                "name": "invalid-pid",
                "pointer": POINTER,
                "accepted": False,
                "changes": [{"path": ["pid"], "value": 0}],
            },
        ],
    }
    (directory / "runtime-constructors.json").write_text(json.dumps(manifest))
    (directory / manifest["case_files"][0]).write_text(module.runtime_constructor_shard(document))
    return module, directory


def test_runtime_constructor_check_is_read_only_and_write_repairs_verdict(recorder) -> None:
    module, directory = recorder
    path = directory / "runtime-constructors-000.json"
    original = path.read_bytes()
    assert module.record_runtime_constructors(True) == 0
    document = json.loads(original)
    document["cases"][-1]["accepted"] = True
    path.write_text(module.runtime_constructor_shard(document))
    incorrect = path.read_bytes()
    assert module.record_runtime_constructors(True) == 1
    assert path.read_bytes() == incorrect
    assert module.record_runtime_constructors(False) == 0
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("models", {}, "model inventory differs"),
        ("case_count", 4, "incomplete runtime constructor cases"),
        ("case_files", ["../escape.json"], "unsafe runtime constructor shard path"),
        ("case_files", ["runtime-constructors-001.json"], "unsafe runtime constructor shard path"),
    ],
)
def test_runtime_constructor_manifest_integrity(recorder, field, value, message: str) -> None:
    module, directory = recorder
    path = directory / "runtime-constructors.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=message):
        module.record_runtime_constructors(True)


def test_runtime_constructor_requires_a_positive_case_for_every_model(recorder) -> None:
    module, directory = recorder
    path = directory / "runtime-constructors-000.json"
    document = json.loads(path.read_text())
    for case in document["cases"]:
        case["data"] = {"pid": 0}
        case["accepted"] = False
    path.write_text(module.runtime_constructor_shard(document))
    with pytest.raises(ValueError, match="incomplete runtime constructor cases"):
        module.record_runtime_constructors(True)


def test_runtime_constructor_rejects_mixed_revisions(recorder) -> None:
    module, directory = recorder
    path = directory / "runtime-constructors-000.json"
    document = json.loads(path.read_text())
    document["reference"] = "different"
    path.write_text(module.runtime_constructor_shard(document))
    with pytest.raises(ValueError, match="inconsistent runtime constructor reference"):
        module.record_runtime_constructors(True)


@pytest.mark.parametrize("path", [[], ["subject", "pid"]])
def test_runtime_constructor_changes_cannot_walk_nested_paths(recorder, path) -> None:
    module, directory = recorder
    file = directory / "runtime-constructors-000.json"
    document = json.loads(file.read_text())
    document["cases"][-1]["changes"][0]["path"] = path
    file.write_text(module.runtime_constructor_shard(document))
    with pytest.raises(ValueError, match="changes must name one field"):
        module.record_runtime_constructors(True)


def test_runtime_constructor_expansion_owns_nested_inputs(recorder) -> None:
    module, _ = recorder
    baselines = {POINTER: {"command": ["run"]}}
    document = {"cases": [{"pointer": POINTER}, {"pointer": POINTER}]}
    original = copy.deepcopy(document)
    expanded = module.expand_runtime_constructors(document, baselines)
    expanded["cases"][0]["data"]["command"].append("changed")
    assert document == original
    assert baselines[POINTER]["command"] == ["run"]
    assert expanded["cases"][1]["data"]["command"] == ["run"]


@pytest.fixture
def helper_files(recorder, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, list[Path]]:
    module, _ = recorder
    relative = [
        "implementations/go/internal/contract/sdlrules/testdata/runtime-inventory.json",
        "implementations/go/contract/admission/testdata/runtime-process-limits.json",
    ]
    paths = []
    for name in relative:
        path = module.ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
        paths.append(path)
    reference = json.loads(paths[0].read_text())["reference"]
    monkeypatch.setattr(module, "reference_revision", lambda: reference)
    return module, paths


def test_runtime_helpers_check_both_files_without_overwriting(helper_files, capsys) -> None:
    module, paths = helper_files
    originals = [path.read_bytes() for path in paths]
    assert module.record_runtime_helpers(True) == 0
    inventory = json.loads(originals[0])
    inventory["Lookups"][0]["Identity"] = "incorrect"
    paths[0].write_text(json.dumps(inventory))
    limits = json.loads(originals[1])
    limits["Cases"][0]["Digest"] = "incorrect"
    paths[1].write_text(json.dumps(limits))
    incorrect = [path.read_bytes() for path in paths]
    assert module.record_runtime_helpers(True) == 1
    assert [path.read_bytes() for path in paths] == incorrect
    assert capsys.readouterr().err.count("runtime helper results differ") == 2
    assert module.record_runtime_helpers(False) == 0
    assert [path.read_bytes() for path in paths] == originals


@pytest.mark.parametrize("index", [0, 1])
def test_runtime_helpers_refuse_mixed_revisions(helper_files, index: int) -> None:
    module, paths = helper_files
    document = json.loads(paths[index].read_text())
    document["reference"] = "different"
    paths[index].write_text(json.dumps(document))
    with pytest.raises(ValueError, match="runtime helper reference commit differs"):
        module.record_runtime_helpers(True)


@pytest.mark.parametrize(
    ("flag", "target"),
    [("--runtime-helpers", "record_runtime_helpers"), ("--runtime-constructors", "record_runtime_constructors")],
)
def test_runtime_command_dispatch_preserves_check_mode(recorder, monkeypatch, flag: str, target: str) -> None:
    module, _ = recorder
    calls = []
    monkeypatch.setattr(module, target, lambda check: calls.append(check) or 1)
    monkeypatch.setattr(sys, "argv", ["recorder", flag, "--check"])
    assert module.main() == 1
    assert calls == [True]


def test_default_command_dispatch_retains_constructor_recording(recorder, monkeypatch) -> None:
    module, directory = recorder
    shard = json.loads((directory / "runtime-constructors-000.json").read_text())
    manifest = json.loads((directory / "runtime-constructors.json").read_text())
    document = module.expand_runtime_constructors(shard, manifest["baselines"])
    path = directory / "sdl-constructors.json"
    path.write_text(module.record(document))
    monkeypatch.setattr(sys, "argv", ["recorder", "--check"])
    assert module.main() == 0


@pytest.mark.parametrize(
    ("guard", "operation"),
    [
        ("if not value: return value", "optional-nonblank"),
        ("if not value: return other", None),
        ("if value: return value", None),
        ("if not value: return value\nelse: return value", None),
    ],
)
def test_optional_predicates_require_the_exact_argument_guard(recorder, guard: str, operation: str | None) -> None:
    rules = importlib.import_module("tools.parity_sdl_field_rules")
    source = "def validate(value):\n" + "\n".join("    " + line for line in guard.splitlines())
    source += "\n    return helper(value)\n"
    declaration = ast.parse(source).body[0]
    assert rules.declaration_rule(declaration, {"helper": rules.require_non_empty}) == operation
