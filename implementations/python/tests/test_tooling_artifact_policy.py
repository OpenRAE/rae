from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import (
    check_atlas_tactic_vocabulary,
    check_attack_tactic_vocabulary,
    check_autonomous_behavior_vocabularies,
    check_nist_csf_defensive_vocabulary,
    check_tooling_artifact_policy,
    gitleaks_tool,
    isabelle_tool,
    osv_scanner_tool,
    tooling_policy_gate,
    vale_tool,
)
from tools.check_tooling_artifact_policy import (
    ACTIONS_POLICY_PATH,
    ARTIFACT_LOCK_PATH,
    INVENTORY_COVERAGE_PATH,
    PROFILES_PATH,
    SELECTOR_BINDINGS_PATH,
    _tracked_paths,
    evaluate_tooling_artifact_policy,
    normalize_platform_id,
    select_tooling_artifact,
    select_tooling_host_profile,
    tooling_policy_sha256,
)
from tools.policy import conftest_tool
from tools.tooling_policy_gate import LockedArtifactSelection, LockedManifestEntry

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLING_ROOT = REPO_ROOT / "implementations" / "tooling"

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_INVENTORY_IDS = (
    *(f"I{index:02d}" for index in range(1, 17)),
    *(f"A{index:02d}" for index in range(1, 8)),
    *(f"O{index:02d}" for index in range(1, 5)),
    *(f"C{index:02d}" for index in range(1, 5)),
    "S01",
    "S02",
    "D01",
)


def _write_json(root: Path, relative: str, payload: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_policy(root: Path) -> Path:
    shutil.copytree(TOOLING_ROOT / "schemas", root / "implementations" / "tooling" / "schemas")
    artifact = {
        "artifact_id": "tool-a",
        "artifact_class": "generic-cli",
        "version": "1.0.0",
        "owner": "Tooling",
        "consumers": ["policy"],
        "trust_root_refs": ["review:fixture"],
        "availability_class": "R",
        "retention_class": "supported-input",
        "license": {
            "spdx": "Apache-2.0",
            "redistribution": "allowed",
            "review_ref": "review:fixture",
        },
        "authenticity": {
            "status": "absent-reviewed",
            "decision_ref": "review:fixture",
        },
        "policy_refs": ["artifact-integrity-v1"],
        "source": {
            "repository": "https://example.invalid/tool-a",
            "release": "v1.0.0",
            "asset": "tool-a.tar.gz",
            "locator_refs": ["official"],
        },
        "platforms": [
            {
                "platform_id": "linux-x86_64",
                "source_urls": ["https://example.invalid/tool-a.tar.gz"],
                "raw_manifest": [
                    {"path": "tool-a.tar.gz", "sha256": _SHA_A, "size": 1},
                ],
                "installed_manifest": [
                    {"path": "tool-a", "sha256": _SHA_B, "size": 1, "executable": True},
                ],
                "dependencies": [],
                "profile_ids": ["public-linux-x86_64"],
            }
        ],
    }
    _write_json(
        root,
        ARTIFACT_LOCK_PATH,
        {
            "schema_version": "raes-development-artifact-lock/v1",
            "lock_revision": "2026-09-06",
            "artifacts": [artifact],
        },
    )
    _write_json(
        root,
        PROFILES_PATH,
        {
            "schema_version": "raes-development-profiles/v2",
            "profiles": [
                {
                    "profile_id": "public-linux-x86_64",
                    "contexts": ["public-contributor"],
                    "platform": {
                        "canonical_id": "linux-x86_64",
                        "aliases": ["Linux-amd64", "linux-amd64", "linux-x86_64"],
                    },
                    "locator_classes": [
                        {
                            "locator_id": "official",
                            "kind": "official-https",
                            "trust_root_ref": "system-ca",
                        }
                    ],
                    "supported_artifact_ids": ["tool-a"],
                }
            ],
            "host_profiles": [
                {
                    "host_profile_id": "fixture-linux-x86_64",
                    "platform_id": "linux-x86_64",
                    "contexts": ["public-contributor"],
                    "native_family": "ubuntu-apt",
                    "base_image_identity": "fixture-image:1",
                    "native_repository_identity": "fixture-repository:1",
                    "trust_root_refs": ["fixture-root"],
                    "credential_refs": [],
                    "bootstrap_payload_ids": ["tool-a"],
                    "required_capability_ids": ["git"],
                    "proof_support": "unsupported",
                    "host_security_control_changes": "prohibited",
                    "offline_kit": {
                        "kit_id": "fixture-kit",
                        "credential_free": True,
                        "network_fallback": "prohibited",
                        "artifact_ids": ["tool-a"],
                        "host_prerequisite_package_ids": ["git"],
                        "host_trust_root_refs": ["fixture-root"],
                    },
                    "qualification_record_ids": ["fixture-evidence"],
                }
            ],
            "qualification_records": [
                {
                    "evidence_id": "fixture-evidence",
                    "host_profile_id": "fixture-linux-x86_64",
                    "test_case_ids": ["T01"],
                    "implementation_revision": "a" * 40,
                    "observed_at": "2026-09-07T00:00:00Z",
                    "context": "fixture",
                    "outcome": "passed",
                    "base_image_identity": "fixture-image:1",
                    "native_repository_identity": "fixture-repository:1",
                    "policy_sha256": _SHA_A,
                    "capability_results": [{"capability_id": "git", "outcome": "passed", "observed_identity": "git:1"}],
                    "evidence_location": "fixture:evidence",
                    "evidence_sha256": _SHA_B,
                }
            ],
        },
    )
    _write_json(
        root,
        "implementations/tooling/admission-policy.json",
        {
            "schema_version": "raes-development-admission-policy/v1",
            "policy_revision": "2026-09-06",
            "policies": [
                {
                    "policy_id": "artifact-integrity-v1",
                    "subject": "artifact",
                    "status": "active",
                    "accepted_evidence": [
                        "raw-sha256",
                        "installed-sha256",
                        "exact-size",
                        "absent-signature-review",
                    ],
                    "reviewer_roles": ["Tooling", "Security"],
                },
                {
                    "policy_id": "action-source-v1",
                    "subject": "action",
                    "status": "active",
                    "accepted_evidence": ["git-commit-sha", "reviewed-workflow-reference"],
                    "reviewer_roles": ["Tooling", "Security"],
                },
            ],
            "denied_digests": [],
        },
    )
    _write_json(
        root,
        ACTIONS_POLICY_PATH,
        {
            "schema_version": "raes-development-actions-policy/v1",
            "policy_revision": "2026-09-06",
            "policy_refs": ["action-source-v1"],
            "actions": [],
            "local_workflows": [],
        },
    )
    _write_json(
        root,
        SELECTOR_BINDINGS_PATH,
        {
            "schema_version": "raes-development-selector-bindings/v1",
            "bindings": [],
            "runtime_selections": [
                {
                    "artifact_id": "tool-a",
                    "consumers": ["tools/acquire_tool_a.py"],
                }
            ],
            "tracked_literals": [],
        },
    )
    acquire_path = root / "tools" / "acquire_tool_a.py"
    acquire_path.parent.mkdir(parents=True, exist_ok=True)
    acquire_path.write_text(
        "load_tooling_artifact_selection(\n"
        "    artifact_id='tool-a', version=VERSION, platform_id=PLATFORM, profile_id=PROFILE\n"
        ")\n",
        encoding="utf-8",
    )
    _write_json(
        root,
        INVENTORY_COVERAGE_PATH,
        {
            "schema_version": "raes-development-inventory-coverage/v1",
            "inventory_source": "docs/decisions/package-artifacts/inventory.md",
            "rows": [
                {
                    "inventory_id": inventory_id,
                    "subjects": ["action" if inventory_id.startswith("A") else "artifact"],
                    "evidence_refs": ["reviewed-workflow-reference" if inventory_id.startswith("A") else "raw-sha256"],
                    "owner_roles": ["Tooling"],
                    "consumers": ["fixture"],
                    "trust_root_refs": ["review:fixture"],
                    "availability_class": "R",
                    "retention_class": "supported-input",
                    "disposition": "locked" if inventory_id == "I05" else "delegated",
                    "authority_refs": [ARTIFACT_LOCK_PATH],
                    "policy_refs": ["action-source-v1" if inventory_id.startswith("A") else "artifact-integrity-v1"],
                    "owning_issue": 1216,
                }
                for inventory_id in _INVENTORY_IDS
            ],
            "acquisition_paths": [],
        },
    )
    profiles = _load(root, PROFILES_PATH)
    profiles["qualification_records"][0]["policy_sha256"] = tooling_policy_sha256(root)
    _write_json(root, PROFILES_PATH, profiles)
    return root


def _failures(root: Path, *, tracked_paths: list[str] | None = None) -> set[str]:
    paths = ["tools/acquire_tool_a.py", *(tracked_paths or [])]
    return {failure.rule_id for failure in evaluate_tooling_artifact_policy(root, tracked_paths=paths)}


def _load(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _seed_python_closure_authorities(root: Path) -> dict[str, dict]:
    for relative in (
        "implementations/python/pyproject.toml",
        "implementations/python/uv.lock",
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)
    shutil.copytree(
        REPO_ROOT / "implementations" / "tooling" / "python",
        root / "implementations" / "tooling" / "python",
        ignore=shutil.ignore_patterns(".venv"),
    )
    return {PROFILES_PATH: _load(REPO_ROOT, PROFILES_PATH)}


def _python_closure_rule_ids(root: Path, documents: dict[str, dict]) -> set[str]:
    from tools.tooling_artifact_policy_python import python_closure_failures

    return {item.rule_id for item in python_closure_failures(root, documents, tracked_paths=[])}


@pytest.mark.integration
@pytest.mark.timeout(300)
def test_checked_in_tooling_policy_is_valid_and_deterministic() -> None:
    first = evaluate_tooling_artifact_policy(REPO_ROOT)
    second = evaluate_tooling_artifact_policy(REPO_ROOT)
    assert first == second == []


def test_checked_in_python_closure_profiles_are_closed_and_complete() -> None:
    from tools.python_closure import load_python_closure_profile

    expected_project = {f"public-linux-x86_64-cp{minor}-all-extras" for minor in (311, 312, 313, 314)} | {
        "public-linux-arm64-cp314-all-extras",
        "public-macos-arm64-cp314-all-extras",
    }
    expected_tools = {
        "public-linux-x86_64-cp314-tools",
        "public-linux-arm64-cp314-tools",
        "public-macos-x86_64-cp314-tools",
        "public-macos-arm64-cp314-tools",
    }
    document = _load(REPO_ROOT, PROFILES_PATH)
    profiles = {profile["python_closure_profile_id"]: profile for profile in document["python_closure_profiles"]}

    assert set(profiles) == expected_project | expected_tools
    assert {profiles[profile_id]["python"]["version"] for profile_id in expected_project} == {
        "3.11",
        "3.12",
        "3.13",
        "3.14",
    }
    assert all(profiles[profile_id]["project_extras"] == ["dev", "docs"] for profile_id in expected_project)
    assert all(profiles[profile_id]["purposes"] == ["tool", "build"] for profile_id in expected_tools)
    assert all(profiles[profile_id]["project_extras"] == [] for profile_id in expected_tools)
    assert all(profiles[profile_id]["tool_groups"] == ["default", "build"] for profile_id in expected_tools)
    macos_x86_tools = json.loads(
        (REPO_ROOT / profiles["public-macos-x86_64-cp314-tools"]["wheelhouse_manifest"]).read_text(encoding="utf-8")
    )
    artifacts = {item["name"]: item for item in macos_x86_tools["artifacts"]}
    assert {"cryptography", "hatchling", "pathspec", "trove-classifiers"} <= artifacts.keys()
    assert "macosx_10_9_universal2" in artifacts["cryptography"]["filename"]
    loaded = load_python_closure_profile(REPO_ROOT, "public-linux-x86_64-cp312-all-extras")
    assert loaded.build_constraints.name == "build-constraints.txt"
    assert loaded.test_case_ids == ("T03", "T10", "T11", "T13", "T23")


def test_python_closure_environment_discards_ambient_acquisition_state(tmp_path: Path) -> None:
    from tools.python_closure import closure_environment, load_python_closure_profile

    profile = load_python_closure_profile(REPO_ROOT, "public-linux-x86_64-cp312-all-extras")
    environment = closure_environment(
        profile,
        context_id="python-offline",
        home=tmp_path / "home",
        cache_dir=tmp_path / "cache",
        source={
            "PATH": "/usr/bin",
            "UV_INDEX_URL": "https://unreviewed.invalid/simple",
            "PIP_EXTRA_INDEX_URL": "https://also-unreviewed.invalid/simple",
            "PYTHONPATH": "/checkout/packages",
            "HTTP_PROXY": "http://proxy.invalid",
        },
    )

    assert environment == {
        "HOME": str(tmp_path / "home"),
        "PATH": "/usr/bin",
        "UV_CACHE_DIR": str(tmp_path / "cache"),
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_OFFLINE": "1",
        "UV_PYTHON_DOWNLOADS": "never",
    }


def test_python_wheelhouse_admission_rejects_missing_unexpected_wrong_hash_and_symlink(tmp_path: Path) -> None:
    from tools.python_closure import verify_wheelhouse

    payload = b"reviewed-wheel"
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {
        "artifacts": [
            {
                "filename": "fixture-1.0-py3-none-any.whl",
                "sha256": digest,
                "size": len(payload),
            }
        ]
    }
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    with pytest.raises(ValueError, match="missing"):
        verify_wheelhouse(wheelhouse, manifest)

    artifact = wheelhouse / "fixture-1.0-py3-none-any.whl"
    artifact.write_bytes(b"wrong")
    with pytest.raises(ValueError, match="digest|size"):
        verify_wheelhouse(wheelhouse, manifest)

    artifact.write_bytes(payload)
    unexpected = wheelhouse / "unexpected.whl"
    unexpected.write_bytes(payload)
    with pytest.raises(ValueError, match="unexpected"):
        verify_wheelhouse(wheelhouse, manifest)

    unexpected.unlink()
    artifact.unlink()
    artifact.symlink_to(tmp_path / "outside.whl")
    with pytest.raises(ValueError, match="regular"):
        verify_wheelhouse(wheelhouse, manifest)


def _seed_bootstrap_wheelhouse_fixture(
    tmp_path: Path,
) -> tuple[Path, str, Path, Path, Path, Path, Path]:
    root = tmp_path / "repo"
    profiles_path = root / PROFILES_PATH
    manifest_path = root / "closure-manifest.json"
    requirements_path = root / "closure-requirements.txt"
    lock_path = root / "closure.lock"
    wheelhouse = root / "wheelhouse"
    snapshot_path = root / "manifest-snapshot.json"
    profiles_path.parent.mkdir(parents=True)
    wheelhouse.mkdir()
    requirements_path.write_text("fixture==1 --hash=sha256:" + _SHA_A + "\n", encoding="utf-8")
    lock_path.write_text("locked\n", encoding="utf-8")
    artifact = wheelhouse / "fixture-1-py3-none-any.whl"
    artifact.write_bytes(b"reviewed-wheel")
    profile_id = "bootstrap-test"
    manifest = {
        "python_closure_profile_id": profile_id,
        "lock_path": lock_path.relative_to(root).as_posix(),
        "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements_path.read_bytes()).hexdigest(),
        "artifacts": [
            {
                "filename": artifact.name,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "size": artifact.stat().st_size,
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    snapshot_path.write_bytes(manifest_path.read_bytes())
    profiles_path.write_text(
        json.dumps(
            {
                "python_closure_profiles": [
                    {
                        "python_closure_profile_id": profile_id,
                        "wheelhouse_manifest": manifest_path.relative_to(root).as_posix(),
                        "smoke_requirements": requirements_path.relative_to(root).as_posix(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return (
        root,
        profile_id,
        wheelhouse,
        snapshot_path,
        manifest_path,
        lock_path,
        requirements_path,
    )


@pytest.mark.integration
def test_bootstrap_wheelhouse_verification_runs_without_site_packages(tmp_path: Path) -> None:
    root, profile_id, wheelhouse, snapshot_path, _manifest_path, _lock_path, _requirements_path = (
        _seed_bootstrap_wheelhouse_fixture(tmp_path)
    )
    code = (
        "import sys; from pathlib import Path; "
        "sys.path.insert(0, sys.argv[1]); "
        "from tools.python_closure import verify_bootstrap_wheelhouse; "
        "verify_bootstrap_wheelhouse(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5]))"
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            code,
            str(REPO_ROOT),
            str(root),
            profile_id,
            str(wheelhouse),
            str(snapshot_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("snapshot", "does not match the reviewed authority"),
        ("lock", "lock identity is stale"),
        ("requirements", "requirements identity is stale"),
        ("profile", "profile identity is wrong"),
        ("symlink", "must be a regular file"),
    ],
)
def test_bootstrap_wheelhouse_verification_rejects_stale_or_untrusted_identity(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    from tools.python_closure import verify_bootstrap_wheelhouse

    root, profile_id, wheelhouse, snapshot_path, manifest_path, _lock_path, _requirements_path = (
        _seed_bootstrap_wheelhouse_fixture(tmp_path)
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "snapshot":
        snapshot_path.write_text("{}\n", encoding="utf-8")
    elif mutation == "lock":
        manifest["lock_sha256"] = _SHA_A
    elif mutation == "requirements":
        manifest["requirements_sha256"] = _SHA_B
    elif mutation == "profile":
        manifest["python_closure_profile_id"] = "another-profile"
    elif mutation == "symlink":
        snapshot_path.unlink()
        snapshot_path.symlink_to(manifest_path)
    else:  # pragma: no cover - the parametrization above is closed.
        raise AssertionError(f"unknown mutation: {mutation}")
    if mutation in {"lock", "requirements", "profile"}:
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        snapshot_path.write_bytes(manifest_path.read_bytes())

    with pytest.raises(ValueError, match=message):
        verify_bootstrap_wheelhouse(root, profile_id, wheelhouse, snapshot_path)


def test_python_closure_anchors_relative_paths_before_temporary_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tools import python_closure

    project_root = REPO_ROOT / "implementations" / "python"
    constraints = REPO_ROOT / "implementations" / "tooling" / "python" / "build-constraints.txt"
    requirements = REPO_ROOT / "implementations" / "tooling" / "python" / "smoke" / "linux-x86_64-cp314.txt"
    profile = SimpleNamespace(
        project_lock=project_root / "uv.lock",
        build_constraints=constraints,
        smoke_requirements=requirements,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
        abi=f"cp{sys.version_info.major}{sys.version_info.minor}",
        platform="x86_64-unknown-linux-gnu",
        acquisition_context_ids=("python-public", "python-offline"),
        contexts={"python-public": {"mode": "public"}, "python-offline": {"mode": "offline"}},
    )
    monkeypatch.chdir(tmp_path)
    relative_source = Path(os.path.relpath(project_root, tmp_path))
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> None:
        calls.append(command)
        if "--sdist" in command:
            (tmp_path / "build-output" / "raes-1.tar.gz").write_bytes(b"sdist")

    monkeypatch.setattr(python_closure, "_run", fake_run)
    monkeypatch.setattr(python_closure, "load_wheelhouse_manifest", lambda _profile: {"artifacts": []})
    monkeypatch.setattr(python_closure, "verify_wheelhouse", lambda *_args: None)

    python_closure._build(profile, relative_source, Path("build-output"), context_id="python-public")
    candidate = tmp_path / "candidate.whl"
    candidate.write_bytes(b"wheel")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    python_closure._smoke(
        profile,
        Path("candidate.whl"),
        Path("installed"),
        wheelhouse=Path("wheelhouse"),
        offline=True,
    )
    monkeypatch.setattr(python_closure, "verify_wheelhouse", lambda *_args: None)
    python_closure._materialize(profile, Path("materialized"))

    rendered = "\n".join(" ".join(command) for command in calls)
    assert str(tmp_path / "build-output") in rendered
    assert str(project_root) in rendered
    assert str(tmp_path / "candidate.whl") in rendered
    assert str(tmp_path / "installed") in rendered
    assert str(tmp_path / "wheelhouse") in rendered
    assert str(tmp_path / "materialized") in rendered


def test_python_closure_policy_rejects_authority_and_projection_drift(tmp_path: Path) -> None:
    direct_root = tmp_path / "direct-pin"
    direct_documents = _seed_python_closure_authorities(direct_root)
    tool_project = direct_root / "implementations" / "tooling" / "python" / "pyproject.toml"
    tool_project.write_text(
        tool_project.read_text(encoding="utf-8").replace("ruff==0.15.9", "ruff==0.15.8"),
        encoding="utf-8",
    )
    assert "tooling-python-direct-pins" in _python_closure_rule_ids(direct_root, direct_documents)

    lock_root = tmp_path / "lock"
    lock_documents = _seed_python_closure_authorities(lock_root)
    tool_lock = lock_root / "implementations" / "tooling" / "python" / "uv.lock"
    tool_lock.write_text(
        tool_lock.read_text(encoding="utf-8").replace(
            'name = "ruff"\nversion = "0.15.9"', 'name = "ruff"\nversion = "0.15.8"'
        ),
        encoding="utf-8",
    )
    lock_failures = _python_closure_rule_ids(lock_root, lock_documents)
    assert {"tooling-python-lock", "tooling-python-projection-generation"} <= lock_failures

    constraints_root = tmp_path / "constraints"
    constraints_documents = _seed_python_closure_authorities(constraints_root)
    constraints = constraints_root / "implementations" / "tooling" / "python" / "build-constraints.txt"
    constraints.write_text("hatchling==1.27.0\n", encoding="utf-8")
    assert "tooling-python-build-constraints" in _python_closure_rule_ids(
        constraints_root,
        constraints_documents,
    )

    projection_root = tmp_path / "projection"
    projection_documents = _seed_python_closure_authorities(projection_root)
    requirements = projection_root / "implementations" / "tooling" / "python" / "smoke" / "linux-x86_64-cp312.txt"
    requirements.write_text(requirements.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
    projection_failures = _python_closure_rule_ids(projection_root, projection_documents)
    assert {"tooling-python-projection-drift", "tooling-python-projection-generation"} <= projection_failures

    profile_root = tmp_path / "profile"
    profile_documents = _seed_python_closure_authorities(profile_root)
    profile_documents[PROFILES_PATH]["python_closure_profiles"][0]["tool_groups"] = ["default"]
    assert "tooling-python-groups" in _python_closure_rule_ids(profile_root, profile_documents)


def test_python_closure_policy_rejects_symlink_authority_and_public_fallback(tmp_path: Path) -> None:
    root = tmp_path / "symlink"
    documents = _seed_python_closure_authorities(root)
    constraints = root / "implementations" / "tooling" / "python" / "build-constraints.txt"
    target = constraints.with_name("constraints-target.txt")
    constraints.rename(target)
    constraints.symlink_to(target.name)
    assert "tooling-python-authority" in _python_closure_rule_ids(root, documents)

    fallback_root = tmp_path / "fallback"
    fallback_documents = _seed_python_closure_authorities(fallback_root)
    fallback_documents[PROFILES_PATH]["python_package_contexts"][1]["public_fallback"] = "permitted"
    assert "tooling-python-fallback" in _python_closure_rule_ids(
        fallback_root,
        fallback_documents,
    )


def test_seeded_policy_has_no_failures(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    assert (
        evaluate_tooling_artifact_policy(
            root,
            tracked_paths=["tools/acquire_tool_a.py"],
        )
        == []
    )


def test_policy_digest_binds_host_policy_and_every_authority(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    original = tooling_policy_sha256(root)
    profiles = _load(root, PROFILES_PATH)
    profiles["host_profiles"][0]["required_capability_ids"].append("sha256")
    _write_json(root, PROFILES_PATH, profiles)
    assert tooling_policy_sha256(root) != original
    assert "tooling-host-evidence-policy" in _failures(root)


def test_policy_digest_excludes_qualification_result_records(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    original = tooling_policy_sha256(root)
    profiles = _load(root, PROFILES_PATH)
    profiles["qualification_records"][0]["policy_sha256"] = "f" * 64
    profiles["qualification_records"][0]["evidence_sha256"] = "e" * 64
    _write_json(root, PROFILES_PATH, profiles)
    assert tooling_policy_sha256(root) == original


def test_python_discovery_parses_each_tracked_source_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _seed_policy(tmp_path)
    from tools import tooling_artifact_policy_discovery

    parse = tooling_artifact_policy_discovery.ast.parse
    parse_calls = 0

    def count_parse(*args: object, **kwargs: object):
        nonlocal parse_calls
        parse_calls += 1
        return parse(*args, **kwargs)

    monkeypatch.setattr(tooling_artifact_policy_discovery.ast, "parse", count_parse)
    assert _failures(root) == set()
    assert parse_calls == 1


def test_selection_launcher_uses_frozen_uv_without_a_tool_venv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "implementations" / "tooling" / "python"
    project_root.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (project_root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    validator = tmp_path / "tools" / "check_tooling_artifact_policy.py"
    validator.parent.mkdir()
    validator.write_text("raise SystemExit(0)\n", encoding="utf-8")

    monkeypatch.setattr(tooling_policy_gate.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    assert tooling_policy_gate._frozen_validator_command(tmp_path) == [
        "/usr/bin/uv",
        "run",
        "--project",
        str(project_root),
        "--frozen",
        "--no-default-groups",
        "python",
        str(validator),
    ]
    assert tooling_policy_gate._VALIDATOR_TIMEOUT_SECONDS == 180


def test_host_selection_launcher_rejects_an_unbound_validator_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "host_profile": {
            "host_profile_id": "host-a",
            "platform_id": "linux-x86_64",
            "bootstrap_payload_ids": ["uv"],
        },
        "artifacts": [
            {
                "artifact_id": "uv",
                "artifact_class": "bootstrap",
                "version": "1.0.0",
                "source": {"repository": "https://example.invalid", "release": "v1.0.0"},
                "platform": {
                    "platform_id": "linux-x86_64",
                    "host_profile_ids": ["host-a"],
                    "source_urls": ["https://example.invalid/uv"],
                    "raw_manifest": [{"path": "uv.tar.gz", "sha256": _SHA_A, "size": 1}],
                    "installed_manifest": [{"path": "uv", "sha256": _SHA_A, "size": 1}],
                },
            }
        ],
        "policy_sha256": _SHA_A,
    }
    monkeypatch.setattr(tooling_policy_gate, "_frozen_validator_command", lambda _root: ["validator"])
    monkeypatch.setattr(tooling_policy_gate, "_validator_host_stdout", lambda *_args, **_kwargs: json.dumps(response))
    assert tooling_policy_gate.load_tooling_host_profile_selection("host-a") == response
    response["artifacts"].append({"artifact_id": "uv"})
    with pytest.raises(RuntimeError, match="invalid host selection response"):
        tooling_policy_gate.load_tooling_host_profile_selection("host-a")


@pytest.mark.integration
def test_repository_discovery_uses_only_git_tracked_paths(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    assert _tracked_paths(tmp_path) == ["tracked.py"]


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    path = root / ARTIFACT_LOCK_PATH
    path.write_text('{"schema_version":"raes-development-artifact-lock/v1","schema_version":"other"}\n')
    assert "tooling-json-parse" in _failures(root)


def test_policy_authority_symlinks_fail_closed(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    path = root / ACTIONS_POLICY_PATH
    target = path.with_name("actions-policy-target.json")
    path.rename(target)
    path.symlink_to(target.name)
    assert "tooling-json-file" in _failures(root)


def test_internal_schemas_cannot_resolve_remote_references(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    schema_path = root / "implementations/tooling/schemas/actions-policy.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$defs"] = {"remote": {"$ref": "https://example.invalid/schema.json"}}
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    assert "tooling-schema-reference" in _failures(root)


@pytest.mark.parametrize("alias", ["linux-amd64", "Linux-x86_64"])
def test_platform_aliases_normalize_before_identity_uniqueness(tmp_path: Path, alias: str) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    duplicate = dict(lock["artifacts"][0]["platforms"][0])
    duplicate["platform_id"] = alias
    lock["artifacts"][0]["platforms"].append(duplicate)
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert normalize_platform_id(alias) == "linux-x86_64"
    assert "tooling-artifact-identity-duplicate" in _failures(root)


@pytest.mark.parametrize(
    ("mutation", "rule_id"),
    [
        (lambda variant: variant.update(raw_manifest=[]), "tooling-schema"),
        (lambda variant: variant.update(installed_manifest=[]), "tooling-schema"),
        (lambda variant: variant.update(dependencies=["missing-tool"]), "tooling-dependency-missing"),
        (lambda variant: variant.update(profile_ids=["unsupported-profile"]), "tooling-profile-missing"),
        (lambda variant: variant.update(post_install="touch /tmp/owned"), "tooling-executable-field"),
    ],
)
def test_artifact_contract_rejects_incomplete_or_executable_records(
    tmp_path: Path,
    mutation,
    rule_id: str,
) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    mutation(lock["artifacts"][0]["platforms"][0])
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert rule_id in _failures(root)


@pytest.mark.parametrize(
    "manifest_path",
    ["/absolute/tool-a", "../tool-a", "nested/../tool-a", r"C:\\tool-a", r"nested\\tool-a"],
)
def test_manifest_paths_must_be_normalized_portable_relative_paths(
    tmp_path: Path,
    manifest_path: str,
) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    lock["artifacts"][0]["platforms"][0]["raw_manifest"][0]["path"] = manifest_path
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-manifest-path" in _failures(root)


def test_mutable_or_unreviewed_integrity_data_is_rejected(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    lock["artifacts"][0]["source"]["release"] = "latest"
    lock["artifacts"][0]["platforms"][0]["raw_manifest"][0]["sha256"] = "latest"
    lock["artifacts"][0]["authenticity"]["status"] = "unreviewed"
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    failures = _failures(root)
    assert {"tooling-schema", "tooling-mutable-selector", "tooling-authenticity-unreviewed"} <= failures


def test_artifact_policy_subject_and_evidence_are_enforced(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    admission = _load(root, "implementations/tooling/admission-policy.json")
    admission["policies"][0]["subject"] = "action"
    admission["policies"][0]["accepted_evidence"].remove("exact-size")
    _write_json(root, "implementations/tooling/admission-policy.json", admission)
    failures = _failures(root)
    assert {"tooling-policy-subject", "tooling-policy-evidence"} <= failures


def test_action_policy_requires_action_subject_and_commit_evidence(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    actions = _load(root, ACTIONS_POLICY_PATH)
    actions["policy_refs"] = ["artifact-integrity-v1"]
    _write_json(root, ACTIONS_POLICY_PATH, actions)
    failures = _failures(root)
    assert {"tooling-policy-subject", "tooling-policy-evidence"} <= failures


def test_inventory_policy_references_subjects_and_evidence_are_joined(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    coverage = _load(root, INVENTORY_COVERAGE_PATH)
    coverage["rows"][0]["policy_refs"] = ["missing-policy"]
    coverage["rows"][1]["subjects"] = ["action"]
    coverage["rows"][2]["evidence_refs"] = ["unknown-evidence"]
    _write_json(root, INVENTORY_COVERAGE_PATH, coverage)
    failures = _failures(root)
    assert {"tooling-policy-reference", "tooling-policy-subject", "tooling-policy-evidence"} <= failures


def test_dependency_cycles_are_rejected(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    second = json.loads(json.dumps(lock["artifacts"][0]))
    second["artifact_id"] = "tool-b"
    second["platforms"][0]["dependencies"] = ["tool-a"]
    lock["artifacts"][0]["platforms"][0]["dependencies"] = ["tool-b"]
    lock["artifacts"].append(second)
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-dependency-cycle" in _failures(root)


def test_duplicate_profiles_and_cross_platform_aliases_are_rejected(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    profiles = _load(root, PROFILES_PATH)
    profiles["profiles"][0]["platform"]["aliases"].append("macos-arm64")
    profiles["profiles"].append(json.loads(json.dumps(profiles["profiles"][0])))
    _write_json(root, PROFILES_PATH, profiles)
    failures = _failures(root)
    assert {"tooling-profile-alias", "tooling-profile-duplicate"} <= failures


def test_host_profiles_fail_closed_on_unknown_payload_evidence_and_proof_platform(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    profiles = _load(root, PROFILES_PATH)
    host = profiles["host_profiles"][0]
    host["bootstrap_payload_ids"] = ["missing-payload"]
    host["qualification_record_ids"] = ["missing-evidence"]
    host["platform_id"] = "macos-arm64"
    host["proof_support"] = "linux-x86_64-required"
    _write_json(root, PROFILES_PATH, profiles)
    failures = _failures(root)
    assert {
        "tooling-host-artifact",
        "tooling-host-evidence-reference",
        "tooling-host-proof-platform",
        "tooling-host-proof-capability",
    } <= failures


def test_bootstrap_installed_identity_must_match_locked_version(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    artifact = lock["artifacts"][0]
    artifact["artifact_class"] = "bootstrap"
    artifact["support_level"] = "blocking"
    platform = artifact["platforms"][0]
    platform.pop("installed_manifest")
    platform["installed_identity"] = {
        "implementation": "fixture",
        "version": "2.0.0",
        "abi": "native",
        "target": "linux-x86_64",
    }
    admission = _load(root, "implementations/tooling/admission-policy.json")
    admission["policies"][0]["accepted_evidence"].append("installed-runtime-identity")
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    _write_json(root, "implementations/tooling/admission-policy.json", admission)
    assert "tooling-installed-identity-version" in _failures(root)


def test_profile_must_admit_the_artifact_locator(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    lock["artifacts"][0]["source"]["locator_refs"] = ["unapproved-mirror"]
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-locator-profile" in _failures(root)


def test_secret_bearing_source_locator_is_rejected_without_echoing_it(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    lock["artifacts"][0]["source"]["repository"] = "https://user:password@example.invalid/tool?token=secret"
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    failures = evaluate_tooling_artifact_policy(root, tracked_paths=[])
    assert "tooling-secret-bearing-locator" in {failure.rule_id for failure in failures}
    assert all("password" not in failure.render() and "token=secret" not in failure.render() for failure in failures)


def test_secret_bearing_exact_source_url_is_rejected_without_echoing_it(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    lock["artifacts"][0]["platforms"][0]["source_urls"] = ["https://user:password@example.invalid/tool?token=secret"]
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    failures = evaluate_tooling_artifact_policy(root, tracked_paths=[])
    assert "tooling-secret-bearing-locator" in {failure.rule_id for failure in failures}
    assert all("password" not in failure.render() and "token=secret" not in failure.render() for failure in failures)


def test_inventory_coverage_is_exact_and_complete(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    coverage = _load(root, INVENTORY_COVERAGE_PATH)
    coverage["rows"].pop()
    coverage["rows"].append(dict(coverage["rows"][0]))
    _write_json(root, INVENTORY_COVERAGE_PATH, coverage)
    failures = _failures(root)
    assert {"tooling-inventory-duplicate", "tooling-inventory-missing"} <= failures


def test_unlisted_or_mutable_workflow_action_fails_closed(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    workflow = root / ".github" / "workflows" / "test.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs:\n  test:\n    steps:\n      - uses: actions/checkout@main\n", encoding="utf-8")
    failures = _failures(root, tracked_paths=[".github/workflows/test.yml"])
    assert {"tooling-action-mutable", "tooling-action-unowned"} <= failures


def test_quoted_workflow_uses_key_is_structurally_validated(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    workflow = root / ".github" / "workflows" / "test.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        'jobs:\n  test:\n    steps:\n      - "uses": actions/checkout@main\n',
        encoding="utf-8",
    )
    failures = _failures(root, tracked_paths=[".github/workflows/test.yml"])
    assert {"tooling-action-mutable", "tooling-action-unowned"} <= failures


def test_stale_workflow_action_policy_entry_is_rejected(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    policy = _load(root, ACTIONS_POLICY_PATH)
    policy["actions"].append(
        {
            "action": "actions/checkout",
            "commit": "c" * 40,
            "owner_roles": ["Tooling"],
            "trust_root_refs": ["reviewed-git-commit"],
        }
    )
    _write_json(root, ACTIONS_POLICY_PATH, policy)
    assert "tooling-action-stale" in _failures(root)


def test_selector_drift_is_rejected_against_the_lock_authority(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    bindings = _load(root, SELECTOR_BINDINGS_PATH)
    bindings["bindings"].append(
        {
            "binding_id": "tool-a-nox",
            "artifact_id": "tool-a",
            "authority_field": "version",
            "consumers": [
                {
                    "path": "noxfile.py",
                    "template": "tool-a=={selector}",
                }
            ],
        }
    )
    _write_json(root, SELECTOR_BINDINGS_PATH, bindings)
    (root / "noxfile.py").write_text('TOOL = "tool-a==2.0.0"\n', encoding="utf-8")
    assert "tooling-selector-drift" in _failures(root, tracked_paths=["noxfile.py"])


def test_tracked_literal_discovery_rejects_a_new_drifted_consumer(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    bindings = _load(root, SELECTOR_BINDINGS_PATH)
    bindings["tracked_literals"].append(
        {
            "selector_id": "fixture-tool",
            "authority_path": "tools/versions.py",
            "authority_template": 'SPEC = "fixture-tool=={selector}"',
            "consumer_prefix": "fixture-tool==",
        }
    )
    _write_json(root, SELECTOR_BINDINGS_PATH, bindings)
    authority = root / "tools" / "versions.py"
    authority.parent.mkdir(parents=True, exist_ok=True)
    authority.write_text('SPEC = "fixture-tool==1.0.0"\n', encoding="utf-8")
    (root / "README.md").write_text("install fixture-tool==2.0.0\n", encoding="utf-8")
    assert "tooling-selector-drift" in _failures(
        root,
        tracked_paths=["README.md", "tools/versions.py"],
    )


def test_new_acquisition_path_requires_owned_inventory_disposition(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    path = root / "tools" / "new_fetch.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from urllib.request import urlopen\nurlopen('https://example.invalid/tool')\n", encoding="utf-8")
    assert "tooling-acquisition-unowned" in _failures(root, tracked_paths=["tools/new_fetch.py"])


def test_variable_runtime_pull_in_a_test_requires_an_explicit_disposition(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    relative_path = "implementations/python/tests/test_runtime_pull.py"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import subprocess\nsubprocess.run([runtime, 'pull', image], check=False)\n",
        encoding="utf-8",
    )
    assert "tooling-acquisition-unowned" in _failures(root, tracked_paths=[relative_path])

    coverage = _load(root, INVENTORY_COVERAGE_PATH)
    coverage["acquisition_paths"].append(
        {
            "path": relative_path,
            "inventory_id": "I11",
            "disposition": "governed",
            "site_count": 1,
        }
    )
    _write_json(root, INVENTORY_COVERAGE_PATH, coverage)
    assert "tooling-acquisition-unowned" not in _failures(root, tracked_paths=[relative_path])


def test_dynamic_executable_form_requires_an_explicit_disposition(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    relative_path = "packages/dynamic_command.py"
    path = root / relative_path
    path.parent.mkdir(parents=True)
    path.write_text(
        "from subprocess import run as execute\nexecute(command, check=False)\n",
        encoding="utf-8",
    )
    assert "tooling-acquisition-unknown" in _failures(root, tracked_paths=[relative_path])


def test_existing_path_disposition_does_not_hide_a_new_acquisition_site(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    relative_path = "tools/two_fetches.py"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from urllib.request import urlopen\n"
        "urlopen('https://example.invalid/one')\n"
        "urlopen('https://example.invalid/two')\n",
        encoding="utf-8",
    )
    coverage = _load(root, INVENTORY_COVERAGE_PATH)
    coverage["acquisition_paths"].append(
        {
            "path": relative_path,
            "inventory_id": "I05",
            "disposition": "governed",
            "site_count": 1,
        }
    )
    _write_json(root, INVENTORY_COVERAGE_PATH, coverage)
    assert "tooling-acquisition-drift" in _failures(root, tracked_paths=[relative_path])


def test_inert_fixture_text_is_not_treated_as_executed_acquisition(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    relative_path = "implementations/python/tests/test_fixture_text.py"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from pathlib import Path\nPath('fixture.py').write_text(\"subprocess.run([runtime, 'pull', image])\\n\")\n",
        encoding="utf-8",
    )
    failures = _failures(root, tracked_paths=[relative_path])
    assert "tooling-acquisition-unowned" not in failures
    assert "tooling-acquisition-unknown" not in failures


def test_http_client_acquisition_in_a_package_requires_inventory_disposition(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    path = root / "packages" / "new_fetch.py"
    path.parent.mkdir(parents=True)
    path.write_text("import http.client\nhttp.client.HTTPSConnection('example.invalid')\n", encoding="utf-8")
    assert "tooling-acquisition-unowned" in _failures(root, tracked_paths=["packages/new_fetch.py"])


@pytest.mark.parametrize(
    "command",
    [
        '["gh", "release", "download", "v1.0.0"]',
        '["git", "clone", "https://example.invalid/tool"]',
        '["uv", "tool", "install", "fixture-tool==1.0.0"]',
    ],
)
def test_acquisition_commands_outside_tools_require_inventory_disposition(
    tmp_path: Path,
    command: str,
) -> None:
    root = _seed_policy(tmp_path)
    path = root / "noxfile.py"
    path.write_text(f"import subprocess\nsubprocess.run({command})\n", encoding="utf-8")
    assert "tooling-acquisition-unowned" in _failures(root, tracked_paths=["noxfile.py"])


def test_unparseable_acquisition_surface_fails_closed(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    path = root / "packages" / "broken.py"
    path.parent.mkdir(parents=True)
    path.write_text("def incomplete(:\n", encoding="utf-8")
    assert "tooling-acquisition-scan" in _failures(root, tracked_paths=["packages/broken.py"])


def test_runtime_selection_binding_requires_every_selection_dimension(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    path = root / "tools" / "acquire_tool_a.py"
    path.write_text(
        "load_tooling_artifact_selection(artifact_id='tool-a', version=VERSION, platform_id=PLATFORM)\n",
        encoding="utf-8",
    )
    assert "tooling-runtime-selection-drift" in _failures(root)


def test_new_runtime_selection_call_requires_a_declared_consumer(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    relative_path = "packages/new_selector.py"
    path = root / relative_path
    path.parent.mkdir(parents=True)
    path.write_text(
        "import tools.tooling_policy_gate as gate\n"
        "gate.load_tooling_artifact_selection(\n"
        "    artifact_id='tool-a', version=VERSION, platform_id=PLATFORM, profile_id=PROFILE\n"
        ")\n",
        encoding="utf-8",
    )
    assert "tooling-runtime-selection-drift" in _failures(root, tracked_paths=[relative_path])


@pytest.mark.integration
def test_exact_lock_selection_normalizes_platform_alias_and_rejects_wrong_version() -> None:
    selection = select_tooling_artifact(
        REPO_ROOT,
        artifact_id="conftest",
        version="0.68.0",
        platform_id="Linux-amd64",
        profile_id="public-linux-x86_64",
    )
    assert selection["platform"]["platform_id"] == "linux-x86_64"
    with pytest.raises(ValueError, match="exactly one reviewed lock entry"):
        select_tooling_artifact(
            REPO_ROOT,
            artifact_id="conftest",
            version="9.9.9",
            platform_id="linux-x86_64",
            profile_id="public-linux-x86_64",
        )


@pytest.mark.integration
def test_exact_host_selection_runs_the_canonical_policy_boundary() -> None:
    selection = select_tooling_host_profile(REPO_ROOT, host_profile_id="public-macos-arm64")
    assert selection["host_profile"]["platform_id"] == "macos-arm64"
    assert {item["artifact_id"] for item in selection["artifacts"]} == {
        "conftest",
        "cpython-3.14",
        "gitleaks",
        "osv-scanner",
        "uv",
        "vale",
    }
    assert len(selection["policy_sha256"]) == 64
    assert selection["policy_sha256"] == tooling_policy_sha256(REPO_ROOT)


def test_source_snapshot_byte_drift_is_rejected(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    artifact = lock["artifacts"][0]
    artifact["artifact_class"] = "source-snapshot"
    artifact["platforms"][0]["installed_manifest"][0]["path"] = "contracts/source.json"
    snapshot = root / "contracts" / "source.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("{}\n", encoding="utf-8")
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-source-snapshot-drift" in _failures(root)


def test_source_snapshot_rejects_a_symlinked_parent_directory(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    payload = b"{}\n"
    lock = _load(root, ARTIFACT_LOCK_PATH)
    artifact = lock["artifacts"][0]
    artifact["artifact_class"] = "source-snapshot"
    installed = artifact["platforms"][0]["installed_manifest"][0]
    installed.update(
        {
            "path": "snapshots/source.json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
    )
    real_parent = root / "real-snapshots"
    real_parent.mkdir()
    (real_parent / "source.json").write_bytes(payload)
    (root / "snapshots").symlink_to(real_parent, target_is_directory=True)
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-source-snapshot-missing" in _failures(root)


@pytest.mark.parametrize(
    "acquire",
    [
        conftest_tool.ensure_conftest,
        gitleaks_tool.ensure_gitleaks,
        isabelle_tool.acquire_isabelle,
        osv_scanner_tool.ensure_osv_scanner,
        vale_tool.ensure_vale,
    ],
)
def test_local_tool_acquisition_checks_policy_before_cache_or_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    acquire,
) -> None:
    def reject_policy(**_kwargs: object) -> None:
        raise RuntimeError("policy-sentinel")

    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", reject_policy)
    with pytest.raises(RuntimeError, match="policy-sentinel"):
        acquire(tmp_path)


@pytest.mark.parametrize(
    ("module", "acquire", "artifact_id", "version", "binary_name"),
    [
        (conftest_tool, conftest_tool.ensure_conftest, "conftest", "0.68.0", "conftest"),
        (gitleaks_tool, gitleaks_tool.ensure_gitleaks, "gitleaks", "8.30.1", "gitleaks"),
        (vale_tool, vale_tool.ensure_vale, "vale", "3.15.2", "vale"),
    ],
)
def test_archive_tool_acquisition_uses_the_exact_lock_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module,
    acquire,
    artifact_id: str,
    version: str,
    binary_name: str,
) -> None:
    binary_bytes = f"reviewed-{artifact_id}".encode()
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo(binary_name)
        member.mode = 0o755
        member.size = len(binary_bytes)
        archive.addfile(member, io.BytesIO(binary_bytes))
    archive_bytes = archive_buffer.getvalue()
    source_url = f"https://example.invalid/{artifact_id}-{version}.tar.gz"
    observed: dict[str, object] = {}

    def selection(**kwargs: object) -> LockedArtifactSelection:
        observed["selection"] = kwargs
        return LockedArtifactSelection(
            artifact_id=artifact_id,
            version=version,
            platform_id="linux-x86_64",
            profile_id="public-linux-x86_64",
            repository=f"https://example.invalid/{artifact_id}",
            release=f"v{version}",
            source_urls=(source_url,),
            raw_manifest=(
                LockedManifestEntry(
                    f"{artifact_id}-{version}.tar.gz",
                    hashlib.sha256(archive_bytes).hexdigest(),
                    len(archive_bytes),
                ),
            ),
            installed_manifest=(
                LockedManifestEntry(binary_name, hashlib.sha256(binary_bytes).hexdigest(), len(binary_bytes)),
            ),
        )

    def download(url: str, **_kwargs: object) -> bytes:
        observed["url"] = url
        return archive_bytes

    monkeypatch.setattr("tools.tooling_policy_gate.host_platform_id", lambda: "linux-x86_64")
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", selection)
    monkeypatch.setattr(module, "download_bytes", download)

    binary = acquire(tmp_path, version=version)

    assert binary.read_bytes() == binary_bytes
    assert observed == {
        "selection": {
            "artifact_id": artifact_id,
            "version": version,
            "platform_id": "linux-x86_64",
            "profile_id": "public-linux-x86_64",
        },
        "url": source_url,
    }


@pytest.mark.parametrize(
    ("module", "acquire", "artifact_id", "version", "binary_name"),
    [
        (conftest_tool, conftest_tool.ensure_conftest, "conftest", "0.68.0", "conftest"),
        (gitleaks_tool, gitleaks_tool.ensure_gitleaks, "gitleaks", "8.30.1", "gitleaks"),
        (vale_tool, vale_tool.ensure_vale, "vale", "3.15.2", "vale"),
    ],
)
def test_archive_tool_rejects_a_symlink_selected_by_the_installed_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module,
    acquire,
    artifact_id: str,
    version: str,
    binary_name: str,
) -> None:
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo(binary_name)
        member.type = tarfile.SYMTYPE
        member.linkname = "outside"
        archive.addfile(member)
    archive_bytes = archive_buffer.getvalue()

    def selection(**_kwargs: object) -> LockedArtifactSelection:
        return LockedArtifactSelection(
            artifact_id=artifact_id,
            version=version,
            platform_id="linux-x86_64",
            profile_id="public-linux-x86_64",
            repository=f"https://example.invalid/{artifact_id}",
            release=f"v{version}",
            source_urls=(f"https://example.invalid/{artifact_id}.tar.gz",),
            raw_manifest=(
                LockedManifestEntry(
                    f"{artifact_id}.tar.gz",
                    hashlib.sha256(archive_bytes).hexdigest(),
                    len(archive_bytes),
                ),
            ),
            installed_manifest=(LockedManifestEntry(binary_name, _SHA_A, 1),),
        )

    monkeypatch.setattr("tools.tooling_policy_gate.host_platform_id", lambda: "linux-x86_64")
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", selection)
    monkeypatch.setattr(module, "download_bytes", lambda *_args, **_kwargs: archive_bytes)

    with pytest.raises(RuntimeError, match="regular"):
        acquire(tmp_path, version=version)


@pytest.mark.parametrize(
    ("module", "acquire", "binary_path", "artifact_id", "version", "binary_name"),
    [
        (
            conftest_tool,
            conftest_tool.ensure_conftest,
            conftest_tool.conftest_binary_path,
            "conftest",
            "0.68.0",
            "conftest",
        ),
        (
            gitleaks_tool,
            gitleaks_tool.ensure_gitleaks,
            gitleaks_tool.gitleaks_binary_path,
            "gitleaks",
            "8.30.1",
            "gitleaks",
        ),
        (vale_tool, vale_tool.ensure_vale, vale_tool.vale_binary_path, "vale", "3.15.2", "vale"),
    ],
)
def test_archive_tool_never_accepts_a_symlink_cache_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module,
    acquire,
    binary_path,
    artifact_id: str,
    version: str,
    binary_name: str,
) -> None:
    binary_bytes = b"reviewed binary"
    outside = tmp_path / "outside-binary"
    outside.write_bytes(binary_bytes)
    cached = binary_path(tmp_path, version=version)
    cached.parent.mkdir(parents=True)
    cached.symlink_to(outside)

    def selection(**_kwargs: object) -> LockedArtifactSelection:
        return LockedArtifactSelection(
            artifact_id=artifact_id,
            version=version,
            platform_id="linux-x86_64",
            profile_id="public-linux-x86_64",
            repository=f"https://example.invalid/{artifact_id}",
            release=f"v{version}",
            source_urls=(f"https://example.invalid/{artifact_id}.tar.gz",),
            raw_manifest=(LockedManifestEntry(f"{artifact_id}.tar.gz", _SHA_A, 1),),
            installed_manifest=(
                LockedManifestEntry(binary_name, hashlib.sha256(binary_bytes).hexdigest(), len(binary_bytes)),
            ),
        )

    monkeypatch.setattr("tools.tooling_policy_gate.host_platform_id", lambda: "linux-x86_64")
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", selection)

    def reject_download(*_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("download-sentinel")

    monkeypatch.setattr(module, "download_bytes", reject_download)
    with pytest.raises(RuntimeError, match="download-sentinel"):
        acquire(tmp_path, version=version)
    assert not cached.is_symlink()
    assert outside.read_bytes() == binary_bytes


def test_archive_tool_rejects_a_symlink_in_its_fixed_cache_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    (repo_root / ".cache").symlink_to(outside, target_is_directory=True)

    def selection(**_kwargs: object) -> LockedArtifactSelection:
        return LockedArtifactSelection(
            artifact_id="conftest",
            version="0.68.0",
            platform_id="linux-x86_64",
            profile_id="public-linux-x86_64",
            repository="https://example.invalid/conftest",
            release="v0.68.0",
            source_urls=("https://example.invalid/conftest.tar.gz",),
            raw_manifest=(LockedManifestEntry("conftest.tar.gz", _SHA_A, 1),),
            installed_manifest=(LockedManifestEntry("conftest", _SHA_B, 1),),
        )

    monkeypatch.setattr("tools.tooling_policy_gate.host_platform_id", lambda: "linux-x86_64")
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", selection)
    with pytest.raises(RuntimeError, match="unsafe conftest cache directory"):
        conftest_tool.ensure_conftest(repo_root)


def test_isabelle_acquisition_and_cache_validation_use_the_exact_lock_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary_bytes = b"#!/bin/sh\nexit 0\n"
    installed_path = f"Isabelle{isabelle_tool.ISABELLE_VERSION}/bin/isabelle"
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo(installed_path)
        member.mode = 0o755
        member.size = len(binary_bytes)
        archive.addfile(member, io.BytesIO(binary_bytes))
    archive_bytes = archive_buffer.getvalue()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    source_url = "https://example.invalid/Isabelle.tar.gz"

    def selection(**_kwargs: object) -> LockedArtifactSelection:
        return LockedArtifactSelection(
            artifact_id="isabelle",
            version=isabelle_tool.ISABELLE_VERSION,
            platform_id="linux-x86_64",
            profile_id="proof-linux-x86_64",
            repository="https://example.invalid/isabelle",
            release=f"Isabelle{isabelle_tool.ISABELLE_VERSION}",
            source_urls=(source_url,),
            raw_manifest=(LockedManifestEntry("Isabelle.tar.gz", digest, len(archive_bytes)),),
            installed_manifest=(
                LockedManifestEntry(installed_path, hashlib.sha256(binary_bytes).hexdigest(), len(binary_bytes)),
            ),
        )

    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", selection)
    monkeypatch.setattr(isabelle_tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(isabelle_tool.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(isabelle_tool, "urlopen", lambda url, **_kwargs: io.BytesIO(archive_bytes))

    acquired = isabelle_tool.acquire_isabelle(tmp_path)

    assert acquired == isabelle_tool.require_isabelle(tmp_path)
    binary = acquired / "bin" / "isabelle"
    assert binary.read_bytes() == binary_bytes

    outside = tmp_path / "outside-isabelle"
    outside.write_bytes(binary_bytes)
    outside.chmod(0o755)
    binary.unlink()
    binary.symlink_to(outside)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="marker or executable is invalid"):
        isabelle_tool.require_isabelle(tmp_path)


@pytest.mark.parametrize(
    "remote_check",
    [
        lambda: check_attack_tactic_vocabulary._check_remote(None),
        lambda: check_atlas_tactic_vocabulary._check_remote(None),
        lambda: check_nist_csf_defensive_vocabulary._check_remote(None),
        lambda: check_autonomous_behavior_vocabularies._check_remote(None, None),
    ],
)
def test_remote_vocabulary_checks_enforce_policy_before_network(
    monkeypatch: pytest.MonkeyPatch,
    remote_check,
) -> None:
    def reject_policy(**_kwargs: object) -> None:
        raise RuntimeError("policy-sentinel")

    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", reject_policy)
    with pytest.raises(RuntimeError, match="policy-sentinel"):
        remote_check()


@pytest.mark.parametrize(
    ("checker", "selected_url"),
    [
        (
            check_attack_tactic_vocabulary,
            "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/fixture.json",
        ),
        (
            check_atlas_tactic_vocabulary,
            "https://github.com/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml",
        ),
        (
            check_nist_csf_defensive_vocabulary,
            "https://csrc.nist.gov/fixture.json",
        ),
    ],
)
def test_remote_vocabulary_helpers_accept_reviewed_urls_and_bytes(checker, selected_url: str) -> None:
    payload = b"reviewed source snapshot"
    source = SimpleNamespace(source_url=selected_url)

    assert checker._remote_url_failure(source, selected_url) is None
    assert (
        checker._remote_bytes_failure(
            payload,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        is None
    )
    assert checker._remote_url_failure(source, "https://example.invalid/source") is not None
    assert checker._remote_bytes_failure(payload, size=len(payload) + 1, sha256=_SHA_A) is not None


def test_autonomous_remote_helpers_verify_reviewed_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"reviewed source snapshot"
    digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    activity_url = "https://www.w3.org/TR/2017/REC-activitystreams-vocabulary-20170523/"
    fipa_url = "https://www.fipa.org/specs/fipa00037/SC00037J.pdf"
    monkeypatch.setattr(
        check_autonomous_behavior_vocabularies,
        "_fetch_official_bytes",
        lambda *_args, **_kwargs: payload,
    )
    monkeypatch.setattr(
        check_autonomous_behavior_vocabularies,
        "_extract_activitystreams_type_names",
        lambda _data: list(check_autonomous_behavior_vocabularies.ACTIVITYSTREAMS_TYPES),
    )

    assert (
        check_autonomous_behavior_vocabularies._check_activitystreams_remote(
            SimpleNamespace(source_url=activity_url, source_digest=digest),
            activity_url,
            expected_size=len(payload),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )
        == []
    )
    assert (
        check_autonomous_behavior_vocabularies._check_fipa_remote(
            SimpleNamespace(source_artifact_url=fipa_url, source_digest=digest),
            fipa_url,
            expected_size=len(payload),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )
        == []
    )


def test_tooling_policy_cli_paths_are_bounded(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(check_tooling_artifact_policy, "evaluate_tooling_artifact_policy", lambda _root: [])
    assert check_tooling_artifact_policy.main([]) == 0
    assert check_tooling_artifact_policy.main(["--select-artifact", "tool-a"]) == 2
    assert "requires artifact" in capsys.readouterr().err


def test_tooling_policy_cli_emits_a_validated_selection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    selected = {"artifact_id": "tool-a", "version": "1.0.0"}
    monkeypatch.setattr(check_tooling_artifact_policy, "select_tooling_artifact", lambda *_args, **_kwargs: selected)

    result = check_tooling_artifact_policy.main(
        [
            "--select-artifact",
            "tool-a",
            "--version",
            "1.0.0",
            "--platform-id",
            "linux-x86_64",
            "--profile-id",
            "public-linux-x86_64",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == selected
