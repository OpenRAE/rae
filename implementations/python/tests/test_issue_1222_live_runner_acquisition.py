"""Issue #1222 — govern live-runner VM and native package acquisition (row I13).

These hermetic checks cover the in-repository slices of the operations T13 and
T21 acceptance cases plus the admission wiring. They never require libvirt,
QEMU, AWS, a network or the frozen tooling validator; the full live T07/T13/T21
qualification is operator-run and recorded separately (see
``docs/decisions/package-artifacts/operations.md`` and the pending live-runner
qualification record).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REAL_DAEMON = REPO_ROOT / "tools" / "real-daemon"
SMOKE_SCRIPT = REAL_DAEMON / "run_aws_smoke.sh"
GUEST_SCRIPT = REAL_DAEMON / "run_aws_guest_certify.sh"

CIRROS_SHA256 = "07e44a73e54c94d988028515403c1ed762055e01b83a767edf3c2b387f78ce00"
CIRROS_SIZE = 21430272


def _load_json(relative: str) -> dict:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _script_code(script: Path) -> str:
    """Return only the executable lines of a shell script (drop comment lines).

    The header comments legitimately name the removed anti-patterns (curl,
    ``security_driver``); the safety assertions target actual command lines.
    """

    return "\n".join(
        line for line in script.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
    )


def _load_real_daemon_module(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, REAL_DAEMON / f"{name}.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


def _live_runner_inputs() -> types.ModuleType:
    return _load_real_daemon_module("live_runner_inputs")


# --------------------------------------------------------------------------- #
# AC1 — CirrOS is pinned as an admitted VM base image (digest + size + source). #
# --------------------------------------------------------------------------- #


def test_cirros_guest_disk_is_pinned_in_the_artifact_lock() -> None:
    lock = _load_json("implementations/tooling/artifacts.lock.json")
    artifact = next((a for a in lock["artifacts"] if a["artifact_id"] == "cirros-guest-disk"), None)
    assert artifact is not None, "cirros-guest-disk must be admitted in the artifact lock"
    assert artifact["artifact_class"] == "vm-base-image"
    assert artifact["availability_class"] == "L"
    (platform,) = artifact["platforms"]
    (raw,) = platform["raw_manifest"]
    (installed,) = platform["installed_manifest"]
    assert raw["sha256"] == CIRROS_SHA256
    assert raw["size"] == CIRROS_SIZE
    assert installed["sha256"] == CIRROS_SHA256
    assert installed["size"] == CIRROS_SIZE
    assert platform["profile_ids"] == ["live-runner-linux-x86_64"]
    assert all(url.startswith("https://") for url in platform["source_urls"])


def test_vm_base_image_class_is_admitted_by_the_lock_schema() -> None:
    schema = _load_json("implementations/tooling/schemas/artifact-lock.schema.json")
    enum = schema["$defs"]["artifact"]["properties"]["artifact_class"]["enum"]
    assert "vm-base-image" in enum


# --------------------------------------------------------------------------- #
# AC3 — an exact qualified host profile that exposes the native dependencies.   #
# --------------------------------------------------------------------------- #


def _live_runner_host() -> dict:
    profiles = _load_json("implementations/tooling/profiles/development-profiles.json")
    host = next(
        (h for h in profiles["host_profiles"] if h["host_profile_id"] == "live-runner-ubuntu-24.04-x86_64"), None
    )
    assert host is not None
    return host


def test_live_runner_host_profile_is_qualified_and_least_privilege() -> None:
    host = _live_runner_host()
    assert host["host_security_control_changes"] == "prohibited"
    assert host["proof_support"] == "unsupported"
    assert host["native_repository_identity"] == "ubuntu:noble:signed-archive"
    # cpython-3.14 is the declared bootstrap interpreter (execution-bound).
    assert "cpython-3.14" in set(host["bootstrap_payload_ids"])
    required = set(host["required_capability_ids"])
    assert {"qemu", "libvirt-daemon", "libvirt-client"} <= required
    # TCG is used, so KVM is optional, not required.
    assert "kvm-access" not in required
    assert "kvm-access" in set(host["optional_capability_ids"])
    packages = set(host["host_prerequisite_package_ids"])
    assert {"qemu-system-x86", "libvirt-daemon-system", "libvirt-dev", "genisoimage"} <= packages
    assert {"build-essential", "python3-dev", "pkg-config"} <= packages  # native build prerequisites


def test_scripts_install_only_reviewed_host_profile_packages() -> None:
    """The apt install list in each runner is a subset of the reviewed profile set."""

    declared = set(_live_runner_host()["host_prerequisite_package_ids"])
    for script in (SMOKE_SCRIPT, GUEST_SCRIPT):
        text = script.read_text(encoding="utf-8")
        match = re.search(r"apt-get install -y ([^\n]+)", text)
        assert match is not None, f"{script.name} must install its native packages via apt-get"
        installed = set(match.group(1).split())
        assert installed <= declared, (
            f"{script.name} installs packages not reviewed in the host profile: {installed - declared}"
        )


# --------------------------------------------------------------------------- #
# Admission wiring — inventory coverage and selector bindings.                  #
# --------------------------------------------------------------------------- #


def test_cirros_runtime_selection_is_declared_for_its_only_consumer() -> None:
    bindings = _load_json("implementations/tooling/selector-bindings.json")
    version_binding = next(b for b in bindings["bindings"] if b["artifact_id"] == "cirros-guest-disk")
    assert version_binding["consumers"][0]["path"] == "tools/tool_versions.py"


# --------------------------------------------------------------------------- #
# AC2/AC4 — the libvirt-python closure is exact, hash-bound and offline.        #
# --------------------------------------------------------------------------- #


def test_libvirt_python_pin_is_exact_version_and_hash() -> None:
    module = _live_runner_inputs()
    pin = module._libvirt_python_pin()
    assert pin["name"] == "libvirt-python"
    assert pin["version"] == "12.7.0"
    assert pin["sha256"] == "03a6800a3cc7657267e2516f579ce95c93d6351182caf03f92a49556685bf8bf"


def test_libvirt_python_pin_rejects_an_unpinned_requirement(tmp_path: Path) -> None:
    module = _live_runner_inputs()
    loose = tmp_path / "loose.txt"
    loose.write_text("libvirt-python\n", encoding="utf-8")  # no version, no hash
    module.LIBVIRT_PYTHON_REQUIREMENTS = loose
    with pytest.raises(RuntimeError):
        module._libvirt_python_pin()


def test_requirements_pin_the_native_binding_and_its_build_backend() -> None:
    """The fetch authority and install authority for the offline closure cannot drift."""

    text = _live_runner_inputs().LIBVIRT_PYTHON_REQUIREMENTS.read_text()
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    pins = [re.fullmatch(r"([A-Za-z0-9._-]+)==[^ ]+ --hash=sha256:[0-9a-f]{64}", line) for line in lines]
    assert all(pins)
    assert {pin.group(1) for pin in pins} == {"libvirt-python", "setuptools", "wheel"}


# --------------------------------------------------------------------------- #
# T13 slice — object admission verifies bytes and rejects tampering.            #
# --------------------------------------------------------------------------- #


def test_admit_bytes_writes_verified_object_and_rejects_tampering(tmp_path: Path) -> None:
    module = _live_runner_inputs()
    data = b"a-verified-guest-object"
    digest = hashlib.sha256(data).hexdigest()
    target = tmp_path / "obj" / "cirros.img"

    written = module._admit_bytes(data, expected_sha256=digest, expected_size=len(data), target=target)
    assert written == target
    assert target.read_bytes() == data

    with pytest.raises(RuntimeError):
        module._admit_bytes(b"tampered", expected_sha256=digest, expected_size=len(data), target=tmp_path / "bad.img")


def test_acquire_cirros_full_valid_path_writes_the_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the complete selection -> acquire -> admit path, not only rejection."""

    module = _live_runner_inputs()
    data = b"cirros-disk-bytes"
    digest = hashlib.sha256(data).hexdigest()
    entry = types.SimpleNamespace(path="cirros.img", sha256=digest, size=len(data))
    selection = types.SimpleNamespace(
        source_urls=["https://example/cirros.img"], raw_manifest=[entry], installed_manifest=[entry]
    )

    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", lambda **_: selection)
    monkeypatch.setattr(module, "acquire_locked_bytes", lambda **_: data)

    target = tmp_path / "cirros.img"
    assert module.acquire_cirros_guest_disk(target) == target
    assert target.read_bytes() == data


def test_acquire_cirros_rejects_installed_manifest_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _live_runner_inputs()
    data = b"cirros-disk-bytes"
    raw = types.SimpleNamespace(path="cirros.img", sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    installed = types.SimpleNamespace(path="cirros.img", sha256="0" * 64, size=len(data))  # wrong installed digest
    selection = types.SimpleNamespace(
        source_urls=["https://example/cirros.img"], raw_manifest=[raw], installed_manifest=[installed]
    )
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", lambda **_: selection)
    monkeypatch.setattr(module, "acquire_locked_bytes", lambda **_: data)
    with pytest.raises(RuntimeError):
        module.acquire_cirros_guest_disk(tmp_path / "cirros.img")


# --------------------------------------------------------------------------- #
# T21 slice — the scripts carry no unsafe acquisition or host-security patterns. #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("script", [SMOKE_SCRIPT, GUEST_SCRIPT], ids=["smoke", "guest-certify"])
def test_scripts_have_no_pipe_to_shell_or_ungoverned_download(script: Path) -> None:
    code = _script_code(script)
    assert "| sh" not in code, "no pipe-to-shell bootstrap"
    assert "astral.sh/uv/install.sh" not in code, "no remote uv installer bootstrap"
    assert "curl" not in code, "no ad-hoc curl acquisition (inputs are pre-seeded)"


@pytest.mark.parametrize("script", [SMOKE_SCRIPT, GUEST_SCRIPT], ids=["smoke", "guest-certify"])
def test_scripts_do_not_weaken_host_security(script: Path) -> None:
    code = _script_code(script)
    assert "security_driver" not in code, "must not disable the QEMU security driver"
    assert "sudo bash -lc" not in code, "no broad sudo login shell"


@pytest.mark.parametrize("script", [SMOKE_SCRIPT, GUEST_SCRIPT], ids=["smoke", "guest-certify"])
def test_scripts_authenticate_the_host_key_before_connecting(script: Path) -> None:
    code = _script_code(script)
    assert "StrictHostKeyChecking=no" not in code, "must not disable host-key verification"
    assert "StrictHostKeyChecking=accept-new" not in code, "trust-on-first-use is not sufficient"
    assert "StrictHostKeyChecking=yes" in code, "the pinned host key must be strictly verified"
    assert "get-console-output" in code, "the host key must be pinned from the authenticated console output"


@pytest.mark.parametrize("script", [SMOKE_SCRIPT, GUEST_SCRIPT], ids=["smoke", "guest-certify"])
def test_scripts_are_frozen_hash_pinned_and_require_explicit_inputs(script: Path) -> None:
    code = _script_code(script)
    assert "set -euo pipefail" in code
    assert "sync --frozen" in code, "uv sync must be frozen"
    assert "--require-hashes" in code, "libvirt-python install must be hash-pinned"
    assert "--build-constraints" in code
    assert "--default-index https://pypi.org/simple" in code
    assert "SSH_INGRESS_CIDR" in code, "ingress CIDR must be explicit"
    assert "THIRD_PARTY_NOTICES.md" in code, "the mandatory packaging input must be in the source handoff"


@pytest.mark.parametrize("script", [SMOKE_SCRIPT, GUEST_SCRIPT], ids=["smoke", "guest-certify"])
def test_scripts_execution_bind_image_and_interpreter(script: Path) -> None:
    """Image, native packages and interpreter are bound to reviewed authorities, not floated/ambient."""

    code = _script_code(script)
    # Image resolved by exact reviewed Canonical name + owner, never "newest".
    assert "Name=name,Values=$IMAGE_NAME" in code, "the AMI must resolve by exact reviewed image name"
    assert "sort_by(Images" not in code, "must not float to the newest AMI"
    assert "snapshot.ubuntu.com" not in code
    assert "Check-Valid-Until" not in code
    # The declared cpython-3.14 interpreter is used and validated, not system python3.
    assert "cpython.tar.gz" in code, "the declared interpreter must be pre-seeded"
    assert "Python 3.14" in code, "the pre-seeded interpreter version must be validated"
    assert "--python /usr/bin/python3" not in code, "must not fall back to the ambient system interpreter"


def test_reviewed_bindings_are_declared_in_tool_versions() -> None:
    text = (REPO_ROOT / "tools" / "tool_versions.py").read_text(encoding="utf-8")
    assert 'LIVE_RUNNER_UBUNTU_IMAGE_OWNER = "099720109477"' in text
    assert "ubuntu-noble-24.04-amd64-server-" in text, "the reviewed image name serial must be pinned"


def test_smoke_verifies_the_pinned_cirros_identity() -> None:
    code = _script_code(SMOKE_SCRIPT)
    assert "RAES_CIRROS_SHA256" in code
    assert "RAES_CIRROS_SIZE" in code
    assert "RAES_LIBVIRT_RUN_DIR" in code, "smoke must use a scoped run directory"


def test_guest_certify_uses_the_fixed_argv_runner_and_preserves_evidence() -> None:
    code = _script_code(GUEST_SCRIPT)
    assert "guest_certify_run.py" in code, "guest-certify must use the committed fixed-argv runner"
    assert "--no-cirros" in code, "guest-certify builds its own appliance and skips CirrOS"
    # A failed run's evidence must be pulled before the EXIT trap tears the host down.
    assert "run_status=$?" in code, "the runner status must be captured without immediate exit"
    evidence_pull = code.index("scenario-evidence/libvirt-scenario-evidence-run.json")
    final_exit = code.index('exit "$copy_status"')
    assert evidence_pull < final_exit, "evidence must be pulled before the final exit"
    # A successful run whose required evidence could not be persisted must not exit 0.
    assert "copy_status=1" in code, "evidence-copy failure must be captured"
    assert 'exit "$run_status"' in code, "copy failure must fold into the exit status"
    assert 'exit "$copy_status"' in code, "copy failure must fold into the exit status"


@pytest.mark.parametrize("script", [SMOKE_SCRIPT, GUEST_SCRIPT], ids=["smoke", "guest-certify"])
def test_source_handoff_is_a_tracked_revision_bound_bundle(script: Path) -> None:
    """Only Git-tracked files are transferred, so ignored files (.env, .pypirc) never cross to the host."""

    code = _script_code(script)
    assert "git ls-files" in code, "the source handoff must transfer only tracked files"
    assert "rev-parse HEAD" in code, "the bundle must be revision-bound"
    assert "rsync -az" not in code, "must not rsync the whole working tree onto the host"


# --------------------------------------------------------------------------- #
# Behavioural coverage of the new security-enforcing entry points.             #
# --------------------------------------------------------------------------- #


def test_verify_object_identity_fails_closed(tmp_path: Path) -> None:
    module = _load_real_daemon_module("_object_identity")
    good = tmp_path / "obj.img"
    good.write_bytes(b"guest-bytes")
    digest = hashlib.sha256(b"guest-bytes").hexdigest()

    module.verify_object_identity(good, expected_sha256=digest, expected_size=len(b"guest-bytes"))  # happy path

    with pytest.raises(RuntimeError):  # missing file
        module.verify_object_identity(tmp_path / "absent.img", expected_sha256=digest, expected_size=11)
    with pytest.raises(RuntimeError):  # unpinned identity
        module.verify_object_identity(good, expected_sha256=None, expected_size=None)
    with pytest.raises(RuntimeError):  # size mismatch
        module.verify_object_identity(good, expected_sha256=digest, expected_size=999)
    with pytest.raises(RuntimeError):  # digest mismatch
        module.verify_object_identity(good, expected_sha256="0" * 64, expected_size=len(b"guest-bytes"))
    link = tmp_path / "link.img"
    link.symlink_to(good)
    with pytest.raises(RuntimeError):  # symlink rejected
        module.verify_object_identity(link, expected_sha256=digest, expected_size=len(b"guest-bytes"))


def test_stage_live_runner_inputs_manifest_matches_the_shell_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """The manifest carries every key the scripts' read_nested/read_top helpers consume."""

    module = _live_runner_inputs()

    def fake_fetch(_host: str, stage_dir: Path, ids: list[str]) -> list[dict]:
        out = []
        for aid in ids:
            rel = f"archives/{aid}/{aid}.tar.gz"
            target = stage_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x")
            out.append({"artifact_id": aid, "path": rel, "sha256": "0" * 64, "size": 1})
        return out

    monkeypatch.setattr("tools.bootstrap_profile.fetch_bootstrap_payloads", fake_fetch)

    def fake_cirros(target: Path, local_input=None):
        target.write_bytes(b"img")
        return target

    monkeypatch.setattr(module, "acquire_cirros_guest_disk", fake_cirros)

    stage = REPO_ROOT / ".cache" / "raes-sdl" / "test-live-runner-stage"
    import shutil

    shutil.rmtree(stage, ignore_errors=True)
    try:
        manifest = json.loads(module.stage_live_runner_inputs(stage, include_cirros=True).read_text())
        # exactly the keys the shell read_nested/read_top helpers dereference:
        assert manifest["base_image"]["owner"]
        assert manifest["base_image"]["name"]
        assert "native_repository_snapshot" not in manifest
        assert manifest["cpython"]["staged_path"]
        assert manifest["uv"]["staged_path"]
        assert manifest["libvirt_python"]["name"] == "libvirt-python"
        assert "python_closure" not in manifest
        assert manifest["cirros_guest_disk"]["sha256"]
        assert manifest["cirros_guest_disk"]["size"]

        shutil.rmtree(stage, ignore_errors=True)
        no_cirros = json.loads(module.stage_live_runner_inputs(stage, include_cirros=False).read_text())
        assert "cirros_guest_disk" not in no_cirros, "guest-certify staging must omit CirrOS"
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _install_fake_raes_operations(monkeypatch: pytest.MonkeyPatch, *, passed: bool) -> dict:
    calls: dict = {}

    evidence = types.ModuleType("raes_operations.libvirt_evidence_run")

    class _Report:
        def render(self) -> str:
            return "evidence-report"

    def _run(**kwargs):
        calls.update(kwargs)
        report = _Report()
        report.passed = passed
        return report

    evidence.run_libvirt_evidence_run = _run
    evidence.LibvirtEvidenceRunConfig = lambda **_: object()

    run_artifacts = types.ModuleType("raes_operations.run_artifacts")
    run_artifacts.is_valid_run_id_label = lambda s: bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", s))

    monkeypatch.setitem(sys.modules, "raes_operations", types.ModuleType("raes_operations"))
    monkeypatch.setitem(sys.modules, "raes_operations.libvirt_evidence_run", evidence)
    monkeypatch.setitem(sys.modules, "raes_operations.run_artifacts", run_artifacts)
    return calls


def test_guest_certify_run_validates_and_returns_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_raes_operations(monkeypatch, passed=True)
    gcr = _load_real_daemon_module("guest_certify_run")
    monkeypatch.setenv("RAES_GUEST_SCENARIO", str(tmp_path / "scenario.yaml"))
    monkeypatch.setenv("RAES_GUEST_PROJECT_DIR", str(tmp_path))

    monkeypatch.setenv("RAES_GUEST_RUN_ID", "bad id!")  # invalid run-id label -> rejected before any run
    assert gcr.main() == 2

    monkeypatch.setenv("RAES_GUEST_RUN_ID", "guest-ok-1")  # valid + passing report
    assert gcr.main() == 0

    monkeypatch.delenv("RAES_GUEST_SCENARIO")  # missing required env -> refused
    assert gcr.main() == 2


def test_guest_certify_run_propagates_a_failed_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_raes_operations(monkeypatch, passed=False)
    gcr = _load_real_daemon_module("guest_certify_run")
    monkeypatch.setenv("RAES_GUEST_RUN_ID", "guest-ok-1")
    monkeypatch.setenv("RAES_GUEST_SCENARIO", str(tmp_path / "scenario.yaml"))
    monkeypatch.setenv("RAES_GUEST_PROJECT_DIR", str(tmp_path))
    assert gcr.main() == 1


def test_tracked_bundle_pipeline_excludes_untracked_and_ignored_files(tmp_path: Path) -> None:
    """Execute the exact git ls-files | tar handoff and prove only tracked files transfer."""

    import subprocess
    import tarfile

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "src").mkdir()
    (repo / "src" / "tracked.py").write_text("ok\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=1\n", encoding="utf-8")  # ignored
    (repo / "src" / "untracked.txt").write_text("nope\n", encoding="utf-8")  # untracked
    subprocess.run(["git", "add", "src/tracked.py", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)

    bundle = tmp_path / "bundle.tar"
    listing = subprocess.Popen(["git", "ls-files", "-z", "--", "src", ".gitignore"], cwd=repo, stdout=subprocess.PIPE)
    with bundle.open("wb") as out:
        subprocess.run(
            ["tar", "--null", "--no-recursion", "-T", "-", "-cf", "-"],
            cwd=repo,
            stdin=listing.stdout,
            stdout=out,
            check=True,
        )
    assert listing.wait() == 0
    with tarfile.open(bundle) as archive:
        members = set(archive.getnames())
    assert "src/tracked.py" in members
    assert ".env" not in members, "ignored secret file must never enter the bundle"
    assert "src/untracked.txt" not in members, "untracked file must never enter the bundle"
