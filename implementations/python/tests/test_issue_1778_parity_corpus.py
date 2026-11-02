"""The parity corpus recorder records each surface deterministically and detects drift (issue #1778)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools import parity_corpus as pc

REAL_PROVENANCE = pc.provenance

PROVENANCE = {
    "python_commit": "a" * 40,
    "python_tree": "b" * 40,
    "recorder_sha256": "c" * 64,
    "python_version": "3.14.7",
    "unicode_version": "16.0.0",
    "hash_seed": "0",
    "lock_sha256": "d" * 64,
}


@pytest.fixture(autouse=True)
def fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "provenance", lambda repo: PROVENANCE)


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
    assert transform.path == Path("cases/cli/semantic-transform", pc.digest(transform.name.encode()) + ".json")


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


def test_check_reports_drift(repo: Path) -> None:
    cases = list(pc.schema_cases(repo))
    recorded = pc.build_corpus(repo, cases)
    root = repo / pc.CORPUS_DIR
    pc.write_corpus(root, recorded)

    assert pc.read_corpus(root) == recorded
    assert pc.corpus_differences(pc.build_corpus(repo, cases), recorded) == []

    changed = dict(recorded)
    changed[cases[0].path] = b"{}\n"
    del changed[cases[1].path]
    changed[Path("cases/schema/validate/extra.json")] = b"{}\n"
    changed[pc.MANIFEST] = pc.encode({"schema": "other/v1"})
    assert sorted(pc.corpus_differences(recorded, changed)) == sorted(
        [
            f"missing: {cases[1].path}",
            f"changed: {cases[0].path}",
            "unexpected: cases/schema/validate/extra.json",
            "changed: manifest.json",
        ]
    )
    assert pc.read_corpus(repo / "absent") == {}


def test_main_records_and_checks_the_corpus(repo: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(pc, "supported_contracts", lambda: ["demo-v1"])
    monkeypatch.setattr(pc, "all_cases", lambda root: list(pc.schema_cases(root)))
    from tools import parity_regressions

    monkeypatch.setattr(parity_regressions, "source_identity", lambda root: None)

    assert pc.main(["check", "--repo-root", str(repo), "--output-dir", str(repo / "fresh")]) == 1
    assert "files differ" in capsys.readouterr().err
    assert pc.read_corpus(repo / "fresh")[pc.MANIFEST] == pc.encode({"schema": pc.SCHEMA, "provenance": PROVENANCE})

    assert pc.main(["record", "--repo-root", str(repo)]) == 0
    assert pc.main(["check", "--repo-root", str(repo)]) == 0
    assert "files match" in capsys.readouterr().out


def test_duplicate_case_cannot_overwrite_a_recording(repo: Path) -> None:
    case = next(pc.schema_cases(repo))
    with pytest.raises(ValueError, match="duplicate corpus case"):
        pc.build_corpus(repo, [case, case])


def test_provenance_identifies_the_python_source_and_locked_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    _write(tmp_path, {"implementations/python/uv.lock": "locked environment"})
    values = iter(["a" * 40, "b" * 40, "b" * 40])
    commands = []

    def git_output(command: list[str], *, text: bool) -> str:
        assert text is True
        commands.append(command)
        return next(values)

    monkeypatch.setattr(pc.subprocess, "check_output", git_output)
    result = REAL_PROVENANCE(tmp_path)
    source = "implementations/python/packages"
    assert commands == [
        ["git", "-C", str(tmp_path), "log", "-1", "--format=%H", "--", source],
        ["git", "-C", str(tmp_path), "rev-parse", "a" * 40 + ":" + source],
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD:" + source],
    ]
    assert result["python_commit"] == "a" * 40
    assert result["python_tree"] == "b" * 40
    assert result["recorder_sha256"] == pc.digest(
        pc.encode(
            {path.name: pc.digest(path.read_bytes()) for path in sorted(Path(pc.__file__).parent.glob("parity_*.py"))}
        )
    )
    assert result["lock_sha256"] == pc.digest(b"locked environment")
    assert result["python_version"] == ".".join(map(str, pc.sys.version_info[:3]))
    assert result["unicode_version"] == pc.unicodedata.unidata_version
    assert result["hash_seed"] == "0"

    values = iter(["a" * 40, "b" * 40, "c" * 40])
    with pytest.raises(ValueError, match="does not identify the current Python tree"):
        REAL_PROVENANCE(tmp_path)


def test_canonical_cases_cover_each_json_fixture_and_each_edge_input(repo: Path) -> None:
    names = {case.name for case in pc.canonical_cases(repo)}

    assert "contracts/fixtures/family/demo-v1/valid/one" in names
    assert sum(name.startswith("edge/") for name in names) == len(pc.CANONICAL_EDGE_TEXTS)


def test_canonical_results_record_each_form_or_its_refusal() -> None:
    def result(text: str) -> dict[str, object]:
        return pc.run_canonical(pc.Case("canonical", "encode", "x", (), {"value.json": text.encode()}))

    def digest(text: bytes) -> str:
        return "sha256:" + pc.digest(text)

    assert result("1.0") == {"jcs": digest(b"1"), "sorted_ascii": digest(b"1.0"), "sorted_unicode": digest(b"1.0")}
    assert result('"é"') == {
        "jcs": digest('"é"'.encode()),
        "sorted_ascii": digest(b'"\\u00e9"'),
        "sorted_unicode": digest('"é"'.encode()),
    }
    assert result("9007199254740992")["jcs"] is None
    assert result("9007199254740992")["sorted_ascii"] == digest(b"9007199254740992")
    longest = "-" + "9" * 4300
    assert result(longest) == {
        "jcs": None,
        "sorted_ascii": digest(longest.encode()),
        "sorted_unicode": digest(longest.encode()),
    }
    for refused in ("NaN", "1e400", "[1] 2", "9" * 4301):
        assert result(refused) == {"jcs": None, "sorted_ascii": None, "sorted_unicode": None}


def test_randstream_cases_reproduce_each_published_vector() -> None:
    repo = Path(__file__).resolve().parents[3]
    cases = list(pc.randstream_cases(repo))

    assert len(cases) == len(list((repo / "contracts/fixtures/random-stream-vectors").rglob(pc.JSON_FILES)))
    for case in cases:
        vector = json.loads(case.files[pc.RANDSTREAM_VECTOR])
        result = pc.run_randstream(case)
        assert result["stream_key_hex"] == vector["stream_key_hex"]
        assert result["address_canonical_bytes_hex"] == vector["address_canonical_bytes_hex"]
        assert result["raw_block_hex"] == vector["raw_block_hex"]
        transform = vector.get("transform")
        if transform is not None:
            assert result["draw"]["rejection_attempts"] == transform["expected_rejection_attempts"]
            assert result["draw"]["rejection_exhausted"] == transform["expected_rejection_exhausted"]
            expected_value = None if transform["expected_rejection_exhausted"] else transform["outcome"]["value"]
            assert result["draw"]["value"] == expected_value


def test_primitive_corpus_records_reference_results_and_all_commands() -> None:
    cases = list(pc.primitive_cases())
    assert {case.command for case in cases} == {
        "ingress",
        "ingress-exception",
        "uri",
        "pointer",
        "tokens",
        "address",
        "render",
        "plan-root",
    }
    assert len({case.path for case in cases}) == len(cases)
    for case in cases:
        result = pc.run_primitive(case)
        assert result == pc.run_primitive(case)
        assert json.loads(pc.encode(result)) == result
    ingress_codes = {pc.run_primitive(case).get("code") for case in cases if case.command == "ingress"}
    assert ingress_codes == {
        None,
        "input-too-large",
        "empty-input",
        "input-too-deep",
        "invalid-json",
        "duplicate-member",
        "non-finite-number",
        "integer-too-long",
        "invalid-root",
    }
    uri_codes = {pc.run_primitive(case)["code"] for case in cases if case.command == "uri"}
    assert uri_codes == {"", "absolute", "invalid", "scheme", "credentials", "fragment", "secret"}


@pytest.mark.parametrize(
    "payload",
    [
        b'{"name":"valid","extra":NaN}',
        b'{"name":"valid","extra":Infinity}',
        b'{"name":"valid","extra":-Infinity}',
        '{"name":"valid"}'.encode("utf-16"),
    ],
)
def test_schema_recording_rejects_non_json_constants_and_non_utf8_wire_payloads(repo: Path, payload: bytes) -> None:
    case = pc.Case("schema", "validate", "wire-format", ("demo-v1",), {"payload.json": payload})
    assert pc.run_schema(repo, case) == {"valid": False}


def test_recording_failure_identifies_the_case_without_printing_input_values(repo: Path, monkeypatch, capsys) -> None:
    case = pc.Case("cli", "sdl publish", "reference-module", (), {})

    def fail(*args):
        raise RuntimeError("private input sentinel")

    monkeypatch.setattr(pc, "run", fail)
    with pytest.raises(RuntimeError):
        pc.build_corpus(repo, [case])
    error = capsys.readouterr().err
    assert "cli sdl publish (reference-module)" in error
    assert "private input sentinel" not in error


def test_provenance_requires_the_recording_hash_seed(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONHASHSEED", "random")
    with pytest.raises(ValueError, match="PYTHONHASHSEED=0"):
        REAL_PROVENANCE(repo)


def test_shared_cases_cover_the_remaining_primitives_and_replay_the_reference() -> None:
    cases = list(pc.shared_cases())
    assert {case.command for case in cases} == {
        "timestamp",
        "version",
        "domain",
        "graph",
        "value",
        "carrier",
        "secret",
        "digest",
        "log",
        "fault",
        "clock",
    }
    assert len({case.path for case in cases}) == len(cases)
    for case in cases:
        result = pc.run_shared(case)
        assert result == pc.run_shared(case)
        assert json.loads(pc.encode(result)) == result
    carrier = next(case for case in cases if case.command == "carrier")
    assert pc.run_shared(carrier)["go"] == {"accepted": False}
