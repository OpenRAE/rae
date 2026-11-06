"""The machine check runs offline from the current sources (issue #1929)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from raes_contracts.errors import EvidenceIntegrityError, OperationalError

ROOT = Path(__file__).resolve().parents[3]


def test_nox_verification_is_offline_without_environment_synchronization():
    from tools.nox_support.machine_check_lane import run_machine_check

    calls = []
    session = SimpleNamespace(run=lambda *args, **kwargs: calls.append((args, kwargs)))
    reporter = SimpleNamespace(run=lambda name, action: action())
    run_machine_check(session, reporter)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert "--offline" in args
    assert "--no-sync" in args
    assert args[-2:] == ("implementations.formal.participant_crossing.machine_check", "check")
    assert kwargs["env"]["PYTHONPATH"] == "implementations/python/packages:."


def test_missing_tooling_environment_cannot_trigger_dependency_acquisition(monkeypatch, tmp_path):
    from tools import mcrl2_tool, tooling_policy_gate

    validator = tmp_path / "tools/check_tooling_artifact_policy.py"
    validator.parent.mkdir()
    validator.write_text("# Must never execute without the installed tooling environment.\n")
    monkeypatch.setattr(tooling_policy_gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(tooling_policy_gate.shutil, "which", lambda name: pytest.fail("acquisition fallback reached"))
    with pytest.raises(tooling_policy_gate.ArtifactPolicyError, match="unavailable"):
        mcrl2_tool.selection()


@pytest.mark.parametrize(
    "dependency",
    [
        "tools/check_tooling_artifact_policy.py",
        "tools/tooling_artifact_selection.py",
        "tools/tooling_artifact_policy_common.py",
        "implementations/tooling/schemas/profiles.schema.json",
        "implementations/tooling/schemas/admission-policy.schema.json",
    ],
)
def test_existing_proof_declares_its_validation_dependencies(dependency):
    from tools import check_participant_opacity_proof as proof

    manifest = proof.load_proof_manifest()
    proof.validate_proof_manifest(manifest, repo_root=ROOT, run_prover=False)
    assert dependency in [item["path"] for item in manifest["toolchain"]["tool_sources"]]
