from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import socket
import ssl
import subprocess
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import bootstrap_profile, maintained_client_acquisition

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_checked_in_host_profiles_join_locked_payloads_and_evidence() -> None:
    document = json.loads(
        (REPO_ROOT / "implementations/tooling/profiles/development-profiles.json").read_text(encoding="utf-8")
    )
    assert document["schema_version"] == "raes-development-profiles/v2"
    profiles = {item["host_profile_id"]: item for item in document["host_profiles"]}
    assert profiles.keys() == {
        "public-ubuntu-24.04-x86_64",
        "public-linux-arm64",
        "public-macos-arm64",
        "proof-ubuntu-22.04-x86_64",
        "container-ubuntu-24.04-x86_64",
        "live-runner-ubuntu-24.04-x86_64",
    }
    proof = profiles["proof-ubuntu-22.04-x86_64"]
    assert proof["proof_support"] == "linux-x86_64-required"
    assert {"bubblewrap", "fontconfig", "fonts", "locale-c-utf-8"} <= set(proof["required_capability_ids"])
    assert proof["host_security_control_changes"] == "prohibited"
    linux = profiles["public-ubuntu-24.04-x86_64"]
    assert {"container-cli", "container-daemon", "libvirt-client", "libvirt-daemon", "qemu", "kvm-access"} <= set(
        linux["optional_capability_ids"]
    )
    for profile in profiles.values():
        assert "offline_kit" not in profile
        assert "qualification_record_ids" not in profile
        assert profile["host_prerequisite_package_ids"]
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
        "macos-arm64",
    }


def test_workflow_action_source_and_payload_selectors_are_separate() -> None:
    import yaml

    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    matrix = ci["jobs"]["interpreters"]["strategy"]["matrix"]["python"]
    assert matrix == [
        {"feature": "3.11", "payload": "3.11.16", "closure": "public-linux-x86_64-cp311-all-extras"},
        {"feature": "3.12", "payload": "3.12.14", "closure": "public-linux-x86_64-cp312-all-extras"},
        {"feature": "3.13", "payload": "3.13.15", "closure": "public-linux-x86_64-cp313-all-extras"},
        {"feature": "3.14", "payload": "3.14.7", "closure": "public-linux-x86_64-cp314-all-extras"},
    ]
    job = ci["jobs"]["interpreters"]
    assert job["env"]["UV_PYTHON"] == "${{ matrix.python.payload }}"
    assert job["env"]["RAES_EXPECTED_PYTHON"] == "${{ matrix.python.feature }}"
    assert job["env"]["RAES_PYTHON_CLOSURE_PROFILE"] == "${{ matrix.python.closure }}"
    setup_python = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/setup-python@"))
    setup_uv = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("astral-sh/setup-uv@"))
    assert setup_python["with"]["python-version"] == "${{ matrix.python.payload }}"
    assert setup_uv["with"]["version"] == "0.12.4"
    assert "@" in setup_python["uses"]
    assert len(setup_python["uses"].rsplit("@", 1)[1].split()[0]) == 40


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
    assert workflow["jobs"]["generic-tool-platforms"]["timeout-minutes"] == 60
    matrix = workflow["jobs"]["generic-tool-platforms"]["strategy"]["matrix"]["include"]
    assert matrix == [
        {
            "profile": "public-ubuntu-24.04-x86_64",
            "runner": "ubuntu-24.04",
            "target": "x86_64-unknown-linux-gnu",
            "project_closure": "public-linux-x86_64-cp314-all-extras",
        },
        {
            "profile": "public-linux-arm64",
            "runner": "ubuntu-24.04-arm",
            "target": "aarch64-unknown-linux-gnu",
            "project_closure": "public-linux-arm64-cp314-all-extras",
        },
        {
            "profile": "public-macos-arm64",
            "runner": "macos-15",
            "target": "aarch64-apple-darwin",
            "project_closure": "public-macos-arm64-cp314-all-extras",
        },
    ]
    closure_profiles = {
        item["python_closure_profile_id"]: item
        for item in json.loads(
            (REPO_ROOT / "implementations/tooling/profiles/development-profiles.json").read_text(encoding="utf-8")
        )["python_closure_profiles"]
    }
    assert all(item["project_closure"] in closure_profiles for item in matrix)
    assert "UV_NO_BINARY_PACKAGE" not in workflow["jobs"]["generic-tool-platforms"].get("env", {})
    assert workflow["jobs"]["generic-tool-platforms"]["env"]["RAES_PYTHON_COMPATIBILITY_SMOKE_ONLY"] == "1"
    setup_uv = next(
        step
        for step in workflow["jobs"]["generic-tool-platforms"]["steps"]
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    )
    assert setup_uv["with"]["enable-cache"] is False
    workflow_text = (REPO_ROOT / ".github/workflows/bootstrap-qualification.yml").read_text(encoding="utf-8")
    assert "offline-kit" not in workflow_text
    assert "-s local-installation-qualification -- --output local-installation-qualification.json" in workflow_text
    canonical = yaml.safe_load((REPO_ROOT / ".github/workflows/canonical-verification.yml").read_text(encoding="utf-8"))
    assert canonical["jobs"]["proof"]["runs-on"] == "ubuntu-22.04"
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
    assert "--insecure" not in argv
    assert "--location-trusted" not in argv
    assert "--retry-all-errors" not in argv
    assert argv[argv.index("--max-filesize") : argv.index("--max-filesize") + 2] == ["--max-filesize", "1024"]


@pytest.mark.parametrize(
    ("url", "max_bytes", "max_time_seconds", "message"),
    [
        ("http://example.test", 1, 30, "credential-free HTTPS"),
        ("https://example.test", 0, 30, "size limit"),
        ("https://example.test", 1, 31, "deadline"),
    ],
)
def test_curl_qualification_rejects_invalid_bounds(
    url: str,
    max_bytes: int,
    max_time_seconds: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        bootstrap_profile.curl_qualification_argv(
            Path("/usr/bin/curl"),
            url,
            Path("qualification-output"),
            ca_cert=None,
            max_bytes=max_bytes,
            max_time_seconds=max_time_seconds,
        )


@pytest.mark.parametrize(
    ("returncode", "expected_reason"),
    [
        (63, "curl-size-limit-enforced"),
        (60, "curl-tls-rejected"),
        (28, "curl-transfer-deadline"),
        (1, "curl-transfer-failed"),
        (0, "curl-transfer-qualified"),
    ],
)
def test_curl_qualification_classifies_transfer_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
    expected_reason: str,
) -> None:
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="curl 8.4.0", stderr=""),
            SimpleNamespace(returncode=returncode, stdout="", stderr=""),
        ]
    )
    monkeypatch.setattr(maintained_client_acquisition.subprocess, "run", lambda *args, **kwargs: next(responses))
    output = tmp_path / "payload"
    output.write_bytes(b"ok")
    result = bootstrap_profile.run_curl_qualification(
        Path("/usr/bin/curl"),
        "https://example.test/payload",
        output,
        ca_cert=None,
        max_bytes=10,
    )
    assert result["reason_code"] == expected_reason
    assert result["outcome"] == ("passed" if returncode in {0, 63} else "failed")


@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    [
        (subprocess.TimeoutExpired("curl", 30), "curl-wall-deadline"),
        (OSError("unavailable"), "curl-unavailable"),
    ],
)
def test_curl_qualification_sanitizes_transfer_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: Exception,
    expected_reason: str,
) -> None:
    calls = 0

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise failure
        return SimpleNamespace(returncode=0, stdout="curl 8.4.0", stderr="")

    monkeypatch.setattr(maintained_client_acquisition.subprocess, "run", fake_run)
    output = tmp_path / "payload"
    output.write_bytes(b"partial")
    result = bootstrap_profile.run_curl_qualification(
        Path("/usr/bin/curl"),
        "https://example.test/payload",
        output,
        ca_cert=None,
        max_bytes=10,
    )
    assert result == {"outcome": "failed", "reason_code": expected_reason}
    assert not output.exists()


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


@pytest.mark.parametrize("mode", ["exception", "oversized", "version-mismatch"])
def test_host_inspection_sanitizes_probe_failures(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        if mode == "exception":
            raise OSError("private detail")
        output = "x" * (bootstrap_profile.MAX_PROBE_OUTPUT_BYTES + 1) if mode == "oversized" else "wrong 1.0"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(bootstrap_profile.subprocess, "run", fake_run)
    result = bootstrap_profile.inspect_executable("git", Path("/usr/bin/git"), ("--version",), expected_version="git 2")
    assert result["outcome"] == "failed"
    assert "private detail" not in json.dumps(result)


@pytest.mark.parametrize("mode", ["preflight", "version-exception", "inadequate-version"])
def test_curl_qualification_rejects_preflight_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
) -> None:
    if mode == "preflight":
        monkeypatch.setattr(
            maintained_client_acquisition,
            "_curl_preflight_failure",
            lambda _executable: "curl-version-inadequate",
        )
    else:

        def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
            if mode == "version-exception":
                raise OSError("private detail")
            return SimpleNamespace(returncode=0, stdout="curl 8.3.0", stderr="")

        monkeypatch.setattr(maintained_client_acquisition.subprocess, "run", fake_run)
    result = bootstrap_profile.run_curl_qualification(
        Path("/usr/bin/curl"),
        "https://example.test/payload",
        tmp_path / "payload",
        ca_cert=None,
        max_bytes=10,
    )
    assert result["outcome"] == "failed"
    assert "private detail" not in json.dumps(result)


def test_native_client_results_cover_reviewed_linux_and_macos_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[tuple[str, Path, tuple[str, ...], object]] = []
    identities: list[tuple[str, Path]] = []

    def observe(
        capability_id: str,
        path: Path,
        version_args: tuple[str, ...],
        *,
        minimum_version: tuple[int, int, int] | None = None,
    ) -> dict[str, str]:
        probes.append((capability_id, path, version_args, minimum_version))
        return {"capability_id": capability_id, "outcome": "passed"}

    def inspect(
        capability_id: str, path: Path, version_args: tuple[str, ...], *, expected_version: str
    ) -> dict[str, str]:
        probes.append((capability_id, path, version_args, expected_version))
        return {"capability_id": capability_id, "outcome": "passed"}

    def file_identity(path: Path) -> str:
        identities.append((path.name, path))
        return "a" * 64

    monkeypatch.setattr(bootstrap_profile, "observe_executable", observe)
    monkeypatch.setattr(bootstrap_profile, "inspect_executable", inspect)
    monkeypatch.setattr(bootstrap_profile, "_sha256", file_identity)
    linux_capabilities = {
        "git",
        "curl-unknown-length-max-filesize",
        "sha256",
        "gh-cli",
        "ca-roots",
        "bubblewrap",
        "fontconfig",
        "fonts",
        "locale-c-utf-8",
    }
    linux = bootstrap_profile._native_client_results(
        {"platform_id": "linux-x86_64", "required_capability_ids": linux_capabilities}
    )
    assert {result["capability_id"] for result in linux} == linux_capabilities
    assert probes == [
        ("git", Path("/usr/bin/git"), ("--version",), None),
        ("curl-unknown-length-max-filesize", Path("/usr/bin/curl"), ("--version",), (8, 4, 0)),
        ("sha256", Path("/usr/bin/sha256sum"), ("--version",), None),
        ("gh-cli", Path("/usr/bin/gh"), ("--version",), None),
        ("bubblewrap", Path("/usr/bin/bwrap"), ("--version",), None),
        ("fontconfig", Path("/usr/bin/fc-match"), ("--version",), None),
        ("locale-c-utf-8", Path("/usr/bin/locale"), ("-a",), "C.utf8"),
    ]
    assert [path for _name, path in identities] == [
        Path("/etc/ssl/certs/ca-certificates.crt"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    probes.clear()
    identities.clear()
    macos = bootstrap_profile._native_client_results(
        {
            "platform_id": "macos-arm64",
            "required_capability_ids": {"git", "curl-unknown-length-max-filesize", "sha256", "gh-cli", "ca-roots"},
        }
    )
    assert {result["capability_id"] for result in macos} == {
        "git",
        "curl-unknown-length-max-filesize",
        "sha256",
        "gh-cli",
        "ca-roots",
    }
    assert probes == [
        ("git", Path("/usr/bin/git"), ("--version",), None),
        ("curl-unknown-length-max-filesize", Path("/usr/bin/curl"), ("--version",), (8, 4, 0)),
        ("sha256", Path("/usr/bin/shasum"), ("--version",), None),
        ("gh-cli", Path("/opt/homebrew/bin/gh"), ("--version",), None),
    ]
    assert [path for _name, path in identities] == [Path("/etc/ssl/cert.pem")]

    def unavailable(_path: Path) -> str:
        raise OSError("unavailable")

    monkeypatch.setattr(bootstrap_profile, "_sha256", unavailable)
    assert bootstrap_profile._file_identity_result("fonts", Path("missing"), "font-unavailable") == {
        "capability_id": "fonts",
        "outcome": "failed",
        "reason_code": "font-unavailable",
    }


def test_observe_executable_records_versions_and_sanitizes_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap_profile.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="tool 2.3.4", stderr=""),
    )
    assert bootstrap_profile.observe_executable(
        "tool", Path("/usr/bin/tool"), ("--version",), minimum_version=(2, 0, 0)
    ) == {"capability_id": "tool", "outcome": "passed", "version": "2.3.4"}

    def unavailable(*args: object, **kwargs: object) -> SimpleNamespace:
        raise OSError("private detail")

    monkeypatch.setattr(bootstrap_profile.subprocess, "run", unavailable)
    result = bootstrap_profile.observe_executable("tool", Path("/usr/bin/tool"), ("--version",))
    assert result["reason_code"] == "native-client-unavailable"
    assert "private detail" not in json.dumps(result)


@pytest.mark.parametrize(
    ("returncode", "stdout", "minimum_version", "expected_reason"),
    [
        (1, "tool 2.3.4", None, "native-client-exit"),
        (0, "x" * (bootstrap_profile.MAX_PROBE_OUTPUT_BYTES + 1), None, "native-client-output-limit"),
        (0, "no version", None, "native-client-version"),
        (0, "tool 1.0.0", (2, 0, 0), "native-client-version"),
    ],
)
def test_observe_executable_rejects_invalid_results(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stdout: str,
    minimum_version: tuple[int, int, int] | None,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(
        bootstrap_profile.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=returncode, stdout=stdout, stderr=""),
    )
    result = bootstrap_profile.observe_executable(
        "tool", Path("/usr/bin/tool"), ("--version",), minimum_version=minimum_version
    )
    assert result["reason_code"] == expected_reason


def test_native_setup_refuses_mutable_repository_execution() -> None:
    result = bootstrap_profile.native_setup_plan(
        {
            "host_profile_id": "public-linux-arm64",
            "native_family": "ubuntu-apt",
            "native_repository_identity": "ubuntu:noble:reviewed-snapshot",
            "trust_root_refs": ["ubuntu-archive-keyring"],
            "host_prerequisite_package_ids": ["git", "curl"],
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
        "reason_code": "operator-installs-native-prerequisites",
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


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("ImageOS", "ubuntu24:X64"),
        ("ImageVersion", "20260907.300.1 injected"),
        ("RUNNER_ARCH", "X64/../ARM64"),
        ("ImageVersion", ""),
    ],
)
def test_malformed_runner_image_metadata_is_sanitized_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    host = {
        "base_image_identity": "github-hosted-runner:ubuntu24:X64",
        "native_repository_identity": "github-hosted-runner-package-set:ubuntu24:X64",
    }
    monkeypatch.setenv("ImageOS", "ubuntu24")
    monkeypatch.setenv("ImageVersion", "20260907.300.1")
    monkeypatch.setenv("RUNNER_ARCH", "X64")
    assert [item["outcome"] for item in bootstrap_profile.observe_host_identity(host)[2]] == ["passed", "passed"]
    monkeypatch.setenv(variable, value)

    image = bootstrap_profile._safe_runner_image()
    observed_base, _observed_repository, results = bootstrap_profile.observe_host_identity(host)

    fields = dict(zip(("ImageOS", "ImageVersion", "RUNNER_ARCH"), image.split(":"), strict=True))
    assert fields[variable] == "unavailable"
    assert value not in observed_base or not value
    assert [(item["outcome"], item["reason_code"]) for item in results] == [
        ("failed", "runner-image-mismatch"),
        ("failed", "native-repository-unobserved"),
    ]


def test_proof_capability_is_explicitly_unsupported_outside_linux_x86_64() -> None:
    assert bootstrap_profile.proof_support_outcome("linux-x86_64") == "required"
    assert bootstrap_profile.proof_support_outcome("linux-arm64") == "unsupported"
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


def test_bootstrap_python_install_extracts_only_the_locked_relocatable_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload_root = tmp_path / "payload"
    (payload_root / "bin").mkdir(parents=True)
    (payload_root / "bin/python3.14").write_bytes(b"relocatable-python")
    kit_root = tmp_path / "kit"
    archive = kit_root / "archives/cpython-3.14/cpython.tar.gz"
    archive.parent.mkdir(parents=True)
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(payload_root, arcname="python")
    artifact = {
        "artifact_id": "cpython-3.14",
        "version": "3.14.7",
        "platform": {
            "raw_manifest": [
                {
                    "path": archive.name,
                    "sha256": bootstrap_profile._sha256(archive),
                    "size": archive.stat().st_size,
                }
            ]
        },
    }
    monkeypatch.setattr(
        bootstrap_profile,
        "_load_host_selection",
        lambda _host_id: ({}, {"cpython-3.14": artifact}, "a" * 64),
    )

    result = bootstrap_profile.install_python_payload("host-a", kit_root, "cpython-3.14")
    installed = kit_root / result["path"] / "bin/python3.14"
    assert installed.read_bytes() == b"relocatable-python"
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="differs from the validated lock"):
        bootstrap_profile.install_python_payload("host-a", kit_root, "cpython-3.14")


@pytest.mark.parametrize("locator_ref", [None, "primary", "mirror"])
def test_bootstrap_payload_fetch_uses_the_validated_exact_raw_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    locator_ref: str | None,
) -> None:
    kit_root = tmp_path / "kit"
    kit_root.mkdir()
    payload = b"locked-payload"
    selection = {
        "host_profile": {
            "host_profile_id": "host-a",
            "bootstrap_payload_ids": ["uv"],
        },
        "artifacts": [
            {
                "artifact_id": "uv",
                "version": "1.0.0",
                "source": {"locator_refs": ["primary", "mirror"]},
                "platform": {
                    "source_urls": ["https://example.invalid/uv.tar.gz", "https://mirror.invalid/uv.tar.gz"],
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
        max_time_seconds: int | None = None,
        budget: maintained_client_acquisition.TransferBudget,
    ) -> dict[str, str]:
        expected_host = "mirror" if locator_ref == "mirror" else "example"
        assert url == f"https://{expected_host}.invalid/uv.tar.gz"
        assert ca_cert is None
        assert max_bytes == len(payload)
        assert max_time_seconds is None
        assert budget is maintained_client_acquisition.GENERIC_TRANSFER_BUDGET
        output.write_bytes(payload)
        return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}

    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", fake_transfer)
    with pytest.raises(ValueError, match="locator is not approved"):
        bootstrap_profile.fetch_bootstrap_payloads("host-a", kit_root, ("uv",), locator_ref="unapproved")
    assert not (kit_root / "archives").exists()
    result = bootstrap_profile.fetch_bootstrap_payloads("host-a", kit_root, ("uv",), locator_ref=locator_ref)
    assert result == [
        {
            "artifact_id": "uv",
            "path": "archives/uv/uv.tar.gz",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
    ]
    with pytest.raises(ValueError, match="already exists"):
        bootstrap_profile.fetch_bootstrap_payloads("host-a", kit_root, ("uv",), locator_ref=locator_ref)

    tampered_root = tmp_path / "tampered-kit"
    tampered_root.mkdir()

    def fake_tampered_transfer(
        _executable: Path,
        _url: str,
        output: Path,
        *,
        ca_cert: Path | None,
        max_bytes: int,
        max_time_seconds: int | None = None,
        budget: maintained_client_acquisition.TransferBudget,
    ) -> dict[str, str]:
        assert ca_cert is None
        assert max_bytes == len(payload)
        assert max_time_seconds is None
        assert budget is maintained_client_acquisition.GENERIC_TRANSFER_BUDGET
        output.write_bytes(b"tampered")
        return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}

    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", fake_tampered_transfer)
    tampered_target = tampered_root / "archives/uv/uv.tar.gz"
    with pytest.raises(ValueError, match="failed exact verification"):
        bootstrap_profile.fetch_bootstrap_payloads("host-a", tampered_root, ("uv",), locator_ref=locator_ref)
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
        if self.path == "/trickle":
            self.send_response(200)
            self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.25)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
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
    # Only the opt-in real-curl TLS fixtures need certificate generation.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

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
    monkeypatch: pytest.MonkeyPatch,
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
        monkeypatch.setattr(_CurlFixture, "retries", {})
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
