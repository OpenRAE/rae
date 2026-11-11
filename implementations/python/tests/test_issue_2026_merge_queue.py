"""Merge queue for `dev`: merge group producers, policy gates, and boundaries (#2026)."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from tools.check_merge_queue_policy import MERGE_POLICY_PATH, evaluate_merge_queue_policy, main
from tools.tooling_artifact_policy_actions import action_failures

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SECRET_SCAN = ".github/workflows/secret-scan.yml"
QUEUE_REF = "refs/heads/gh-readonly-queue/dev/pr-2026-" + "a" * 40


def _load(name: str) -> dict[Any, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    return workflow.get("on", workflow.get(True))


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    (step,) = [step for step in job["steps"] if step.get("name") == name]
    return step


# Producers of the required `dev` contexts run on every merge group.


@pytest.mark.parametrize(
    "workflow", ["ci.yml", "codeql.yml", "pr-title-lint.yml", "pr-body-policy.yml", "secret-scan.yml"]
)
def test_required_producers_run_on_every_merge_group(workflow: str) -> None:
    assert _triggers(_load(workflow))["merge_group"] == {"types": ["checks_requested"]}


def test_repository_merge_policy_passes() -> None:
    assert evaluate_merge_queue_policy(REPO_ROOT) == []


def test_dev_uses_the_merge_queue_without_strict_checks_and_main_does_not() -> None:
    policy = json.loads((REPO_ROOT / MERGE_POLICY_PATH).read_text(encoding="utf-8"))
    dev, main = policy["branches"]["dev"], policy["branches"]["main"]
    assert (dev["merge_queue"], dev["strict_status_checks"]) == (True, False)
    assert (main["merge_queue"], main["strict_status_checks"]) == (False, True)
    contexts = {check["context"] for check in dev["required_checks"]}
    assert contexts == {check["context"] for check in main["required_checks"]}
    assert all("workflow" in check for check in dev["required_checks"])


# The merge queue gate fails closed.


def _policy_repo(tmp_path: Path, edit: Any = None) -> Path:
    for name in ("ci.yml", "codeql.yml", "pr-title-lint.yml", "pr-body-policy.yml", "secret-scan.yml"):
        target = tmp_path / ".github" / "workflows" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((WORKFLOWS / name).read_text(encoding="utf-8"), encoding="utf-8")
    policy = json.loads((REPO_ROOT / MERGE_POLICY_PATH).read_text(encoding="utf-8"))
    if edit is not None:
        edit(tmp_path, policy)
    target = tmp_path / MERGE_POLICY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(policy), encoding="utf-8")
    return tmp_path


def _rules(root: Path) -> set[str]:
    return {item.rule_id for item in evaluate_merge_queue_policy(root)}


def _drop_merge_group(root: Path, _policy: dict[str, Any]) -> None:
    path = root / ".github" / "workflows" / "pr-title-lint.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    del workflow[True]["merge_group"]
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")


def _filter_merge_group(root: Path, _policy: dict[str, Any]) -> None:
    path = root / ".github" / "workflows" / "secret-scan.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow[True]["merge_group"]["branches"] = ["dev"]
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")


def _skip_job_on_merge_group(root: Path, _policy: dict[str, Any]) -> None:
    path = root / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow["jobs"]["fuzz"]["if"] = "github.event_name == 'pull_request'"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")


def _app_producer(_root: Path, policy: dict[str, Any]) -> None:
    policy["branches"]["dev"]["required_checks"][-1] = {"context": "body-guard", "app": "Example"}


def _strict_off_without_queue(_root: Path, policy: dict[str, Any]) -> None:
    policy["branches"]["main"]["strict_status_checks"] = False


def _missing_job(_root: Path, policy: dict[str, Any]) -> None:
    policy["branches"]["dev"]["required_checks"][0]["job"] = "absent"


def _foreign_producer(_root: Path, policy: dict[str, Any]) -> None:
    policy["branches"]["dev"]["required_checks"][0]["workflow"] = "tools/ci.yml"


def _duplicate_context(_root: Path, policy: dict[str, Any]) -> None:
    checks = policy["branches"]["dev"]["required_checks"]
    checks.append(copy.deepcopy(checks[0]))


def _extra_key(_root: Path, policy: dict[str, Any]) -> None:
    policy["branches"]["dev"]["required_checks"][0]["optional"] = True


def _non_boolean_queue(_root: Path, policy: dict[str, Any]) -> None:
    policy["branches"]["dev"]["merge_queue"] = "yes"


@pytest.mark.parametrize(
    ("edit", "rule"),
    [
        (_drop_merge_group, "merge-policy-merge-group"),
        (_filter_merge_group, "merge-policy-merge-group"),
        (_skip_job_on_merge_group, "merge-policy-merge-group"),
        (_app_producer, "merge-policy-merge-group"),
        (_strict_off_without_queue, "merge-policy-strict"),
        (_missing_job, "merge-policy-producer"),
        (_foreign_producer, "merge-policy-producer"),
        (_duplicate_context, "merge-policy-shape"),
        (_extra_key, "merge-policy-shape"),
        (_non_boolean_queue, "merge-policy-shape"),
    ],
)
def test_merge_queue_gate_fails_closed(tmp_path: Path, edit: Any, rule: str) -> None:
    assert _rules(_policy_repo(tmp_path)) == set()
    assert rule in _rules(_policy_repo(tmp_path, edit))


def test_merge_queue_gate_requires_its_declaration(tmp_path: Path) -> None:
    assert _rules(tmp_path) == {"merge-policy-shape"}


def test_app_producer_is_admitted_only_without_the_merge_queue(tmp_path: Path) -> None:
    def edit(_root: Path, policy: dict[str, Any]) -> None:
        policy["branches"]["main"]["required_checks"][-1] = {"context": "body-guard", "app": "Example"}

    assert _rules(_policy_repo(tmp_path, edit)) == set()


# Merge group commits are untrusted, and only the reviewed scan job holds the GitGuardian key.


def _check(tmp_path: Path, workflow: dict[Any, Any], path: str) -> set[str]:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    return {failure.rule_id for failure in action_failures(tmp_path, {}, [path])}


def _merge_group_workflow(job: dict[str, Any]) -> dict[str, Any]:
    return {"on": {"merge_group": {}}, "permissions": {"contents": "read"}, "jobs": {"test": job}}


def test_merge_group_job_cannot_hold_publishing_permissions(tmp_path: Path) -> None:
    job = {"runs-on": "ubuntu-24.04", "permissions": {"contents": "write"}, "steps": [{"run": "true"}]}
    assert "tooling-action-permissions" in _check(tmp_path, _merge_group_workflow(job), ".github/workflows/x.yml")


def test_merge_group_job_cannot_hold_credentials(tmp_path: Path) -> None:
    job = {
        "runs-on": "ubuntu-24.04",
        "permissions": {"contents": "read"},
        "steps": [{"run": "true", "env": {"TOKEN": "${{ secrets.TOKEN }}"}}],
    }
    assert "tooling-action-credentials" in _check(tmp_path, _merge_group_workflow(job), ".github/workflows/x.yml")


def test_secret_scan_job_is_admitted(tmp_path: Path) -> None:
    assert _check(tmp_path, _load("secret-scan.yml"), SECRET_SCAN) == set()


def _add_run_step(job: dict[str, Any]) -> None:
    job["steps"].append({"run": "python tools/anything.py"})


def _key_in_checkout(job: dict[str, Any]) -> None:
    job["steps"][0]["env"] = {"GITGUARDIAN_API_KEY": "${{ secrets.GITGUARDIAN_API_KEY }}"}


def _foreign_image(job: dict[str, Any]) -> None:
    job["steps"][1]["uses"] = "docker://example/scanner@sha256:" + "a" * 64


def _other_secret(job: dict[str, Any]) -> None:
    job["steps"][1]["env"]["OTHER"] = "${{ secrets.OTHER }}"


def _write_permission(job: dict[str, Any]) -> None:
    job["permissions"] = {"contents": "read", "pull-requests": "write"}


@pytest.mark.parametrize("change", [_add_run_step, _key_in_checkout, _foreign_image, _other_secret, _write_permission])
def test_secret_scan_credential_boundary_is_narrow(tmp_path: Path, change: Any) -> None:
    workflow = _load("secret-scan.yml")
    change(workflow["jobs"]["ggshield"])
    failures = _check(tmp_path, workflow, SECRET_SCAN)
    assert failures & {"tooling-action-credentials", "tooling-action-permissions"}


def test_secret_scan_boundary_does_not_apply_to_another_workflow(tmp_path: Path) -> None:
    assert "tooling-action-credentials" in _check(tmp_path, _load("secret-scan.yml"), ".github/workflows/x.yml")


def test_secret_scan_uses_a_fixed_config_and_the_change_range() -> None:
    workflow = _load("secret-scan.yml")
    job = workflow["jobs"]["ggshield"]
    assert job["name"] == "GitGuardian Security Checks"
    assert job["steps"][0]["with"] == {"fetch-depth": 0, "persist-credentials": False}
    scan = job["steps"][1]
    assert "entrypoint" not in scan["with"]
    # The runner evaluates the expressions before it splits `args` on spaces.
    assert scan["with"]["args"] == (
        "ggshield --config-path /dev/null secret scan commit-range"
        " ${{ github.event.merge_group.base_sha || github.event.pull_request.base.sha }}"
        "..${{ github.event.merge_group.head_sha || github.event.pull_request.head.sha }}"
    )
    assert scan["env"]["GIT_CONFIG_VALUE_0"] == "/github/workspace"
    assert "continue-on-error" not in scan
    assert "continue-on-error" not in job


# Merge group steps resolve the queued pull request and fail closed.


def _gh_stub(tmp_path: Path, pull_request: dict[str, Any]) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    payload = tmp_path / "pull.json"
    payload.write_text(json.dumps(pull_request), encoding="utf-8")
    stub = bin_dir / "gh"
    # The stub honours `--jq` with the real jq so the step's filter runs unchanged.
    stub.write_text(
        "#!/bin/bash\n"
        'jq_filter=""\n'
        'while [ "$#" -gt 0 ]; do if [ "$1" = "--jq" ]; then jq_filter="$2"; shift; fi; shift; done\n'
        f'if [ -n "$jq_filter" ]; then jq -r "$jq_filter" "{payload}"; else cat "{payload}"; fi\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


def _run_step(tmp_path: Path, script: str, env: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], Path]:
    output = tmp_path / "github-output"
    output.touch()
    completed = subprocess.run(
        ["bash", "-c", script],  # noqa: S607 - the workflow step is a bash script
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            **env,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "OpenRAE/rae",
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
    )
    return completed, output


@pytest.mark.parametrize(
    ("ref", "base", "exit_code"),
    [(QUEUE_REF, "dev", 0), ("refs/heads/2026-feature", "dev", 1), (QUEUE_REF, "main", 1)],
)
def test_ci_resolves_the_queued_pull_request_head_branch(tmp_path: Path, ref: str, base: str, exit_code: int) -> None:
    step = _step(_load("ci.yml")["jobs"]["queued-pull-request"], "Resolve the queued pull request")
    env = _gh_stub(tmp_path, {"base": {"ref": base}, "head": {"ref": "2026-dev-merge-queue"}})
    completed, output = _run_step(tmp_path, step["run"], {**env, "QUEUE_REF": ref})
    assert completed.returncode == exit_code, completed.stderr
    if exit_code == 0:
        assert output.read_text(encoding="utf-8").splitlines() == ["number=2026", "head-ref=2026-dev-merge-queue"]


def test_ci_runs_the_canonical_graph_after_the_resolver() -> None:
    workflow = _load("ci.yml")
    canonical = workflow["jobs"]["canonical"]
    assert canonical["needs"] == "queued-pull-request"
    assert canonical["if"] == "${{ !cancelled() && needs.queued-pull-request.result != 'failure' }}"
    assert workflow["jobs"]["queued-pull-request"]["if"] == "github.event_name == 'merge_group'"
    assert "github.event_name == 'merge_group'" in workflow["jobs"]["sonar"]["steps"][0]["env"]["SONAR_REQUIRED"]


@pytest.mark.parametrize("workflow", ["pr-title-lint.yml", "pr-body-policy.yml"])
@pytest.mark.parametrize(("ref", "base", "exit_code"), [(QUEUE_REF, "dev", 0), (QUEUE_REF, "main", 5)])
def test_pull_request_guards_read_the_queued_pull_request(
    tmp_path: Path, workflow: str, ref: str, base: str, exit_code: int
) -> None:
    (job,) = _load(workflow)["jobs"].values()
    step = _step(job, "Resolve the queued pull request")
    assert step["if"] == "github.event_name == 'merge_group'"
    pull_request = {"number": 2026, "title": "fix: x", "body": "b", "base": {"ref": base}}
    completed, _ = _run_step(tmp_path, step["run"], {**_gh_stub(tmp_path, pull_request), "QUEUE_REF": ref})
    assert completed.returncode == exit_code, completed.stderr
    if exit_code == 0:
        event = json.loads((tmp_path / "pull-request-event.json").read_text(encoding="utf-8"))
        assert event == {"repository": {"full_name": "OpenRAE/rae"}, "pull_request": pull_request}


@pytest.mark.parametrize(
    ("event", "number", "branch", "exit_code", "args"),
    [
        ("pull_request", "", "", 0, "args="),
        ("merge_group", "2026", "2026-dev-merge-queue", 0, None),
        ("merge_group", "", "2026-dev-merge-queue", 1, None),
        ("merge_group", "2026", "", 1, None),
        ("merge_group", "2026", "a b", 1, None),
    ],
)
def test_sonar_analyzes_the_queued_pull_request_on_a_merge_group(
    tmp_path: Path, event: str, number: str, branch: str, exit_code: int, args: str | None
) -> None:
    job = _load("canonical-verification.yml")["jobs"]["sonar"]
    step = _step(job, "Resolve the analysis target")
    env = {"EVENT_NAME": event, "PULL_REQUEST": number, "PULL_REQUEST_BRANCH": branch}
    completed, output = _run_step(tmp_path, step["run"], env)
    assert completed.returncode == exit_code, completed.stderr
    if exit_code == 0:
        expected = args or (
            "args=-Dsonar.pullrequest.key=2026 -Dsonar.pullrequest.branch=2026-dev-merge-queue"
            " -Dsonar.pullrequest.base=dev"
        )
        assert output.read_text(encoding="utf-8").splitlines() == [expected]
    assert "github.event_name == 'merge_group'" in job["if"]
    assert _step(job, "SonarCloud Scan")["with"] == {"args": "${{ steps.target.outputs.args }}"}


@pytest.mark.parametrize(
    "policy",
    [
        {"schema_version": 2, "branches": {"dev": {}}},
        {"schema_version": 1, "branches": ["dev"]},
        {"schema_version": 1, "branches": {}},
        {"schema_version": 1, "branches": {"dev": {"merge_queue": True}}},
        {
            "schema_version": 1,
            "branches": {
                "dev": {"merge_queue": True, "strict_status_checks": False, "required_checks": [{"context": ""}]}
            },
        },
    ],
)
def test_malformed_merge_policy_is_rejected(tmp_path: Path, policy: dict[str, Any]) -> None:
    target = tmp_path / MERGE_POLICY_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(policy), encoding="utf-8")
    assert _rules(tmp_path) == {"merge-policy-shape"}


def test_merge_queue_gate_command_reports_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo-root", str(_policy_repo(tmp_path))]) == 0
    assert main(["--repo-root", str(_policy_repo(tmp_path, _strict_off_without_queue))]) == 1
    assert "[merge-policy-strict]" in capsys.readouterr().err
