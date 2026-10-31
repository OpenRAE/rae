"""Routine verification checks behavior without requiring new research captures."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_recorded_selection_does_not_hash_current_source(tmp_path, monkeypatch):
    from tools import research_evidence as evidence

    monkeypatch.setattr(evidence, "implementation_digest", lambda _: pytest.fail("whole-source refresh required"))
    records = []
    for name, date in [("older", "2026-01-01T00:00:00+00:00"), ("newer", "2026-01-02T00:00:00+00:00")]:
        (tmp_path / f"{name}.json").write_text(json.dumps({"captured_at": date}))
        records.append(
            (name, {"revision": "capture-" + ("a" if name == "older" else "b") * 64, "snapshot_path": f"{name}.json"})
        )
    assert evidence.latest_recorded_release_path(records, tmp_path) == "newer"


def test_ordinary_application_edit_keeps_model_records_admissible(monkeypatch):
    from implementations.formal.participant_crossing import machine_check as machine
    from test_issue_976_evidence_identity import checkout_with_changed

    checkout_with_changed(
        monkeypatch, "implementations/python/packages/raes_contracts/realization_structure/_evaluation.py"
    )
    machine.admit_bundle(
        Path(__file__).resolve().parents[3], *machine.load_retained(Path(__file__).resolve().parents[3])
    )


def test_nox_runs_current_finite_verification():
    from tools.nox_support.machine_check_lane import run_machine_check

    calls = []
    run_machine_check(
        SimpleNamespace(run=lambda *args, **kwargs: calls.append(args)),
        SimpleNamespace(run=lambda name, action: action()),
    )
    assert calls[0][-1] == "replay"
