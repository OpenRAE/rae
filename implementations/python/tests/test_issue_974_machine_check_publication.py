"""Only complete admitted results reach the canonical hosted artifact path."""

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
    assert args[-2:] == ("implementations.formal.participant_crossing.machine_check", "replay")
    assert kwargs["env"]["PYTHONPATH"] == "implementations/python/packages:."


def test_nox_publication_uses_the_same_guarded_offline_entrypoint():
    from tools.nox_support.machine_check_lane import run_machine_check

    calls = []
    session = SimpleNamespace(run=lambda *args, **kwargs: calls.append(args))
    reporter = SimpleNamespace(run=lambda name, action: action())
    run_machine_check(session, reporter, publish=True)
    assert calls[0][-1] == "implementations.formal.participant_crossing.machine_check_publication"
    assert "--offline" in calls[0]
    assert "--no-sync" in calls[0]


def test_publication_refuses_missing_source_and_runner_identity(monkeypatch):
    from implementations.formal.participant_crossing.machine_check_publication import execution_record

    for name in ("RAES_MACHINE_CHECK_SOURCE_SHA", "ImageOS", "ImageVersion", "RUNNER_ARCH"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises((OperationalError, EvidenceIntegrityError)):
        execution_record(ROOT, "sha256:" + "0" * 64)


def test_invalid_evidence_is_never_staged_for_upload(monkeypatch, tmp_path):
    from implementations.formal.participant_crossing import machine_check_publication as publication

    monkeypatch.setattr(publication.machine, "load_retained", lambda root: ({}, "sha256:" + "0" * 64))
    monkeypatch.setattr(publication, "publish_bundle", lambda *args: pytest.fail("unadmitted artifact staged"))
    with pytest.raises(EvidenceIntegrityError):
        publication.publish(tmp_path)


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
def test_existing_proof_also_refuses_validation_dependency_drift(monkeypatch, dependency):
    from tools import check_participant_opacity_proof as proof

    manifest = proof.load_proof_manifest()
    proof.validate_proof_manifest(manifest, repo_root=ROOT, run_prover=False)
    original = proof._file_digest
    monkeypatch.setattr(
        proof, "_file_digest", lambda path: "sha256:" + "0" * 64 if path == ROOT / dependency else original(path)
    )
    with pytest.raises(proof.ProofEvidenceError, match="source digest"):
        proof._validate_tool_sources(manifest["toolchain"], ROOT)


@pytest.mark.parametrize("native", ["bubblewrap\t0.11.0\n", "bubblewrap\tunsafe/path\n", ""])
def test_execution_record_uses_only_verified_allowlisted_host_fields(monkeypatch, native):
    from implementations.formal.participant_crossing import machine_check_publication as publication

    sha = "1" * 40
    monkeypatch.setenv("RAES_MACHINE_CHECK_SOURCE_SHA", sha)
    monkeypatch.setenv("SYNTHETIC_PRIVATE_VALUE", "must-not-appear")
    monkeypatch.setattr(publication, "probe", lambda argv: sha + "\n" if "rev-parse" in argv else native)
    monkeypatch.setattr(
        publication,
        "load_tooling_host_profile_selection_with_current_interpreter",
        lambda profile: {"host_profile": {"host_prerequisite_package_ids": ["bubblewrap"]}},
    )
    monkeypatch.setattr(
        publication, "observe_host_identity", lambda host: ("runner:exact", "repository:exact", [{"outcome": "passed"}])
    )
    if native != "bubblewrap\t0.11.0\n":
        with pytest.raises((EvidenceIntegrityError, OperationalError)):
            publication.execution_record(ROOT, "sha256:" + "0" * 64)
    else:
        record = publication.execution_record(ROOT, "sha256:" + "0" * 64)
        assert record["source_revision"] == sha
        assert record["native_packages"] == {"bubblewrap": "0.11.0"}
        assert "must-not-appear" not in str(record)
        assert record["python_lock_digest"].startswith("sha256:")
