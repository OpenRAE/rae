from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from tools.check_identity_cutover import evaluate_identity_cutover

REPO_ROOT = Path(__file__).resolve().parents[3]
RETIRED_LOWER = "a" + "ces"
RETIRED_UPPER = "A" + "CES"
MANIFEST_PATH = Path("tools/policy/historical_identity_records.json")


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _record(
    path: str,
    content: bytes,
    *,
    occurrences: int = 1,
    record_class: str = "dated-design-record",
) -> dict[str, object]:
    return {
        "path": path,
        "record_class": record_class,
        "rationale": "Preserves a dated design decision from before the identity cutover.",
        "occurrences": occurrences,
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }


def _binding(path: str, content: bytes, *, occurrences: int = 1) -> dict[str, object]:
    return {
        "path": path,
        "binding_class": "external-service-project-key",
        "rationale": "Retains an exact service-owned project key.",
        "occurrences": occurrences,
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }


def _generated_record(
    path: str,
    tail: bytes,
    *,
    occurrences: int = 1,
) -> dict[str, object]:
    return {
        "path": path,
        "record_class": "generated-release-history",
        "rationale": "Pins the classified tail of a bot-maintained release history.",
        "occurrences": occurrences,
        "content_sha256": hashlib.sha256(tail).hexdigest(),
        "classified_suffix_bytes": len(tail),
    }


def _seed_repo(
    repo_root: Path,
    *,
    files: dict[str, str | bytes],
    records: list[dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
    generated: list[dict[str, object]] | None = None,
) -> None:
    for relative_path, content in files.items():
        _write(repo_root / relative_path, content)
    manifest = {
        "schema_version": "historical-identity-records/v3",
        "hash_algorithm": "sha256",
        "generated_history_records": generated or [],
        "operational_bindings": bindings or [],
        "records": records or [],
    }
    _write(
        repo_root / MANIFEST_PATH,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    _git(repo_root, "init", "-q")
    _git(repo_root, "add", "-A")


def _seed_manifest_fixture(repo_root: Path) -> dict[str, object]:
    record_content = f"Historical {RETIRED_UPPER} record.\n".encode()
    binding_content = f"projectKey=service_{RETIRED_LOWER}\n".encode()
    record_path = "docs/decisions/issue-1-preflight.md"
    binding_path = "service-project.properties"
    _seed_repo(
        repo_root,
        files={
            record_path: record_content,
            binding_path: binding_content,
        },
        records=[_record(record_path, record_content)],
        bindings=[_binding(binding_path, binding_content)],
    )
    return json.loads((repo_root / MANIFEST_PATH).read_text(encoding="utf-8"))


def _write_manifest(repo_root: Path, manifest: object) -> None:
    _write(
        repo_root / MANIFEST_PATH,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )


def _manifest_rule_ids(repo_root: Path) -> set[str]:
    return {failure.rule_id for failure in evaluate_identity_cutover(repo_root)}


def test_current_repository_satisfies_identity_cutover() -> None:
    assert evaluate_identity_cutover(REPO_ROOT) == []


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("schema_version", "wrong-schema"),
        ("hash_algorithm", "sha512"),
        ("records", {}),
        ("operational_bindings", {}),
    ],
)
def test_invalid_manifest_top_level_fields_fail(tmp_path: Path, field: str, invalid_value: object) -> None:
    manifest = _seed_manifest_fixture(tmp_path)
    manifest[field] = invalid_value
    _write_manifest(tmp_path, manifest)

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


@pytest.mark.parametrize("content", ["{", '{"records": [], "records": []}', b"\xff\xfe"])
def test_undecodable_or_duplicate_key_manifest_is_a_manifest_failure(tmp_path: Path, content: str | bytes) -> None:
    _seed_manifest_fixture(tmp_path)
    _write(tmp_path / MANIFEST_PATH, content)

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


def test_a_defect_while_loading_the_manifest_is_not_reported_as_a_manifest_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.check_identity_cutover as gate

    _seed_manifest_fixture(tmp_path)

    def defective(*_args, **_kwargs):
        raise ValueError("loader defect")

    monkeypatch.setattr(gate, "load_bounded_json_object", defective)
    with pytest.raises(ValueError, match="loader defect"):
        gate.evaluate_identity_cutover(tmp_path)


@pytest.mark.parametrize("collection", ["records", "operational_bindings"])
@pytest.mark.parametrize(
    "mutation",
    [
        "non-object",
        "missing-key",
        "extra-key",
        "unknown-class",
        "blank-rationale",
        "bad-digest",
    ],
)
def test_invalid_manifest_entry_shapes_fail(tmp_path: Path, collection: str, mutation: str) -> None:
    manifest = _seed_manifest_fixture(tmp_path)
    entries = manifest[collection]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)

    if mutation == "non-object":
        entries[0] = "not-an-object"
    elif mutation == "missing-key":
        del entry["content_sha256"]
    elif mutation == "extra-key":
        entry["unexpected"] = "field"
    elif mutation == "unknown-class":
        class_field = "record_class" if collection == "records" else "binding_class"
        entry[class_field] = "unknown-class"
    elif mutation == "blank-rationale":
        entry["rationale"] = " "
    else:
        entry["content_sha256"] = "not-a-sha256"

    _write_manifest(tmp_path, manifest)

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


@pytest.mark.parametrize("collection", ["records", "operational_bindings"])
@pytest.mark.parametrize("invalid_occurrences", [True, 0, -1, "1"])
def test_invalid_manifest_occurrence_counts_fail(
    tmp_path: Path,
    collection: str,
    invalid_occurrences: object,
) -> None:
    manifest = _seed_manifest_fixture(tmp_path)
    entries = manifest[collection]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    entry["occurrences"] = invalid_occurrences
    _write_manifest(tmp_path, manifest)

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


@pytest.mark.parametrize("collection", ["records", "operational_bindings"])
def test_duplicate_manifest_paths_fail(tmp_path: Path, collection: str) -> None:
    manifest = _seed_manifest_fixture(tmp_path)
    entries = manifest[collection]
    assert isinstance(entries, list)
    entries.append(copy.deepcopy(entries[0]))
    _write_manifest(tmp_path, manifest)

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


def test_path_shared_between_record_and_binding_fails(tmp_path: Path) -> None:
    manifest = _seed_manifest_fixture(tmp_path)
    records = manifest["records"]
    bindings = manifest["operational_bindings"]
    assert isinstance(records, list) and isinstance(records[0], dict)
    assert isinstance(bindings, list) and isinstance(bindings[0], dict)
    bindings[0]["path"] = records[0]["path"]
    _write_manifest(tmp_path, manifest)

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


def test_live_retired_identity_fails_in_visible_hidden_and_binary_files(tmp_path: Path) -> None:
    _seed_repo(
        tmp_path,
        files={
            "README.md": f"live {RETIRED_UPPER} identity\n",
            ".github/workflow.yml": f"project: {RETIRED_LOWER}-sdl\n",
            "artifact.bin": b"\x00" + RETIRED_LOWER.encode() + b".runtime\xff",
            "escaped.py": f'value = "prefix\\\\n{RETIRED_LOWER}-artifact\\\\n"\n',
        },
    )

    failures = evaluate_identity_cutover(tmp_path)

    assert {failure.path for failure in failures if failure.rule_id == "identity-cutover-live-token"} == {
        ".github/workflow.yml",
        "README.md",
        "artifact.bin",
        "escaped.py",
    }


def test_exact_content_bound_historical_record_passes(tmp_path: Path) -> None:
    content = f"# Decision\n\nThe {RETIRED_UPPER} name was current on this date.\n".encode()
    path = "docs/decisions/issue-1-preflight.md"
    _seed_repo(
        tmp_path,
        files={path: content},
        records=[_record(path, content)],
    )

    assert evaluate_identity_cutover(tmp_path) == []


def test_exact_content_bound_lifecycle_record_passes(tmp_path: Path) -> None:
    content = f'identifier: "retired {RETIRED_LOWER}-sdl distribution"\n'.encode()
    path = "specs/evolution/deprecation-records.yaml"
    _seed_repo(
        tmp_path,
        files={path: content},
        records=[_record(path, content, record_class="lifecycle-record")],
    )

    assert evaluate_identity_cutover(tmp_path) == []


def test_changed_historical_record_fails_closed(tmp_path: Path) -> None:
    original = f"Historical {RETIRED_UPPER} record.\n".encode()
    path = "docs/decisions/issue-1-preflight.md"
    _seed_repo(
        tmp_path,
        files={path: original},
        records=[_record(path, original)],
    )
    _write(tmp_path / path, original + b"Changed after classification.\n")

    failures = evaluate_identity_cutover(tmp_path)

    assert any(
        failure.rule_id == "identity-cutover-historical-content" and failure.path == path for failure in failures
    )


def test_exact_content_bound_operational_binding_passes_and_fails_closed(tmp_path: Path) -> None:
    content = f"projectKey=Brad-Edwards_{RETIRED_LOWER}\n".encode()
    path = "sonar-project.properties"
    _seed_repo(
        tmp_path,
        files={path: content},
        bindings=[_binding(path, content)],
    )

    assert evaluate_identity_cutover(tmp_path) == []

    _write(tmp_path / path, content + b"changed=true\n")
    failures = evaluate_identity_cutover(tmp_path)

    assert any(
        failure.rule_id == "identity-cutover-operational-content" and failure.path == path for failure in failures
    )


def test_historical_occurrence_count_is_verified(tmp_path: Path) -> None:
    content = f"{RETIRED_UPPER} and {RETIRED_LOWER}.runtime\n".encode()
    path = "docs/research/snapshot.md"
    _seed_repo(
        tmp_path,
        files={path: content},
        records=[_record(path, content, occurrences=1)],
    )

    failures = evaluate_identity_cutover(tmp_path)

    assert any(failure.rule_id == "identity-cutover-historical-count" and failure.path == path for failure in failures)


def test_unsafe_or_untracked_historical_path_fails_closed(tmp_path: Path) -> None:
    _seed_repo(
        tmp_path,
        files={"README.md": "RAES\n"},
        records=[
            _record(
                "../outside.md",
                f"Historical {RETIRED_UPPER} record.\n".encode(),
            )
        ],
    )

    failures = evaluate_identity_cutover(tmp_path)

    assert any(failure.rule_id == "identity-cutover-manifest-path" for failure in failures)


def test_unsafe_operational_binding_path_fails_closed(tmp_path: Path) -> None:
    manifest = _seed_manifest_fixture(tmp_path)
    bindings = manifest["operational_bindings"]
    assert isinstance(bindings, list) and isinstance(bindings[0], dict)
    bindings[0]["path"] = "../outside.properties"
    _write_manifest(tmp_path, manifest)

    assert "identity-cutover-manifest-path" in _manifest_rule_ids(tmp_path)


_GENERATED_PATH = "CHANGELOG.md"
_GENERATED_TAIL = f"## [1.0.0]\n\n* retained {RETIRED_UPPER} release note\n".encode()
_GENERATED_HEAD = b"# Changelog\n\n## [2.0.0]\n\n* a released feature\n\n"


def _seed_generated_history(repo_root: Path, content: bytes, tail: bytes = _GENERATED_TAIL) -> None:
    _seed_repo(
        repo_root,
        files={_GENERATED_PATH: content},
        generated=[_generated_record(_GENERATED_PATH, tail)],
    )


def test_generated_release_history_tolerates_new_sections_above_the_classified_tail(tmp_path: Path) -> None:
    """A release bot prepending a section must not turn the gate red."""
    _seed_generated_history(tmp_path, _GENERATED_HEAD + _GENERATED_TAIL)

    assert evaluate_identity_cutover(tmp_path) == []


def test_generated_release_history_rejects_retired_identity_in_generated_head(tmp_path: Path) -> None:
    head = f"# Changelog\n\n## [2.0.0]\n\n* revive the {RETIRED_LOWER}-invariants profile\n\n".encode()
    _seed_generated_history(tmp_path, head + _GENERATED_TAIL)

    assert "identity-cutover-generated-head" in _manifest_rule_ids(tmp_path)


def test_generated_release_history_rejects_edited_tail(tmp_path: Path) -> None:
    edited_tail = _GENERATED_TAIL.replace(b"1.0.0", b"1.0.1")
    _seed_generated_history(tmp_path, _GENERATED_HEAD + edited_tail)

    assert "identity-cutover-generated-content" in _manifest_rule_ids(tmp_path)


def test_generated_release_history_rejects_truncated_tail(tmp_path: Path) -> None:
    _seed_generated_history(tmp_path, _GENERATED_TAIL[:4])

    assert "identity-cutover-generated-content" in _manifest_rule_ids(tmp_path)


def test_generated_release_history_verifies_tail_occurrence_count(tmp_path: Path) -> None:
    _seed_repo(
        tmp_path,
        files={_GENERATED_PATH: _GENERATED_HEAD + _GENERATED_TAIL},
        generated=[_generated_record(_GENERATED_PATH, _GENERATED_TAIL, occurrences=2)],
    )

    assert "identity-cutover-generated-count" in _manifest_rule_ids(tmp_path)


def test_generated_release_history_path_must_be_tracked(tmp_path: Path) -> None:
    _seed_generated_history(tmp_path, _GENERATED_HEAD + _GENERATED_TAIL)
    (tmp_path / _GENERATED_PATH).unlink()
    _git(tmp_path, "rm", "--cached", "-q", _GENERATED_PATH)

    assert "identity-cutover-manifest-path" in _manifest_rule_ids(tmp_path)


def test_generated_release_history_rejects_non_positive_suffix_bytes(tmp_path: Path) -> None:
    record = _generated_record(_GENERATED_PATH, _GENERATED_TAIL)
    record["classified_suffix_bytes"] = 0
    _seed_repo(
        tmp_path,
        files={_GENERATED_PATH: _GENERATED_HEAD + _GENERATED_TAIL},
        generated=[record],
    )

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


def test_generated_release_history_rejects_duplicate_content_bound_path(tmp_path: Path) -> None:
    content = _GENERATED_HEAD + _GENERATED_TAIL
    _seed_repo(
        tmp_path,
        files={_GENERATED_PATH: content},
        records=[_record(_GENERATED_PATH, content, record_class="release-history")],
        generated=[_generated_record(_GENERATED_PATH, _GENERATED_TAIL)],
    )

    assert "identity-cutover-manifest" in _manifest_rule_ids(tmp_path)


def test_repository_changelog_is_bound_as_generated_release_history() -> None:
    """The real CHANGELOG must stay on the append-tolerant class, not a whole-file pin."""
    manifest = json.loads((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    generated = {entry["path"] for entry in manifest["generated_history_records"]}
    pinned = {entry["path"] for entry in manifest["records"]}

    assert "CHANGELOG.md" in generated
    assert "CHANGELOG.md" not in pinned


def test_identity_cutover_check_is_registered_in_canonical_policy_graph() -> None:
    policy_lane_source = (REPO_ROOT / "tools" / "nox_support" / "policy_lanes.py").read_text(encoding="utf-8")
    assert '"tools/check_identity_cutover.py"' in policy_lane_source
