from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from tools import bootstrap_profile

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_checked_in_host_profiles_join_locked_payloads_and_evidence() -> None:
    document = json.loads(
        (REPO_ROOT / "implementations/tooling/profiles/development-profiles.json").read_text(encoding="utf-8")
    )
    assert document["schema_version"] == "raes-development-profiles/v2"
    profiles = {item["host_profile_id"]: item for item in document["host_profiles"]}
    assert {
        "public-ubuntu-24.04-x86_64",
        "public-linux-arm64",
        "public-macos-x86_64",
        "public-macos-arm64",
        "proof-ubuntu-22.04-x86_64",
    } <= profiles.keys()
    proof = profiles["proof-ubuntu-22.04-x86_64"]
    assert proof["proof_support"] == "linux-x86_64-required"
    assert {"bubblewrap", "fontconfig", "fonts", "locale-c-utf-8"} <= set(proof["required_capability_ids"])
    assert proof["host_security_control_changes"] == "prohibited"
    linux = profiles["public-ubuntu-24.04-x86_64"]
    assert {"container-cli", "container-daemon", "libvirt-client", "libvirt-daemon", "qemu", "kvm-access"} <= set(
        linux["optional_capability_ids"]
    )
    for profile in profiles.values():
        assert profile["offline_kit"]["credential_free"] is True
        assert profile["offline_kit"]["network_fallback"] == "prohibited"
        assert all("secret" not in ref.lower() and "token" not in ref.lower() for ref in profile["credential_refs"])


def test_standard_python_and_uv_payloads_are_exact_and_preview_is_advisory() -> None:
    lock = json.loads((REPO_ROOT / "implementations/tooling/artifacts.lock.json").read_text(encoding="utf-8"))
    artifacts = {item["artifact_id"]: item for item in lock["artifacts"]}
    expected = {
        "cpython-3.11": "3.11.16",
        "cpython-3.12": "3.12.14",
        "cpython-3.13": "3.13.15",
        "cpython-3.14": "3.14.7",
    }
    for artifact_id, version in expected.items():
        artifact = artifacts[artifact_id]
        assert artifact["version"] == version
        assert artifact["support_level"] == "blocking"
        assert all(item["installed_identity"]["version"] == version for item in artifact["platforms"])
    assert {(item["platform_id"], item["distribution_id"]) for item in artifacts["cpython-3.14"]["platforms"]} == {
        ("linux-x86_64", "ubuntu-24.04"),
        ("linux-arm64", "ubuntu-24.04"),
        ("macos-x86_64", "macos-15"),
        ("macos-arm64", "macos-15"),
    }
    assert {
        item["distribution_id"]
        for item in artifacts["cpython-3.12"]["platforms"]
        if item["platform_id"] == "linux-x86_64"
    } == {"ubuntu-22.04", "ubuntu-24.04"}
    assert artifacts["cpython-3.14t"]["support_level"] == "advisory"
    assert artifacts["uv"]["version"] == "0.12.4"
    assert {item["platform_id"] for item in artifacts["uv"]["platforms"]} == {
        "linux-x86_64",
        "linux-arm64",
        "macos-x86_64",
        "macos-arm64",
    }


def test_workflow_action_source_and_payload_selectors_are_separate() -> None:
    import yaml

    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    matrix = ci["jobs"]["interpreters"]["strategy"]["matrix"]["python"]
    assert matrix == [
        {"feature": "3.11", "payload": "3.11.16"},
        {"feature": "3.12", "payload": "3.12.14"},
        {"feature": "3.13", "payload": "3.13.15"},
        {"feature": "3.14", "payload": "3.14.7"},
    ]
    job = ci["jobs"]["interpreters"]
    assert job["env"]["UV_PYTHON"] == "${{ matrix.python.payload }}"
    assert job["env"]["RAES_EXPECTED_PYTHON"] == "${{ matrix.python.feature }}"
    setup_python = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/setup-python@"))
    setup_uv = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("astral-sh/setup-uv@"))
    assert setup_python["with"]["python-version"] == "${{ matrix.python.payload }}"
    assert setup_uv["with"]["version"] == "0.12.4"
    assert "@" in setup_python["uses"] and len(setup_python["uses"].rsplit("@", 1)[1].split()[0]) == 40


def test_every_setup_action_uses_an_exact_admitted_payload() -> None:
    import yaml

    allowed_python = {"3.11.16", "3.12.14", "3.13.15", "3.14.7", "3.14.7t", "${{ matrix.python.payload }}"}
    for path in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps", []):
                uses = str(step.get("uses", ""))
                if uses.startswith("actions/setup-python@"):
                    assert step.get("with", {}).get("python-version") in allowed_python, path
                if uses.startswith("astral-sh/setup-uv@"):
                    assert step.get("with", {}).get("version") == "0.12.4", path


def test_qualification_and_python_consumers_select_reviewed_host_labels() -> None:
    import yaml

    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/bootstrap-qualification.yml").read_text(encoding="utf-8"))
    matrix = workflow["jobs"]["generic-tool-platforms"]["strategy"]["matrix"]["include"]
    assert matrix == [
        {
            "profile": "public-ubuntu-24.04-x86_64",
            "runner": "ubuntu-24.04",
            "target": "x86_64-unknown-linux-gnu",
        },
        {
            "profile": "public-linux-arm64",
            "runner": "ubuntu-24.04-arm",
            "target": "aarch64-unknown-linux-gnu",
        },
        {"profile": "public-macos-x86_64", "runner": "macos-15-intel", "target": "x86_64-apple-darwin"},
        {"profile": "public-macos-arm64", "runner": "macos-15", "target": "aarch64-apple-darwin"},
    ]
    workflow_text = (REPO_ROOT / ".github/workflows/bootstrap-qualification.yml").read_text(encoding="utf-8")
    assert "offline-kit-fetch" in workflow_text
    assert "offline-kit-manifest" in workflow_text
    assert "offline-kit-verify" in workflow_text
    assert "implementations/python/.venv/bin/python -m tools.bootstrap_profile offline-kit-verify" in workflow_text
    assert '"${restored_python}" -m tools.bootstrap_profile offline-kit-verify' not in workflow_text
    assert "UV_PYTHON_DOWNLOADS=never" in workflow_text
    assert "UV_OFFLINE=1" in workflow_text
    assert "record-case T12" in workflow_text
    assert "bootstrap-offline-kit.tar" in workflow_text
    canonical = yaml.safe_load((REPO_ROOT / ".github/workflows/canonical-verification.yml").read_text(encoding="utf-8"))
    assert canonical["jobs"]["verify"]["runs-on"] == "ubuntu-22.04"
    for path in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in parsed.get("jobs", {}).values():
            if not isinstance(job, dict):
                continue
            if any(str(step.get("uses", "")).startswith("actions/setup-python@") for step in job.get("steps", [])):
                assert job.get("runs-on") != "ubuntu-latest", path


@pytest.mark.parametrize(
    ("value", "accepted"),
    [("8.3.0", False), ("8.4.0", True), ("8.5.0-2ubuntu10.13", True), ("garbage", False)],
)
def test_curl_version_floor_is_fail_closed(value: str, accepted: bool) -> None:
    assert bootstrap_profile.curl_version_is_supported(value) is accepted


def test_curl_qualification_uses_fixed_hardened_argv() -> None:
    argv = bootstrap_profile.curl_qualification_argv(
        Path("/usr/bin/curl"),
        "https://127.0.0.1:8443/payload",
        Path("qualification-output"),
        ca_cert=Path("qualification-ca.pem"),
        max_bytes=1024,
    )
    assert argv[:2] == ["/usr/bin/curl", "--disable"]
    assert argv[argv.index("--proto") : argv.index("--proto") + 2] == ["--proto", "=https"]
    assert argv[argv.index("--proto-redir") : argv.index("--proto-redir") + 2] == ["--proto-redir", "=https"]
    assert "--insecure" not in argv and "--location-trusted" not in argv and "--retry-all-errors" not in argv
    assert argv[argv.index("--max-filesize") : argv.index("--max-filesize") + 2] == ["--max-filesize", "1024"]


def test_host_inspection_uses_closed_stdin_minimal_environment_and_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        observed.update(argv=argv, kwargs=kwargs)
        return SimpleNamespace(returncode=1, stdout="", stderr="token=should-not-leak")

    monkeypatch.setattr(bootstrap_profile.subprocess, "run", fake_run)
    result = bootstrap_profile.inspect_executable(
        "git",
        Path("/usr/bin/git"),
        ("--version",),
        expected_version="2.43.0",
    )
    assert result == {
        "capability_id": "git",
        "outcome": "failed",
        "reason_code": "native-client-exit",
    }
    kwargs = observed["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["timeout"] == bootstrap_profile.PROBE_TIMEOUT_SECONDS
    assert kwargs["env"] == {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
    assert "should-not-leak" not in json.dumps(result)


def test_native_setup_refuses_mutable_repository_execution() -> None:
    result = bootstrap_profile.native_setup_plan(
        {
            "host_profile_id": "public-linux-arm64",
            "native_family": "ubuntu-apt",
            "native_repository_identity": "ubuntu:noble:reviewed-snapshot",
            "trust_root_refs": ["ubuntu-archive-keyring"],
            "offline_kit": {
                "host_prerequisite_package_ids": ["git", "curl"],
                "host_trust_root_refs": ["ubuntu-archive-keyring"],
            },
        }
    )
    assert result == {
        "host_profile_id": "public-linux-arm64",
        "native_family": "ubuntu-apt",
        "native_repository_identity": "ubuntu:noble:reviewed-snapshot",
        "trust_root_refs": ["ubuntu-archive-keyring"],
        "host_prerequisite_package_ids": ["git", "curl"],
        "host_trust_root_refs": ["ubuntu-archive-keyring"],
        "outcome": "not-run",
        "reason_code": "immutable-native-closure-required",
    }
    assert not hasattr(bootstrap_profile, "run_native_setup")


def test_host_identity_fails_closed_on_runner_release_or_architecture_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = {
        "base_image_identity": "github-hosted-runner:ubuntu24:X64",
        "native_repository_identity": "github-hosted-runner-package-set:ubuntu24:X64",
    }
    monkeypatch.setenv("ImageOS", "ubuntu24")
    monkeypatch.setenv("ImageVersion", "20260907.300.1")
    monkeypatch.setenv("RUNNER_ARCH", "ARM64")
    observed_base, observed_repository, results = bootstrap_profile.observe_host_identity(host)
    assert observed_base == "github-runner:ubuntu24:20260907.300.1:ARM64"
    assert observed_repository == "github-runner-package-set:ubuntu24:20260907.300.1:ARM64"
    assert [result["outcome"] for result in results] == ["failed", "failed"]


def test_proof_capability_is_explicitly_unsupported_outside_linux_x86_64() -> None:
    assert bootstrap_profile.proof_support_outcome("linux-x86_64") == "required"
    assert bootstrap_profile.proof_support_outcome("linux-arm64") == "unsupported"
    assert bootstrap_profile.proof_support_outcome("macos-x86_64") == "unsupported"
    assert bootstrap_profile.proof_support_outcome("macos-arm64") == "unsupported"


def test_generic_tool_qualification_executes_each_selected_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        environments.append(environment)
        return SimpleNamespace(returncode=0, stdout=f"{Path(argv[0]).name} 1.0.0", stderr="")

    monkeypatch.setattr(bootstrap_profile.subprocess, "run", fake_run)
    result = bootstrap_profile.qualify_generic_tools(
        selections=(
            ("conftest", Path("/qualified/conftest"), ("--version",), "1.0.0"),
            ("gitleaks", Path("/qualified/gitleaks"), ("version",), "1.0.0"),
            ("osv-scanner", Path("/qualified/osv-scanner"), ("--version",), "1.0.0"),
            ("vale", Path("/qualified/vale"), ("--version",), "1.0.0"),
        )
    )
    assert result["outcome"] == "passed"
    assert [item["capability_id"] for item in result["results"]] == [
        "conftest",
        "gitleaks",
        "osv-scanner",
        "vale",
    ]
    assert calls == [
        ["/qualified/conftest", "--version"],
        ["/qualified/gitleaks", "version"],
        ["/qualified/osv-scanner", "--version"],
        ["/qualified/vale", "--version"],
    ]
    assert len(environments) == 4
    for environment in environments:
        assert "HOME" not in environment
        assert all(
            Path(environment[name]).is_absolute() for name in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME")
        )


def test_qualification_evidence_binds_profile_payloads_versions_and_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tools.check_tooling_artifact_policy import select_tooling_host_profile

    host_selection = select_tooling_host_profile(REPO_ROOT, host_profile_id="public-ubuntu-24.04-x86_64")

    def fake_run(argv: list[str], **_kwargs: object) -> SimpleNamespace:
        versions = {
            "/usr/bin/curl": "curl 8.5.0",
            "/usr/bin/git": "git version 2.55.0",
            "/usr/bin/sha256sum": "sha256sum 9.4",
            "/usr/bin/gh": "gh version 2.98.0",
        }
        return SimpleNamespace(returncode=0, stdout=versions.get(argv[0], "uv 0.12.4"), stderr="")

    monkeypatch.setattr(bootstrap_profile.subprocess, "run", fake_run)
    monkeypatch.setattr(bootstrap_profile, "load_tooling_host_profile_selection", lambda _host_id: host_selection)
    monkeypatch.setattr(bootstrap_profile.shutil, "which", lambda _name: "/qualified/uv")
    expected_python_identity = {
        "implementation": "CPython",
        "version": "3.14.7",
        "abi": "cp314",
        "target": "x86_64-unknown-linux-gnu",
    }
    monkeypatch.setattr(bootstrap_profile, "observe_current_python_identity", lambda: expected_python_identity)
    monkeypatch.setattr(
        bootstrap_profile,
        "_observed_uv_identity",
        lambda _version: {
            "implementation": "uv",
            "version": "0.12.4",
            "abi": "native",
            "target": "x86_64-unknown-linux-gnu",
        },
    )
    monkeypatch.setenv("ImageOS", "ubuntu24")
    monkeypatch.setenv("ImageVersion", "20261005.999.1")
    monkeypatch.setenv("RUNNER_ARCH", "X64")
    selections = tuple(
        (name, Path(f"/qualified/{name}"), ("--version",), "1.0.0")
        for name in ("conftest", "gitleaks", "osv-scanner", "vale")
    )
    case_result = bootstrap_profile.record_case_result(
        REPO_ROOT,
        "T02",
        "a" * 40,
        "noxfile.py",
        ("cpython-3.14", "uv", "conftest", "gitleaks", "osv-scanner", "vale"),
    )
    case_path = tmp_path / "t02.json"
    case_path.write_text(json.dumps(case_result), encoding="utf-8")
    result = bootstrap_profile.build_qualification_evidence(
        REPO_ROOT,
        "public-ubuntu-24.04-x86_64",
        "a" * 40,
        "github-actions:OpenRAE/rae:1:1",
        python_artifact_id="cpython-3.14",
        case_result_paths=(case_path,),
        generic_selections=selections,
    )
    assert result["outcome"] == "passed"
    assert result["base_image_identity"] == "github-runner:ubuntu24:20261005.999.1:X64"
    assert result["observed_runner_image"] == "ubuntu24:20261005.999.1:X64"
    assert result["native_repository_identity"] == ("github-runner-package-set:ubuntu24:20261005.999.1:X64")
    assert len(result["policy_sha256"]) == 64
    assert len(result["harness_sha256"]) == 64
    assert len(result["evidence_sha256"]) == 64
    payloads = {item["artifact_id"]: item for item in result["payload_results"]}
    assert payloads["cpython-3.14"]["distribution_id"] == "ubuntu-24.04"
    assert payloads["cpython-3.14"]["expected_installed_identity"] == expected_python_identity
    assert payloads["cpython-3.14"]["observed_installed_identity"] == expected_python_identity
    assert {item["artifact_id"] for item in result["payload_results"]} == {
        "conftest",
        "cpython-3.14",
        "gitleaks",
        "osv-scanner",
        "uv",
        "vale",
    }
    capabilities = {item["capability_id"]: item for item in result["capability_results"]}
    assert capabilities["curl-unknown-length-max-filesize"]["version"] == "8.5.0"
    assert capabilities["ca-roots"]["outcome"] == "passed"
    assert capabilities["base-image"]["outcome"] == "passed"
    assert capabilities["native-repository"]["outcome"] == "passed"
    schema = json.loads(
        (REPO_ROOT / "implementations/tooling/schemas/profiles.schema.json").read_text(encoding="utf-8")
    )
    evidence_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/qualificationRecord",
    }
    jsonschema.validate(result, evidence_schema)
    monkeypatch.setattr(
        bootstrap_profile,
        "observe_current_python_identity",
        lambda: {**expected_python_identity, "abi": "cp314t", "target": "aarch64-unknown-linux-gnu"},
    )
    mismatched = bootstrap_profile.build_qualification_evidence(
        REPO_ROOT,
        "public-ubuntu-24.04-x86_64",
        "a" * 40,
        "github-actions:OpenRAE/rae:1:1",
        python_artifact_id="cpython-3.14",
        case_result_paths=(case_path,),
        generic_selections=selections,
    )
    assert mismatched["outcome"] == "failed"
    mismatched_capabilities = {item["capability_id"]: item for item in mismatched["capability_results"]}
    assert mismatched_capabilities["cpython"]["reason_code"] == "payload-identity-mismatch"


def test_case_results_are_bound_to_the_exact_harness_and_revision(tmp_path: Path) -> None:
    result = bootstrap_profile.record_case_result(
        REPO_ROOT,
        "T08",
        "b" * 40,
        "implementations/python/tests/test_issue_1217_bootstrap_profiles.py",
        (),
    )
    path = tmp_path / "t08.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert bootstrap_profile._load_case_results(REPO_ROOT, (path,), "b" * 40) == [result]
    result["harness_sha256"] = "0" * 64
    path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        bootstrap_profile._load_case_results(REPO_ROOT, (path,), "b" * 40)


def test_offline_tool_selection_verifies_imported_bytes_without_acquisition(tmp_path: Path) -> None:
    artifacts: dict[str, dict[str, object]] = {}
    for artifact_id in ("conftest", "gitleaks", "osv-scanner", "vale"):
        payload = artifact_id.encode()
        binary = tmp_path / ".cache/raes-sdl/tooling" / artifact_id / "1.0.0" / artifact_id
        binary.parent.mkdir(parents=True)
        binary.write_bytes(payload)
        artifacts[artifact_id] = {
            "artifact_id": artifact_id,
            "version": "1.0.0",
            "platform": {
                "platform_id": "linux-arm64",
                "installed_manifest": [
                    {
                        "path": artifact_id,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "size": len(payload),
                    }
                ],
            },
        }
    selected = bootstrap_profile._offline_generic_tool_selections(tmp_path, "linux-arm64", artifacts)
    assert [item[0] for item in selected] == ["conftest", "gitleaks", "osv-scanner", "vale"]
    compromised = selected[0][1]
    compromised.unlink()
    compromised.symlink_to(selected[1][1])
    with pytest.raises(ValueError, match="not a regular file"):
        bootstrap_profile._offline_generic_tool_selections(tmp_path, "linux-arm64", artifacts)


@pytest.mark.parametrize(
    "tampered_relative",
    ("bin/uv", "python/cpython/bin/python3.14"),
)
def test_offline_kit_requires_external_trust_before_executing_installed_payloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tampered_relative: str,
) -> None:
    artifact_ids = {"conftest", "cpython-3.14", "gitleaks", "osv-scanner", "uv", "vale"}
    kit_root = tmp_path / "kit"
    artifacts: list[dict[str, object]] = []
    for artifact_id in sorted(artifact_ids):
        version = "3.14.7" if artifact_id == "cpython-3.14" else "0.12.4" if artifact_id == "uv" else "1.0.0"
        platform: dict[str, object] = {
            "platform_id": "linux-arm64",
            "raw_manifest": [],
        }
        raw = f"raw-{artifact_id}".encode()
        raw_path = kit_root / "archives" / artifact_id / f"{artifact_id}.archive"
        raw_path.parent.mkdir(parents=True)
        raw_path.write_bytes(raw)
        platform["raw_manifest"] = [
            {"path": f"{artifact_id}.archive", "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        ]
        if artifact_id in {"cpython-3.14", "uv"}:
            platform["installed_identity"] = {
                "implementation": "CPython" if artifact_id == "cpython-3.14" else "uv",
                "version": version,
                "abi": "cp314" if artifact_id == "cpython-3.14" else "native",
                "target": "aarch64-unknown-linux-gnu",
            }
        else:
            binary = kit_root / ".cache/raes-sdl/tooling" / artifact_id / version / artifact_id
            binary.parent.mkdir(parents=True)
            binary.write_bytes(artifact_id.encode())
            platform["installed_manifest"] = [
                {
                    "path": artifact_id,
                    "sha256": hashlib.sha256(artifact_id.encode()).hexdigest(),
                    "size": len(artifact_id),
                }
            ]
        artifacts.append({"artifact_id": artifact_id, "version": version, "platform": platform})
    uv_path = kit_root / "bin/uv"
    uv_path.parent.mkdir(parents=True)
    uv_path.write_bytes(b"uv")
    python_path = kit_root / "python/cpython/bin/python3.14"
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b"python")
    selection = {
        "host_profile": {
            "host_profile_id": "host-a",
            "platform_id": "linux-arm64",
            "offline_kit": {"kit_id": "host-a-kit", "artifact_ids": sorted(artifact_ids)},
        },
        "artifacts": artifacts,
        "policy_sha256": "a" * 64,
    }
    monkeypatch.setattr(bootstrap_profile, "load_tooling_host_profile_selection", lambda _host_id: selection)
    monkeypatch.setattr(
        bootstrap_profile,
        "_observed_uv_identity",
        lambda version: {
            "implementation": "uv",
            "version": version,
            "abi": "native",
            "target": "aarch64-unknown-linux-gnu",
        },
    )

    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        stdout = (
            json.dumps(
                [
                    "CPython",
                    "3.14.7",
                    False,
                    "Linux",
                    "aarch64",
                    str(python_path),
                    str(python_path.parents[2]),
                ]
            )
            if argv[0].endswith("python3.14")
            else "uv 0.12.4\n"
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(bootstrap_profile.subprocess, "run", fake_run)
    manifest = bootstrap_profile.build_offline_kit_manifest("host-a", kit_root, python_artifact_id="cpython-3.14")
    manifest_path = kit_root / "offline-kit-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    trusted_digest = bootstrap_profile._sha256(manifest_path)
    result = bootstrap_profile.verify_offline_kit(
        "host-a",
        kit_root,
        python_artifact_id="cpython-3.14",
        trusted_manifest_sha256=trusted_digest,
    )
    assert result["outcome"] == "passed"
    monkeypatch.setattr(
        bootstrap_profile,
        "_observed_uv_identity",
        lambda version: {
            "implementation": "uv",
            "version": version,
            "abi": "native",
            "target": "x86_64-unknown-linux-gnu",
        },
    )
    wrong_uv = bootstrap_profile.verify_offline_kit(
        "host-a",
        kit_root,
        python_artifact_id="cpython-3.14",
        trusted_manifest_sha256=trusted_digest,
    )
    assert wrong_uv["outcome"] == "failed"
    assert wrong_uv["uv"]["reason_code"] == "payload-identity-mismatch"
    monkeypatch.setattr(
        bootstrap_profile,
        "_observed_uv_identity",
        lambda version: {
            "implementation": "uv",
            "version": version,
            "abi": "native",
            "target": "aarch64-unknown-linux-gnu",
        },
    )

    def wrong_python_run(argv: list[str], **_kwargs: object) -> SimpleNamespace:
        stdout = (
            json.dumps(
                [
                    "CPython",
                    "3.14.7",
                    True,
                    "Linux",
                    "x86_64",
                    str(python_path),
                    str(python_path.parents[2]),
                ]
            )
            if argv[0].endswith("python3.14")
            else "uv 0.12.4\n"
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(bootstrap_profile.subprocess, "run", wrong_python_run)
    wrong_python = bootstrap_profile.verify_offline_kit(
        "host-a",
        kit_root,
        python_artifact_id="cpython-3.14",
        trusted_manifest_sha256=trusted_digest,
    )
    assert wrong_python["outcome"] == "failed"
    assert wrong_python["python"]["outcome"] == "failed"
    monkeypatch.setattr(bootstrap_profile.subprocess, "run", fake_run)
    (kit_root / tampered_relative).write_bytes(b"substituted")
    rewritten = bootstrap_profile.build_offline_kit_manifest("host-a", kit_root, python_artifact_id="cpython-3.14")
    manifest_path.write_text(json.dumps(rewritten), encoding="utf-8")
    calls.clear()
    with pytest.raises(ValueError, match="externally trusted digest"):
        bootstrap_profile.verify_offline_kit(
            "host-a",
            kit_root,
            python_artifact_id="cpython-3.14",
            trusted_manifest_sha256=trusted_digest,
        )
    assert calls == []


def test_offline_kit_manifest_rejects_an_escaping_symlink(tmp_path: Path) -> None:
    kit_root = tmp_path / "kit"
    kit_root.mkdir()
    (kit_root / "escape").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="escaping symbolic link"):
        bootstrap_profile._offline_kit_entries(kit_root)


def test_offline_kit_manifest_uses_the_profile_specific_proof_closure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    kit_root = tmp_path / "proof-kit"
    (kit_root / "bin").mkdir(parents=True)
    (kit_root / "bin/uv").write_bytes(b"uv")
    (kit_root / "python/cpython/bin").mkdir(parents=True)
    (kit_root / "python/cpython/bin/python3.12").write_bytes(b"python")
    artifacts = []
    for artifact_id, version in (("cpython-3.12", "3.12.14"), ("isabelle", "2025-2"), ("uv", "0.12.4")):
        raw = f"raw-{artifact_id}".encode()
        raw_path = kit_root / "archives" / artifact_id / f"{artifact_id}.archive"
        raw_path.parent.mkdir(parents=True)
        raw_path.write_bytes(raw)
        platform = {
            "raw_manifest": [
                {
                    "path": raw_path.name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size": len(raw),
                }
            ]
        }
        if artifact_id in {"cpython-3.12", "uv"}:
            platform["installed_identity"] = {
                "implementation": "CPython" if artifact_id == "cpython-3.12" else "uv",
                "version": version,
                "abi": "cp312" if artifact_id == "cpython-3.12" else "native",
                "target": "x86_64-unknown-linux-gnu",
            }
        artifacts.append({"artifact_id": artifact_id, "version": version, "platform": platform})
    selection = {
        "host_profile": {
            "host_profile_id": "proof-host",
            "platform_id": "linux-x86_64",
            "offline_kit": {
                "kit_id": "proof-kit",
                "artifact_ids": ["cpython-3.12", "isabelle", "uv"],
            },
        },
        "artifacts": artifacts,
        "policy_sha256": "a" * 64,
    }
    monkeypatch.setattr(bootstrap_profile, "load_tooling_host_profile_selection", lambda _host_id: selection)
    manifest = bootstrap_profile.build_offline_kit_manifest(
        "proof-host",
        kit_root,
        python_artifact_id="cpython-3.12",
    )
    assert manifest["artifact_ids"] == ["cpython-3.12", "isabelle", "uv"]


def test_offline_kit_fetch_uses_the_validated_exact_raw_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    kit_root = tmp_path / "kit"
    kit_root.mkdir()
    payload = b"locked-payload"
    selection = {
        "host_profile": {
            "host_profile_id": "host-a",
            "offline_kit": {"artifact_ids": ["uv"]},
        },
        "artifacts": [
            {
                "artifact_id": "uv",
                "version": "1.0.0",
                "platform": {
                    "source_urls": ["https://example.invalid/uv.tar.gz"],
                    "raw_manifest": [
                        {
                            "path": "uv.tar.gz",
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "size": len(payload),
                        }
                    ],
                },
            }
        ],
        "policy_sha256": "a" * 64,
    }
    monkeypatch.setattr(bootstrap_profile, "load_tooling_host_profile_selection", lambda _host_id: selection)

    def fake_transfer(
        _executable: Path,
        url: str,
        output: Path,
        *,
        ca_cert: Path | None,
        max_bytes: int,
        max_time_seconds: int = 30,
    ) -> dict[str, str]:
        assert url == "https://example.invalid/uv.tar.gz"
        assert ca_cert is None and max_bytes == len(payload) and max_time_seconds == 30
        output.write_bytes(payload)
        return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}

    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", fake_transfer)
    result = bootstrap_profile.fetch_offline_kit_payloads("host-a", kit_root, ("uv",))
    assert result == [
        {
            "artifact_id": "uv",
            "path": "archives/uv/uv.tar.gz",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
    ]
    with pytest.raises(ValueError, match="already exists"):
        bootstrap_profile.fetch_offline_kit_payloads("host-a", kit_root, ("uv",))

    tampered_root = tmp_path / "tampered-kit"
    tampered_root.mkdir()

    def fake_tampered_transfer(
        _executable: Path,
        _url: str,
        output: Path,
        *,
        ca_cert: Path | None,
        max_bytes: int,
        max_time_seconds: int = 30,
    ) -> dict[str, str]:
        assert ca_cert is None and max_bytes == len(payload) and max_time_seconds == 30
        output.write_bytes(b"tampered")
        return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}

    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", fake_tampered_transfer)
    tampered_target = tampered_root / "archives/uv/uv.tar.gz"
    with pytest.raises(ValueError, match="failed exact verification"):
        bootstrap_profile.fetch_offline_kit_payloads("host-a", tampered_root, ("uv",))
    assert not tampered_target.exists()


class _CurlFixture(BaseHTTPRequestHandler):
    retries: dict[str, int] = {}

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/retry429", "/retry503"} and type(self).retries.get(self.path, 0) == 0:
            type(self).retries[self.path] = 1
            self.send_response(429 if self.path == "/retry429" else 503)
            self.end_headers()
            return
        if self.path == "/disconnect":
            self.send_response(200)
            self.send_header("Content-Length", "1024")
            self.end_headers()
            self.wfile.write(b"partial")
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if self.path == "/slow":
            time.sleep(2)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"https://127.0.0.1:{self.server.server_port}/small")
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        try:
            self.wfile.write(b"ok" if self.path in {"/small", "/retry429", "/retry503"} else b"x" * 4096)
        except (BrokenPipeError, ConnectionResetError):
            return


def _https_fixture(tmp_path: Path) -> tuple[ThreadingHTTPServer, Path]:
    curl_version = bootstrap_profile.observe_executable(
        "curl-unknown-length-max-filesize",
        Path("/usr/bin/curl"),
        ("--version",),
        minimum_version=(8, 4, 0),
    )
    if curl_version["outcome"] != "passed":
        pytest.skip("real curl qualification requires curl 8.4.0 or newer")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RAES curl qualification fixture")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(now + dt.timedelta(minutes=10))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "ca.pem"
    key_path = tmp_path / "server-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CurlFixture)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, cert_path


@pytest.mark.parametrize(("path", "status"), [("/retry429", 429), ("/retry503", 503)])
@pytest.mark.integration
def test_real_curl_enforces_unknown_length_limit_and_native_retry(
    tmp_path: Path,
    path: str,
    status: int,
) -> None:
    server, ca_cert = _https_fixture(tmp_path)
    try:
        oversize = bootstrap_profile.run_curl_qualification(
            Path("/usr/bin/curl"),
            f"https://127.0.0.1:{server.server_port}/oversize",
            tmp_path / "oversize",
            ca_cert=ca_cert,
            max_bytes=1024,
        )
        assert oversize == {"outcome": "passed", "reason_code": "curl-size-limit-enforced"}
        _CurlFixture.retries = {}
        retry = bootstrap_profile.run_curl_qualification(
            Path("/usr/bin/curl"),
            f"https://127.0.0.1:{server.server_port}{path}",
            tmp_path / "retry",
            ca_cert=ca_cert,
            max_bytes=1024,
        )
        assert retry == {"outcome": "passed", "reason_code": "curl-transfer-qualified"}
        assert _CurlFixture.retries[path] == 1, status
    finally:
        server.shutdown()


@pytest.mark.integration
def test_real_curl_keeps_tls_and_https_redirect_enforcement(tmp_path: Path) -> None:
    server, ca_cert = _https_fixture(tmp_path)
    try:
        redirected = bootstrap_profile.run_curl_qualification(
            Path("/usr/bin/curl"),
            f"https://127.0.0.1:{server.server_port}/redirect",
            tmp_path / "redirect",
            ca_cert=ca_cert,
            max_bytes=1024,
        )
        assert redirected == {"outcome": "passed", "reason_code": "curl-transfer-qualified"}
        rejected = bootstrap_profile.run_curl_qualification(
            Path("/usr/bin/curl"),
            f"https://127.0.0.1:{server.server_port}/small",
            tmp_path / "tls-rejected",
            ca_cert=tmp_path / "wrong-ca.pem",
            max_bytes=1024,
        )
        assert rejected == {"outcome": "failed", "reason_code": "curl-tls-rejected"}
    finally:
        server.shutdown()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/disconnect", {"outcome": "failed", "reason_code": "curl-transfer-failed"}),
        ("/slow", {"outcome": "failed", "reason_code": "curl-transfer-deadline"}),
    ],
)
@pytest.mark.integration
def test_real_curl_fails_closed_on_disconnect_and_total_deadline(
    tmp_path: Path,
    path: str,
    expected: dict[str, str],
) -> None:
    server, ca_cert = _https_fixture(tmp_path)
    try:
        result = bootstrap_profile.run_curl_qualification(
            Path("/usr/bin/curl"),
            f"https://127.0.0.1:{server.server_port}{path}",
            tmp_path / "transfer",
            ca_cert=ca_cert,
            max_bytes=1024,
            max_time_seconds=1,
        )
        assert result == expected
    finally:
        server.shutdown()
