"""Reference evidence follows the pinned Python tree when history changes."""

from __future__ import annotations

import gzip
import importlib
import json
import subprocess
from pathlib import Path

import pytest


def test_module_policy_vectors_match_the_pinned_reference(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "tools"))
    recorder = importlib.import_module("tools.parity_module_policy_vectors")
    expected = json.loads((root / "implementations/go/sdl/module/testdata/policy-versions.json").read_text())
    assert recorder.record() == expected


def test_shared_rule_vectors_match_the_constructed_reference(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "tools"))
    recorder = importlib.import_module("tools.parity_shared_rule_vectors")
    path = root / "implementations/go/internal/contract/sdlrules/testdata/constructed-reference.json.gz"
    assert recorder.record() == json.loads(gzip.decompress(path.read_bytes()))


@pytest.mark.parametrize("name", ["sdl_constructors", "sdl_field_patterns"])
def test_reference_recording_keeps_exact_tree_identity_after_history_change(monkeypatch, name):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "tools"))
    recorder = importlib.import_module("tools.parity_" + name)
    document = json.loads((root / "implementations/go/contract/admission/testdata/sdl-constructors.json").read_text())
    reference = document["reference"]

    def record():
        return recorder.record(document) if name == "sdl_constructors" else recorder.records()

    monkeypatch.setattr(subprocess, "check_output", lambda *_args, **_kwargs: reference + "\n")
    expected = record()
    monkeypatch.setattr(subprocess, "check_output", lambda *_args, **_kwargs: "a" * 40 + "\n")

    def unchanged(arguments, *, cwd, **_kwargs):
        assert arguments == ["git", "diff", "--quiet", reference, "--", "implementations/python/packages/raes"]
        assert cwd == root
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(subprocess, "run", unchanged)
    assert record() == expected
    monkeypatch.setattr(subprocess, "run", lambda arguments, **_kwargs: subprocess.CompletedProcess(arguments, 1))
    with pytest.raises(ValueError, match="reference commit differs"):
        record()
