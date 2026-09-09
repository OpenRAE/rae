#!/usr/bin/env python3
"""Inspect and provision reviewed development host prerequisites.

Policy documents contain capability identifiers and package names only.  This
module owns the small fixed mapping from those identifiers to native commands;
it never evaluates policy data as shell input and never implements HTTP.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform as runtime_platform
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from tools.tooling_policy_gate import load_tooling_host_profile_selection, safe_tooling_cache_parent

PROBE_TIMEOUT_SECONDS = 15
MAX_PROBE_OUTPUT_BYTES = 8192
MAX_CASE_RESULT_BYTES = 65536
MAX_OFFLINE_MANIFEST_BYTES = 32 * 1024 * 1024
_CASE_IDS = {"T01", "T02", "T03", "T08", "T12"}
_MINIMUM_CURL = (8, 4, 0)
_VERSION_RE = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)")
_OBSERVED_VERSION_RE = re.compile(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?!\d)")
_PROBE_ENV = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}


def curl_version_is_supported(value: str) -> bool:
    """Return whether a curl version meets the unknown-length size floor."""

    match = _VERSION_RE.search(value)
    return match is not None and tuple(int(part) for part in match.groups()) >= _MINIMUM_CURL


def curl_qualification_argv(
    executable: Path,
    url: str,
    output: Path,
    *,
    ca_cert: Path | None,
    max_bytes: int,
    max_time_seconds: int = 30,
) -> list[str]:
    """Build the fixed native-client argv used by behavioral qualification."""

    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("curl qualification requires a credential-free HTTPS URL")
    if max_bytes < 1:
        raise ValueError("curl qualification size limit must be positive")
    if not 1 <= max_time_seconds <= 30:
        raise ValueError("curl qualification deadline must be between 1 and 30 seconds")
    argv = [
        str(executable),
        "--disable",
        "--silent",
        "--show-error",
        "--fail",
        "--location",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--max-redirs",
        "5",
        "--retry",
        "2",
        "--retry-delay",
        "1",
        "--retry-max-time",
        "15",
        "--connect-timeout",
        "5",
        "--max-time",
        str(max_time_seconds),
        "--max-filesize",
        str(max_bytes),
    ]
    if ca_cert is not None:
        argv.extend(("--cacert", str(ca_cert)))
    argv.extend(("--output", str(output), url))
    return argv


def run_curl_qualification(
    executable: Path,
    url: str,
    output: Path,
    *,
    ca_cert: Path | None,
    max_bytes: int,
    max_time_seconds: int = 30,
) -> dict[str, str]:
    """Exercise the real selected curl and classify only sanitized outcomes."""

    version_result = inspect_executable("curl", executable, ("--version",), expected_version="curl ")
    if version_result.get("outcome") != "passed":
        return {"outcome": "failed", "reason_code": "curl-unavailable"}
    try:
        version_probe = subprocess.run(
            [str(executable), "--version"],
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=dict(_PROBE_ENV),
        )
    except (OSError, subprocess.SubprocessError):
        return {"outcome": "failed", "reason_code": "curl-unavailable"}
    if version_probe.returncode != 0 or not curl_version_is_supported(version_probe.stdout):
        return {"outcome": "failed", "reason_code": "curl-version-inadequate"}
    try:
        completed = subprocess.run(
            curl_qualification_argv(
                executable,
                url,
                output,
                ca_cert=ca_cert,
                max_bytes=max_bytes,
                max_time_seconds=max_time_seconds,
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=max_time_seconds + 5,
            env=dict(_PROBE_ENV),
        )
    except subprocess.TimeoutExpired:
        output.unlink(missing_ok=True)
        return {"outcome": "failed", "reason_code": "curl-wall-deadline"}
    except OSError:
        output.unlink(missing_ok=True)
        return {"outcome": "failed", "reason_code": "curl-unavailable"}
    if completed.returncode == 63:
        output.unlink(missing_ok=True)
        return {"outcome": "passed", "reason_code": "curl-size-limit-enforced"}
    if completed.returncode in {35, 51, 58, 60, 77, 82, 83, 90, 91}:
        output.unlink(missing_ok=True)
        return {"outcome": "failed", "reason_code": "curl-tls-rejected"}
    if completed.returncode == 28:
        output.unlink(missing_ok=True)
        return {"outcome": "failed", "reason_code": "curl-transfer-deadline"}
    if completed.returncode != 0:
        output.unlink(missing_ok=True)
        return {"outcome": "failed", "reason_code": "curl-transfer-failed"}
    try:
        within_limit = output.is_file() and output.stat().st_size <= max_bytes
    except OSError:
        within_limit = False
    if not within_limit:
        output.unlink(missing_ok=True)
        return {"outcome": "failed", "reason_code": "curl-size-limit-bypassed"}
    return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}


def inspect_executable(
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


def observe_executable(
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


def _native_client_results(host: dict[str, object]) -> list[dict[str, str]]:
    platform_id = str(host["platform_id"])
    if platform_id.startswith("linux-"):
        paths = {
            "git": Path("/usr/bin/git"),
            "curl-unknown-length-max-filesize": Path("/usr/bin/curl"),
            "sha256": Path("/usr/bin/sha256sum"),
            "gh-cli": Path("/usr/bin/gh"),
        }
    else:
        brew_root = Path("/usr/local") if platform_id == "macos-x86_64" else Path("/opt/homebrew")
        paths = {
            "git": Path("/usr/bin/git"),
            "curl-unknown-length-max-filesize": Path("/usr/bin/curl"),
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
        try:
            ca_identity = _sha256(ca_path)
        except OSError:
            results.append(
                {
                    "capability_id": "ca-roots",
                    "outcome": "failed",
                    "reason_code": "ca-store-unavailable",
                }
            )
        else:
            results.append(
                {
                    "capability_id": "ca-roots",
                    "outcome": "passed",
                    "observed_identity": ca_identity,
                }
            )
    if "bubblewrap" in required:
        results.append(observe_executable("bubblewrap", Path("/usr/bin/bwrap"), ("--version",)))
    if "fontconfig" in required:
        results.append(observe_executable("fontconfig", Path("/usr/bin/fc-match"), ("--version",)))
    if "fonts" in required:
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        try:
            font_identity = _sha256(font_path)
        except OSError:
            results.append(
                {
                    "capability_id": "fonts",
                    "outcome": "failed",
                    "reason_code": "font-unavailable",
                }
            )
        else:
            results.append(
                {
                    "capability_id": "fonts",
                    "outcome": "passed",
                    "observed_identity": font_identity,
                }
            )
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
    """Return the reviewed prerequisites while refusing mutable native installation."""

    offline_kit = host["offline_kit"]
    return {
        "host_profile_id": host["host_profile_id"],
        "native_family": host["native_family"],
        "native_repository_identity": host["native_repository_identity"],
        "trust_root_refs": host["trust_root_refs"],
        "host_prerequisite_package_ids": offline_kit["host_prerequisite_package_ids"],
        "host_trust_root_refs": offline_kit["host_trust_root_refs"],
        "outcome": "not-run",
        "reason_code": "immutable-native-closure-required",
    }


def proof_support_outcome(platform_id: str) -> str:
    """Return the explicit native proof support classification."""

    return "required" if platform_id == "linux-x86_64" else "unsupported"


def _default_generic_tool_selections() -> tuple[tuple[str, Path, tuple[str, ...], str], ...]:
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

    return (
        ("conftest", ensure_conftest(), ("--version",), CONTFEST_VERSION),
        ("gitleaks", ensure_gitleaks(), ("version",), GITLEAKS_VERSION),
        ("osv-scanner", ensure_osv_scanner(), ("--version",), OSV_SCANNER_VERSION),
        ("vale", ensure_vale(), ("--version",), VALE_VERSION),
    )


def _offline_generic_tool_selections(
    repo_root: Path,
    platform_id: str,
    artifacts: dict[str, dict[str, object]],
) -> tuple[tuple[str, Path, tuple[str, ...], str], ...]:
    """Select a verified imported tool kit without entering acquisition code."""

    version_args = {
        "conftest": ("--version",),
        "gitleaks": ("version",),
        "osv-scanner": ("--version",),
        "vale": ("--version",),
    }
    selections: list[tuple[str, Path, tuple[str, ...], str]] = []
    for artifact_id, args in version_args.items():
        artifact = artifacts[artifact_id]
        platform = artifact["platform"]
        if platform["platform_id"] != platform_id:
            raise ValueError(f"offline {artifact_id} does not match the selected platform")
        installed = platform["installed_manifest"]
        if len(installed) != 1:
            raise ValueError(f"offline {artifact_id} must select exactly one installed binary")
        entry = installed[0]
        path = repo_root / ".cache" / "raes-sdl" / "tooling" / artifact_id / artifact["version"] / entry["path"]
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise ValueError(f"offline {artifact_id} binary is unavailable") from exc
        if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
            raise ValueError(f"offline {artifact_id} binary is not a regular file")
        if path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
            raise ValueError(f"offline {artifact_id} binary differs from the lock")
        selections.append((artifact_id, path, args, artifact["version"]))
    return tuple(selections)


def qualify_generic_tools(
    *,
    selections: Sequence[tuple[str, Path, tuple[str, ...], str]] | None = None,
) -> dict[str, object]:
    """Execute every selected generic tool and return bounded logical evidence."""

    selected = tuple(selections) if selections is not None else _default_generic_tool_selections()
    results: list[dict[str, str]] = []
    for capability_id, executable, version_args, version in selected:
        try:
            completed = subprocess.run(
                [str(executable), *version_args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=PROBE_TIMEOUT_SECONDS,
                env=dict(_PROBE_ENV),
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
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_offline_kit_payloads(
    host_profile_id: str,
    kit_root: Path,
    artifact_ids: Sequence[str],
) -> list[dict[str, object]]:
    """Fetch exact raw payloads with the qualified native curl client."""

    if not kit_root.is_dir() or kit_root.is_symlink():
        raise ValueError("offline kit root must be a regular directory")
    host, artifacts, _ = _load_host_selection(host_profile_id)
    requested = sorted(set(artifact_ids))
    if not requested or not set(requested) <= set(host["offline_kit"]["artifact_ids"]):
        raise ValueError("offline kit fetch must select reviewed payload ids")
    results: list[dict[str, object]] = []
    for artifact_id in requested:
        artifact = artifacts[artifact_id]
        platform = artifact["platform"]
        raw_manifest = platform["raw_manifest"]
        source_urls = platform["source_urls"]
        if len(raw_manifest) != 1 or len(source_urls) != 1:
            raise ValueError("offline kit fetch requires one exact source object per payload")
        expected = raw_manifest[0]
        target = kit_root / "archives" / artifact_id / expected["path"]
        safe_tooling_cache_parent(kit_root, target, artifact_id=artifact_id)
        if target.exists() or target.is_symlink():
            raise ValueError(f"offline kit {artifact_id} raw target already exists")
        transfer = run_curl_qualification(
            Path("/usr/bin/curl"),
            source_urls[0],
            target,
            ca_cert=None,
            max_bytes=expected["size"],
        )
        if (
            transfer.get("outcome") != "passed"
            or not target.is_file()
            or target.is_symlink()
            or target.stat().st_size != expected["size"]
            or _sha256(target) != expected["sha256"]
        ):
            target.unlink(missing_ok=True)
            raise ValueError(f"offline kit {artifact_id} raw payload failed exact verification")
        results.append(
            {
                "artifact_id": artifact_id,
                "path": target.relative_to(kit_root).as_posix(),
                "sha256": expected["sha256"],
                "size": expected["size"],
            }
        )
    return results


def _offline_kit_entries(kit_root: Path) -> list[dict[str, object]]:
    """Measure every offline-kit entry without following links."""

    if not kit_root.is_dir() or kit_root.is_symlink():
        raise ValueError("offline kit root must be a regular directory")
    entries: list[dict[str, object]] = []
    for path in sorted(kit_root.rglob("*")):
        relative = path.relative_to(kit_root).as_posix()
        if relative == "offline-kit-manifest.json":
            continue
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if stat.S_ISLNK(mode):
            target = os.readlink(path)
            try:
                (path.parent / target).resolve().relative_to(kit_root.resolve())
            except ValueError as exc:
                raise ValueError("offline kit contains an escaping symbolic link") from exc
            entries.append({"path": relative, "kind": "symlink", "target": target})
        elif stat.S_ISREG(mode):
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "sha256": _sha256(path),
                    "size": path.stat().st_size,
                }
            )
        else:
            raise ValueError("offline kit contains an unsupported filesystem entry")
    if not entries:
        raise ValueError("offline kit is empty")
    return entries


def build_offline_kit_manifest(
    host_profile_id: str,
    kit_root: Path,
    *,
    python_artifact_id: str,
) -> dict[str, object]:
    """Bind an installed payload closure to the validated host policy."""

    host, artifacts, policy_sha256 = _load_host_selection(host_profile_id)
    offline_kit = host["offline_kit"]
    expected_ids = set(offline_kit["artifact_ids"])
    required_ids = {python_artifact_id, "uv"}
    if not required_ids <= expected_ids or not expected_ids <= artifacts.keys():
        raise ValueError("offline kit payload closure does not match the validated host selection")
    entries = _offline_kit_entries(kit_root)
    installed_payload_bindings: list[dict[str, object]] = []
    for artifact_id, prefix in ((python_artifact_id, "python/"), ("uv", "bin/uv")):
        installed_entries = [
            entry for entry in entries if entry["path"] == prefix or str(entry["path"]).startswith(prefix)
        ]
        if not installed_entries:
            raise ValueError(f"offline kit omits the installed {artifact_id} payload")
        installed_payload_bindings.append(
            {
                "artifact_id": artifact_id,
                "version": artifacts[artifact_id]["version"],
                "source_raw_manifest": artifacts[artifact_id]["platform"]["raw_manifest"],
                "installed_entries": installed_entries,
            }
        )
    return {
        "schema_version": "raes-offline-bootstrap-kit/v1",
        "kit_id": offline_kit["kit_id"],
        "host_profile_id": host_profile_id,
        "platform_id": host["platform_id"],
        "policy_sha256": policy_sha256,
        "python_artifact_id": python_artifact_id,
        "artifact_ids": sorted(expected_ids),
        "installed_payload_bindings": installed_payload_bindings,
        "entries": entries,
    }


def _load_offline_kit_manifest(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_OFFLINE_MANIFEST_BYTES:
        raise ValueError("offline kit manifest must be a bounded regular file")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("offline kit manifest contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("offline kit manifest is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("offline kit manifest is invalid")
    return value


def verify_offline_kit(
    host_profile_id: str,
    kit_root: Path,
    *,
    python_artifact_id: str,
    trusted_manifest_sha256: str,
) -> dict[str, object]:
    """Verify and execute the imported uv, Python, and generic-tool closure."""

    manifest_path = kit_root / "offline-kit-manifest.json"
    if re.fullmatch(r"[0-9a-f]{64}", trusted_manifest_sha256) is None:
        raise ValueError("offline kit requires an exact trusted manifest digest")
    if not manifest_path.is_file() or manifest_path.is_symlink() or _sha256(manifest_path) != trusted_manifest_sha256:
        raise ValueError("offline kit manifest differs from the externally trusted digest")
    manifest = _load_offline_kit_manifest(manifest_path)
    expected = build_offline_kit_manifest(host_profile_id, kit_root, python_artifact_id=python_artifact_id)
    if manifest != expected:
        raise ValueError("offline kit contents differ from the bound manifest")
    host, artifacts, _ = _load_host_selection(host_profile_id)
    for artifact_id in manifest["artifact_ids"]:
        platform = artifacts[artifact_id]["platform"]
        for raw in platform["raw_manifest"]:
            raw_path = kit_root / "archives" / artifact_id / raw["path"]
            if (
                not raw_path.is_file()
                or raw_path.is_symlink()
                or raw_path.stat().st_size != raw["size"]
                or _sha256(raw_path) != raw["sha256"]
            ):
                raise ValueError(f"offline kit {artifact_id} raw payload differs from the lock")
    uv_result = inspect_executable(
        "uv",
        kit_root / "bin" / "uv",
        ("--version",),
        expected_version=f"uv {artifacts['uv']['version']}",
    )
    expected_uv_identity = artifacts["uv"]["platform"]["installed_identity"]
    observed_uv_identity = _observed_uv_identity(artifacts["uv"]["version"])
    uv_identity_passed = uv_result["outcome"] == "passed" and observed_uv_identity == expected_uv_identity
    if not uv_identity_passed:
        uv_result = {
            "capability_id": "uv",
            "outcome": "failed",
            "reason_code": "payload-identity-mismatch",
        }
    python_version = artifacts[python_artifact_id]["version"]
    feature = ".".join(python_version.split(".")[:2])
    python_candidates = sorted((kit_root / "python").glob(f"*/bin/python{feature}"))
    if len(python_candidates) != 1:
        raise ValueError("offline kit must contain exactly one selected Python executable")
    try:
        python_candidates[0].resolve().relative_to(kit_root.resolve())
    except ValueError as exc:
        raise ValueError("offline kit Python executable escapes the kit") from exc
    if not python_candidates[0].is_file():
        raise ValueError("offline kit selected Python executable is unavailable")
    try:
        python_probe = subprocess.run(
            [
                str(python_candidates[0]),
                "-c",
                "import json,platform,sys,sysconfig; "
                "print(json.dumps([platform.python_implementation(),platform.python_version(),"
                "bool(sysconfig.get_config_var('Py_GIL_DISABLED')),platform.system(),platform.machine(),"
                "sys.executable,sys.prefix]))",
            ],
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=dict(_PROBE_ENV),
        )
    except (OSError, subprocess.SubprocessError):
        python_probe = None
    try:
        python_identity = json.loads(python_probe.stdout) if python_probe is not None else []
        observed_python_identity = {
            "implementation": python_identity[0],
            "version": python_identity[1],
            "abi": f"cp{python_identity[1].split('.')[0]}{python_identity[1].split('.')[1]}"
            f"{'t' if python_identity[2] else ''}",
            "target": _runtime_target(python_identity[3], python_identity[4]),
        }
        executable_identity = Path(python_identity[5]).resolve()
        prefix_identity = Path(python_identity[6]).resolve()
        executable_identity.relative_to(kit_root.resolve())
        prefix_identity.relative_to(kit_root.resolve())
        python_passed = (
            python_probe.returncode == 0
            and observed_python_identity == artifacts[python_artifact_id]["platform"]["installed_identity"]
        )
    except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        observed_python_identity = {
            "implementation": "unobserved",
            "version": "unobserved",
            "abi": "unobserved",
            "target": "unobserved",
        }
        python_passed = False
    generic_ids = {"conftest", "gitleaks", "osv-scanner", "vale"} & set(manifest["artifact_ids"])
    if generic_ids and generic_ids != {"conftest", "gitleaks", "osv-scanner", "vale"}:
        raise ValueError("offline kit must contain either all four generic tools or none")
    generic = (
        qualify_generic_tools(selections=_offline_generic_tool_selections(kit_root, host["platform_id"], artifacts))
        if generic_ids
        else {"outcome": "not-run", "results": []}
    )
    outcome = (
        "passed" if uv_identity_passed and python_passed and generic["outcome"] in {"passed", "not-run"} else "failed"
    )
    return {
        "outcome": outcome,
        "kit_id": manifest["kit_id"],
        "manifest_sha256": trusted_manifest_sha256,
        "python": {
            "outcome": "passed" if python_passed else "failed",
            "expected_installed_identity": artifacts[python_artifact_id]["platform"]["installed_identity"],
            "observed_installed_identity": observed_python_identity,
        },
        "uv": uv_result,
        "uv_identity": {
            "outcome": "passed" if uv_identity_passed else "failed",
            "expected_installed_identity": expected_uv_identity,
            "observed_installed_identity": observed_uv_identity,
        },
        "generic_tools": generic,
    }


def _load_host_selection(host_profile_id: str) -> tuple[dict[str, object], dict[str, dict[str, object]], str]:
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


def observe_host_identity(host: dict[str, object]) -> tuple[str, str, list[dict[str, str]]]:
    """Validate the hosted-runner family and retain its exact observed release."""

    runner_image = _safe_runner_image()
    image_os, image_version, runner_arch = runner_image.split(":")
    observed_base = f"github-runner:{runner_image}"
    observed_repository = f"github-runner-package-set:{runner_image}"
    observed_family = f"github-hosted-runner:{image_os}:{runner_arch}"
    observed_repository_family = f"github-hosted-runner-package-set:{image_os}:{runner_arch}"
    metadata_available = (
        "unavailable" not in runner_image
        and re.fullmatch(r"20[0-9]{6}\.[0-9]{1,4}\.[0-9]{1,3}", image_version) is not None
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
    return targets.get((system.lower(), normalized_machine), f"unsupported-{system.lower()}-{normalized_machine}")


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


def record_case_result(
    repo_root: Path,
    test_case_id: str,
    implementation_revision: str,
    harness_path: str,
    artifact_ids: Sequence[str],
) -> dict[str, object]:
    """Bind a passed case to the exact local harness and implementation revision."""

    if test_case_id not in _CASE_IDS or re.fullmatch(r"[0-9a-f]{40}", implementation_revision) is None:
        raise ValueError("case result identity is invalid")
    if not all(isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value) for value in artifact_ids):
        raise ValueError("case result artifact identity is invalid")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}", harness_path) is None or ".." in Path(harness_path).parts:
        raise ValueError("case harness must be a bounded repository-relative path")
    harness = repo_root / harness_path
    if not harness.is_file() or harness.is_symlink():
        raise ValueError("case harness is unavailable")
    return {
        "test_case_id": test_case_id,
        "outcome": "passed",
        "implementation_revision": implementation_revision,
        "harness_path": harness_path,
        "harness_sha256": _sha256(harness),
        "artifact_ids": sorted(set(artifact_ids)),
    }


def _load_case_results(
    repo_root: Path,
    paths: Sequence[Path],
    implementation_revision: str,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in paths:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_CASE_RESULT_BYTES:
            raise ValueError("case result must be a bounded regular file")
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("case result is invalid") from exc
        if not isinstance(result, dict) or set(result) != {
            "test_case_id",
            "outcome",
            "implementation_revision",
            "harness_path",
            "harness_sha256",
            "artifact_ids",
        }:
            raise ValueError("case result has an invalid closed shape")
        case_id = result["test_case_id"]
        harness_path = result["harness_path"]
        artifact_ids = result["artifact_ids"]
        if (
            case_id not in _CASE_IDS
            or case_id in seen
            or result["outcome"] != "passed"
            or result["implementation_revision"] != implementation_revision
            or not isinstance(harness_path, str)
            or not isinstance(artifact_ids, list)
            or not all(
                isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value) for value in artifact_ids
            )
            or record_case_result(
                repo_root,
                case_id,
                implementation_revision,
                harness_path,
                artifact_ids,
            )
            != result
        ):
            raise ValueError("case result does not match its harness or revision")
        seen.add(case_id)
        results.append(result)
    if not results:
        raise ValueError("at least one passed case result is required")
    return results


def build_qualification_evidence(
    repo_root: Path,
    host_profile_id: str,
    implementation_revision: str,
    evidence_location: str,
    *,
    python_artifact_id: str,
    case_result_paths: Sequence[Path],
    offline_kit_root: Path | None = None,
    offline_kit_archive_path: Path | None = None,
    offline_kit_manifest_sha256: str | None = None,
    generic_selections: Sequence[tuple[str, Path, tuple[str, ...], str]] | None = None,
) -> dict[str, object]:
    """Execute maintained clients and build a bounded, credential-free evidence record."""

    if re.fullmatch(r"[0-9a-f]{40}", implementation_revision) is None:
        raise ValueError("implementation revision must be an exact commit SHA")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", evidence_location) is None:
        raise ValueError("evidence location must be a bounded public identifier")
    host, artifacts, policy_sha256 = _load_host_selection(host_profile_id)
    case_results = _load_case_results(repo_root, case_result_paths, implementation_revision)
    passed_case_ids = {result["test_case_id"] for result in case_results}
    if offline_kit_root is None:
        if offline_kit_archive_path is not None or offline_kit_manifest_sha256 is not None or "T12" in passed_case_ids:
            raise ValueError("T12 and offline-kit evidence require a verified restored kit")
        offline_kit_result = None
    else:
        if offline_kit_archive_path is None or offline_kit_manifest_sha256 is None:
            raise ValueError("restored offline-kit evidence requires its exact archive and trusted manifest digest")
        offline_kit_result = verify_offline_kit(
            host_profile_id,
            offline_kit_root,
            python_artifact_id=python_artifact_id,
            trusted_manifest_sha256=offline_kit_manifest_sha256,
        )
        if offline_kit_result["outcome"] != "passed":
            raise ValueError("restored offline kit did not pass exact verification")
    measured_artifact_ids = {artifact_id for result in case_results for artifact_id in result["artifact_ids"]}
    if not measured_artifact_ids <= artifacts.keys() or python_artifact_id not in measured_artifact_ids:
        raise ValueError("case results name payloads outside the validated host selection")
    if python_artifact_id not in host["bootstrap_payload_ids"] or not python_artifact_id.startswith("cpython-"):
        raise ValueError("Python evidence must select a CPython payload admitted by the host profile")
    expected_python_identity = artifacts[python_artifact_id]["platform"]["installed_identity"]
    expected_uv_identity = artifacts["uv"]["platform"]["installed_identity"]
    if offline_kit_result is not None:
        observed_python_identity = offline_kit_result["python"]["observed_installed_identity"]
        python_identity_passed = offline_kit_result["python"]["outcome"] == "passed"
        observed_uv_identity = offline_kit_result["uv_identity"]["observed_installed_identity"]
        uv_result = offline_kit_result["uv"]
    else:
        observed_python_identity = observe_current_python_identity()
        python_identity_passed = observed_python_identity == expected_python_identity
        observed_uv_identity = _observed_uv_identity(artifacts["uv"]["version"])
        if uv_path := shutil.which("uv"):
            uv_result = inspect_executable(
                "uv",
                Path(uv_path),
                ("--version",),
                expected_version=f"uv {artifacts['uv']['version']}",
            )
        else:
            uv_result = {
                "capability_id": "uv",
                "outcome": "failed",
                "reason_code": "native-client-unavailable",
            }
        if observed_uv_identity != expected_uv_identity:
            uv_result = {
                "capability_id": "uv",
                "outcome": "failed",
                "reason_code": "payload-identity-mismatch",
            }
    payloads: list[dict[str, object]] = []
    for artifact_id in sorted(measured_artifact_ids):
        artifact = artifacts[artifact_id]
        platform = artifact["platform"]
        if platform["platform_id"] != host["platform_id"] or (
            platform.get("host_profile_ids") and host_profile_id not in platform["host_profile_ids"]
        ):
            raise ValueError(f"host profile must select exactly one {artifact_id} payload")
        payload_evidence: dict[str, object] = {
            "artifact_id": artifact_id,
            "version": artifact["version"],
            "support_level": artifact.get("support_level", "blocking"),
            "platform_id": platform["platform_id"],
            "distribution_id": platform.get("distribution_id", "portable"),
            "expected_raw_manifest": platform["raw_manifest"],
            "measurement": (
                "offline-kit-manifest-verified-and-executed"
                if offline_kit_result is not None
                else "installed-manifest-verified-and-executed"
                if artifact_id in {"conftest", "gitleaks", "osv-scanner", "vale"}
                else "case-harness-verified"
                if artifact_id == "isabelle"
                else "installed-identity-observed"
            ),
        }
        if "installed_identity" in platform:
            payload_evidence["expected_installed_identity"] = platform["installed_identity"]
            if artifact_id == python_artifact_id:
                payload_evidence["observed_installed_identity"] = observed_python_identity
            elif artifact_id == "uv":
                payload_evidence["observed_installed_identity"] = observed_uv_identity
        if "installed_manifest" in platform:
            payload_evidence["installed_manifest"] = platform["installed_manifest"]
        payloads.append(payload_evidence)
    generic_artifact_ids = {"conftest", "gitleaks", "osv-scanner", "vale"}
    measured_generic_ids = measured_artifact_ids & generic_artifact_ids
    if measured_generic_ids and measured_generic_ids != generic_artifact_ids:
        raise ValueError("generic-tool evidence must measure the complete four-tool platform set")
    if measured_generic_ids:
        generic = (
            offline_kit_result["generic_tools"]
            if offline_kit_result is not None
            else qualify_generic_tools(selections=generic_selections)
        )
    else:
        generic = {"outcome": "not-run", "results": []}
    proof_required = host["proof_support"] == "linux-x86_64-required"
    observed_base, observed_repository, host_identity_results = observe_host_identity(host)
    capabilities: list[dict[str, str]] = [
        {
            "capability_id": "cpython",
            "outcome": "passed" if python_identity_passed else "failed",
            "version": observed_python_identity["version"],
            "expected_version": expected_python_identity["version"],
            "observed_identity": json.dumps(observed_python_identity, sort_keys=True, separators=(",", ":")),
            **({} if python_identity_passed else {"reason_code": "payload-identity-mismatch"}),
        },
        {
            "capability_id": "native-proof",
            "outcome": "passed" if proof_required and "T01" in passed_case_ids else "unsupported",
            "observed_identity": "case:T01" if proof_required and "T01" in passed_case_ids else host["platform_id"],
            "reason_code": "bound-proof-harness"
            if proof_required and "T01" in passed_case_ids
            else "proof-requires-linux-x86_64",
        },
    ]
    capabilities.extend(host_identity_results)
    if measured_generic_ids:
        capabilities.extend(generic["results"])
    capabilities.extend(_native_client_results(host))
    if offline_kit_result is not None:
        capabilities.append(
            {
                "capability_id": "offline-kit",
                "outcome": "passed",
                "observed_identity": f"manifest:{offline_kit_result['manifest_sha256']}",
            }
        )
    capabilities.append(uv_result)
    for capability in capabilities:
        capability.setdefault(
            "observed_identity",
            f"{capability['capability_id']}:{capability.get('version', capability['outcome'])}",
        )
    outcome = (
        "passed"
        if (generic["outcome"] == "passed" or not measured_generic_ids)
        and uv_result["outcome"] == "passed"
        and python_identity_passed
        and all(item["outcome"] == "passed" for item in capabilities if item["outcome"] != "unsupported")
        else "failed"
    )
    record: dict[str, object] = {
        "evidence_id": (
            f"{host_profile_id}-{python_artifact_id}-"
            f"{'-'.join(sorted(passed_case_ids)).lower()}-{implementation_revision[:12]}"
        ),
        "host_profile_id": host_profile_id,
        "platform_id": host["platform_id"],
        "implementation_revision": implementation_revision,
        "observed_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "test_case_ids": sorted(result["test_case_id"] for result in case_results),
        "context": "restored-offline-kit" if offline_kit_root is not None else "public-runner",
        "base_image_identity": observed_base,
        "declared_base_image_identity": host["base_image_identity"],
        "observed_runner_image": _safe_runner_image(),
        "native_repository_identity": observed_repository,
        "policy_sha256": policy_sha256,
        "harness_sha256": _sha256(Path(__file__)),
        "evidence_location": evidence_location,
        "payload_results": payloads,
        "capability_results": capabilities,
        "case_results": case_results,
        "outcome": outcome,
    }
    if offline_kit_archive_path is not None:
        if not offline_kit_archive_path.is_file() or offline_kit_archive_path.is_symlink():
            raise ValueError("offline kit archive must be a regular file")
        record["offline_kit_evidence"] = {
            "path": offline_kit_archive_path.name,
            "sha256": _sha256(offline_kit_archive_path),
            "size": offline_kit_archive_path.stat().st_size,
        }
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["evidence_sha256"] = hashlib.sha256(encoded).hexdigest()
    return record


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    setup = subparsers.add_parser("setup-plan", help="render reviewed native prerequisites")
    setup.add_argument("host_profile_id")
    inspect = subparsers.add_parser("inspect-profile", help="run the reviewed read-only host probes")
    inspect.add_argument("host_profile_id")
    subparsers.add_parser("generic-tools", help="execute the four locked generic tools")
    evidence = subparsers.add_parser("qualification-evidence", help="execute tools and emit host-bound evidence")
    evidence.add_argument("host_profile_id")
    evidence.add_argument("implementation_revision")
    evidence.add_argument("evidence_location")
    evidence.add_argument("--python-artifact-id", required=True)
    evidence.add_argument("--case-result", action="append", type=Path, required=True)
    evidence.add_argument("--offline-kit-root", type=Path)
    evidence.add_argument("--offline-kit", type=Path)
    evidence.add_argument("--offline-kit-manifest-sha256")
    case = subparsers.add_parser("record-case", help="bind a passed case to its exact harness")
    case.add_argument("test_case_id", choices=sorted(_CASE_IDS))
    case.add_argument("implementation_revision")
    case.add_argument("harness_path")
    case.add_argument("--artifact-id", action="append", default=[])
    kit_fetch = subparsers.add_parser("offline-kit-fetch", help="fetch exact raw payloads with native curl")
    kit_fetch.add_argument("host_profile_id")
    kit_fetch.add_argument("kit_root", type=Path)
    kit_fetch.add_argument("--artifact-id", action="append", required=True)
    kit_manifest = subparsers.add_parser("offline-kit-manifest", help="measure a target-specific payload kit")
    kit_manifest.add_argument("host_profile_id")
    kit_manifest.add_argument("kit_root", type=Path)
    kit_manifest.add_argument("--python-artifact-id", required=True)
    kit_digest = subparsers.add_parser("offline-kit-manifest-digest", help="hash a producer-authenticated manifest")
    kit_digest.add_argument("manifest_path", type=Path)
    kit_verify = subparsers.add_parser("offline-kit-verify", help="verify and execute an imported payload kit")
    kit_verify.add_argument("host_profile_id")
    kit_verify.add_argument("kit_root", type=Path)
    kit_verify.add_argument("--python-artifact-id", required=True)
    kit_verify.add_argument("--trusted-manifest-sha256", required=True)
    proof = subparsers.add_parser("proof-support", help="report the native proof support classification")
    proof.add_argument("platform_id")
    return parser.parse_args()


def main() -> int:
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
        result = qualify_generic_tools()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["outcome"] == "passed" else 1
    elif args.operation == "qualification-evidence":
        result = build_qualification_evidence(
            Path.cwd(),
            args.host_profile_id,
            args.implementation_revision,
            args.evidence_location,
            python_artifact_id=args.python_artifact_id,
            case_result_paths=args.case_result,
            offline_kit_root=args.offline_kit_root,
            offline_kit_archive_path=args.offline_kit,
            offline_kit_manifest_sha256=args.offline_kit_manifest_sha256,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["outcome"] == "passed" else 1
    elif args.operation == "record-case":
        print(
            json.dumps(
                record_case_result(
                    Path.cwd(),
                    args.test_case_id,
                    args.implementation_revision,
                    args.harness_path,
                    args.artifact_id,
                ),
                sort_keys=True,
            )
        )
    elif args.operation == "offline-kit-manifest":
        print(
            json.dumps(
                build_offline_kit_manifest(
                    args.host_profile_id,
                    args.kit_root,
                    python_artifact_id=args.python_artifact_id,
                ),
                sort_keys=True,
            )
        )
    elif args.operation == "offline-kit-fetch":
        print(
            json.dumps(
                fetch_offline_kit_payloads(
                    args.host_profile_id,
                    args.kit_root,
                    args.artifact_id,
                ),
                sort_keys=True,
            )
        )
    elif args.operation == "offline-kit-manifest-digest":
        _load_offline_kit_manifest(args.manifest_path)
        print(_sha256(args.manifest_path))
    elif args.operation == "offline-kit-verify":
        result = verify_offline_kit(
            args.host_profile_id,
            args.kit_root,
            python_artifact_id=args.python_artifact_id,
            trusted_manifest_sha256=args.trusted_manifest_sha256,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["outcome"] == "passed" else 1
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
