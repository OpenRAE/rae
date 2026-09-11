from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
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
            "schema_version": "raes-development-profiles/v1",
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
    return root


def _failures(root: Path, *, tracked_paths: list[str] | None = None) -> set[str]:
    paths = ["tools/acquire_tool_a.py", *(tracked_paths or [])]
    return {failure.rule_id for failure in evaluate_tooling_artifact_policy(root, tracked_paths=paths)}


def _load(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


@pytest.mark.integration
@pytest.mark.timeout(300)
def test_checked_in_tooling_policy_is_valid_and_deterministic() -> None:
    first = evaluate_tooling_artifact_policy(REPO_ROOT)
    second = evaluate_tooling_artifact_policy(REPO_ROOT)
    assert first == second == []


def test_seeded_policy_has_no_failures(tmp_path: Path) -> None:
    root = _seed_policy(tmp_path)
    assert (
        evaluate_tooling_artifact_policy(
            root,
            tracked_paths=["tools/acquire_tool_a.py"],
        )
        == []
    )


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


def test_selection_launcher_uses_frozen_uv_without_a_project_venv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "implementations" / "python"
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
        "python",
        str(validator),
    ]
    assert tooling_policy_gate._VALIDATOR_TIMEOUT_SECONDS == 180


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
    ["/tmp/tool-a", "../tool-a", "nested/../tool-a", r"C:\\tool-a", r"nested\\tool-a"],
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
