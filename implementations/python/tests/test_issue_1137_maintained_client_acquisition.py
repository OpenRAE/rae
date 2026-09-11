"""Regression tests for maintained-client generic-tool acquisition."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import bootstrap_profile, gitleaks_tool, osv_scanner_tool, vale_tool
from tools import maintained_client_acquisition as acquisition
from tools.policy import conftest_tool

REPO_ROOT = Path(__file__).resolve().parents[3]


def _expected(payload: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        path="reviewed-tool.tar.gz",
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
    )


def test_curl_transfer_argv_is_fixed_and_bounded() -> None:
    argv = acquisition.curl_transfer_argv(
        Path("/usr/bin/curl"),
        "https://example.test/reviewed-tool",
        Path("private-output"),
        ca_cert=None,
        max_bytes=1024,
    )

    assert argv[:2] == ["/usr/bin/curl", "--disable"]
    assert argv[argv.index("--proto") : argv.index("--proto") + 2] == ["--proto", "=https"]
    assert argv[argv.index("--proto-redir") : argv.index("--proto-redir") + 2] == ["--proto-redir", "=https"]
    assert argv[argv.index("--retry") : argv.index("--retry") + 2] == ["--retry", "2"]
    assert argv[argv.index("--retry-max-time") : argv.index("--retry-max-time") + 2] == [
        "--retry-max-time",
        "15",
    ]
    assert argv[argv.index("--max-filesize") : argv.index("--max-filesize") + 2] == [
        "--max-filesize",
        "1024",
    ]
    assert "--insecure" not in argv
    assert "--location-trusted" not in argv
    assert "--retry-all-errors" not in argv


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/tool",
        "https://user:password@example.test/tool",
        "file:///tmp/tool",
    ],
)
def test_curl_transfer_rejects_untrusted_locator_shapes(url: str) -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        acquisition.curl_transfer_argv(
            Path("/usr/bin/curl"),
            url,
            Path("private-output"),
            ca_cert=None,
            max_bytes=1,
        )


def test_curl_transfer_uses_closed_stdin_and_a_minimal_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    output = tmp_path / "payload"

    def run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((argv, kwargs))
        if argv[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="curl 8.4.0", stderr="")
        output.write_bytes(b"reviewed")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(acquisition.subprocess, "run", run)

    assert acquisition.run_curl_transfer(
        Path("/usr/bin/curl"),
        "https://example.test/tool",
        output,
        ca_cert=None,
        max_bytes=len(b"reviewed"),
    ) == {"outcome": "passed", "reason_code": "curl-transfer-qualified"}
    assert len(calls) == 2
    for _argv, kwargs in calls:
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["env"] == {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
    assert calls[1][1]["stdout"] is subprocess.DEVNULL
    assert calls[1][1]["stderr"] is subprocess.DEVNULL


def test_curl_size_limit_is_terminal_and_removes_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="curl 8.4.0", stderr=""),
            SimpleNamespace(returncode=63, stdout=b"", stderr=b"private detail"),
        ]
    )
    monkeypatch.setattr(acquisition.subprocess, "run", lambda *_args, **_kwargs: next(responses))
    output = tmp_path / "partial"
    output.write_bytes(b"partial")

    result = acquisition.run_curl_transfer(
        Path("/usr/bin/curl"),
        "https://example.test/tool",
        output,
        ca_cert=None,
        max_bytes=4,
    )

    assert result == {"outcome": "failed", "reason_code": "curl-size-limit-enforced"}
    assert not output.exists()
    assert "private detail" not in str(result)


@pytest.mark.parametrize(
    ("probe", "reason_code"),
    [
        (OSError("private unavailable detail"), "curl-unavailable"),
        (SimpleNamespace(returncode=0, stdout="curl 8.3.0", stderr=""), "curl-version-inadequate"),
    ],
)
def test_curl_preflight_reports_stable_unavailable_and_inadequate_reasons(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    probe: object,
    reason_code: str,
) -> None:
    def run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        if isinstance(probe, Exception):
            raise probe
        assert isinstance(probe, SimpleNamespace)
        return probe

    monkeypatch.setattr(acquisition.subprocess, "run", run)

    result = acquisition.run_curl_transfer(
        Path("/usr/bin/curl"),
        "https://example.test/tool",
        tmp_path / "output",
        ca_cert=None,
        max_bytes=1,
    )

    assert result == {"outcome": "failed", "reason_code": reason_code}
    assert "private unavailable detail" not in str(result)


def test_exact_local_input_bypasses_transport_but_not_raw_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed local bytes"
    local_input = tmp_path / "local-input"
    local_input.write_bytes(payload)
    monkeypatch.setattr(
        acquisition,
        "run_curl_transfer",
        lambda *_args, **_kwargs: pytest.fail("network used for explicit local input"),
    )

    assert (
        acquisition.acquire_locked_bytes(
            artifact_id="conftest",
            source_url="https://example.test/conftest",
            expected=_expected(payload),
            local_input=local_input,
        )
        == payload
    )


@pytest.mark.parametrize("shape", ["wrong-bytes", "symlink"])
def test_invalid_local_input_is_terminal_without_network_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shape: str,
) -> None:
    expected_payload = b"reviewed local bytes"
    local_input = tmp_path / "local-input"
    if shape == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(expected_payload)
        local_input.symlink_to(outside)
    else:
        local_input.write_bytes(b"different")
    monkeypatch.setattr(
        acquisition,
        "run_curl_transfer",
        lambda *_args, **_kwargs: pytest.fail("network fallback used after invalid local input"),
    )
    expected = _expected(expected_payload)

    with pytest.raises(RuntimeError, match="conftest local input failed locked identity validation") as raised:
        acquisition.acquire_locked_bytes(
            artifact_id="conftest",
            source_url="https://example.test/conftest",
            expected=expected,
            local_input=local_input,
        )
    assert str(local_input) not in str(raised.value)


def test_network_output_must_match_the_locked_raw_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_payload = b"reviewed network bytes"

    def transfer(
        _executable: Path,
        _url: str,
        output: Path,
        **_kwargs: object,
    ) -> dict[str, str]:
        output.write_bytes(b"different")
        return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}

    monkeypatch.setattr(acquisition, "run_curl_transfer", transfer)
    expected = _expected(expected_payload)

    with pytest.raises(RuntimeError, match="vale acquired bytes differ from the reviewed lock"):
        acquisition.acquire_locked_bytes(
            artifact_id="vale",
            source_url="https://example.test/vale",
            expected=expected,
        )


def test_bootstrap_qualification_uses_the_shared_curl_argv_builder() -> None:
    assert bootstrap_profile.curl_qualification_argv is acquisition.curl_transfer_argv


def test_generic_tool_local_input_root_routes_each_locked_raw_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_input_root = tmp_path / "local-inputs"
    local_input_root.mkdir()
    raw_paths = {
        "conftest": "conftest.tar.gz",
        "gitleaks": "gitleaks.tar.gz",
        "osv-scanner": "osv-scanner",
        "vale": "vale.tar.gz",
    }
    observed: dict[str, Path | None] = {}

    monkeypatch.setattr(
        "tools.tooling_policy_gate.host_platform_id",
        lambda: "linux-x86_64",
    )
    monkeypatch.setattr(
        bootstrap_profile,
        "_load_host_selection",
        lambda profile_id: (
            {},
            {
                artifact_id: {
                    "version": version,
                    "platform": {"raw_manifest": [{"path": raw_paths[artifact_id]}]},
                }
                for artifact_id, version in {
                    "conftest": "0.68.0",
                    "gitleaks": "8.30.1",
                    "osv-scanner": "2.4.0",
                    "vale": "3.15.2",
                }.items()
            },
            "policy-digest",
        ),
    )

    for module, artifact_id in (
        (conftest_tool, "conftest"),
        (gitleaks_tool, "gitleaks"),
        (osv_scanner_tool, "osv-scanner"),
        (vale_tool, "vale"),
    ):
        binary = tmp_path / f"installed-{artifact_id}"

        def ensure(*, local_input: Path | None = None, artifact_id: str = artifact_id, binary: Path = binary) -> Path:
            observed[artifact_id] = local_input
            return binary

        monkeypatch.setattr(module, f"ensure_{artifact_id.replace('-', '_')}", ensure)

    selections = bootstrap_profile._default_generic_tool_selections(local_input_root)

    assert [item[0] for item in selections] == ["conftest", "gitleaks", "osv-scanner", "vale"]
    assert observed == {
        artifact_id: local_input_root / "archives" / artifact_id / raw_path
        for artifact_id, raw_path in raw_paths.items()
    }


def test_canonical_proof_job_consumes_same_run_locked_generic_tool_inputs() -> None:
    import yaml

    workflow_path = REPO_ROOT / ".github/workflows/canonical-verification.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    prepare = workflow["jobs"]["generic-tool-local-inputs"]
    verify = workflow["jobs"]["verify"]
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert prepare["runs-on"] == "ubuntu-24.04"
    assert verify["runs-on"] == "ubuntu-22.04"
    assert verify["needs"] == "generic-tool-local-inputs"
    assert "offline-kit-fetch" in workflow_text
    assert "--artifact-id conftest" in workflow_text
    assert "--artifact-id gitleaks" in workflow_text
    assert "--artifact-id osv-scanner" in workflow_text
    assert "--artifact-id vale" in workflow_text
    assert "generic-tools --local-input-root .canonical-tool-inputs" in workflow_text
    upload = next(step for step in prepare["steps"] if str(step.get("uses", "")).startswith("actions/upload-artifact@"))
    assert upload["with"]["include-hidden-files"] is True


def test_bootstrap_qualification_maps_size_enforcement_without_changing_production_semantics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        acquisition,
        "run_curl_transfer",
        lambda *_args, **_kwargs: {"outcome": "failed", "reason_code": "curl-size-limit-enforced"},
    )

    assert bootstrap_profile.run_curl_qualification(
        Path("/usr/bin/curl"),
        "https://example.test/oversize",
        tmp_path / "output",
        ca_cert=None,
        max_bytes=1,
    ) == {"outcome": "passed", "reason_code": "curl-size-limit-enforced"}


@pytest.mark.parametrize(
    ("module", "ensure", "artifact_id", "version", "binary_name"),
    [
        (conftest_tool, conftest_tool.ensure_conftest, "conftest", "0.68.0", "conftest"),
        (gitleaks_tool, gitleaks_tool.ensure_gitleaks, "gitleaks", "8.30.1", "gitleaks"),
        (vale_tool, vale_tool.ensure_vale, "vale", "3.15.2", "vale"),
        (osv_scanner_tool, osv_scanner_tool.ensure_osv_scanner, "osv-scanner", "2.4.0", "osv-scanner"),
    ],
)
def test_each_installer_passes_the_locked_raw_object_and_explicit_local_input_to_the_shared_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module: object,
    ensure: object,
    artifact_id: str,
    version: str,
    binary_name: str,
) -> None:
    binary_bytes = f"reviewed-{artifact_id}".encode()
    if artifact_id == "osv-scanner":
        raw_bytes = binary_bytes
        raw_path = binary_name
    else:
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
            member = tarfile.TarInfo(binary_name)
            member.mode = 0o755
            member.size = len(binary_bytes)
            archive.addfile(member, io.BytesIO(binary_bytes))
        raw_bytes = archive_buffer.getvalue()
        raw_path = f"{artifact_id}-{version}.tar.gz"
    source_url = f"https://example.test/{raw_path}"
    raw = _expected(raw_bytes)
    raw.path = raw_path
    installed = SimpleNamespace(
        path=binary_name,
        sha256=hashlib.sha256(binary_bytes).hexdigest(),
        size=len(binary_bytes),
    )
    selection = SimpleNamespace(
        artifact_id=artifact_id,
        version=version,
        source_urls=(source_url,),
        raw_manifest=(raw,),
        installed_manifest=(installed,),
    )
    local_input = tmp_path / "explicit-local-input"
    local_input.write_bytes(raw_bytes)
    observed: dict[str, object] = {}

    monkeypatch.setattr("tools.tooling_policy_gate.host_platform_id", lambda: "linux-x86_64")
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", lambda **_kwargs: selection)

    def acquire_locked_bytes(**kwargs: object) -> bytes:
        observed.update(kwargs)
        return raw_bytes

    monkeypatch.setattr(module, "acquire_locked_bytes", acquire_locked_bytes)

    binary = ensure(tmp_path, version=version, local_input=local_input)  # type: ignore[operator]

    assert binary.read_bytes() == binary_bytes
    assert observed == {
        "artifact_id": artifact_id,
        "source_url": source_url,
        "expected": raw,
        "local_input": local_input,
    }


@pytest.mark.parametrize("module", [conftest_tool, gitleaks_tool])
def test_archive_installers_bound_the_selected_member_read_by_the_locked_installed_size(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module: object,
) -> None:
    observed: list[int] = []

    class Stream:
        def read(self, size: int = -1) -> bytes:
            observed.append(size)
            return b"four"

    class Member:
        def isfile(self) -> bool:
            return True

    class Archive:
        def __enter__(self) -> Archive:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def getmember(self, _path: str) -> Member:
            return Member()

        def extractfile(self, _member: Member) -> Stream:
            return Stream()

    monkeypatch.setattr(module.tarfile, "open", lambda *_args, **_kwargs: Archive())  # type: ignore[attr-defined]
    installed = SimpleNamespace(path="tool", size=3, sha256=hashlib.sha256(b"any").hexdigest())

    with pytest.raises(RuntimeError, match="differs from the reviewed lock manifest"):
        module._install_locked_binary(b"archive", installed, tmp_path / "tool")  # type: ignore[attr-defined]
    assert observed == [installed.size + 1]


def test_vale_bounds_the_selected_member_read_by_the_locked_installed_size(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[int] = []

    class Stream:
        def read(self, size: int = -1) -> bytes:
            observed.append(size)
            return b"four"

    class Member:
        def isfile(self) -> bool:
            return True

    class Archive:
        def __enter__(self) -> Archive:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def getmember(self, _path: str) -> Member:
            return Member()

        def extractfile(self, _member: Member) -> Stream:
            return Stream()

    monkeypatch.setattr(vale_tool.tarfile, "open", lambda *_args, **_kwargs: Archive())
    expected_sha256 = hashlib.sha256(b"any").hexdigest()
    vale_path = tmp_path / "vale"

    with pytest.raises(RuntimeError, match="size differs from the reviewed lock manifest"):
        vale_tool._extract_binary(
            b"archive",
            vale_path,
            expected_size=3,
            expected_sha256=expected_sha256,
        )
    assert observed == [4]
