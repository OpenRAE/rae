"""Frozen SDL records guard the Go port against reference-recorder drift."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def recorders(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    return {
        name: importlib.import_module("tools.parity_" + name)
        for name in (
            "authoring_layout",
            "authoring_vectors",
            "format_bytes",
            "sdl_constructors",
            "sdl_field_patterns",
            "sdl_field_rules",
            "source_vectors",
        )
    }


@pytest.mark.parametrize(
    ("module", "relative"),
    [
        ("authoring_layout", "internal/sdl/authoring/layout.json"),
        ("sdl_field_rules", "contract/admission/sdl-field-rules.json"),
        ("sdl_field_patterns", "contract/validation/sdl-field-patterns.json"),
        ("sdl_constructors", "contract/admission/testdata/sdl-constructors.json"),
        ("source_vectors", "internal/sdl/source/testdata/reference.json"),
    ],
)
def test_recorder_matches_frozen_reference(
    recorders: dict[str, Any], module: str, relative: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    expected = (ROOT / "implementations/go" / relative).read_bytes()
    recorder = recorders[module]
    if module == "sdl_constructors":
        actual = recorder.record(json.loads(expected)).encode()
    elif module == "sdl_field_patterns":
        actual = (json.dumps(recorder.records(), indent=2, sort_keys=True) + "\n").encode()
    elif module == "source_vectors":
        actual = (json.dumps(recorder.record(), indent=2, ensure_ascii=True) + "\n").encode()
    else:
        actual = recorder.record()
        if isinstance(actual, str):
            actual = actual.encode()
    assert actual == expected


def test_reference_identity_and_case_names_are_required(
    recorders: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    constructors = recorders["sdl_constructors"]
    reference = json.loads((ROOT / "implementations/go/contract/admission/testdata/sdl-constructors.json").read_text())
    with pytest.raises(ValueError, match="case names must be unique"):
        constructors.record({"reference": reference["reference"], "cases": [reference["cases"][0]] * 2})
    monkeypatch.setattr(constructors.subprocess, "check_output", lambda *args, **kwargs: "wrong-reference\n")
    with pytest.raises(ValueError, match="reference commit differs"):
        constructors.record(reference)
    with pytest.raises(ValueError, match="reference commit differs"):
        recorders["sdl_field_patterns"].records()


@pytest.mark.parametrize("facts", [[], [{"path": ["items"], "pattern": ".*"}], [{"path": []}, {"path": []}]])
def test_combined_patterns_require_one_direct_field(recorders: dict[str, Any], facts: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError, match="changed shape"):
        recorders["sdl_field_patterns"].combined_pattern(facts, {"type": "string"})


def _nonblank(value):
    if not value.strip():
        raise ValueError("blank")
    return value


def _nullable_nonblank(value):
    if value is not None and not value.strip():
        raise ValueError("blank")
    return value


def _list_nonblank(values):
    for value in values:
        if not value.strip():
            raise ValueError("blank")
    return values


def _unique_nonblank(values):
    for value in values:
        if not value.strip():
            raise ValueError("blank")
    if len(values) != len(set(values)):
        raise ValueError("duplicate")
    return values


def _changes_value(value):
    if not value.strip():
        raise ValueError("blank")
    return value.strip()


@pytest.mark.parametrize(
    ("function", "operation"),
    [
        (_nonblank, "nonblank"),
        (_nullable_nonblank, "nullable-nonblank"),
        (_list_nonblank, "list-nonblank"),
        (_unique_nonblank, "unique-nonblank"),
        (_changes_value, None),
    ],
)
def test_predicate_recorder_accepts_only_audited_shapes(
    recorders: dict[str, Any], function, operation: str | None
) -> None:
    assert recorders["sdl_field_rules"].direct_rule(function) == operation


@pytest.mark.parametrize("name", ["../escape.yaml", "/absolute.yaml", "nested/../../escape.yaml"])
def test_import_recorder_refuses_unsafe_file_and_link_names(
    recorders: dict[str, Any], name: str, tmp_path: Path
) -> None:
    recorder = recorders["authoring_vectors"]
    for row in ({"files": {name: "name: test\n"}}, {"files": {}, "links": {name: "safe.yaml"}}):
        with pytest.raises(ValueError, match="unsafe reference file name"):
            recorder.write_import_files(row, str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_import_recorder_preserves_rooted_links(recorders: dict[str, Any], tmp_path: Path) -> None:
    recorder = recorders["authoring_vectors"]
    row = {
        "files": {"nested/main.yaml": "path: $ROOT/input.yaml\n"},
        "links": {"alias.yaml": "$ROOT/nested/main.yaml"},
        "rooted": True,
    }
    recorder.write_import_files(row, str(tmp_path))
    assert (tmp_path / "alias.yaml").read_text() == f"path: {tmp_path}/input.yaml\n"


@pytest.mark.parametrize("name", ["../escape.yaml", "/absolute.yaml", "nested\\escape.yaml"])
def test_corpus_recorder_confines_input_paths(recorders: dict[str, Any], name: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe corpus file name"):
        recorders["format_bytes"].write_case_files({"files": {name: "sha256:unused"}}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_selected_formatter_bytes_and_verdicts(recorders: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = recorders["format_bytes"]
    from tools.parity_storage import read_document

    wanted = {"examples/scenarios/minimal.sdl.yaml", "examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml"}
    cases = [
        read_document(recorder.CORPUS, path.relative_to(recorder.CORPUS))
        for path in (recorder.CORPUS / "cases/cli/sdl-format").glob("*.json")
    ]
    # Select a valid independent corpus input, preserving its exact stored command verdict.
    case = next(row for row in cases if row["name"] in wanted and row["result"]["exit_code"] == 0)
    recorded = recorder.record(case)
    assert recorded["accepted"] is True
    assert recorded["content"].startswith("name:")
    wrong = {**case, "result": {**case["result"], "exit_code": 2}}
    with pytest.raises(ValueError, match="reference formatter verdict changed"):
        recorder.record(wrong)
    monkeypatch.setattr(recorder, "read_blob", lambda *_args: b"name: [\n")
    refused = recorder.record({**case, "result": {"exit_code": 2}})
    assert refused == {"name": case["name"], "accepted": False, "error": "SDLParseError"}
