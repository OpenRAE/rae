"""The Go reference recorders reproduce their committed references from the Python reference."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# Each recorder re-evaluates the cases of its committed Go reference with the
# Python reference and fails its check when one recorded result differs.
RECORDERS = (
    "parity_capability_authority",
    "parity_compiled_resources",
    "parity_concern_registry",
    "parity_contract_seals",
    "parity_experiment_factories",
    "parity_experiment_projections",
    "parity_full_admission",
    "parity_governance_references",
    "parity_model_references",
    "parity_realization_references",
    "parity_runtime_experiment",
    "parity_safe_state",
    "parity_sdl_comparison",
    "parity_sdl_union_labels",
    "parity_stub_manifest",
    "parity_trial_compiler",
    "parity_trial_references",
)


@pytest.mark.parametrize("name", RECORDERS)
def test_recorder_reproduces_its_committed_reference(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    recorder = importlib.import_module(f"tools.{name}")
    if name == "parity_stub_manifest":
        # The recorder pins the reference backend version; restore it after the check.
        monkeypatch.setattr(
            recorder.stub_manifest, "_current_backend_version", recorder.stub_manifest._current_backend_version
        )
    monkeypatch.setattr(sys, "argv", [name, "--check"])
    assert recorder.main() == 0


def test_recorder_check_fails_when_a_recorded_result_differs(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    recorder = importlib.import_module("tools.parity_realization_references")
    real = recorder.evaluate

    def changed(case, inputs):
        result = real(case, inputs)
        return None if result is None else ([{"code": "changed"}], result[1])

    monkeypatch.setattr(recorder, "evaluate", changed)
    monkeypatch.setattr(recorder, "patch_cases", lambda *_args: pytest.fail("a check must not write"))
    assert recorder.record(check=True) is True
    assert "differs" in capsys.readouterr().err
