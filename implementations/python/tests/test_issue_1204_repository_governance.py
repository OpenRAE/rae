"""Repository-authoritative governance cannot become an unavailable HTTP skip."""

import pytest


@pytest.fixture
def merging_repository(tmp_path):
    import subprocess

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    def write(name, value):
        path = tmp_path / "implementations" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(value, encoding="utf-8")

    git("init", "-b", "integration")
    git("config", "user.name", "Test Maintainer")
    git("config", "user.email", "maintainer@example.invalid")
    write("incoming.py", "baseline")
    write("resolved.py", "baseline")
    git("add", ".")
    git("commit", "-m", "baseline")
    git("switch", "-c", "1204-feature")
    write("feature.py", "feature")
    git("add", ".")
    git("commit", "-m", "feature")
    git("switch", "integration")
    write("incoming.py", "integration")
    write("upstream.py", "integration")
    git("add", ".")
    git("commit", "-m", "integration")
    git("update-ref", "refs/remotes/origin/dev", "HEAD")
    git("switch", "1204-feature")
    git("merge", "--no-ff", "--no-commit", "integration")
    write("resolved.py", "resolved")
    git("add", ".")
    return tmp_path, git, write


@pytest.mark.parametrize("staged", [False, True])
@pytest.mark.parametrize("trust", ["matched", "advanced", "mismatched", "missing"])
def test_merge_governance_keeps_feature_and_resolution_paths(merging_repository, monkeypatch, staged, trust):
    from tools import check_requirement_governance as gate

    root, git, _write = merging_repository
    if trust == "mismatched":
        git("update-ref", "refs/remotes/origin/dev", "HEAD")
    elif trust == "missing":
        git("update-ref", "-d", "refs/remotes/origin/dev")
    elif trust == "advanced":
        # A later integration commit already contains the feature file. The
        # current merge must still govern it against its actual pinned parent.
        advanced = git("commit-tree", "HEAD^{tree}", "-p", "integration", "-m", "advanced integration")
        git("update-ref", "refs/remotes/origin/dev", advanced)
    observed = []
    monkeypatch.setattr(gate, "REPO_ROOT", root)
    monkeypatch.setattr(
        gate, "evaluate_configured_governance", lambda paths, *_args, **_kwargs: observed.extend(paths) or 0
    )
    monkeypatch.setattr("sys.argv", ["check", "--requirement-uid", "ASR-532", *(["--staged"] if staged else [])])
    assert gate.main() == 0
    expected = (
        {"implementations/feature.py", "implementations/resolved.py"}
        if trust in {"matched", "advanced"}
        else {"implementations/incoming.py", "implementations/upstream.py", "implementations/resolved.py"}
    )
    assert set(observed) == expected


def test_merge_governance_preserves_the_staged_boundary(merging_repository, monkeypatch):
    from tools import check_requirement_governance as gate

    root, _git, write = merging_repository
    write("incoming.py", "unstaged feature edit")
    observed = []
    monkeypatch.setattr(gate, "REPO_ROOT", root)
    monkeypatch.setattr(
        gate, "evaluate_configured_governance", lambda paths, *_args, **_kwargs: observed.extend(paths) or 0
    )
    for flags, includes_unstaged in ((["--staged"], False), ([], True)):
        observed.clear()
        monkeypatch.setattr("sys.argv", ["check", "--requirement-uid", "ASR-532", *flags])
        assert gate.main() == 0
        assert ("implementations/incoming.py" in observed) is includes_unstaged


@pytest.mark.parametrize("staged", [False, True])
def test_explicit_governance_base_is_not_replaced_during_merge(merging_repository, monkeypatch, staged):
    from tools import check_requirement_governance as gate

    root, _git, _write = merging_repository
    monkeypatch.setattr(gate, "REPO_ROOT", root)
    expected = (
        ["implementations/incoming.py", "implementations/resolved.py", "implementations/upstream.py"]
        if staged
        else ["implementations/feature.py"]
    )
    assert gate.requirement_changed_paths(staged=staged, base_rev="HEAD^") == expected


def test_nonmerge_governance_still_checks_the_local_diff(merging_repository, monkeypatch):
    from tools import check_requirement_governance as gate

    root, git, write = merging_repository
    git("commit", "-m", "resolve integration")
    write("incoming.py", "local edit")
    monkeypatch.setattr(gate, "REPO_ROOT", root)
    assert gate.requirement_changed_paths(staged=False, base_rev=None) == ["implementations/incoming.py"]


def _requirement(tmp_path, *, uid="ASR-532", status="ACTIVE"):
    path = tmp_path / "docs" / "requirements" / "ASR-532" / "requirement.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {uid}\nstatus: {status}\ntitle: Integrity\n---\n\n"
        "## Traceability\n\n"
        "- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_calls.py` (Admission)\n"
        "- TESTS → TEST `implementations/python/tests/test_issue_158_runtime_result_integrity.py` (Regressions)\n",
        encoding="utf-8",
    )
    return path


def test_repository_client_preserves_status_and_native_traceability(tmp_path):
    from tools.policy.repository_requirements import RepositoryRequirementClient

    _requirement(tmp_path)
    client = RepositoryRequirementClient(tmp_path)
    requirement = client.get_requirement("raes-sdl", "ASR-532")
    assert requirement == {"id": "ASR-532", "uid": "ASR-532", "status": "ACTIVE"}
    assert client.get_traceability(requirement["id"]) == [
        {
            "link_type": "IMPLEMENTS",
            "artifact_type": "CODE_FILE",
            "artifact_identifier": "implementations/python/packages/raes_runtime/backend_calls.py",
        },
        {
            "link_type": "TESTS",
            "artifact_type": "TEST",
            "artifact_identifier": "implementations/python/tests/test_issue_158_runtime_result_integrity.py",
        },
    ]


@pytest.mark.parametrize("mutation", ["missing", "wrong-uid", "invalid-status", "path-escape", "symlink"])
def test_invalid_repository_requirement_fails_closed(tmp_path, mutation):
    from tools.policy.repository_requirements import RepositoryRequirementClient, RepositoryRequirementError

    path = _requirement(
        tmp_path,
        uid="ASR-533" if mutation == "wrong-uid" else "ASR-532",
        status="maybe" if mutation == "invalid-status" else "ACTIVE",
    )
    uid = "ASR-532"
    if mutation == "missing":
        uid = "ASR-533"
    elif mutation == "path-escape":
        uid = "../ASR-532"
    elif mutation == "symlink":
        outside = tmp_path / "outside.md"
        path.rename(outside)
        path.symlink_to(outside)
    client = RepositoryRequirementClient(tmp_path)

    with pytest.raises(RepositoryRequirementError):
        client.get_requirement("raes-sdl", uid)


def test_configured_repository_governance_never_uses_or_falls_back_to_http(tmp_path, monkeypatch, capsys):
    from tools import check_requirement_governance as gate

    path = _requirement(tmp_path)
    policy = tmp_path / "tools" / "policy" / "requirement_order.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text(
        "project: raes-sdl\nrequirement_source: repository\nphases:\n"
        "  - id: runtime-integrity\n    requirements: [ASR-532]\n"
        "traceability:\n  required_code_roots: []\n  required_test_roots: []\n",
        encoding="utf-8",
    )
    (policy.parent / "exceptions.yaml").write_text("exceptions: []\n", encoding="utf-8")
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(gate, "evaluate_against_ground_control", lambda *args, **kwargs: calls.append("http"))
    assert gate.evaluate_configured_governance([], "ASR-532", require_governance=True, as_json=False) == 0
    path.rename(path.with_suffix(".unavailable"))
    assert gate.evaluate_configured_governance([], "ASR-532", require_governance=False, as_json=False) == 1
    assert "repository-requirement-invalid" in capsys.readouterr().err
    assert calls == []


@pytest.mark.parametrize(
    "metadata",
    [
        "id: ASR-532\nstatus: DRAFT\nstatus: ACTIVE",
        "id: ASR-532\nstatus: ACTIVE\nextra: " + "[" * 1500 + "0" + "]" * 1500,
    ],
)
def test_ambiguous_or_excessively_nested_metadata_is_a_governed_failure(tmp_path, metadata):
    from tools.policy.repository_requirements import RepositoryRequirementClient, RepositoryRequirementError

    path = _requirement(tmp_path)
    path.write_text(f"---\n{metadata}\n---\n", encoding="utf-8")
    client = RepositoryRequirementClient(tmp_path)

    with pytest.raises(RepositoryRequirementError):
        client.get_requirement("raes-sdl", "ASR-532")
