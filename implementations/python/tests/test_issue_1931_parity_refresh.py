"""Keep golden behavior checks independent of unrelated source bookkeeping."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
IDENTITY = {
    **{key: "a" * 40 for key in ("test_tree", "python_tree", "contracts_tree", "examples_tree")},
    **{key: "b" * 64 for key in ("collector_sha256", "environment_sha256")},
}
PROVENANCE = {
    "python_commit": "a" * 40,
    "python_tree": "b" * 40,
    "recorder_sha256": "c" * 64,
    "lock_sha256": "d" * 64,
    "python_version": "3.14.7",
    "unicode_version": "16.0.0",
    "hash_seed": "0",
}


def _snapshot(repo: Path) -> Path:
    from tools import parity_corpus as corpus
    from tools import parity_regressions as regressions
    from tools.parity_storage import pack
    from tools.parity_support import digest, encode

    content = encode({"sdl_content": "name: recorded\n"})
    origin = "tests/test_protocol.py::test_parse"
    descriptor = {
        "surface": "mcp",
        "command": "sdl_parse",
        "args": [],
        "files": {"arguments.json": "sha256:" + digest(content)},
    }
    manifest = {
        "schema": regressions.FORMAT,
        "source_identity": IDENTITY,
        "complete": True,
        "tests": [origin],
        "non_protocol_tests": [],
        "inputs": {digest(encode(descriptor)): {**descriptor, "tests": [origin]}},
    }
    root = repo / corpus.CORPUS_DIR
    files, _ = pack(
        {
            Path("regressions/manifest.json"): encode(manifest),
            Path("inputs", digest(content)): content,
        }
    )
    for name, value in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    return root / "regressions"


def test_frozen_snapshot_survives_unrelated_source_changes(tmp_path: Path, monkeypatch) -> None:
    from tools import parity_regressions as regressions

    frozen = _snapshot(tmp_path)
    changed = {**IDENTITY, "test_tree": "c" * 40, "python_tree": "d" * 40}
    cases, inventory, files = regressions.read_inputs(frozen, identity=changed)
    assert len(cases) == 1
    assert inventory["source_identity"] == IDENTITY
    assert inventory["complete"] is True
    assert json.loads(files[Path("manifest.json")])["source_identity"] == IDENTITY
    monkeypatch.setattr(regressions, "source_identity", lambda _root: changed)
    monkeypatch.setattr("sys.argv", ["parity_regressions", "current", "--repo-root", str(tmp_path)])
    assert regressions.main() == 0


def test_metadata_only_reference_changes_do_not_rewrite_cases(tmp_path: Path) -> None:
    from tools import parity_corpus as corpus
    from tools.parity_support import encode

    old_manifest = encode({"schema": corpus.SCHEMA, "provenance": PROVENANCE})
    current = {**PROVENANCE, "python_commit": "e" * 40, "python_tree": "f" * 40, "recorder_sha256": "e" * 64}
    new_manifest = encode({"schema": corpus.SCHEMA, "provenance": current})
    case = Path("cases/schema/validate/case.json")
    committed = {corpus.MANIFEST: old_manifest, case: encode({"result": {"valid": True}})}
    corpus.write_corpus(tmp_path / "stored", committed)
    recorded = {**committed, corpus.MANIFEST: new_manifest}
    assert corpus.check_recording(recorded, tmp_path / "stored", tmp_path / "fresh") == 0
    assert (tmp_path / "stored/manifest.json").read_bytes() == old_manifest
    assert not (tmp_path / "fresh").exists()


def test_explicit_ci_refresh_overrides_a_usable_snapshot(tmp_path: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    step = next(s for s in workflow["jobs"]["parity-inputs"]["steps"] if s.get("id") == "capture")
    script = step["run"].replace("${{ matrix.shard }}", "0")
    binary = tmp_path / "bin"
    binary.mkdir()
    uv = binary / "uv"
    uv.write_text("#!/bin/sh\nexit 0\n")
    uv.chmod(0o755)
    source = tmp_path / "implementations/go/internal/parity/testdata"
    (source / "regressions").mkdir(parents=True)
    (source / "inputs").mkdir()
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "REFRESH_PARITY_INPUTS": "true",
            "RUNNER_TEMP": str(tmp_path / "runner"),
            "GITHUB_OUTPUT": str(output),
        },
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "needed=true\n"
