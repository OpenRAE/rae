"""The post-edit policy hook checks Claude Code's absolute file paths as paths in their own checkout.

#1427 strips the project directory; #1505 runs the checker of the checkout that holds the file, such as a
Claude Code worktree under `.claude/worktrees/` or a checkout nested in the project by hand, and checks a
path through a symlink at the location it resolves to while still refusing parent traversal and a symlink that
leaves the checkout.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tools.verified_tool_installation import default_installation_root

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".claude" / "hooks" / "check_policy_after_edit.sh"
# The legacy-root rule reads only the path, so this file does not need to exist.
LEGACY_ROOT_PATH = "schemas/legacy-contract.json"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the post-edit policy hook requires bash and jq",
)
path_forms = pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])


def _without_git_variables() -> dict[str, str]:
    """Drop variables an enclosing git process may set, such as GIT_DIR, so git finds each checkout itself."""
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def _run_hook(file_path: str, project_dir: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the hook as `.claude/settings.json` does: PostToolUse JSON on stdin and a 30-second timeout."""
    event = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": file_path}}
    environment = {**_without_git_variables(), "CLAUDE_PROJECT_DIR": str(project_dir)}
    return subprocess.run(
        [str(HOOK)], input=json.dumps(event), capture_output=True, text=True, env=environment, check=False, timeout=30
    )


def _file_path(path: str, *, absolute: bool) -> str:
    return str(REPO_ROOT / path) if absolute else path


# A path the checker accepts reaches its Conftest rules, which the integration lane installs.
# A root-level file named like an option must reach the checker as a path: read as an option,
# "-h" prints the checker's usage on stdout and exits 0 without checking anything.
@pytest.mark.integration
@path_forms
@pytest.mark.parametrize("path", ["README.md", "-h"], ids=["readme", "option-like-name"])
def test_a_clean_file_passes(path: str, absolute: bool) -> None:
    result = _run_hook(_file_path(path, absolute=absolute))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.integration
@path_forms
def test_a_finding_names_the_repository_path(absolute: bool) -> None:
    result = _run_hook(_file_path(LEGACY_ROOT_PATH, absolute=absolute))
    assert result.returncode == 1
    assert result.stderr.startswith(f"[legacy-top-level-root] {LEGACY_ROOT_PATH}: ")


@pytest.mark.parametrize(
    ("file_path", "checked_path"),
    [
        pytest.param(f"{REPO_ROOT}-sibling/README.md", f"{REPO_ROOT}-sibling/README.md", id="sibling-directory"),
        pytest.param(f"{REPO_ROOT}/../outside.py", "../outside.py", id="parent-traversal"),
        pytest.param(f"{REPO_ROOT}/tools/../README.md", "tools/../README.md", id="contained-parent-traversal"),
    ],
)
def test_the_checker_refuses_parent_traversal_and_paths_outside_the_project(file_path: str, checked_path: str) -> None:
    result = _run_hook(file_path)
    assert result.returncode == 1
    assert result.stderr.startswith(f"[policy-path-unsafe] {checked_path}: ")


# Stands in for tools/check_repo_policy.py in a temporary project, so these cases need neither the project's
# rules nor Conftest. Like a finding, it writes to stderr and exits 1: which checkout's checker ran, from which
# directory, under which interpreter, and with which arguments.
RECORDING_CHECKER = """\
import json, os, sys
from pathlib import Path

report = {
    "checkout": str(Path(__file__).resolve().parents[1]),
    "cwd": os.getcwd(),
    "interpreter": os.environ.get("HOOK_TEST_INTERPRETER"),
    "arguments": sys.argv[1:],
}
print(json.dumps(report), file=sys.stderr)
sys.exit(1)
"""
CHECKOUTS = {"main-checkout": ".", "claude-worktree": ".claude/worktrees/bg", "nested-checkout": "nested/checkout"}
INTERPRETERS = {"tooling": "implementations/tooling/python", "package": "implementations/python"}


def _git(cwd: Path, *arguments: str) -> None:
    identity = ("-c", "user.name=Hook Test", "-c", "user.email=hook@example.invalid")
    subprocess.run(
        ["git", *identity, *arguments], cwd=cwd, env=_without_git_variables(), capture_output=True, check=True
    )


def _make_checkout(root: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("a temporary checkout requires git")
    checker = root / "tools" / "check_repo_policy.py"
    checker.parent.mkdir(parents=True)
    checker.write_text(RECORDING_CHECKER, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "tools")
    _git(root, "commit", "-q", "--no-gpg-sign", "-m", "checker")
    return root


def _add_interpreter(root: Path, name: str) -> None:
    """Add an untracked interpreter for the hook, which tells the checker which environment ran it."""
    interpreter = root / INTERPRETERS[name] / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text(
        f'#!/bin/sh\nexport HOOK_TEST_INTERPRETER={name}\nexec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    interpreter.chmod(0o700)


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A checkout with a real Claude Code worktree, a nested clone and a nested checkout of another repository."""
    root = _make_checkout(tmp_path_factory.mktemp("project").resolve())
    _git(root, "worktree", "add", "-q", "--detach", CHECKOUTS["claude-worktree"])
    _git(root, "clone", "-q", ".", CHECKOUTS["nested-checkout"])
    (root / "vendor" / "other").mkdir(parents=True)
    _git(root / "vendor" / "other", "init", "-q")
    # The hook prefers the tooling interpreter: a new checkout's first check installs Conftest, which needs filelock.
    _add_interpreter(root, "tooling")
    _add_interpreter(root, "package")
    for checkout in CHECKOUTS.values():
        (root / checkout / "tools" / "target.py").touch()
        (root / checkout / "relative-link.py").symlink_to("tools/target.py")
        (root / checkout / "absolute-link.py").symlink_to(root / checkout / "tools" / "target.py")
        (root / checkout / "directory-link").symlink_to("tools", target_is_directory=True)
    worktree_tools = root / CHECKOUTS["claude-worktree"] / "tools"
    (root / "worktree-file-link.py").symlink_to(worktree_tools / "target.py")
    (root / "worktree-directory-link").symlink_to(worktree_tools, target_is_directory=True)
    (root / "outside-directory-link").symlink_to(tmp_path_factory.mktemp("outside"), target_is_directory=True)
    return root


def _outcome(result: subprocess.CompletedProcess[str]) -> tuple[int, str, str]:
    return result.returncode, result.stdout, result.stderr


# The same edit gets the same checker call in every checkout, run from that checkout's root with this
# project's interpreter, as neither the worktree nor the clone has one. A new file's directory may not exist.
@pytest.mark.parametrize("checkout", list(CHECKOUTS.values()), ids=list(CHECKOUTS))
@pytest.mark.parametrize(
    "path",
    ["implementations/python/packages/raes/new_module.py", "tools/new_tool.py"],
    ids=["new-directory", "existing-directory"],
)
def test_each_checkout_checks_the_path_against_its_own_root(project: Path, checkout: str, path: str) -> None:
    root = project / checkout
    result = _run_hook(str(root / path), project)
    assert result.returncode == 1
    assert json.loads(result.stderr) == {
        "checkout": str(root),
        "cwd": str(root),
        "interpreter": "tooling",
        "arguments": ["--check-set", "file-local", "--", path],
    }


def test_without_a_tooling_environment_the_package_interpreter_runs(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path.resolve())
    _add_interpreter(root, "package")
    result = _run_hook(str(root / "README.md"), root)
    assert result.returncode == 1
    assert json.loads(result.stderr)["interpreter"] == "package"


# A checkout of another repository, or of a commit before the checker, has no policy to check.
def test_a_checkout_without_the_checker_is_not_checked(project: Path) -> None:
    result = _run_hook(str(project / "vendor" / "other" / "module.py"), project)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


# A checkout outside the project is not checked against its own root: the path stays absolute and is refused.
def test_a_checkout_outside_the_project_is_refused(project: Path) -> None:
    file_path = str(project / "tools" / "new_tool.py")
    result = _run_hook(file_path)
    assert result.returncode == 1
    assert result.stderr.startswith(f"[policy-path-unsafe] {file_path}: ")


# An alias of the main checkout's or the worktree's root outside the project gets the same checker call as the
# canonical path, so the checker reports the same findings.
@pytest.mark.parametrize("checkout", ["main-checkout", "claude-worktree"])
def test_a_checkout_root_alias_is_checked_as_the_canonical_path(project: Path, tmp_path: Path, checkout: str) -> None:
    root = project / CHECKOUTS[checkout]
    alias = tmp_path / "root"
    alias.symlink_to(root, target_is_directory=True)
    canonical = _run_hook(str(root / "tools" / "new_tool.py"), project)
    assert _outcome(_run_hook(str(alias / "tools" / "new_tool.py"), project)) == _outcome(canonical)
    assert json.loads(canonical.stderr)["arguments"][-1] == "tools/new_tool.py"


# A link to a file in the same checkout is checked at its target's repository-relative path.
@pytest.mark.parametrize("checkout", ["main-checkout", "claude-worktree"])
@pytest.mark.parametrize("link", ["relative-link.py", "absolute-link.py", "directory-link/target.py"])
def test_an_in_checkout_link_is_checked_at_its_target(project: Path, checkout: str, link: str) -> None:
    root = project / CHECKOUTS[checkout]
    result = _run_hook(str(root / link), project)
    assert _outcome(result) == _outcome(_run_hook(str(root / "tools" / "target.py"), project))
    assert json.loads(result.stderr)["arguments"][-1] == "tools/target.py"


# A link in the main checkout into the worktree or out of the project keeps its absolute path, which the
# checker refuses, instead of letting the main checkout's rules check another checkout's file.
@pytest.mark.parametrize(
    "link", ["worktree-file-link.py", "worktree-directory-link/target.py", "outside-directory-link/module.py"]
)
def test_a_link_out_of_the_checkout_stays_absolute(project: Path, link: str) -> None:
    result = _run_hook(str(project / link), project)
    assert json.loads(result.stderr)["arguments"][-1] == str(project / link)


PROBE = "implementations/python/packages/raes/_probe_policy_hook.py"


def _remove_worktree(root: Path) -> None:
    """Remove a worktree whose verified installation left read-only directories."""
    for directory, _, _ in os.walk(root):
        Path(directory).chmod(0o700)
    _git(REPO_ROOT, "worktree", "remove", "--force", str(root))


@pytest.fixture(scope="module")
def policy_checkout(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A worktree of this repository's HEAD with the real checker, its Conftest, and a probe that breaks layering."""
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("the real checker needs a git checkout of this repository")
    base = tmp_path_factory.mktemp("policy-checkout").resolve()
    root = base / "checkout"
    _git(REPO_ROOT, "worktree", "add", "-q", "--detach", str(root), "HEAD")
    try:
        conftest = default_installation_root(REPO_ROOT) / "conftest"
        if conftest.is_dir():
            directory = root
            for part in default_installation_root(root).relative_to(root).parts:
                directory /= part
                directory.mkdir(mode=0o700, exist_ok=True)
            # The installer accepts only owner-only directories and lock files with a single link.
            shutil.copytree(conftest, directory / "conftest", symlinks=True)
        _add_interpreter(root, "package")
        (root / PROBE).write_text("import raes_processor\n", encoding="utf-8")
        (root / "probe-link.py").symlink_to(PROBE)
        (base / "root-alias").symlink_to(root, target_is_directory=True)
        os.mkfifo(base / "outside.fifo")
        (root / "escape.py").symlink_to(base / "outside.fifo")
        (root / "escape-directory").symlink_to(base, target_is_directory=True)
        yield root
    finally:
        _remove_worktree(root)


# The real checker reports the same path-scoped findings, including the layering rule for
# implementations/python/packages/raes/, for the canonical path, a root alias and an in-checkout link.
@pytest.mark.integration
@pytest.mark.parametrize("alias", ["root-alias/" + PROBE, "checkout/probe-link.py"], ids=["root-alias", "file-link"])
def test_the_real_checker_reports_the_canonical_findings_for_an_alias(policy_checkout: Path, alias: str) -> None:
    canonical = _run_hook(str(policy_checkout / PROBE), policy_checkout)
    assert canonical.returncode == 1
    assert f"[layering-rule-violation] {PROBE}: " in canonical.stderr
    assert _outcome(_run_hook(str(policy_checkout.parent / alias), policy_checkout)) == _outcome(canonical)


# A file or directory link out of the checkout is refused. Its target is a FIFO, so any read would block
# until the hook's timeout instead of returning the refusal.
@pytest.mark.integration
@pytest.mark.parametrize("link", ["escape.py", "escape-directory/outside.fifo"], ids=["file-link", "directory-link"])
def test_a_link_out_of_the_checkout_is_refused_without_reading_its_target(policy_checkout: Path, link: str) -> None:
    file_path = str(policy_checkout / link)
    result = _run_hook(file_path, policy_checkout)
    assert result.returncode == 1
    assert result.stderr.startswith(f"[policy-path-unsafe] {file_path}: ")
