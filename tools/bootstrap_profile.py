#!/usr/bin/env python3
"""Inspect and provision reviewed development host prerequisites.

Policy documents contain capability identifiers and package names only.  This
module owns the small fixed mapping from those identifiers to native commands;
it never evaluates policy data as shell input and never implements HTTP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as runtime_platform
import re
import stat
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from tools import maintained_client_acquisition
from tools.tooling_policy_gate import (
    load_tooling_host_profile_selection_with_current_interpreter as load_tooling_host_profile_selection,
)
from tools.tooling_policy_gate import (
    safe_tooling_cache_parent,
)

PROBE_TIMEOUT_SECONDS = 15
MAX_PROBE_OUTPUT_BYTES = 8192
_MINIMUM_CURL = (8, 4, 0)
_OBSERVED_VERSION_RE = re.compile(r"(\d{1,10})[.](\d{1,10})(?:[.](\d{1,10}))?")
_PROBE_ENV = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
_SYSTEM_CURL = maintained_client_acquisition.SYSTEM_CURL
_GENERIC_TOOL_HOST_PROFILES = {
    "linux-x86_64": "public-ubuntu-24.04-x86_64",
    "linux-arm64": "public-linux-arm64",
    "macos-arm64": "public-macos-arm64",
}
curl_qualification_argv = maintained_client_acquisition.curl_transfer_argv
curl_version_is_supported = maintained_client_acquisition.curl_version_is_supported


def run_curl_qualification(  # NOSONAR -- explicit fail-closed outcomes are part of the qualification record.
    executable: Path,
    url: str,
    output: Path,
    *,
    ca_cert: Path | None,
    max_bytes: int,
    max_time_seconds: int | None = None,
    budget: maintained_client_acquisition.TransferBudget = maintained_client_acquisition.GENERIC_TRANSFER_BUDGET,
) -> dict[str, str]:
    """Exercise the real selected curl and classify only sanitized outcomes."""

    result = maintained_client_acquisition.run_curl_transfer(
        executable,
        url,
        output,
        ca_cert=ca_cert,
        max_bytes=max_bytes,
        max_time_seconds=max_time_seconds,
        budget=budget,
    )
    if result["reason_code"] == "curl-size-limit-enforced":
        return {"outcome": "passed", "reason_code": result["reason_code"]}
    return result


def inspect_executable(  # NOSONAR -- explicit fail-closed outcomes are part of the qualification record.
    capability_id: str,
    executable: Path,
    version_args: tuple[str, ...],
    *,
    expected_version: str,
) -> dict[str, str]:
    """Run one fixed version probe and return a sanitized logical result."""

    try:
        completed = subprocess.run(
            [str(executable), *version_args],
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=dict(_PROBE_ENV),
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-unavailable",
        }
    if completed.returncode != 0:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-exit",
        }
    observed = f"{completed.stdout}\n{completed.stderr}"
    if len(observed.encode("utf-8")) > MAX_PROBE_OUTPUT_BYTES:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-output-limit",
        }
    if expected_version not in observed:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-version",
        }
    return {
        "capability_id": capability_id,
        "outcome": "passed",
        "version": expected_version,
    }


def observe_executable(  # NOSONAR -- explicit fail-closed outcomes are part of the qualification record.
    capability_id: str,
    executable: Path,
    version_args: tuple[str, ...],
    *,
    minimum_version: tuple[int, int, int] | None = None,
) -> dict[str, str]:
    """Record one sanitized native-client version from a fixed probe."""

    try:
        completed = subprocess.run(
            [str(executable), *version_args],
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=dict(_PROBE_ENV),
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-unavailable",
        }
    if completed.returncode != 0:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-exit",
        }
    observed = f"{completed.stdout}\n{completed.stderr}"
    if len(observed.encode("utf-8")) > MAX_PROBE_OUTPUT_BYTES:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-output-limit",
        }
    match = _OBSERVED_VERSION_RE.search(observed)
    if match is None:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-version",
        }
    parts = tuple(int(part or 0) for part in match.groups())
    if minimum_version is not None and parts < minimum_version:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": "native-client-version",
        }
    return {
        "capability_id": capability_id,
        "outcome": "passed",
        "version": match.group(0),
    }


def _file_identity_result(capability_id: str, path: Path, unavailable_reason: str) -> dict[str, str]:
    try:
        identity = _sha256(path)
    except OSError:
        return {
            "capability_id": capability_id,
            "outcome": "failed",
            "reason_code": unavailable_reason,
        }
    return {
        "capability_id": capability_id,
        "outcome": "passed",
        "observed_identity": identity,
    }


def _native_client_results(  # NOSONAR -- audited capability map is intentionally explicit.
    host: dict[str, object],
) -> list[dict[str, str]]:
    platform_id = str(host["platform_id"])
    if platform_id.startswith("linux-"):
        paths = {
            "git": Path("/usr/bin/git"),
            "curl-unknown-length-max-filesize": _SYSTEM_CURL,
            "sha256": Path("/usr/bin/sha256sum"),
            "gh-cli": Path("/usr/bin/gh"),
        }
    else:
        brew_root = Path("/opt/homebrew")
        paths = {
            "git": Path("/usr/bin/git"),
            "curl-unknown-length-max-filesize": _SYSTEM_CURL,
            "sha256": Path("/usr/bin/shasum"),
            "gh-cli": brew_root / "bin/gh",
        }
    arguments = {
        "git": ("--version",),
        "curl-unknown-length-max-filesize": ("--version",),
        "sha256": ("--version",),
        "gh-cli": ("--version",),
    }
    required = set(host["required_capability_ids"])
    results = [
        observe_executable(
            capability_id,
            path,
            arguments[capability_id],
            minimum_version=_MINIMUM_CURL if capability_id == "curl-unknown-length-max-filesize" else None,
        )
        for capability_id, path in paths.items()
        if capability_id in required
    ]
    ca_path = Path("/etc/ssl/certs/ca-certificates.crt" if platform_id.startswith("linux-") else "/etc/ssl/cert.pem")
    if "ca-roots" in required:
        results.append(_file_identity_result("ca-roots", ca_path, "ca-store-unavailable"))
    if "bubblewrap" in required:
        results.append(observe_executable("bubblewrap", Path("/usr/bin/bwrap"), ("--version",)))
    if "fontconfig" in required:
        results.append(observe_executable("fontconfig", Path("/usr/bin/fc-match"), ("--version",)))
    if "fonts" in required:
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        results.append(_file_identity_result("fonts", font_path, "font-unavailable"))
    if "locale-c-utf-8" in required:
        results.append(
            inspect_executable(
                "locale-c-utf-8",
                Path("/usr/bin/locale"),
                ("-a",),
                expected_version="C.utf8",
            )
        )
    return results


def native_setup_plan(host: dict[str, object]) -> dict[str, object]:
    """Return the reviewed prerequisites without running package-manager commands."""

    return {
        "host_profile_id": host["host_profile_id"],
        "native_family": host["native_family"],
        "native_repository_identity": host["native_repository_identity"],
        "trust_root_refs": host["trust_root_refs"],
        "host_prerequisite_package_ids": host["host_prerequisite_package_ids"],
        "host_trust_root_refs": host["trust_root_refs"],
        "outcome": "not-run",
        "reason_code": "operator-installs-native-prerequisites",
    }


def proof_support_outcome(platform_id: str) -> str:
    """Return the explicit native proof support classification."""

    return "required" if platform_id == "linux-x86_64" else "unsupported"


def _generic_tool_local_artifacts(
    local_input_root: Path | None,
) -> dict[str, dict[str, object]]:
    if local_input_root is None:
        return {}
    if not local_input_root.is_dir() or local_input_root.is_symlink():
        raise ValueError("generic-tool local input root must be a regular directory")

    from tools.tooling_policy_gate import host_platform_id

    host_profile_id = _GENERIC_TOOL_HOST_PROFILES.get(host_platform_id())
    if host_profile_id is None:
        raise RuntimeError("generic-tool local inputs do not support this host platform")
    _host, artifacts, _policy_sha256 = _load_host_selection(host_profile_id)
    return artifacts


def _generic_tool_local_input(
    local_input_root: Path | None,
    local_artifacts: dict[str, dict[str, object]],
    artifact_id: str,
    version: str,
) -> Path | None:
    if local_input_root is None:
        return None
    artifact = local_artifacts.get(artifact_id)
    if artifact is None or artifact.get("version") != version:
        raise RuntimeError(f"{artifact_id} is not selected by the reviewed host profile")
    platform = artifact.get("platform")
    if not isinstance(platform, dict):
        raise RuntimeError(f"{artifact_id} host selection has an invalid platform")
    raw_manifest = platform.get("raw_manifest")
    if not isinstance(raw_manifest, list) or len(raw_manifest) != 1:
        raise RuntimeError(f"{artifact_id} lock selection must contain one raw asset")
    raw = raw_manifest[0]
    if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
        raise RuntimeError(f"{artifact_id} lock selection has an invalid raw asset")
    return local_input_root / "archives" / artifact_id / raw["path"]


def _default_generic_tool_selections(
    local_input_root: Path | None = None,
) -> tuple[tuple[str, Path, tuple[str, ...], str], ...]:
    from tools.gitleaks_tool import ensure_gitleaks
    from tools.osv_scanner_tool import ensure_osv_scanner
    from tools.policy.conftest_tool import ensure_conftest
    from tools.tool_versions import (
        CONTFEST_VERSION,
        GITLEAKS_VERSION,
        OSV_SCANNER_VERSION,
        VALE_VERSION,
    )
    from tools.vale_tool import ensure_vale

    local_artifacts = _generic_tool_local_artifacts(local_input_root)

    def local_input(artifact_id: str, version: str) -> Path | None:
        return _generic_tool_local_input(local_input_root, local_artifacts, artifact_id, version)

    return (
        (
            "conftest",
            ensure_conftest(local_input=local_input("conftest", CONTFEST_VERSION)),
            ("--version",),
            CONTFEST_VERSION,
        ),
        (
            "gitleaks",
            ensure_gitleaks(local_input=local_input("gitleaks", GITLEAKS_VERSION)),
            ("version",),
            GITLEAKS_VERSION,
        ),
        (
            "osv-scanner",
            ensure_osv_scanner(local_input=local_input("osv-scanner", OSV_SCANNER_VERSION)),
            ("--version",),
            OSV_SCANNER_VERSION,
        ),
        (
            "vale",
            ensure_vale(local_input=local_input("vale", VALE_VERSION)),
            ("--version",),
            VALE_VERSION,
        ),
    )


def qualify_generic_tools(
    *,
    selections: Sequence[tuple[str, Path, tuple[str, ...], str]] | None = None,
    local_input_root: Path | None = None,
) -> dict[str, object]:
    """Execute every selected generic tool and return bounded logical evidence."""

    if selections is not None and local_input_root is not None:
        raise ValueError("generic-tool selections and local input root are mutually exclusive")
    selected = tuple(selections) if selections is not None else _default_generic_tool_selections(local_input_root)
    results: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="raes-generic-tool-probe-") as probe_root:
        probe_environment = {
            **_PROBE_ENV,
            "XDG_CACHE_HOME": f"{probe_root}/cache",
            "XDG_CONFIG_HOME": f"{probe_root}/config",
            "XDG_DATA_HOME": f"{probe_root}/data",
        }
        for capability_id, executable, version_args, version in selected:
            try:
                completed = subprocess.run(
                    [str(executable), *version_args],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=PROBE_TIMEOUT_SECONDS,
                    env=probe_environment,
                )
            except (OSError, subprocess.SubprocessError):
                results.append(
                    {
                        "capability_id": capability_id,
                        "outcome": "failed",
                        "reason_code": "native-client-unavailable",
                    }
                )
                continue
            if completed.returncode != 0:
                results.append(
                    {
                        "capability_id": capability_id,
                        "outcome": "failed",
                        "reason_code": "native-client-exit",
                    }
                )
            else:
                results.append(
                    {
                        "capability_id": capability_id,
                        "outcome": "passed",
                        "version": version,
                    }
                )
    return {
        "outcome": "passed" if results and all(item["outcome"] == "passed" for item in results) else "failed",
        "results": results,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:  # NOSONAR -- callers bind this bounded regular file to a repo or kit root.
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _transfer_budget(
    artifact: dict[str, object],
) -> maintained_client_acquisition.TransferBudget:
    """Select the separately qualified large-object budget only for native proof tools."""

    if artifact.get("artifact_class") == "native-tool":
        return maintained_client_acquisition.LARGE_OBJECT_TRANSFER_BUDGET
    return maintained_client_acquisition.GENERIC_TRANSFER_BUDGET


def fetch_bootstrap_payloads(  # NOSONAR -- explicit validation branches keep acquisition fail-closed.
    host_profile_id: str,
    kit_root: Path,
    artifact_ids: Sequence[str],
    *,
    locator_ref: str | None = None,
) -> list[dict[str, object]]:
    """Fetch exact raw payloads with the qualified native curl client."""

    if not kit_root.is_dir() or kit_root.is_symlink():
        raise ValueError("bootstrap root must be a regular directory")
    host, artifacts, _ = _load_host_selection(host_profile_id)
    requested = sorted(set(artifact_ids))
    if not requested or not set(requested) <= set(host["bootstrap_payload_ids"]):
        raise ValueError("bootstrap fetch must select reviewed payload ids")
    if locator_ref is not None and len(requested) != 1:
        raise ValueError("bootstrap locator selection requires exactly one artifact")
    results: list[dict[str, object]] = []
    for artifact_id in requested:
        artifact = artifacts[artifact_id]
        platform = artifact["platform"]
        raw_manifest = platform["raw_manifest"]
        # A different approved locator is explicit, never an automatic failover.
        source_urls = platform["source_urls"]
        if len(raw_manifest) != 1 or not source_urls:
            raise ValueError("bootstrap fetch requires one exact source object per payload")
        source_url = source_urls[0]
        if locator_ref is not None:
            locator_refs = artifact["source"]["locator_refs"]
            if locator_ref not in locator_refs or len(locator_refs) != len(source_urls):
                raise ValueError("bootstrap locator is not approved by the reviewed lock")
            source_url = source_urls[locator_refs.index(locator_ref)]
        expected = raw_manifest[0]
        target = kit_root / "archives" / artifact_id / expected["path"]
        safe_tooling_cache_parent(kit_root, target, artifact_id=artifact_id)
        if target.exists() or target.is_symlink():
            raise ValueError(f"bootstrap {artifact_id} raw target already exists")
        transfer = run_curl_qualification(
            _SYSTEM_CURL,
            source_url,
            target,
            ca_cert=None,
            max_bytes=expected["size"],
            budget=_transfer_budget(artifact),
        )
        if (
            transfer.get("outcome") != "passed"
            or not target.is_file()
            or target.is_symlink()
            or target.stat().st_size != expected["size"]
            or _sha256(target) != expected["sha256"]
        ):
            target.unlink(missing_ok=True)
            raise ValueError(f"bootstrap {artifact_id} raw payload failed exact verification")
        results.append(
            {
                "artifact_id": artifact_id,
                "path": target.relative_to(kit_root).as_posix(),
                "sha256": expected["sha256"],
                "size": expected["size"],
            }
        )
    return results


def install_python_payload(  # NOSONAR -- archive validation is intentionally explicit and auditable.
    host_profile_id: str, kit_root: Path, python_artifact_id: str
) -> dict[str, str]:
    """Verify and extract one locked relocatable CPython payload."""

    _host, artifacts, _policy_sha256 = _load_host_selection(host_profile_id)
    artifact = artifacts.get(python_artifact_id)
    if artifact is None:
        raise ValueError("bootstrap Python payload is not selected by the host profile")
    raw_manifest = artifact["platform"]["raw_manifest"]
    if not isinstance(raw_manifest, list) or len(raw_manifest) != 1:
        raise ValueError("bootstrap Python payload must have exactly one raw archive")
    raw = raw_manifest[0]
    archive = kit_root / "archives" / python_artifact_id / raw["path"]
    if (
        not archive.is_file()
        or archive.is_symlink()
        or archive.stat().st_size != raw["size"]
        or _sha256(archive) != raw["sha256"]
    ):
        raise ValueError("bootstrap Python archive differs from the validated lock")
    destination = kit_root / "python" / f"cpython-{artifact['version']}"
    if destination.exists() or destination.is_symlink():
        raise ValueError("bootstrap Python destination must be new")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".python-extract-", dir=kit_root) as temporary_dir:
        temporary_root = Path(temporary_dir)
        try:
            with tarfile.open(archive, mode="r:gz") as bundle:
                members = bundle.getmembers()
                if not members or any(PurePosixPath(member.name).parts[:1] != ("python",) for member in members):
                    raise ValueError("bootstrap Python archive has an unexpected root")
                bundle.extractall(temporary_root, filter="data")
        except (OSError, tarfile.TarError) as exc:
            raise ValueError("bootstrap Python archive could not be extracted safely") from exc
        extracted = temporary_root / "python"
        if not extracted.is_dir() or extracted.is_symlink():
            raise ValueError("bootstrap Python archive omits its payload root")
        extracted.rename(destination)
    return {
        "artifact_id": python_artifact_id,
        "path": destination.relative_to(kit_root).as_posix(),
    }


def install_uv_payload(  # NOSONAR -- archive validation is intentionally explicit and auditable.
    host_profile_id: str, kit_root: Path, uv_artifact_id: str
) -> dict[str, str]:
    """Verify and extract the locked uv client from an imported payload kit.

    The CI and container bootstrap paths have no host-supplied uv to copy,
    so the reviewed raw archive is the only admitted source of the client that
    later runs the frozen validator.
    """

    _host, artifacts, _policy_sha256 = _load_host_selection(host_profile_id)
    artifact = artifacts.get(uv_artifact_id)
    if artifact is None:
        raise ValueError("bootstrap uv payload is not selected by the host profile")
    raw_manifest = artifact["platform"]["raw_manifest"]
    if not isinstance(raw_manifest, list) or len(raw_manifest) != 1:
        raise ValueError("bootstrap uv payload must have exactly one raw archive")
    raw = raw_manifest[0]
    archive = kit_root / "archives" / uv_artifact_id / raw["path"]
    if (
        not archive.is_file()
        or archive.is_symlink()
        or archive.stat().st_size != raw["size"]
        or _sha256(archive) != raw["sha256"]
    ):
        raise ValueError("bootstrap uv archive differs from the validated lock")
    destination = kit_root / "bin"
    destination.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    with tempfile.TemporaryDirectory(prefix=".uv-extract-", dir=kit_root) as temporary_dir:
        temporary_root = Path(temporary_dir)
        try:
            with tarfile.open(archive, mode="r:gz") as bundle:
                members = bundle.getmembers()
                roots = {PurePosixPath(member.name).parts[:1] for member in members}
                if not members or len(roots) != 1 or any(not (member.isfile() or member.isdir()) for member in members):
                    raise ValueError("bootstrap uv archive has an unexpected shape")
                bundle.extractall(temporary_root, filter="data")
        except (OSError, tarfile.TarError) as exc:
            raise ValueError("bootstrap uv archive could not be extracted safely") from exc
        extracted = temporary_root / next(iter(roots))[0]
        for name in ("uv", "uvx"):
            source = extracted / name
            target = destination / name
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"bootstrap uv archive omits its {name} client")
            if target.exists() or target.is_symlink():
                raise ValueError(f"bootstrap uv destination {name} must be new")
            source.rename(target)
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            installed.append(target.relative_to(kit_root).as_posix())
    return {
        "artifact_id": uv_artifact_id,
        "path": installed[0],
        "extra_path": installed[1],
    }


_PROOF_NATIVE_CAPABILITY_IDS = ("bubblewrap", "fontconfig", "fonts", "locale-c-utf-8")


def _proof_native_closure_result(host: dict[str, object]) -> dict[str, object]:
    """Probe the imported proof host's native Bubblewrap, font, and locale closure."""

    if host.get("proof_support") != "linux-x86_64-required":
        return {"outcome": "not-run", "results": []}
    closure_host = {
        **host,
        "required_capability_ids": list(_PROOF_NATIVE_CAPABILITY_IDS),
    }
    results = [
        result
        for result in _native_client_results(closure_host)
        if result["capability_id"] in _PROOF_NATIVE_CAPABILITY_IDS
    ]
    observed = {result["capability_id"] for result in results}
    passed = observed == set(_PROOF_NATIVE_CAPABILITY_IDS) and all(item["outcome"] == "passed" for item in results)
    return {"outcome": "passed" if passed else "failed", "results": results}


def _load_host_selection(
    host_profile_id: str,
) -> tuple[dict[str, object], dict[str, dict[str, object]], str]:
    selection = load_tooling_host_profile_selection(host_profile_id)
    host = selection["host_profile"]
    selected_artifacts = selection["artifacts"]
    policy_sha256 = selection["policy_sha256"]
    if not isinstance(host, dict) or not isinstance(selected_artifacts, list) or not isinstance(policy_sha256, str):
        raise RuntimeError("validated host selection has an invalid response shape")
    artifacts = {
        item["artifact_id"]: item
        for item in selected_artifacts
        if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
    }
    return host, artifacts, policy_sha256


def _safe_runner_image() -> str:
    values = [os.environ.get(name, "") for name in ("ImageOS", "ImageVersion", "RUNNER_ARCH")]
    return ":".join(value if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value) else "unavailable" for value in values)


def observe_host_identity(
    host: dict[str, object],
) -> tuple[str, str, list[dict[str, str]]]:
    """Validate the hosted-runner family and retain its exact observed release."""

    runner_image = _safe_runner_image()
    image_os, image_version, runner_arch = runner_image.split(":")
    observed_base = f"github-runner:{runner_image}"
    observed_repository = f"github-runner-package-set:{runner_image}"
    observed_family = f"github-hosted-runner:{image_os}:{runner_arch}"
    observed_repository_family = f"github-hosted-runner-package-set:{image_os}:{runner_arch}"
    metadata_available = (
        "unavailable" not in runner_image and re.fullmatch(r"20\d{6}\.\d{1,4}\.\d{1,3}", image_version) is not None
    )
    base_passed = observed_family == host["base_image_identity"] and metadata_available
    repository_passed = observed_repository_family == host["native_repository_identity"] and base_passed
    return (
        observed_base,
        observed_repository,
        [
            {
                "capability_id": "base-image",
                "outcome": "passed" if base_passed else "failed",
                "observed_identity": observed_base,
                **({} if base_passed else {"reason_code": "runner-image-mismatch"}),
            },
            {
                "capability_id": "native-repository",
                "outcome": "passed" if repository_passed else "failed",
                "observed_identity": observed_repository,
                **({} if repository_passed else {"reason_code": "native-repository-unobserved"}),
            },
        ],
    )


def _runtime_target(system: str, machine: str) -> str:
    normalized_machine = machine.lower().replace("amd64", "x86_64").replace("arm64", "aarch64")
    targets = {
        ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
        ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
        ("darwin", "x86_64"): "x86_64-apple-darwin",
        ("darwin", "aarch64"): "aarch64-apple-darwin",
    }
    return targets.get(
        (system.lower(), normalized_machine),
        f"unsupported-{system.lower()}-{normalized_machine}",
    )


def observe_current_python_identity() -> dict[str, str]:
    """Observe every lock-declared CPython identity field from the running interpreter."""

    gil_suffix = "t" if sysconfig.get_config_var("Py_GIL_DISABLED") else ""
    return {
        "implementation": runtime_platform.python_implementation(),
        "version": runtime_platform.python_version(),
        "abi": f"cp{sys.version_info[0]}{sys.version_info[1]}{gil_suffix}",
        "target": _runtime_target(runtime_platform.system(), runtime_platform.machine()),
    }


def _observed_uv_identity(version: str) -> dict[str, str]:
    return {
        "implementation": "uv",
        "version": version,
        "abi": "native",
        "target": _runtime_target(runtime_platform.system(), runtime_platform.machine()),
    }


# Local qualification harnesses and the canonical case each slice belongs to.
# A slice is bound evidence for part of a case; it never becomes a passed case.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    setup = subparsers.add_parser("setup-plan", help="render reviewed native prerequisites")
    setup.add_argument("host_profile_id")
    inspect = subparsers.add_parser("inspect-profile", help="run the reviewed read-only host probes")
    inspect.add_argument("host_profile_id")
    generic = subparsers.add_parser("generic-tools", help="execute the four locked generic tools")
    generic.add_argument("--local-input-root", type=Path)
    kit_fetch = subparsers.add_parser("fetch-inputs", help="fetch exact raw payloads with native curl")
    kit_fetch.add_argument("host_profile_id")
    kit_fetch.add_argument("kit_root", type=Path)
    kit_fetch.add_argument("--artifact-id", action="append", required=True)
    kit_fetch.add_argument("--locator-ref", help="approved same-byte locator for one selected artifact")
    kit_python = subparsers.add_parser("install-python", help="verify and extract locked CPython")
    kit_python.add_argument("host_profile_id")
    kit_python.add_argument("kit_root", type=Path)
    kit_python.add_argument("--python-artifact-id", required=True)
    kit_uv = subparsers.add_parser("install-uv", help="verify and extract the locked uv client")
    kit_uv.add_argument("host_profile_id")
    kit_uv.add_argument("kit_root", type=Path)
    kit_uv.add_argument("--uv-artifact-id", required=True)
    proof = subparsers.add_parser("proof-support", help="report the native proof support classification")
    proof.add_argument("platform_id")
    return parser.parse_args()


def main() -> int:  # NOSONAR -- CLI dispatch keeps operation exit semantics explicit.
    args = _parse_args()
    if args.operation == "setup-plan":
        host, _, _ = _load_host_selection(args.host_profile_id)
        print(json.dumps(native_setup_plan(host), sort_keys=True))
    elif args.operation == "inspect-profile":
        host, _, _ = _load_host_selection(args.host_profile_id)
        result = _native_client_results(host)
        print(json.dumps(result, sort_keys=True))
        return 0 if all(item["outcome"] == "passed" for item in result) else 1
    elif args.operation == "generic-tools":
        local_input_root = getattr(args, "local_input_root", None)
        result = (
            qualify_generic_tools(local_input_root=local_input_root)
            if local_input_root is not None
            else qualify_generic_tools()
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["outcome"] == "passed" else 1
    elif args.operation == "fetch-inputs":
        print(
            json.dumps(
                fetch_bootstrap_payloads(
                    args.host_profile_id,
                    args.kit_root,
                    args.artifact_id,
                    locator_ref=args.locator_ref,
                ),
                sort_keys=True,
            )
        )
    elif args.operation == "install-python":
        print(
            json.dumps(
                install_python_payload(args.host_profile_id, args.kit_root, args.python_artifact_id),
                sort_keys=True,
            )
        )
    elif args.operation == "install-uv":
        print(
            json.dumps(
                install_uv_payload(args.host_profile_id, args.kit_root, args.uv_artifact_id),
                sort_keys=True,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "platform_id": args.platform_id,
                    "proof_support": proof_support_outcome(args.platform_id),
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
