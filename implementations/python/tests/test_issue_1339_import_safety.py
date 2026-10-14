"""Locked imports and workspace policy errors remain bounded on every authoring path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from raes import SDLParseError, parse_sdl_file
from raes._source_profile import SDLParserLimits, SDLSourceParseOptions
from raes.language_service import (
    apply_structured_edit,
    language_completions,
    language_diagnostics,
    language_format,
    language_references,
)
from raes.module_registry import resolve_import
from raes.module_registry.models import Lockfile, load_lockfile, load_trust_policy
from raes.scenario import ImportDecl
from test_issue_1339_editor_imports import _root, _write


def _record(name: str, source: str) -> dict:
    return {
        "source": source,
        "resolved_source": name,
        "namespace": "first",
        "module_id": "example/hosts",
        "module_version": "1.0.0",
        "manifest_digest": "",
        "content_digest": "",
        "export_hash": "",
    }


def _locked_workspace(tmp_path: Path, records: list[dict]) -> tuple[str, Path]:
    (tmp_path / "raes.lock.json").write_text(json.dumps({"imports": records}), encoding="utf-8")
    root = _root()
    root["imports"] = [{"source": "locked:first", "namespace": "first"}]
    return _write(tmp_path, root)


@pytest.mark.parametrize(
    "records",
    [
        [_record("first", "locked:first")],
        [_record("first", "locked:second"), _record("second", "locked:first")],
        [_record("first" if n == 0 else f"item{n}", f"locked:item{n + 1}") for n in range(40)],
    ],
    ids=["self-cycle", "two-record-cycle", "chain-budget"],
)
def test_locked_cycles_and_overlong_chains_are_safe_on_all_editor_paths(tmp_path: Path, records: list[dict]) -> None:
    text, path = _locked_workspace(tmp_path, records)
    with pytest.raises(SDLParseError, match="Locked import (cycle|chain)"):
        parse_sdl_file(path)
    diagnostics = language_diagnostics(text, path=path)
    assert diagnostics["status"] == "invalid"
    assert "Locked import" in diagnostics["diagnostics"][0]["message"]
    assert language_completions(text, cursor_path="/relationships/link/target", path=path)["status"] == "ok"
    assert language_references(text, "nodes.local", path=path)["status"] == "ok"
    assert language_format(text, path=path)["diagnostics"]
    assert apply_structured_edit(text, operation="set", pointer="/description", value="updated", path=path)[
        "diagnostics"
    ]


def test_locked_chain_uses_the_configured_budget_and_resolves_valid_local_sources(tmp_path: Path) -> None:
    records = [_record("first", "locked:second"), _record("second", "local:module.yaml")]
    text, path = _locked_workspace(tmp_path, records)
    assert "first.vm" in parse_sdl_file(path).nodes
    assert language_diagnostics(text, path=path)["status"] == "valid"
    lock = Lockfile.model_validate({"imports": records})
    decl = ImportDecl(source="locked:first", namespace="first")
    resolved = resolve_import(
        decl,
        base_dir=tmp_path,
        lockfile=lock,
        source_options=SDLSourceParseOptions(limits=SDLParserLimits(max_composition_depth=2)),
    )
    assert resolved.module_descriptor.id == "example/hosts"
    with pytest.raises(SDLParseError, match="Locked import chain"):
        resolve_import(
            decl,
            base_dir=tmp_path,
            lockfile=lock,
            source_options=SDLSourceParseOptions(limits=SDLParserLimits(max_composition_depth=1)),
        )


def test_editor_refuses_a_registry_import_at_the_end_of_a_locked_chain(tmp_path: Path, monkeypatch) -> None:
    from raes.module_registry import resolution

    def fetch(*_args, **_kwargs):
        raise AssertionError("editor must refuse before registry resolution")

    monkeypatch.setattr(resolution, "_resolve_oci_import", fetch)
    records = [_record("first", "locked:second"), _record("second", "oci:registry.example/acme/hosts")]
    text, path = _locked_workspace(tmp_path, records)
    assert language_diagnostics(text, path=path)["diagnostics"][0]["message"] == (
        "Registry import 'locked:first' is not resolved in editor path mode; validate with parse_sdl_file()"
    )
    assert language_completions(text, cursor_path="/relationships/link/target", path=path)["status"] == "ok"
    assert language_references(text, "nodes.local", path=path)["status"] == "ok"
    assert not (tmp_path / ".raes").exists()


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("raes-trust.yaml", "api_token: REVIEW_SYNTHETIC_VALUE"),
        ("raes-trust.yaml", "registries: [REVIEW_SYNTHETIC_VALUE"),
        ("raes-trust.yaml", "[]"),
        ("raes-trust.yaml", "false"),
        ("raes-trust.yaml", "registries: REVIEW_SYNTHETIC_VALUE\x00"),
        ("raes-trust.yaml", "registries: &cycle [*cycle]"),
        ("raes-trust.yaml", "registries: {host: {require_signatures: REVIEW_SYNTHETIC_VALUE}}"),
        ("raes.lock.json", '{"imports": "REVIEW_SYNTHETIC_VALUE"}'),
        ("raes.lock.json", '{"imports": "REVIEW_SYNTHETIC_VALUE"'),
    ],
)
def test_workspace_policy_errors_do_not_escape_or_disclose_values(tmp_path: Path, filename: str, content: str) -> None:
    text, path = _write(tmp_path, _root("first"))
    (tmp_path / filename).write_text(content, encoding="utf-8")
    with pytest.raises(SDLParseError) as caught:
        parse_sdl_file(path)
    assert caught.value.path == tmp_path / filename
    assert "REVIEW_SYNTHETIC_VALUE" not in str(caught.value)
    diagnostics = language_diagnostics(text, path=path)
    assert diagnostics["status"] == "invalid"
    assert "REVIEW_SYNTHETIC_VALUE" not in json.dumps(diagnostics)
    assert "Traceback" not in json.dumps(diagnostics)
    assert language_completions(text, cursor_path="/relationships/link/target", path=path)["status"] == "ok"
    assert language_references(text, "nodes.local", path=path)["status"] == "ok"
    assert language_format(text, path=path)["diagnostics"]


@pytest.mark.parametrize(
    ("filename", "loader"), [("raes-trust.yaml", load_trust_policy), ("raes.lock.json", load_lockfile)]
)
@pytest.mark.parametrize("failure", ["encoding", "directory", "permission", "size"])
def test_workspace_policy_loading_failures_use_safe_sdl_errors(
    tmp_path: Path, monkeypatch, filename, loader, failure
) -> None:
    path = tmp_path / filename
    if failure == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"\xff" if failure == "encoding" else b"{}")
    if failure == "permission":
        original = Path.open

        def denied(self, *args, **kwargs):
            if self == path:
                raise PermissionError("REVIEW_SYNTHETIC_VALUE")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", denied)
    elif failure == "size":
        from raes.module_registry import models

        monkeypatch.setattr(models, "DEFAULT_PARSER_LIMITS", SDLParserLimits(max_input_bytes=1))
    with pytest.raises(SDLParseError) as caught:
        loader(tmp_path)
    assert caught.value.path == path
    assert "REVIEW_SYNTHETIC_VALUE" not in str(caught.value)


def test_missing_workspace_policy_preserves_defaults_and_empty_trust_mapping(tmp_path: Path) -> None:
    assert load_lockfile(tmp_path) is None
    assert load_trust_policy(tmp_path).allow_unsigned_local_sources
    (tmp_path / "raes-trust.yaml").write_text(yaml.safe_dump({}), encoding="utf-8")
    assert load_trust_policy(tmp_path).allow_unsigned_local_sources


def test_invalid_locked_version_constraints_do_not_disclose_configuration_values(tmp_path: Path) -> None:
    record = _record("first", "local:module.yaml")
    record["requested_version"] = "REVIEW_SYNTHETIC_VALUE"
    text, path = _locked_workspace(tmp_path, [record])
    with pytest.raises(SDLParseError) as caught:
        parse_sdl_file(path)
    assert "REVIEW_SYNTHETIC_VALUE" not in str(caught.value)
    result = language_diagnostics(text, path=path)
    assert result["status"] == "invalid"
    assert "REVIEW_SYNTHETIC_VALUE" not in json.dumps(result)
