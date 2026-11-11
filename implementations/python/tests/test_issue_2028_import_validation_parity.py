"""Issue #2028: import resolution and expansion admit imports exactly as the parser does."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from raes._errors import SDLParseError
from raes._source_profile import PROGRESSIVE_SDL_REVISION
from raes.composition import expand_sdl_modules
from raes.module_registry import resolve_lock_records
from raes.parser import parse_sdl_file
from raes_cli.main import app
from typer.testing import CliRunner

_UNIT = "local:unit.sdl.yaml"
_VALID_IMPORT = f"imports:\n  - source: {_UNIT}\n    namespace: u\n"


def _workspace(tmp_path: Path, imports: str, *, module_version: str = "1.0.0", unit_extra: str = "") -> Path:
    (tmp_path / "unit.sdl.yaml").write_text(
        f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\n"
        "name: unit\n"
        "module:\n"
        "  id: example/unit\n"
        f"  version: '{module_version}'\n"
        f"{unit_extra}",
        encoding="utf-8",
    )
    root = tmp_path / "root.sdl.yaml"
    root.write_text(f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\nname: root\n{imports}", encoding="utf-8")
    return root


def _shape(error: SDLParseError) -> list[tuple[str, str, int, int, int, int]]:
    return [
        (
            item.code,
            item.pointer,
            item.primary_range.start.line,
            item.primary_range.start.column,
            item.primary_range.end.line,
            item.primary_range.end.column,
        )
        for item in error.diagnostics
    ]


_INVALID_ROOT_IMPORTS = {
    "unquoted-float-version": (
        f"imports:\n  - source: {_UNIT}\n    namespace: u\n    version: 1.0\n",
        "/imports/0/version",
    ),
    "missing-namespace": (f"imports:\n  - source: {_UNIT}\n", "/imports/0"),
    "invalid-range": (
        f"imports:\n  - source: {_UNIT}\n    namespace: u\n    version: '>=banana'\n",
        "/imports/0/version",
    ),
    "mapping-imports": ("imports: {}\n", "/imports"),
    "blank-version": (f"imports:\n  - source: {_UNIT}\n    namespace: u\n    version: ''\n", "/imports/0/version"),
    "whitespace-version": (
        f"imports:\n  - source: {_UNIT}\n    namespace: u\n    version: '  '\n",
        "/imports/0/version",
    ),
    "overlong-version": (
        f"imports:\n  - source: {_UNIT}\n    namespace: u\n    version: '{'1' * 257}'\n",
        "/imports/0/version",
    ),
}


@pytest.mark.parametrize("imports, pointer", _INVALID_ROOT_IMPORTS.values(), ids=_INVALID_ROOT_IMPORTS.keys())
def test_lock_resolution_reports_invalid_root_imports_as_the_parser_does(
    tmp_path: Path, imports: str, pointer: str
) -> None:
    root = _workspace(tmp_path, imports)

    with pytest.raises(SDLParseError) as parsed:
        parse_sdl_file(root)
    with pytest.raises(SDLParseError) as locked:
        resolve_lock_records(root)

    assert _shape(locked.value) == _shape(parsed.value)
    assert [item.pointer for item in locked.value.diagnostics] == [pointer]
    assert {item.code for item in locked.value.diagnostics} == {"sdl.model.invalid"}


@pytest.mark.parametrize("module_version", ["", "  ", "1" * 257])
def test_invalid_module_version_is_a_parse_diagnostic_on_both_paths(tmp_path: Path, module_version: str) -> None:
    root = _workspace(tmp_path, _VALID_IMPORT, module_version=module_version)

    with pytest.raises(SDLParseError) as parsed:
        parse_sdl_file(root)
    with pytest.raises(SDLParseError) as locked:
        resolve_lock_records(root)

    assert _shape(locked.value) == _shape(parsed.value)
    assert [item.pointer for item in parsed.value.diagnostics] == ["/module/version"]


def test_imported_unit_with_removed_scoring_section_gets_the_adr_073_message(tmp_path: Path) -> None:
    root = _workspace(tmp_path, _VALID_IMPORT, unit_extra="metrics: {}\n")
    root_with_metrics = tmp_path / "scoring-root.sdl.yaml"
    root_with_metrics.write_text(
        f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\nname: root\nmetrics: {{}}\n", encoding="utf-8"
    )

    with pytest.raises(SDLParseError) as root_error:
        parse_sdl_file(root_with_metrics)
    with pytest.raises(SDLParseError) as parsed:
        parse_sdl_file(root)
    with pytest.raises(SDLParseError) as locked:
        resolve_lock_records(root)

    expected = str(root_error.value).split(": ", 1)[1]
    assert "ADR-073" in expected
    for error in (parsed.value, locked.value):
        assert error.path == tmp_path / "unit.sdl.yaml"
        assert str(error).split(": ", 1)[1] == expected


def test_direct_expansion_reports_an_invalid_import_declaration_as_a_field_diagnostic(tmp_path: Path) -> None:
    with pytest.raises(SDLParseError) as error:
        expand_sdl_modules({"imports": [{"source": _UNIT}]}, path=tmp_path / "root.sdl.yaml")

    assert [(item.code, item.pointer) for item in error.value.diagnostics] == [("sdl.model.invalid", "/imports/0")]
    assert error.value.diagnostics[0].message == "Import requires an explicit namespace"


@pytest.mark.parametrize("case", ["mapping-imports", "blank-version"])
def test_resolve_cli_writes_no_lockfile_for_a_root_the_parser_rejects(tmp_path: Path, case: str) -> None:
    root = _workspace(tmp_path, _INVALID_ROOT_IMPORTS[case][0])

    result = CliRunner().invoke(app, ["sdl", "resolve", str(root)])

    assert result.exit_code == 1
    assert "the input was rejected (SDLParseError)" in result.stderr
    assert not (tmp_path / "raes.lock.json").exists()


def test_valid_root_still_resolves_and_parses(tmp_path: Path) -> None:
    root = _workspace(tmp_path, _VALID_IMPORT)

    result = CliRunner().invoke(app, ["sdl", "resolve", str(root)])

    assert result.exit_code == 0, result.output
    lock = json.loads((tmp_path / "raes.lock.json").read_text(encoding="utf-8"))
    assert [(record["source"], record["namespace"], record["requested_version"]) for record in lock["imports"]] == [
        (_UNIT, "u", "*")
    ]
    assert lock == resolve_lock_records(root).model_dump(mode="python")
    assert parse_sdl_file(root).expansion_provenance.imports[0].module_version == "1.0.0"
