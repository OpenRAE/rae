"""The canonical gate must include isolated counterexample replay failures."""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("result,expected", [("success", 0), ("failure", 1), ("cancelled", 1), ("skipped", 1)])
def test_canonical_gate_requires_model_check(tmp_path: Path, result: str, expected: int) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    gate = workflow["jobs"]["gate"]
    assert "model-check" in gate["needs"]
    step = gate["steps"][0]
    environment = {key: "success" for key in step["env"]}
    environment.update(PATH="/usr/bin", GITHUB_OUTPUT=str(tmp_path / "output"), MODEL_CHECK_RESULT=result)
    completed = subprocess.run(
        ["/bin/bash", "-c", step["run"]], env=environment, capture_output=True, check=False, timeout=5
    )
    assert completed.returncode == expected


def test_model_check_has_distinct_host_and_exact_replay() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    job = workflow["jobs"]["model-check"]
    assert job["runs-on"] == "ubuntu-26.04"
    assert job["needs"] == "generic-tool-local-inputs"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "tools.mcrl2_tool acquire" in commands
    assert "--local-input" in commands
    assert "nox -f noxfile.py -s participant-crossing-machine-check -- --publish" in commands
    assert "--offline --no-sync" in commands
    assert "sysctl" not in commands
    assert "apparmor_parser" not in commands
