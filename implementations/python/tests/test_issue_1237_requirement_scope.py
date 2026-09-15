"""Mixed-requirement delivery preserves each owner's independent predicates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

CODE = "implementations/python/packages/example.py"
TEST = "implementations/python/tests/test_example.py"


@pytest.fixture(autouse=True)
def isolated_requirement_environment(monkeypatch):
    for name in ("RAES_REQUIREMENT_UID", "RAES_REQUIREMENT_BRANCH", "GITHUB_HEAD_REF", "GITHUB_BASE_REF"):
        monkeypatch.delenv(name, raising=False)


def scope_document():
    return {
        "schema_version": "requirement-scope/v1",
        "issue_number": 1237,
        "primary_requirement_uid": "EXP-708",
        "requirement_uids": ["EXP-708", "GOV-913"],
        "bindings": {CODE: ["EXP-708"], TEST: ["GOV-913"]},
    }


@pytest.fixture
def scope_repo(tmp_path):
    policy = {
        "project": "example",
        "requirement_source": "repository",
        "phases": [
            {"id": "foundation", "requirements": ["EXP-701"]},
            {"id": "evidence", "requirements": ["EXP-708"], "blocked_until": ["foundation"]},
            {"id": "tooling", "requirements": ["GOV-913"]},
        ],
        "ownership": {"evidence": [CODE], "tooling": [TEST]},
        "traceability": {
            "required_code_roots": ["implementations/python/packages"],
            "required_test_roots": ["implementations/python/tests"],
        },
    }
    policy_dir = tmp_path / "tools/policy"
    policy_dir.mkdir(parents=True)
    (policy_dir / "requirement_order.yaml").write_text(yaml.safe_dump(policy))
    (policy_dir / "exceptions.yaml").write_text("exceptions: []\n")
    for uid, link in [
        ("EXP-701", ""),
        ("EXP-708", f"- IMPLEMENTS → CODE_FILE `{CODE}`\n"),
        ("GOV-913", f"- TESTS → TEST `{TEST}`\n"),
    ]:
        path = tmp_path / "docs/requirements" / uid / "requirement.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"---\nid: {uid}\nstatus: ACTIVE\n---\n## Traceability\n{link}")
    return tmp_path


def evaluate(root, document=None, paths=None):
    from tools.policy.repository_requirements import RepositoryRequirementClient
    from tools.policy.requirement_scope import evaluate_requirement_scope, parse_requirement_scope

    scope = parse_requirement_scope(document or scope_document(), issue_number=1237)
    return evaluate_requirement_scope(
        root,
        paths if paths is not None else [CODE, TEST],
        client=RepositoryRequirementClient(root),
        scope=scope,
    )


def test_mixed_scope_checks_each_file_against_its_actual_requirement(scope_repo):
    assert evaluate(scope_repo) == []


def test_mixed_scope_cannot_borrow_another_requirements_traceability(scope_repo):
    document = scope_document()
    document["bindings"][TEST] = ["EXP-708"]
    assert {item.rule_id for item in evaluate(scope_repo, document)} == {
        "requirement-ownership-mismatch",
        "traceability-missing-tests",
    }


def test_mixed_scope_requires_an_explicit_assignment_for_every_changed_file(scope_repo):
    failures = evaluate(scope_repo, paths=[CODE, TEST, "docs/unassigned.md"])
    assert [(item.rule_id, item.path) for item in failures] == [
        ("requirement-scope-unassigned", "docs/unassigned.md"),
    ]


@pytest.mark.parametrize("uid,status", [("GOV-913", "ARCHIVED"), ("GOV-913", "DEPRECATED"), ("EXP-701", "DRAFT")])
def test_mixed_scope_retains_status_and_prerequisite_gates(scope_repo, uid, status):
    path = scope_repo / "docs/requirements" / uid / "requirement.md"
    path.write_text(path.read_text().replace("status: ACTIVE", f"status: {status}"))
    expected = "requirement-order-blocked" if uid == "EXP-701" else "requirement-invalid-status"
    assert expected in {item.rule_id for item in evaluate(scope_repo)}


def test_every_shared_assignment_must_pass_not_just_one(scope_repo):
    document = scope_document()
    document["bindings"][TEST] = ["EXP-708", "GOV-913"]
    assert "traceability-missing-tests" in {item.rule_id for item in evaluate(scope_repo, document)}


def test_listed_requirements_are_checked_even_without_current_changed_files(scope_repo):
    path = scope_repo / "docs/requirements/GOV-913/requirement.md"
    path.write_text(path.read_text().replace("status: ACTIVE", "status: ARCHIVED"))
    assert "requirement-invalid-status" in {item.rule_id for item in evaluate(scope_repo, paths=[CODE])}


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "unknown/v1"),
        ("issue_number", 1238),
        ("issue_number", True),
        ("primary_requirement_uid", "GOV-999"),
        ("requirement_uids", []),
        ("requirement_uids", ["EXP-708", "EXP-708"]),
        ("requirement_uids", ["EXP-708", "../GOV-913"]),
        ("bindings", {CODE: ["GOV-999"]}),
        ("bindings", {CODE: []}),
        ("bindings", {CODE: ["EXP-708", "EXP-708"]}),
        ("bindings", {"../outside.py": ["EXP-708"]}),
        ("bindings", {"/absolute.py": ["EXP-708"]}),
        ("bindings", {"implementations/*.py": ["EXP-708"]}),
        ("bindings", {"implementations/../other.py": ["EXP-708"]}),
        ("bindings", {"implementations//other.py": ["EXP-708"]}),
        ("bindings", {"C:\\outside.py": ["EXP-708"]}),
        ("bindings", {".": ["EXP-708"]}),
        ("bindings", {"safe\nforged.py": ["EXP-708"]}),
        ("bindings", {}),
        ("bindings", []),
    ],
)
def test_scope_rejects_malformed_or_ambiguous_authority(field, value):
    from tools.policy.requirement_scope import RequirementScopeError, parse_requirement_scope

    document = scope_document()
    document[field] = value
    with pytest.raises(RequirementScopeError):
        parse_requirement_scope(document, issue_number=1237)


def test_scope_rejects_unknown_fields():
    from tools.policy.requirement_scope import RequirementScopeError, parse_requirement_scope

    document = {**scope_document(), "fallback": True}
    with pytest.raises(RequirementScopeError):
        parse_requirement_scope(document, issue_number=1237)


def write_scope(root: Path, content=None):
    path = root / "docs/governance/requirement-scopes/1237.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scope_document()) if content is None else content)
    return path


def commit_scope_fixture(root: Path, message: str):
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Scope Test",
            "-c",
            "user.email=scope@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            message,
        ],
        cwd=root,
        capture_output=True,
        check=True,
    )


@pytest.mark.parametrize("removal", ["delete", "rename", "committed-delete", "base-only"])
@pytest.mark.parametrize("entry", ["resolver", "cli", "hook"])
def test_established_scope_removal_cannot_enable_legacy_skip(scope_repo, monkeypatch, capsys, removal, entry):
    import tools.requirement_context as context
    from tools.policy.requirement_scope import RequirementScopeError

    subprocess.run(["git", "init", "-b", "1237-capture"], cwd=scope_repo, capture_output=True, check=True)
    commit_scope_fixture(scope_repo, "root")
    path = write_scope(scope_repo)
    subprocess.run(["git", "add", "."], cwd=scope_repo, capture_output=True, check=True)
    commit_scope_fixture(scope_repo, "establish scope")
    if removal == "base-only":
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/dev", "HEAD"], cwd=scope_repo, capture_output=True, check=True
        )
        subprocess.run(["git", "switch", "--detach", "HEAD~1"], cwd=scope_repo, capture_output=True, check=True)
    else:
        if removal == "rename":
            path.rename(path.with_name("renamed.json"))
        else:
            path.unlink()
        subprocess.run(["git", "add", "-A"], cwd=scope_repo, capture_output=True, check=True)
        if removal == "committed-delete":
            commit_scope_fixture(scope_repo, "remove scope")
    if entry == "resolver":
        with pytest.raises(RequirementScopeError):
            context.resolve_requirement_context(scope_repo, "1237-capture")
    elif entry == "cli":
        monkeypatch.setattr(context, "REPO_ROOT", scope_repo)
        assert context.main(["--branch", "1237-capture"]) == 1
        assert capsys.readouterr().out == ""
    else:
        monkeypatch.setitem(sys.modules, "nox", SimpleNamespace(Session=object))
        from tools.nox_support import runner

        monkeypatch.setattr(runner, "REPO_ROOT", scope_repo)
        monkeypatch.setattr(runner, "current_requirement_branch", lambda _root: "1237-capture")
        with pytest.raises(RequirementScopeError):
            runner._requirement_aware_policy_args("--skip-requirement")


def test_new_git_issue_without_scope_preserves_legacy_context(tmp_path):
    from tools.requirement_context import resolve_requirement_context

    subprocess.run(["git", "init", "-b", "1238-legacy"], cwd=tmp_path, capture_output=True, check=True)
    assert resolve_requirement_context(tmp_path, "1238-legacy") == (None, None)


def test_index_only_scope_cannot_disappear_before_first_commit(tmp_path):
    from tools.policy.requirement_scope import RequirementScopeError, load_requirement_scope

    subprocess.run(["git", "init", "-b", "1237-capture"], cwd=tmp_path, capture_output=True, check=True)
    path = write_scope(tmp_path)
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    path.unlink()
    with pytest.raises(RequirementScopeError):
        load_requirement_scope(tmp_path, "1237-capture")


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("git", 10), subprocess.CalledProcessError(128, "git")])
def test_scope_history_failure_cannot_enable_legacy_skip(tmp_path, monkeypatch, failure):
    from tools.policy import requirement_scope

    (tmp_path / ".git").mkdir()

    def unavailable(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(requirement_scope.subprocess, "run", unavailable)
    with pytest.raises(requirement_scope.RequirementScopeError):
        requirement_scope.load_requirement_scope(tmp_path, "1237-capture")


def test_context_resolves_scope_on_numeric_issue_branch_and_preserves_legacy(tmp_path):
    from tools.requirement_context import resolve_requirement_context

    write_scope(tmp_path)
    uid, scope = resolve_requirement_context(tmp_path, "1237-capture-evidence-authority")
    assert uid == "EXP-708"
    assert scope.requirement_uids == ("EXP-708", "GOV-913")
    assert resolve_requirement_context(tmp_path, "1238-GOV-918-other") == ("GOV-918", None)
    assert resolve_requirement_context(tmp_path, "dev") == (None, None)


def test_explicit_primary_conflict_cannot_select_a_weaker_requirement(tmp_path):
    from tools.policy.requirement_scope import RequirementScopeError
    from tools.requirement_context import resolve_requirement_context

    write_scope(tmp_path)
    with pytest.raises(RequirementScopeError):
        resolve_requirement_context(tmp_path, "1237-capture", "GOV-913")


@pytest.mark.parametrize("content", ["{", '{"issue_number":1237,"issue_number":1238}', "[]"])
def test_invalid_scope_never_falls_back_to_single_requirement(tmp_path, content):
    from tools.policy.requirement_scope import RequirementScopeError
    from tools.requirement_context import resolve_requirement_context

    write_scope(tmp_path, content)
    with pytest.raises(RequirementScopeError):
        resolve_requirement_context(tmp_path, "1237-capture", "EXP-708")


def test_scope_file_cannot_be_a_symlink(tmp_path):
    from tools.policy.requirement_scope import RequirementScopeError, load_requirement_scope

    path = write_scope(tmp_path)
    actual = path.with_suffix(".retained")
    path.rename(actual)
    path.symlink_to(actual)
    with pytest.raises(RequirementScopeError):
        load_requirement_scope(tmp_path, "1237-capture")


@pytest.mark.parametrize("extra", [[], ["docs/unassigned.md"]])
def test_cli_governance_enforces_mixed_scope(scope_repo, monkeypatch, capsys, extra):
    import tools.check_requirement_governance as gate

    write_scope(scope_repo)
    monkeypatch.setattr(gate, "REPO_ROOT", scope_repo)
    monkeypatch.setattr(gate, "current_branch", lambda _root: "1237-capture")
    monkeypatch.setattr(sys, "argv", ["gate", "--json", CODE, TEST, *extra])
    assert gate.main() == (1 if extra else 0)
    if extra:
        assert json.loads(capsys.readouterr().out)[0]["rule_id"] == "requirement-scope-unassigned"


def test_cli_rejects_malformed_scope_even_for_exempt_only_changes(scope_repo, monkeypatch, capsys):
    import tools.check_requirement_governance as gate

    write_scope(scope_repo, "{")
    monkeypatch.setattr(gate, "REPO_ROOT", scope_repo)
    monkeypatch.setattr(gate, "current_branch", lambda _root: "1237-capture")
    monkeypatch.setattr(sys, "argv", ["gate", "--json", "tools/example.py"])
    assert gate.main() == 1
    assert json.loads(capsys.readouterr().out)[0]["rule_id"] == "requirement-scope-invalid"


def test_nox_hooks_use_scope_and_refuse_explicit_skip(scope_repo, monkeypatch):
    monkeypatch.setitem(sys.modules, "nox", SimpleNamespace(Session=object))
    from tools.nox_support import runner
    from tools.policy.requirement_scope import RequirementScopeError

    write_scope(scope_repo)
    monkeypatch.setattr(runner, "REPO_ROOT", scope_repo)
    monkeypatch.setattr(runner, "current_requirement_branch", lambda _root: "1237-capture")
    assert runner._requirement_aware_policy_args("--staged") == ["--staged"]
    with pytest.raises(RequirementScopeError):
        runner._requirement_aware_policy_args("--skip-requirement")


def test_context_uses_detached_ci_branch_and_emits_only_canonical_uid(scope_repo, monkeypatch, capsys):
    import tools.requirement_context as context

    write_scope(scope_repo)
    monkeypatch.setattr(context, "REPO_ROOT", scope_repo)
    monkeypatch.setenv("RAES_REQUIREMENT_BRANCH", "1237-capture")
    assert context.current_requirement_branch(scope_repo) == "1237-capture"
    assert context.main([]) == 0
    assert capsys.readouterr().out == "EXP-708\n"


@pytest.mark.parametrize("kind", ["directory", "oversized", "dangling", "parent-symlink"])
def test_scope_reader_rejects_unsafe_authority(scope_repo, kind):
    from tools.policy.requirement_scope import RequirementScopeError, load_requirement_scope

    path = write_scope(scope_repo)
    if kind == "oversized":
        path.write_text(" " * (256 * 1024 + 1))
    else:
        path.unlink()
        if kind == "directory":
            path.mkdir()
        elif kind == "dangling":
            path.symlink_to(path.with_suffix(".absent"))
        else:
            parent = path.parent
            actual = parent.with_name("retained-scopes")
            parent.rename(actual)
            parent.symlink_to(actual, target_is_directory=True)
    with pytest.raises(RequirementScopeError):
        load_requirement_scope(scope_repo, "1237-capture")


@pytest.mark.integration
def test_actual_ci_resolver_retains_governance_for_numeric_issue_branches(tmp_path):
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/canonical-verification.yml").read_text())
    steps = workflow["jobs"]["verify"]["steps"]
    step = next(step for step in steps if step.get("id") == "requirement")
    output = tmp_path / "github-output"
    environment = {**os.environ, "BRANCH": "1237-capture-evidence-authority", "GITHUB_OUTPUT": str(output)}
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert output.read_text() == "uid=EXP-708\n"


def test_context_cli_fails_without_emitting_a_uid_on_invalid_scope(scope_repo, monkeypatch, capsys):
    import tools.requirement_context as context

    write_scope(scope_repo, "{")
    monkeypatch.setattr(context, "REPO_ROOT", scope_repo)
    assert context.main(["--branch", "1237-capture"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "context unavailable" in output.err


def test_scope_requires_available_authority_even_when_legacy_mode_allows_skip(scope_repo, monkeypatch, capsys):
    import tools.check_requirement_governance as gate
    from tools.policy.requirement_scope import parse_requirement_scope

    policy_path = scope_repo / "tools/policy/requirement_order.yaml"
    policy = yaml.safe_load(policy_path.read_text())
    policy["requirement_source"] = "ground-control-http"
    policy_path.write_text(yaml.safe_dump(policy))
    monkeypatch.setattr(gate, "REPO_ROOT", scope_repo)
    monkeypatch.setattr(gate, "resolve_base_url", lambda _root: None)
    assert (
        gate.evaluate_configured_governance(
            [CODE, TEST],
            "EXP-708",
            require_governance=False,
            as_json=True,
            scope=parse_requirement_scope(scope_document(), issue_number=1237),
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)[0]["status"] == "required-unevaluated"


def test_scope_cannot_fall_back_when_a_requirement_record_is_missing(scope_repo, monkeypatch, capsys):
    import tools.check_requirement_governance as gate

    write_scope(scope_repo)
    (scope_repo / "docs/requirements/GOV-913/requirement.md").unlink()
    monkeypatch.setattr(gate, "REPO_ROOT", scope_repo)
    monkeypatch.setattr(gate, "current_branch", lambda _root: "1237-capture")
    monkeypatch.setattr(sys, "argv", ["gate", "--json", CODE, TEST])
    assert gate.main() == 1
    assert json.loads(capsys.readouterr().out)[0]["rule_id"] == "repository-requirement-invalid"
