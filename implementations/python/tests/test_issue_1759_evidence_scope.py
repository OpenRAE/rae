"""Routine verification checks behavior without requiring new research captures."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from raes_contracts.errors import EvidenceIntegrityError


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


def test_finite_verification_checks_current_decision_without_retained_publication(monkeypatch):
    from implementations.formal.participant_crossing import machine_check as machine

    monkeypatch.setattr(machine, "load_retained", lambda _: pytest.fail("saved publication required"))
    monkeypatch.setattr(machine, "build_bundle", lambda _: {"result.json": b'{"equivalent":true}'})
    machine.verify(Path("."))
    monkeypatch.setattr(machine, "build_bundle", lambda _: {"result.json": b'{"equivalent":false}'})
    with pytest.raises(EvidenceIntegrityError):
        machine.verify(Path("."))


def test_nox_runs_current_finite_verification():
    from tools.nox_support.machine_check_lane import run_machine_check

    calls = []
    run_machine_check(
        SimpleNamespace(run=lambda *args, **kwargs: calls.append(args)),
        SimpleNamespace(run=lambda name, action: action()),
    )
    assert calls[0][-1] == "verify"
