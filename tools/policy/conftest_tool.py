from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from tools import verified_tool_installation as installation
from tools.maintained_client_acquisition import acquire_locked_bytes

from ..tool_versions import CONTFEST_VERSION
from .common import REPO_ROOT, PolicyFailure

POLICY_DIR = REPO_ROOT / "tools" / "policy" / "conftest"
CACHE_ROOT = REPO_ROOT / ".cache" / "raes-sdl" / "tooling" / "conftest"


def conftest_binary_path(repo_root: Path = REPO_ROOT, *, version: str = CONTFEST_VERSION) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling" / "conftest" / version / "conftest"


def ensure_conftest(
    repo_root: Path = REPO_ROOT,
    *,
    version: str = CONTFEST_VERSION,
    local_input: Path | None = None,
    installation_root: Path | None = None,
    immutable_seed_root: Path | None = None,
) -> Path:
    from tools.tooling_policy_gate import (
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
        raise RuntimeError("conftest lock selection must contain one source, raw asset, and installed binary")
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
        immutable_seed_root=immutable_seed_root,
    )


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
        proc = subprocess.run(
            [
                str(binary),
                "test",
                str(input_path),
                "--policy",
                str(policy_dir),
                "--output",
                "json",
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

    if proc.returncode not in {0, 1}:
        details = proc.stderr.strip() or proc.stdout.strip() or "unknown conftest failure"
        raise RuntimeError(f"conftest repo policy evaluation failed: {details}")

    if not proc.stdout.strip():
        return []

    raw_results = json.loads(proc.stdout)
    failures: list[PolicyFailure] = []
    for result in raw_results:
        for failure in result.get("failures", []):
            metadata = failure.get("metadata", {})
            failures.append(
                PolicyFailure(
                    metadata.get("rule_id", "conftest-policy-failure"),
                    failure["msg"],
                    metadata.get("path"),
                )
            )
    failures.sort(key=lambda item: (item.path or "", item.rule_id, item.message))
    return failures


def verify_conftest_policy(*, repo_root: Path = REPO_ROOT, policy_dir: Path = POLICY_DIR) -> None:
    binary = ensure_conftest(repo_root)
    proc = subprocess.run(
        [
            str(binary),
            "verify",
            "--policy",
            str(policy_dir),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        details = proc.stderr.strip() or proc.stdout.strip() or "unknown conftest verify failure"
        raise RuntimeError(f"conftest policy verification failed: {details}")
