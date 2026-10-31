"""The parity corpus recorder records each surface deterministically and detects drift (issue #1778)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools import parity_corpus as pc

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
}


def _write(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        {
            "examples/scenarios/minimal.sdl.yaml": "name: minimal\n",
            "examples/scenarios/broken.sdl.yaml": "name: [\n",
            "contracts/fixtures/sdl/sdl-yaml-v1/valid/core.yaml": "name: core\n",
            "contracts/fixtures/sdl/sdl-yaml-v1/migration/alias.yaml": "name: alias\n",
            "contracts/fixtures/family/demo-v1/valid/one.json": '{"name": "one"}',
            "contracts/fixtures/family/demo-v1/invalid/two.json": '{"name": 2}',
            "contracts/fixtures/family/demo-v1/invalid/three.json": "{",
            "contracts/schema-publication/entries/demo-v1.json": json.dumps(
                {"contract_id": "demo-v1", "schema_path": "contracts/schemas/demo-v1.json"}
            ),
            "contracts/schemas/demo-v1.json": json.dumps(SCHEMA),
        },
    )
    return tmp_path


def test_normalized_output_drops_only_the_diagnostic_messages() -> None:
    stdout = json.dumps(
        {
            "status": "invalid",
            "payload": {"message": "authored data stays"},
            "diagnostics": [{"code": "sdl.parse", "address": "/a", "message": "free text"}, "not an object"],
        }
    )

    assert pc.normalized_output(stdout) == {
        "status": "invalid",
        "payload": {"message": "authored data stays"},
        "diagnostics": [{"code": "sdl.parse", "address": "/a"}, "not an object"],
    }
    assert pc.normalized_output("Usage: raes semantic validate") is None


def test_sdl_cases_record_each_command_and_the_migration_policy_of_migration_fixtures(repo: Path) -> None:
    cases = list(pc.sdl_cases(repo))
    names = {(case.command, case.name) for case in cases}

    commands = {*("semantic " + command for command in pc.SDL_COMMANDS), "semantic transform"}
    assert {case.command for case in cases} == commands
    assert ("semantic validate", "examples/scenarios/minimal.sdl") in names
    assert ("semantic transform", "examples/scenarios/minimal.sdl/transform-canonical") in names
    assert ("semantic parse", "contracts/fixtures/sdl/sdl-yaml-v1/migration/alias/migration-policy-accept") in names
    assert not any("migration-policy" in name for _, name in names if "valid/core" in name)
    transform = next(case for case in cases if case.name == "examples/scenarios/minimal.sdl/transform-format")
    assert transform.args == (
        "semantic",
        "transform",
        "--output",
        "json",
        "--contract",
        "sdl-yaml/v1",
        "--transform",
        "format",
        "input.yaml",
    )
    assert transform.files == {"input.yaml": b"name: minimal\n"}
    assert transform.path == Path("cases/cli/semantic-transform/examples/scenarios/minimal.sdl/transform-format.json")


def test_portable_cases_cover_each_fixture_and_the_rejected_commands(repo: Path) -> None:
    cases = list(pc.portable_cases(repo, ["demo-v1"]))
    names = {(case.command, case.name) for case in cases}

    for fixture in ("valid/one", "invalid/two", "invalid/three"):
        for command in pc.PORTABLE_COMMANDS:
            assert ("semantic " + command, "contracts/fixtures/family/demo-v1/" + fixture) in names
    for command in pc.UNSUPPORTED_PORTABLE_COMMANDS:
        assert ("semantic " + command, "contracts/fixtures/family/demo-v1/valid/one") in names
    unknown = next(case for case in cases if case.name.endswith("/unknown-contract"))
    assert "unknown-contract-v1" in unknown.args
    assert list(pc.portable_cases(repo, [])) == []


def test_schema_cases_record_the_verdict_of_the_published_schema(repo: Path) -> None:
    results = {case.name: pc.run(repo, case) for case in pc.schema_cases(repo)}

    assert results == {
        "contracts/fixtures/family/demo-v1/invalid/three": {"valid": False},
        "contracts/fixtures/family/demo-v1/invalid/two": {"valid": False},
        "contracts/fixtures/family/demo-v1/valid/one": {"valid": True},
    }


def test_cli_cases_record_the_exit_code_and_the_normalized_output(repo: Path) -> None:
    cases = {case.name: case for case in pc.sdl_cases(repo) if case.command == "semantic parse"}
    accepted = pc.run(repo, cases["examples/scenarios/minimal.sdl"])
    rejected = pc.run(repo, cases["examples/scenarios/broken.sdl"])

    assert accepted["exit_code"] == 0
    assert accepted["stdout"]["operation"] == "parse"
    assert rejected["exit_code"] == 1
    assert rejected["stdout"]["diagnostics"]
    assert all("message" not in diagnostic for diagnostic in rejected["stdout"]["diagnostics"])
    assert pc.run(repo, cases["examples/scenarios/broken.sdl"]) == rejected


def test_check_reports_drift_and_ignores_the_recorded_python_commit(repo: Path) -> None:
    cases = list(pc.schema_cases(repo))
    recorded = pc.build_corpus(repo, cases, "commit-a")
    root = repo / pc.CORPUS_DIR
    pc.write_corpus(root, recorded)

    assert pc.read_corpus(root) == recorded
    assert pc.corpus_differences(pc.build_corpus(repo, cases, "commit-b"), recorded) == []

    changed = dict(recorded)
    changed[cases[0].path] = b"{}\n"
    del changed[cases[1].path]
    changed[Path("cases/schema/validate/extra.json")] = b"{}\n"
    changed[pc.MANIFEST] = pc.encode({"schema": "other/v1", "python_commit": "commit-a"})
    assert pc.corpus_differences(recorded, changed) == [
        f"missing: {cases[1].path}",
        f"changed: {cases[0].path}",
        "unexpected: cases/schema/validate/extra.json",
        "changed: manifest.json",
    ]
    assert pc.read_corpus(repo / "absent") == {}


def test_main_records_and_checks_the_corpus(repo: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(pc, "python_commit", lambda _repo: "commit-a")
    monkeypatch.setattr(pc, "supported_contracts", lambda: ["demo-v1"])

    assert pc.main(["check", "--repo-root", str(repo), "--output-dir", str(repo / "fresh")]) == 1
    assert "files differ" in capsys.readouterr().err
    assert pc.read_corpus(repo / "fresh")[pc.MANIFEST] == pc.encode({"schema": pc.SCHEMA, "python_commit": "commit-a"})

    assert pc.main(["record", "--repo-root", str(repo)]) == 0
    assert pc.main(["check", "--repo-root", str(repo)]) == 0
    assert "files match" in capsys.readouterr().out
