"""ASR-535 regression guard for the canonical proof sandbox setup."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_canonical_workflow_installs_the_offline_proof_runtime() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "canonical-verification.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["proof"]["steps"]
    proof_runtime = next(step["run"] for step in steps if step.get("name") == "Install proof sandbox")

    assert "command -v bwrap" in proof_runtime
    assert "command -v fc-list" in proof_runtime
    assert "bubblewrap fontconfig fonts-dejavu-core" in proof_runtime
    assert "test -d /etc/fonts" in proof_runtime
    assert "test -d /usr/share/fonts" in proof_runtime
    assert "test -n" in proof_runtime
    assert "fc-list --format=" in proof_runtime
