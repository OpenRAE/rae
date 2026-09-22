"""Focused checks of native workflows, without a second workflow inventory."""

import re
import shlex
import sys
import tomllib
from fnmatch import fnmatch
from pathlib import Path

import pytest
import yaml
from tools.tooling_artifact_policy_actions import action_failures


def _check(tmp_path: Path, workflow: dict) -> set[str]:
    path = ".github/workflows/test.yml"
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    return {failure.rule_id for failure in action_failures(tmp_path, {}, [path])}


@pytest.fixture
def workflow() -> dict:
    return {
        "on": {"pull_request": {}},
        "permissions": {"contents": "read"},
        "jobs": {
            "test": {
                "runs-on": "ubuntu-24.04",
                "steps": [
                    {"uses": "actions/checkout@" + "a" * 40, "with": {"persist-credentials": False}},
                    {"run": "python -m pytest"},
                ],
            }
        },
    }


def test_pinned_workflow_needs_no_parallel_policy_inventory(tmp_path: Path, workflow: dict) -> None:
    assert _check(tmp_path, workflow) == set()


@pytest.mark.parametrize("uses", ["actions/checkout@v7", "actions/checkout@main", "docker://alpine:latest"])
def test_mutable_executable_is_rejected(tmp_path: Path, workflow: dict, uses: str) -> None:
    workflow["jobs"]["test"]["steps"][0]["uses"] = uses
    assert "tooling-action-pin" in _check(tmp_path, workflow)


@pytest.mark.parametrize("permissions", ["write-all", {"contents": "write"}, {"id-token": "write"}])
def test_pull_request_cannot_acquire_publishing_permissions(tmp_path: Path, workflow: dict, permissions) -> None:
    workflow["jobs"]["test"]["permissions"] = permissions
    assert "tooling-action-permissions" in _check(tmp_path, workflow)


def _finalization_workflow() -> dict:
    root = Path(__file__).resolve().parents[3]
    return yaml.safe_load((root / ".github/workflows/ground-control-phase-e.yml").read_text())


def test_merged_issue_finalization_has_a_valid_credential_boundary(tmp_path: Path) -> None:
    assert _check(tmp_path, _finalization_workflow()) == set()


@pytest.mark.parametrize("permission", ["contents", "pull-requests", "id-token"])
def test_merged_issue_finalization_cannot_gain_other_writes(tmp_path: Path, permission: str) -> None:
    workflow = _finalization_workflow()
    workflow["permissions"][permission] = "write"
    assert "tooling-action-permissions" in _check(tmp_path, workflow)


@pytest.mark.parametrize("guard", [None, "always()", "github.event_name == 'pull_request'"])
def test_issue_writes_require_the_exact_merged_guard(tmp_path: Path, guard: str | None) -> None:
    workflow = _finalization_workflow()
    workflow["jobs"]["finalize"]["if"] = guard
    assert "tooling-action-permissions" in _check(tmp_path, workflow)


@pytest.mark.parametrize("event", ["pull_request_target", "workflow_call", "push"])
def test_issue_finalization_cannot_add_an_unchecked_trigger(tmp_path: Path, event: str) -> None:
    workflow = _finalization_workflow()
    workflow[True][event] = {}
    assert "tooling-action-permissions" in _check(tmp_path, workflow)


def test_issue_finalization_requires_closed_pull_requests(tmp_path: Path) -> None:
    workflow = _finalization_workflow()
    workflow[True]["pull_request"]["types"] = ["opened", "closed"]
    assert "tooling-action-permissions" in _check(tmp_path, workflow)


def test_issue_finalization_does_not_allow_repository_secrets(tmp_path: Path) -> None:
    workflow = _finalization_workflow()
    workflow["jobs"]["finalize"]["env"] = {"TOKEN": "${{ secrets.TOKEN }}"}
    assert "tooling-action-credentials" in _check(tmp_path, workflow)


@pytest.mark.parametrize("secret", ["${{ secrets.TOKEN }}", "${{ secrets['TOKEN'] }}", "${{ toJSON(secrets) }}"])
def test_pull_request_secret_exposure_is_rejected(tmp_path: Path, workflow: dict, secret: str) -> None:
    workflow["jobs"]["test"]["steps"][1]["env"] = {"TOKEN": secret}
    assert "tooling-action-credentials" in _check(tmp_path, workflow)


def test_pull_request_target_cannot_use_main_ref_as_a_credential_boundary(tmp_path: Path, workflow: dict) -> None:
    workflow["on"] = {"pull_request_target": {}}
    workflow["jobs"]["test"]["if"] = "github.ref == 'refs/heads/main'"
    workflow["jobs"]["test"]["permissions"] = {"contents": "write"}
    workflow["jobs"]["test"]["env"] = {"TOKEN": "${{ secrets.TOKEN }}"}
    assert {"tooling-action-permissions", "tooling-action-credentials"} <= _check(tmp_path, workflow)


def test_sonar_boundary_does_not_admit_an_unrelated_credential(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    path = ".github/workflows/canonical-verification.yml"
    document = yaml.safe_load((root / path).read_text())
    document["jobs"]["sonar"].setdefault("env", {})["EXTRA"] = "${{ secrets.OTHER }}"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(yaml.safe_dump(document))
    failures = {item.rule_id for item in action_failures(tmp_path, {}, [path])}
    assert "tooling-action-credentials" in failures


def test_checkout_must_not_persist_credentials(tmp_path: Path, workflow: dict) -> None:
    workflow["jobs"]["test"]["steps"][0]["with"] = {}
    assert "tooling-action-credentials" in _check(tmp_path, workflow)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("implementations/python/packages/raes_runtime/control_plane.py", False),
        ("docs/explain/sdl/runtime.md", False),
        ("CHANGELOG.md", False),
        ("tools/verified_tool_installation.py", True),
        ("tools/bootstrap_profile.py", True),
        ("tools/maintained_client_acquisition.py", True),
        ("implementations/tooling/artifacts.lock.json", True),
        ("implementations/python/uv.lock", True),
        (".devcontainer/Dockerfile", True),
        (".github/workflows/bootstrap-qualification.yml", True),
    ],
)
def test_component_qualification_runs_only_for_relevant_inputs(path: str, expected: bool) -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/bootstrap-qualification.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    pull_request = triggers["pull_request"]
    matches = any(fnmatch(path, pattern) for pattern in pull_request.get("paths", ["**"]))
    assert matches is expected
    assert "workflow_dispatch" in triggers


def test_ordinary_bootstrap_does_not_build_disconnected_kits() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/bootstrap-qualification.yml").read_text())
    steps = workflow["jobs"]["generic-tool-platforms"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "offline-kit" not in commands
    assert "generic-tools" in commands
    assert "python-compatibility" in commands


def _workflow_bootstrap_invocations():
    root = Path(__file__).resolve().parents[3]
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                script = step.get("run", "").replace("\\\n", " ")
                for match in re.finditer(
                    r"(?:-m\s+tools\.bootstrap_profile|tools/bootstrap_profile\.py)\s+([^\n]+)", script
                ):
                    command = re.sub(r"\$\{\{.*?\}\}", "fixture", match[1])
                    arguments = shlex.split(command)
                    if ">" in arguments:
                        arguments = arguments[: arguments.index(">")]
                    yield pytest.param(arguments, id=f"{path.name}:{job_name}:{arguments[0]}")


@pytest.mark.parametrize("arguments", list(_workflow_bootstrap_invocations()))
def test_every_workflow_bootstrap_invocation_matches_the_live_cli(arguments, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.bootstrap_profile import _parse_args

    monkeypatch.setattr(sys, "argv", ["bootstrap_profile", *arguments])
    assert _parse_args().operation == arguments[0]


def test_proof_workflow_retains_only_the_harness_output_it_produces() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/canonical-verification.yml").read_text())
    steps = workflow["jobs"]["proof"]["steps"]
    runs = "\n".join(step.get("run", "") for step in steps)
    uploads = [step["with"]["path"] for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")]
    assert "-s participant-opacity-proof" in runs
    assert "-s proof-input-qualification -- --real-installation --output proof-input-qualification.json" in runs
    assert uploads == ["proof-input-qualification.json"]


def test_interpreter_workflow_has_no_upload_without_an_evidence_producer() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["interpreters"]["steps"]
    assert any("-s python-compatibility" in step.get("run", "") for step in steps)
    assert not any(step.get("uses", "").startswith("actions/upload-artifact@") for step in steps)


def test_acquisition_fixture_dependencies_are_optional() -> None:
    root = Path(__file__).resolve().parents[3]
    project = tomllib.loads((root / "implementations/tooling/python/pyproject.toml").read_text())
    assert not any(value.startswith("cryptography") for value in project["project"]["dependencies"])
    assert "cryptography==50.0.1" in project["dependency-groups"]["acquisition-tests"]


def test_development_container_uses_native_signed_package_sources() -> None:
    root = Path(__file__).resolve().parents[3]
    dockerfile = (root / ".devcontainer/Dockerfile").read_text()
    assert "APT::Snapshot" not in dockerfile
    assert "Check-Valid-Until" not in dockerfile
    assert "--allow-unauthenticated" not in dockerfile
    assert "apt-get update" in dockerfile
    assert "USER raes" in dockerfile


def test_release_container_lane_has_no_same_job_export_import() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/release-please.yml").read_text())
    job = workflow["jobs"]["integration-docker-release"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "oci_release_image.py export" not in commands
    assert "oci_release_image.py import" not in commands
    required = next(step for step in job["steps"] if step.get("name") == "Require real-container release integration")
    assert required["env"]["RAES_DOCKER_INTEGRATION_REQUIRED"] == "1"
    assert "RAES_OCI_SOURCE_CLASS" not in required["env"]


@pytest.mark.parametrize("mode", ["mirror", "preseeded"])
def test_retired_oci_modes_do_not_silently_enable_public_network(mode: str) -> None:
    from tools.oci_release_image import ImageAdmissionError, resolve_source

    with pytest.raises(ImageAdmissionError, match="source-class"):
        resolve_source({"RAES_OCI_SOURCE_CLASS": mode, "RAES_OCI_MIRROR_REPOSITORY": "mirror.invalid/alpine"})


@pytest.mark.parametrize("script", ["run_aws_smoke.sh", "run_aws_guest_certify.sh"])
def test_online_aws_smokes_do_not_preseed_a_complete_python_wheelhouse(script: str) -> None:
    root = Path(__file__).resolve().parents[3]
    text = (root / "tools/real-daemon" / script).read_text()
    assert "snapshot.ubuntu.com" not in text
    assert "Check-Valid-Until: no" not in text
    assert "stage/wheelhouse" not in text
    assert "--require-hashes" in text
    assert "--build-constraints" in text
    assert "--frozen" in text


def test_release_inventory_reads_only_its_native_workflow_graph(tmp_path: Path) -> None:
    from tools.release_evidence import _workflow_actions

    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "release-please.yml").write_text(
        yaml.safe_dump(
            {
                "jobs": {
                    "build": {"uses": "./.github/workflows/canonical-verification.yml"},
                    "publish": {"steps": [{"uses": "pypa/gh-action-pypi-publish@" + "a" * 40}]},
                }
            }
        )
    )
    (workflows / "canonical-verification.yml").write_text(
        yaml.safe_dump({"jobs": {"test": {"steps": [{"uses": "actions/checkout@" + "b" * 40}]}}})
    )
    (workflows / "unrelated.yml").write_text("not valid: [")
    assert _workflow_actions(tmp_path) == [
        {"action": "actions/checkout", "commit": "b" * 40},
        {"action": "pypa/gh-action-pypi-publish", "commit": "a" * 40},
    ]


@pytest.mark.parametrize("host", [False, True])
def test_selection_launcher_sanitizes_environment_and_failure(monkeypatch: pytest.MonkeyPatch, host: bool) -> None:
    from types import SimpleNamespace

    from tools import tooling_policy_gate

    monkeypatch.setenv("GITHUB_TOKEN", "fixture-credential")
    monkeypatch.setenv("PYTHONPATH", "/untrusted/override")
    observed = {}

    def run(_argv, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(returncode=1, stdout="", stderr="fixture-credential: candidate-url?token=private")

    monkeypatch.setattr(tooling_policy_gate.subprocess, "run", run)
    validator = tooling_policy_gate._validator_host_stdout if host else tooling_policy_gate._validator_stdout
    selection = (
        {"host_profile_id": "host"}
        if host
        else {"artifact_id": "tool", "version": "1", "platform_id": "linux-x86_64", "profile_id": "public-linux-x86_64"}
    )
    with pytest.raises(RuntimeError) as caught:
        validator(["python", "validator"], **selection)
    assert "fixture-credential" not in str(caught.value)
    assert "candidate-url" not in str(caught.value)
    assert "GITHUB_TOKEN" not in observed["env"]
    assert "PYTHONPATH" not in observed["env"]
