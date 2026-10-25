"""Issue #1580: module import resolution fails as SDL diagnostics, never as raw exceptions.

Invalid root import declarations, lock records, lockfiles, trust policies,
directory imports, removed scoring sections in imported units and provenance
bounds reach ``parse_sdl_file``, ``resolve_lock_records``, ``expand_sdl_modules``
and ``raes sdl resolve`` through one ``SDLParseError`` envelope. Expected
diagnostics come from ``parse_sdl_file`` on the same root where possible. The
workspace-configuration reader and the locked-chain budget that #1446 added
stay in force on every one of these entry points.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest
import raes.composition._expand as composition_expand
import raes.parser as sdl_parser
from raes._errors import SDLParseError
from raes._source_profile import DEFAULT_PARSER_LIMITS
from raes.composition import expand_sdl_modules
from raes.module_registry import LOCKFILE_NAME, LOCKFILE_SCHEMA_VERSION, TRUST_POLICY_NAME, resolve_lock_records
from raes.parser import SDLSourceDocument, parse_sdl, parse_sdl_file
from raes.scenario import ExpandedScenario
from raes_cli.main import app
from typer.testing import CliRunner

MODULE = """\
name: shared
version: 1.2.3
module:
  id: acme/shared
  version: 1.2.3
  exports:
    nodes: [vm]
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
"""
SHARED = "- source: local:shared.yaml\n  namespace: shared\n"
SENTINEL = "SENTINEL-7d1f"
REMOVED_SCORING = "metrics: {}\n"
LONG_RANGE = ",".join([">=1.0", *(f"!=0.{index}" for index in range(48))])
# Valid content one input limit too long, so only the bounded read can refuse it.
PADDING = " " * DEFAULT_PARSER_LIMITS.max_input_bytes


def _scenario(directory: Path, imports: str | None, files: dict[str, str | bytes | None] | None = None) -> Path:
    """Write ``shared.yaml``, a root importing ``imports`` and extra files (``None`` makes a directory)."""

    (directory / "shared.yaml").write_text(MODULE, encoding="utf-8")
    for name, content in (files or {}).items():
        target = directory / name
        if content is None:
            target.mkdir()
        elif isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    body = "imports: {}\n" if imports is None else "imports:\n" + textwrap.indent(imports, "  ")
    root = directory / "root.yaml"
    root.write_text(f"name: root\n{body}", encoding="utf-8")
    return root


def _raised(call: Callable[[], object]) -> SDLParseError:
    with pytest.raises(SDLParseError) as caught:
        call()
    return caught.value


def _diagnostics(error: SDLParseError) -> list[tuple[object, ...]]:
    return [(item.code, item.pointer, item.primary_range.as_dict(), item.message) for item in error.diagnostics]


def _adr_073_message() -> str:
    return _raised(lambda: parse_sdl(f"name: root\n{REMOVED_SCORING}")).details


def _lock_record(**overrides: str) -> dict[str, str]:
    record = {
        "source": "local:shared.yaml",
        "namespace": "shared",
        "requested_version": "*",
        "resolved_source": "shared.yaml",
        "module_id": "acme/shared",
        "module_version": "1.2.3",
        "manifest_digest": "",
        "content_digest": "",
        "export_hash": "",
    }
    return record | overrides


def _lockfile(*records: dict[str, str]) -> str:
    return json.dumps({"imports": list(records)})


@pytest.mark.parametrize(
    "imports",
    [
        pytest.param(f"{SHARED}  version: 1.0\n", id="number-version"),
        pytest.param("- source: local:shared.yaml\n", id="no-namespace"),
        pytest.param("- namespace: shared\n", id="no-source"),
        pytest.param(f"{SHARED}  path: shared.yaml\n", id="source-and-path"),
        pytest.param("- source: local:shared.yaml\n  namespace: Not An Id\n", id="bad-namespace"),
        pytest.param(f"{SHARED}  colour: red\n", id="unknown-field"),
        pytest.param(f"{SHARED}  parameters: [a]\n", id="parameters-list"),
        pytest.param(f"{SHARED}  version: '>=banana'\n", id="malformed-range"),
        pytest.param(None, id="imports-mapping"),
    ],
)
def test_resolve_reports_invalid_declarations_like_parse(tmp_path: Path, imports: str | None) -> None:
    root = _scenario(tmp_path, imports)

    parsed = _raised(lambda: parse_sdl_file(root))
    resolved = _raised(lambda: resolve_lock_records(root))

    assert parsed.diagnostics
    assert all(item.pointer.startswith("/imports") for item in parsed.diagnostics)
    assert _diagnostics(resolved) == _diagnostics(parsed)
    assert resolved.path == parsed.path == root


def test_direct_expansion_reports_an_invalid_declaration_as_a_field_diagnostic(tmp_path: Path) -> None:
    root = _scenario(tmp_path, SHARED)
    data = {"name": "root", "imports": [{"source": "local:shared.yaml", "namespace": "shared", "version": 1.0}]}

    error = _raised(lambda: expand_sdl_modules(data, path=root))

    assert [(item.code, item.pointer, item.primary_range.start.line) for item in error.diagnostics] == [
        ("sdl.model.invalid", "/imports/0/version", 1)
    ]
    assert error.path == root


def _lock_failure(root: Path) -> SDLParseError:
    """Parse ``root`` and check the error names the lockfile without rendering its values."""

    error = _raised(lambda: parse_sdl_file(root))
    assert error.path == root.parent / LOCKFILE_NAME
    assert str(error).startswith(f"{root.parent / LOCKFILE_NAME}: ")
    assert SENTINEL not in str(error)
    return error


@pytest.mark.parametrize(
    "record",
    [
        pytest.param(_lock_record(requested_version=f">={SENTINEL}"), id="bad-requested-version"),
        pytest.param(_lock_record(source=""), id="blank-source"),
    ],
)
def test_invalid_lock_record_is_a_typed_error_naming_the_lockfile(tmp_path: Path, record: dict[str, str]) -> None:
    lockfile = _lockfile(record)
    root = _scenario(tmp_path, "- source: locked:shared.yaml\n  namespace: shared\n", {LOCKFILE_NAME: lockfile})

    assert _lock_failure(root).details == "Locked import record is invalid"


def _chain(length: int) -> list[dict[str, str]]:
    """Return ``length`` acyclic records leading from ``locked:x`` to the local module."""

    names = ["x", *(f"hop{index}" for index in range(1, length))]
    targets = [f"locked:{name}" for name in names[1:]] + ["local:shared.yaml"]
    return [_lock_record(source=target, resolved_source=name) for name, target in zip(names, targets, strict=True)]


@pytest.mark.parametrize(
    ("records", "expected"),
    [
        pytest.param(
            [_lock_record(source="locked:x", resolved_source="x")], "Locked import cycle detected", id="self-cycle"
        ),
        pytest.param(
            [
                _lock_record(source="locked:b", resolved_source="x"),
                _lock_record(source="locked:x", resolved_source="b"),
            ],
            "Locked import cycle detected",
            id="two-record-cycle",
        ),
        pytest.param(
            _chain(DEFAULT_PARSER_LIMITS.max_composition_depth + 1),
            "Locked import chain budget exceeded",
            id="chain-over-budget",
        ),
    ],
)
def test_locked_import_cycles_and_overlong_chains_are_typed_errors(
    tmp_path: Path, records: list[dict[str, str]], expected: str
) -> None:
    root = _scenario(tmp_path, "- source: locked:x\n  namespace: shared\n", {LOCKFILE_NAME: _lockfile(*records)})

    assert _lock_failure(root).details == expected


@pytest.mark.parametrize("length", [2, DEFAULT_PARSER_LIMITS.max_composition_depth])
def test_acyclic_locked_chain_resolves_like_its_local_target(tmp_path: Path, length: int) -> None:
    (tmp_path / "direct").mkdir()
    (tmp_path / "chain").mkdir()
    chain = _lockfile(*_chain(length))
    direct_root = _scenario(tmp_path / "direct", SHARED)
    locked_root = _scenario(tmp_path / "chain", "- source: locked:x\n  namespace: shared\n", {LOCKFILE_NAME: chain})

    direct = parse_sdl_file(direct_root)
    locked = parse_sdl_file(locked_root)

    assert isinstance(locked, ExpandedScenario)
    assert isinstance(direct, ExpandedScenario)
    expected = direct.expansion_provenance.imports[0].model_dump(mode="python") | {"requested_source": "locked:x"}
    assert locked.expansion_provenance.imports[0].model_dump(mode="python") == expected


POLICY_FILES = [
    pytest.param(LOCKFILE_NAME, '{"imports": [' + SENTINEL, id="lockfile-bad-json"),
    pytest.param(LOCKFILE_NAME, json.dumps({"imports": SENTINEL}), id="lockfile-bad-shape"),
    pytest.param(LOCKFILE_NAME, b"\xff" + SENTINEL.encode(), id="lockfile-not-utf8"),
    pytest.param(LOCKFILE_NAME, None, id="lockfile-directory"),
    pytest.param(TRUST_POLICY_NAME, f"registries: {SENTINEL}\n", id="trust-bad-shape"),
    pytest.param(TRUST_POLICY_NAME, f"registries: [{SENTINEL}\n", id="trust-bad-yaml"),
    pytest.param(TRUST_POLICY_NAME, f"registries: {SENTINEL}\x07\n", id="trust-control-character"),
    pytest.param(TRUST_POLICY_NAME, b"\xff" + SENTINEL.encode(), id="trust-not-utf8"),
    pytest.param(TRUST_POLICY_NAME, None, id="trust-directory"),
    pytest.param(TRUST_POLICY_NAME, f"registries: &{SENTINEL} [*{SENTINEL}]\n", id="trust-alias-cycle"),
    pytest.param(TRUST_POLICY_NAME, "registries: {}\n#" + PADDING, id="trust-oversized"),
    pytest.param(LOCKFILE_NAME, '{"imports": []}' + PADDING, id="lockfile-oversized"),
]


def _entry_points(name: str) -> list[Callable[[Path], object]]:
    # resolve_lock_records never reads the lockfile, so only the trust policy reaches it.
    return [parse_sdl_file] if name == LOCKFILE_NAME else [parse_sdl_file, resolve_lock_records]


@pytest.mark.parametrize(("name", "content"), POLICY_FILES)
def test_invalid_policy_files_are_typed_errors_naming_the_file(
    tmp_path: Path, name: str, content: str | bytes | None
) -> None:
    root = _scenario(tmp_path, SHARED, {name: content})

    for entry in _entry_points(name):
        error = _raised(lambda entry=entry: entry(root))

        assert error.path == tmp_path / name
        assert error.details == f"Cannot load workspace configuration {name}."
        assert [(item.code, item.source) for item in error.diagnostics] == [
            ("sdl.workspace-config.invalid", str(tmp_path / name))
        ]
        rendered = [str(error), *(item.message for item in error.diagnostics)]
        assert not any(SENTINEL in text for text in rendered)


@pytest.mark.parametrize(
    ("imports", "module_version"),
    [
        pytest.param(f"{SHARED}  version: ''\n", "1.2.3", id="blank-import-version"),
        pytest.param(f"{SHARED}  version: '{LONG_RANGE}'\n", "1.2.3", id="long-import-range"),
        pytest.param(SHARED, "''", id="blank-module-version"),
        pytest.param(SHARED, f"'{'9' * 257}'", id="long-module-version"),
    ],
)
def test_unrecordable_provenance_fails_alike_through_parse_and_resolve(
    tmp_path: Path, imports: str, module_version: str
) -> None:
    assert len(LONG_RANGE) > 256
    root = _scenario(tmp_path, imports)
    (tmp_path / "shared.yaml").write_text(MODULE.replace("  version: 1.2.3", f"  version: {module_version}"))

    parsed = _raised(lambda: parse_sdl_file(root))
    resolved = _raised(lambda: resolve_lock_records(root))

    assert parsed.details.startswith("Import 'local:shared.yaml' cannot be recorded as resolved import provenance: ")
    assert (resolved.details, resolved.path) == (parsed.details, parsed.path)
    assert parsed.path == root


@pytest.mark.parametrize("entry", [parse_sdl_file, resolve_lock_records])
def test_directory_import_is_a_typed_error_naming_the_import(tmp_path: Path, entry: Callable[[Path], object]) -> None:
    root = _scenario(tmp_path, "- source: local:unit\n  namespace: shared\n", {"unit": None})

    error = _raised(lambda: entry(root))

    assert error.details == "Imported SDL source is not a regular file: unit"


@pytest.mark.parametrize("entry", [parse_sdl_file, resolve_lock_records])
def test_unreadable_import_is_a_typed_error_naming_the_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: Callable[[Path], object]
) -> None:
    root = _scenario(tmp_path, SHARED)
    real_read = sdl_parser.read_sdl_source

    def denied(path: Path, **kwargs: object) -> SDLSourceDocument:
        if path.name == "shared.yaml":
            raise PermissionError(f"{SENTINEL}: permission denied")
        return real_read(path, **kwargs)

    monkeypatch.setattr(sdl_parser, "read_sdl_source", denied)
    error = _raised(lambda: entry(root))

    assert error.details == "Imported SDL file could not be read: shared.yaml"


def test_imported_unit_with_removed_scoring_gets_the_root_migration_message(tmp_path: Path) -> None:
    root = _scenario(tmp_path, SHARED)
    (tmp_path / "shared.yaml").write_text(MODULE + REMOVED_SCORING, encoding="utf-8")

    error = _raised(lambda: parse_sdl_file(root))

    assert error.details == _adr_073_message()
    assert error.path == tmp_path / "shared.yaml"


def test_unvalidated_resolver_unit_with_removed_scoring_gets_the_migration_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # OCI resolution returns the unit's verified bytes without typed validation;
    # expansion is then the first place that reads the unit's sections.
    root = _scenario(tmp_path, SHARED)
    real_resolve_import = composition_expand.resolve_import
    text = MODULE + REMOVED_SCORING

    def unvalidated(*args: object, **kwargs: object) -> object:
        resolved = real_resolve_import(*args, **kwargs)
        document = SDLSourceDocument(raw_bytes=text.encode("utf-8"), text=text)
        return dataclasses.replace(resolved, source_document=document)

    monkeypatch.setattr(composition_expand, "resolve_import", unvalidated)
    error = _raised(lambda: parse_sdl_file(root))

    assert error.details == _adr_073_message()


def _compact(text: str) -> str:
    return "".join(text.split())


def _cli_output(arguments: list[str]) -> tuple[int, str]:
    """Return the exit code and the output without styling, panel borders or whitespace.

    Rich wraps and folds the error panel at the terminal width, so long paths
    can break anywhere; callers compare whitespace-free fragments.
    """

    result = CliRunner().invoke(app, arguments)
    return result.exit_code, _compact(re.sub(r"\x1b\[[0-9;]*m", "", result.output).replace("│", " "))


@pytest.mark.parametrize(
    ("imports", "files", "expected"),
    [
        pytest.param(f"{SHARED}  version: 1.0\n", {}, ["root.yaml", "/imports/0/version"], id="declaration"),
        pytest.param(
            SHARED,
            {TRUST_POLICY_NAME: "registries: [1]\n"},
            [f"Cannot load workspace configuration {TRUST_POLICY_NAME}."],
            id="trust",
        ),
        pytest.param(
            f"{SHARED}  version: ''\n",
            {},
            ["root.yaml: Import 'local:shared.yaml' cannot be recorded as resolved import provenance"],
            id="provenance",
        ),
        pytest.param(
            "- source: local:mod.yaml\n  namespace: shared\n",
            {"mod.yaml": MODULE + REMOVED_SCORING},
            ["mod.yaml", "removed from the language by ADR-073"],
            id="imported-unit",
        ),
        pytest.param(
            SHARED, {LOCKFILE_NAME: None}, ["Lockfile could not be written", LOCKFILE_NAME], id="lockfile-directory"
        ),
    ],
)
def test_raes_sdl_resolve_reports_each_failure_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, imports: str, files: dict[str, str], expected: list[str]
) -> None:
    _scenario(tmp_path, imports, files)
    monkeypatch.chdir(tmp_path)

    exit_code, output = _cli_output(["sdl", "resolve", "root.yaml"])

    assert exit_code != 0
    assert "Traceback" not in output
    assert all(_compact(fragment) in output for fragment in expected), output
    assert "input_value" not in output
    assert not (tmp_path / LOCKFILE_NAME).is_file()


def test_valid_root_keeps_a_byte_identical_lockfile_and_parse_result(tmp_path: Path) -> None:
    root = _scenario(tmp_path, SHARED)
    content_digest = "sha256:" + hashlib.sha256(MODULE.encode("utf-8")).hexdigest()
    export_hash = hashlib.sha256(b'{"nodes":["vm"]}').hexdigest()
    record = _lock_record(content_digest=content_digest, export_hash=export_hash) | {"signer_id": ""}
    lockfile = {"imports": [record], "schema_version": LOCKFILE_SCHEMA_VERSION}
    expected = json.dumps(lockfile, indent=2, sort_keys=True) + "\n"

    exit_code, output = _cli_output(["sdl", "resolve", str(root)])
    scenario = parse_sdl_file(root)
    (tmp_path / "plain.yaml").write_text("name: plain\n", encoding="utf-8")
    assert resolve_lock_records(tmp_path / "plain.yaml").imports == []

    assert exit_code == 0, output
    assert (tmp_path / LOCKFILE_NAME).read_text(encoding="utf-8") == expected
    assert isinstance(scenario, ExpandedScenario)
    provenance = scenario.expansion_provenance.imports[0]
    assert (provenance.requested_source, provenance.module_version, provenance.content_digest) == (
        "local:shared.yaml",
        "1.2.3",
        content_digest,
    )
