"""Reference evidence follows the pinned Python tree when history changes."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest


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
