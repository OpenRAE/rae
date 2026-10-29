from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from raes_contracts.errors import OperationalError

from tools import verified_tool_installation as installation
from tools.maintained_client_acquisition import acquire_locked_bytes

from ..tool_versions import CONTFEST_VERSION
from .common import REPO_ROOT, PolicyFailure

POLICY_DIR = REPO_ROOT / "tools" / "policy" / "conftest"
CACHE_ROOT = REPO_ROOT / ".cache" / "raes-sdl" / "tooling" / "conftest"
_EVALUATION_FAILED = "conftest repo policy evaluation failed"
_RESULT_INVALID = f"{_EVALUATION_FAILED}: the JSON result is invalid"


class ConftestPolicyError(OperationalError):
    """The pinned conftest client could not evaluate or verify the repository policy."""


def conftest_binary_path(repo_root: Path = REPO_ROOT, *, version: str = CONTFEST_VERSION) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling" / "conftest" / version / "conftest"


def ensure_conftest(
    repo_root: Path = REPO_ROOT,
    *,
    version: str = CONTFEST_VERSION,
    local_input: Path | None = None,
    installation_root: Path | None = None,
) -> Path:
    from tools.tooling_policy_gate import (
        ArtifactPolicyError,
        host_platform_id,
        load_tooling_artifact_selection,
    )

    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id="conftest",
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1 or len(selection.installed_manifest) != 1:
        raise ArtifactPolicyError("conftest lock selection must contain one source, raw asset, and installed binary")
    raw = selection.raw_manifest[0]
    return installation.ensure_verified_installation(
        repo_root,
        selection,
        acquire=lambda: acquire_locked_bytes(
            artifact_id="conftest",
            source_url=selection.source_urls[0],
            expected=raw,
            local_input=local_input,
        ),
        materialize=installation.materialize_tar_gz,
        legacy_path=conftest_binary_path(repo_root, version=version),
        installation_root=installation_root,
    )


def _run_client(command: list[str], repo_root: Path, failure: str) -> subprocess.CompletedProcess[str]:
    """Run the verified client; a client that cannot run or that writes no text is a client failure."""

    try:
        return subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise ConftestPolicyError(f"{failure}: the client could not run") from exc
    except UnicodeDecodeError as exc:
        # Text mode decodes the client output strictly, so output that is not text carries no result.
        raise ConftestPolicyError(f"{failure}: the client output is not text") from exc


def _result_integer(literal: str) -> int:
    # The decoder passes only JSON integer literals, so int() fails only beyond the interpreter digit limit.
    try:
        return int(literal)
    except ValueError as exc:
        raise ConftestPolicyError(_RESULT_INVALID) from exc


def _policy_failure(failure: object) -> PolicyFailure:
    if not isinstance(failure, dict):
        raise ConftestPolicyError(_RESULT_INVALID)
    metadata = failure.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ConftestPolicyError(_RESULT_INVALID)
    rule_id = metadata.get("rule_id", "conftest-policy-failure")
    message = failure.get("msg")
    path = metadata.get("path")
    if not isinstance(rule_id, str) or not isinstance(message, str) or not (path is None or isinstance(path, str)):
        raise ConftestPolicyError(_RESULT_INVALID)
    return PolicyFailure(rule_id, message, path)


def _policy_failures(output: str) -> list[PolicyFailure]:
    """Read the conftest JSON result list; output in any other shape is a client failure."""

    try:
        results = json.loads(output, parse_int=_result_integer)
    except json.JSONDecodeError as exc:
        raise ConftestPolicyError(_RESULT_INVALID) from exc
    except RecursionError as exc:
        # Without a depth limit, the recursive decoder stops at the interpreter recursion limit.
        raise ConftestPolicyError(_RESULT_INVALID) from exc
    if not isinstance(results, list):
        raise ConftestPolicyError(_RESULT_INVALID)
    failures: list[PolicyFailure] = []
    for result in results:
        result_failures = result.get("failures", []) if isinstance(result, dict) else None
        if not isinstance(result_failures, list):
            raise ConftestPolicyError(_RESULT_INVALID)
        failures.extend(_policy_failure(failure) for failure in result_failures)
    failures.sort(key=lambda item: (item.path or "", item.rule_id, item.message))
    return failures


def run_conftest_policy(
    input_document: dict[str, object],
    *,
    repo_root: Path = REPO_ROOT,
    policy_dir: Path = POLICY_DIR,
) -> list[PolicyFailure]:
    binary = ensure_conftest(repo_root)

    with tempfile.TemporaryDirectory(prefix="raes-conftest-input-") as tmpdir:
        input_path = Path(tmpdir) / "repo-policy-input.json"
        input_path.write_text(json.dumps(input_document, indent=2, sort_keys=True), encoding="utf-8")
        proc = _run_client(
            [
                str(binary),
                "test",
                str(input_path),
                "--policy",
                str(policy_dir),
                "--output",
                "json",
            ],
            repo_root,
            _EVALUATION_FAILED,
        )

    # conftest prints a JSON result list for every evaluation it completes, passing or failing. It exits 1 with
    # nothing on stdout when it cannot load or evaluate the policy, the same exit code it uses for policy failures.
    if proc.returncode not in {0, 1} or not proc.stdout.strip():
        details = proc.stderr.strip() or proc.stdout.strip() or "unknown conftest failure"
        raise ConftestPolicyError(f"{_EVALUATION_FAILED}: {details}")
    return _policy_failures(proc.stdout)


def verify_conftest_policy(*, repo_root: Path = REPO_ROOT, policy_dir: Path = POLICY_DIR) -> None:
    binary = ensure_conftest(repo_root)
    proc = _run_client(
        [
            str(binary),
            "verify",
            "--policy",
            str(policy_dir),
        ],
        repo_root,
        "conftest policy verification failed",
    )
    if proc.returncode != 0:
        details = proc.stderr.strip() or proc.stdout.strip() or "unknown conftest verify failure"
        raise ConftestPolicyError(f"conftest policy verification failed: {details}")
