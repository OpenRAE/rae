"""Routine CI verifies current behavior without republishing research captures."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_required_lane_runs_current_finite_checks_without_historical_publication():
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    job = workflow["jobs"]["model-check"]
    steps = [step for step in job["steps"] if "-s participant-crossing-machine-check" in step.get("run", "")]
    assert len(steps) == 1
    replay = steps[0]
    assert "if" not in replay
    assert "continue-on-error" not in replay
    assert "--offline --no-sync" in replay["run"]
    assert "--publish" not in replay["run"]
    assert not any("participant_crossing.reproduction" in step.get("run", "") for step in job["steps"])
