"""Repository-authoritative governance cannot become an unavailable HTTP skip."""

import pytest


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
    with pytest.raises(RepositoryRequirementError):
        RepositoryRequirementClient(tmp_path).get_requirement("raes-sdl", uid)


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
    with pytest.raises(RepositoryRequirementError):
        RepositoryRequirementClient(tmp_path).get_requirement("raes-sdl", "ASR-532")
