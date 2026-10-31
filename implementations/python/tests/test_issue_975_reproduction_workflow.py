"""The required canonical model-check lane also runs the isolated reproducer."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_required_lane_demands_a_pinned_qualified_reproduction():
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    job = workflow["jobs"]["model-check"]
    steps = [step for step in job["steps"] if "participant_crossing.reproduction " in step.get("run", "")]
    assert len(steps) == 1
    replay = steps[0]
    assert "if" not in replay
    assert "continue-on-error" not in replay
    assert "--offline --no-sync" in replay["run"]
    assert "--qualified" in replay["run"]
    pin = json.loads((ROOT / "specs/formal/participant-semantics/machine-check/pin.json").read_text())
    assert f"--expected-manifest {pin['manifest_digest']}" in " ".join(replay["run"].split())
    assert replay["env"]["RAES_MACHINE_CHECK_SOURCE_SHA"] == "${{ inputs.ref }}"
    uploads = [step for step in job["steps"] if "actions/upload-artifact@" in step.get("uses", "")]
    paths = "\n".join(step["with"]["path"] for step in uploads)
    assert ".cache/raes-sdl/crossing-reproduction-publication/measurement.json" in paths
    assert ".cache/raes-sdl/crossing-reproduction-publication/execution.json" in paths
