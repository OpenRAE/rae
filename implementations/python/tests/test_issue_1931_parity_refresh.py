"""Keep golden behavior checks independent of unrelated source bookkeeping."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
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


def _snapshot(repo: Path, identity: dict[str, str] | None = None) -> Path:
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
        "source_identity": identity or IDENTITY,
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


def _capture_decision(tmp_path: Path, *, refresh: bool, usable: bool):
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    step = next(s for s in workflow["jobs"]["parity-inputs"]["steps"] if s.get("id") == "capture")
    script = step["run"].replace("${{ matrix.shard }}", "0")
    binary = tmp_path / "bin"
    binary.mkdir()
    uv = binary / "uv"
    uv.write_text(f"#!/bin/sh\nexit {0 if usable else 1}\n")
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
            "REFRESH_PARITY_INPUTS": str(refresh).lower(),
            "RUNNER_TEMP": str(tmp_path / "runner"),
            "GITHUB_OUTPUT": str(output),
        },
        text=True,
        capture_output=True,
    )
    return result, output


def test_explicit_ci_refresh_overrides_a_usable_snapshot(tmp_path: Path) -> None:
    result, output = _capture_decision(tmp_path, refresh=True, usable=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "needed=true\n"


def test_normal_ci_reuses_a_usable_snapshot(tmp_path: Path) -> None:
    result, output = _capture_decision(tmp_path, refresh=False, usable=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "needed=false\n"
    assert (tmp_path / "runner/parity-inputs").is_dir()


def test_invalid_snapshot_does_not_trigger_automatic_collection(tmp_path: Path) -> None:
    result, output = _capture_decision(tmp_path, refresh=False, usable=False)
    assert result.returncode != 0
    assert not output.exists()
    assert not (tmp_path / "runner/parity-inputs").exists()


def test_ci_refresh_is_explicit_and_defaults_off() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    caller = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for document, event in ((workflow, "workflow_call"), (caller, "workflow_dispatch")):
        triggers = document.get("on", document.get(True))
        option = triggers[event]["inputs"]["refresh-parity-inputs"]
        assert option["type"] == "boolean"
        assert option["default"] is False
    assert "inputs.refresh-parity-inputs" in caller["jobs"]["canonical"]["with"]["refresh-parity-inputs"]
    step = next(s for s in workflow["jobs"]["parity-inputs"]["steps"] if s.get("id") == "capture")
    assert step["env"]["REFRESH_PARITY_INPUTS"] == "${{ inputs.refresh-parity-inputs }}"


@pytest.mark.parametrize("key", list(IDENTITY))
def test_frozen_provenance_is_still_validated(tmp_path: Path, key: str) -> None:
    from tools import parity_regressions as regressions

    root = _snapshot(tmp_path)
    path = root / "manifest.json"
    document = json.loads(path.read_bytes())
    document["source_identity"][key] = "invalid"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="source identity"):
        regressions.read_inputs(root, identity=IDENTITY)


def test_snapshot_blob_integrity_is_still_checked(tmp_path: Path) -> None:
    import gzip

    from tools import parity_regressions as regressions

    root = _snapshot(tmp_path)
    blob = next((root.parent / "inputs").iterdir())
    blob.write_bytes(gzip.compress(b"wrong content", mtime=0))
    with pytest.raises(ValueError, match="does not match its digest"):
        regressions.read_inputs(root)


def test_fresh_workers_must_still_match_current_sources(tmp_path: Path) -> None:
    from tools import parity_regressions as regressions

    (tmp_path / "worker.json").write_text(json.dumps({"schema": "raes-parity-inputs/v1", "source_identity": IDENTITY}))
    with pytest.raises(ValueError, match="different test or collector source"):
        regressions.read_inputs(tmp_path, identity={**IDENTITY, "test_tree": "c" * 40})


@pytest.mark.parametrize("path", ["cases/result.json", "inputs/blob", "inventory.json", "regressions/manifest.json"])
def test_real_corpus_differences_still_fail_and_keep_current_provenance(tmp_path: Path, path: str) -> None:
    from tools import parity_corpus as corpus
    from tools.parity_support import encode

    old = {corpus.MANIFEST: encode({"schema": corpus.SCHEMA, "provenance": PROVENANCE}), Path(path): b"old\n"}
    current = {**PROVENANCE, "python_commit": "e" * 40}
    recorded = {corpus.MANIFEST: encode({"schema": corpus.SCHEMA, "provenance": current}), Path(path): b"new\n"}
    corpus.write_corpus(tmp_path / "stored", old)
    assert corpus.check_recording(recorded, tmp_path / "stored", tmp_path / "fresh") == 1
    assert corpus.read_corpus(tmp_path / "fresh") == recorded


@pytest.mark.parametrize(
    "field,value",
    [
        ("python_commit", "invalid"),
        ("python_tree", "G" * 40),
        ("recorder_sha256", None),
        ("lock_sha256", "a" * 63),
        ("python_version", "latest"),
        ("unicode_version", "1.2"),
        ("hash_seed", "random"),
    ],
)
def test_malformed_receipts_cannot_receive_metadata_only_tolerance(tmp_path: Path, field: str, value: object) -> None:
    from tools import parity_corpus as corpus
    from tools.parity_support import encode

    invalid = {corpus.MANIFEST: encode({"schema": corpus.SCHEMA, "provenance": {**PROVENANCE, field: value}})}
    recorded = {corpus.MANIFEST: encode({"schema": corpus.SCHEMA, "provenance": PROVENANCE})}
    corpus.write_corpus(tmp_path / "stored", invalid)
    assert corpus.check_recording(recorded, tmp_path / "stored", None) == 1


@pytest.mark.parametrize(
    "receipt",
    [
        b"not-json",
        b"\xff",
        b"[]",
        b"{}",
        b'{"schema":"wrong","provenance":{}}',
        b'{"schema":"raes-parity-corpus/v2","provenance":null}',
    ]
    + [
        json.dumps({"schema": "raes-parity-corpus/v2", "provenance": PROVENANCE}).encode(encoding)
        for encoding in ("utf-16", "utf-32")
    ],
)
def test_invalid_receipt_structures_fail(tmp_path: Path, receipt: bytes) -> None:
    from tools import parity_corpus as corpus
    from tools.parity_support import encode

    corpus.write_corpus(tmp_path / "stored", {corpus.MANIFEST: receipt})
    recorded = {corpus.MANIFEST: encode({"schema": corpus.SCHEMA, "provenance": PROVENANCE})}
    assert corpus.check_recording(recorded, tmp_path / "stored", None) == 1


@pytest.mark.parametrize("identity", [None, {}, {**IDENTITY, "unknown": "a" * 40}])
def test_incomplete_snapshot_identity_fails(tmp_path: Path, identity: object) -> None:
    from tools import parity_regressions as regressions

    root = _snapshot(tmp_path)
    path = root / "manifest.json"
    document = json.loads(path.read_bytes())
    document["source_identity"] = identity
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="source identity"):
        regressions.read_inputs(root)


def test_snapshot_completeness_requires_a_boolean(tmp_path: Path) -> None:
    from tools import parity_regressions as regressions

    root = _snapshot(tmp_path)
    path = root / "manifest.json"
    document = json.loads(path.read_bytes())
    document["complete"] = "false"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="completeness"):
        regressions.read_inputs(root)


def test_real_git_merge_of_unrelated_tests_keeps_snapshot_usable(tmp_path: Path, monkeypatch) -> None:
    from tools import parity_regressions as regressions

    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env=environment, check=True, capture_output=True)

    git("init", "-qb", "feature")
    git("config", "user.name", "Parity test fixture")
    git("config", "user.email", "tests@example.invalid")
    git("config", "commit.gpgsign", "false")
    for name in (
        "implementations/python/tests/test_protocol.py",
        "implementations/python/packages/module.py",
        "implementations/python/uv.lock",
        "implementations/python/pyproject.toml",
        "contracts/example.json",
        "examples/input.yaml",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n")
    git("add", ".")
    git("commit", "-qm", "Initial source fixture")
    identity = regressions.source_identity(tmp_path)
    snapshot = _snapshot(tmp_path, identity)
    before = (snapshot / "manifest.json").read_bytes()
    git("add", ".")
    git("commit", "-qm", "Retain input snapshot")
    git("checkout", "-qb", "dev")
    (tmp_path / "implementations/python/tests/test_documentation.py").write_text("# Documentation-only test\n")
    git("add", ".")
    git("commit", "-qm", "Add documentation test")
    git("checkout", "feature")
    (tmp_path / "README.md").write_text("# Feature documentation\n")
    git("add", ".")
    git("commit", "-qm", "Update feature documentation")
    git("merge", "--no-ff", "dev", "-m", "Merge development fixture")
    assert regressions.source_identity(tmp_path)["test_tree"] != identity["test_tree"]
    monkeypatch.setattr("sys.argv", ["parity_regressions", "current", "--repo-root", str(tmp_path)])
    assert regressions.main() == 0
    assert (snapshot / "manifest.json").read_bytes() == before


def test_frozen_replay_does_not_query_the_live_test_tree(tmp_path: Path, monkeypatch) -> None:
    from tools import parity_corpus as corpus
    from tools import parity_regressions as regressions

    _snapshot(tmp_path)
    monkeypatch.setattr(
        regressions, "source_identity", lambda _root: pytest.fail("frozen replay must not query live tests")
    )
    monkeypatch.setattr(corpus, "all_cases", lambda _root: [])
    monkeypatch.setattr(corpus, "provenance", lambda _root: PROVENANCE)
    monkeypatch.setattr(corpus, "run", lambda _root, _case: {"accepted": True})
    # The omitted recorded case still fails comparison after snapshot validation.
    assert corpus.main(["check", "--repo-root", str(tmp_path)]) == 1
