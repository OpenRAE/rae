"""Editor helpers resolve local duplicate imports as file-backed parsing does, and fetch nothing (#1339)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from raes import SDLParseError, SDLValidationError, parse_sdl_file
from raes.language_service import (
    apply_structured_edit,
    language_completions,
    language_diagnostics,
    language_format,
    language_references,
)
from raes.module_registry import resolution

_HOST = {"type": "compute", "resources": {"ram": "1 GiB", "cpu": 1}}
_MODULE = {
    "name": "module",
    "module": {"id": "example/hosts", "version": "1.0.0", "exports": {"nodes": ["vm", "services", "runtime"]}},
    "nodes": {
        "vm": _HOST,
        # Grammar words as local ids: their services and runtime records keep their own kinds.
        "services": {
            **_HOST,
            "services": [{"name": "smtp", "port": 25}],
            "runtime": {"applications": [{"application_id": "portal"}]},
        },
        "runtime": {
            **_HOST,
            "services": [{"name": "dns", "port": 53}],
            "runtime": {"applications": [{"application_id": "resolver"}]},
        },
    },
}
_OCI = "oci:registry.example/acme/hosts:1.0.0"


def _root(*namespaces: str, **relationships: str) -> dict:
    return {
        "name": "two-copies",
        "imports": [{"path": "module.yaml", "namespace": namespace} for namespace in namespaces],
        "nodes": {"local": _HOST},
        "relationships": {
            name: {"type": "connects_to", "source": "local", "target": target} for name, target in relationships.items()
        },
    }


def _write(directory: Path, root: dict, module: dict = _MODULE) -> tuple[str, Path]:
    (directory / "module.yaml").write_text(yaml.safe_dump(module), encoding="utf-8")
    text = yaml.safe_dump(root, sort_keys=False)
    path = directory / "root.yaml"
    path.write_text(text, encoding="utf-8")
    return text, path


def _messages(result: dict) -> list[str]:
    return [item["message"] for item in result["diagnostics"]]


def _file_error(path: Path) -> str:
    with pytest.raises((SDLParseError, SDLValidationError)) as caught:
        parse_sdl_file(path)
    error = caught.value
    return error.errors[0] if isinstance(error, SDLValidationError) else error.details


def test_path_mode_composes_local_imports_for_diagnostics_completion_and_navigation(tmp_path: Path) -> None:
    text, path = _write(tmp_path, _root("first", "second", to_first="first.vm", to_second="nodes.second.vm"))
    parse_sdl_file(path)

    completion = language_completions(text, cursor_path="/relationships/to_first/target", path=path)
    labels = {item["detail"]: item["label"] for item in completion["items"]}

    assert language_diagnostics(text, path=path) == {
        "status": "valid",
        "stage": "semantic_validation",
        "diagnostics": [],
    }
    assert (labels["nodes.first.vm"], labels["nodes.second.vm"], labels["nodes.local"]) == (
        "first.vm",
        "second.vm",
        "local",
    )
    first = {item["path"] for item in language_references(text, "nodes.first.vm", path=path)["occurrences"]}
    assert first == {"/relationships/to_first/target"}


def test_without_a_path_the_helpers_keep_the_content_only_boundary(tmp_path: Path) -> None:
    text, _path = _write(tmp_path, _root("first", "second", to_first="first.vm"))

    labels = {
        item["label"] for item in language_completions(text, cursor_path="/relationships/to_first/target")["items"]
    }

    assert _messages(language_diagnostics(text)) == ["SDL imports require file-backed parsing via parse_sdl_file()"]
    assert "first.vm" not in labels
    assert language_references(text, "nodes.first.vm")["occurrences"] == []


def test_a_bare_name_that_only_imports_declare_is_refused_as_file_backed_parsing_refuses_it(tmp_path: Path) -> None:
    text, path = _write(tmp_path, _root("first", "second", bare="vm"))

    labels = {
        item["label"]
        for item in language_completions(text, cursor_path="/relationships/bare/target", path=path)["items"]
    }

    assert "vm" not in labels
    assert _messages(language_diagnostics(text, path=path)) == [_file_error(path)]
    assert "does not reference any defined targetable element" in _file_error(path)


def test_a_root_local_bare_name_beside_an_imported_copy_stays_unambiguous(tmp_path: Path) -> None:
    root = _root("first", local_vm="vm")
    root["nodes"]["vm"] = _HOST
    text, path = _write(tmp_path, root)
    parse_sdl_file(path)

    labels = {
        item["detail"]: item["label"]
        for item in language_completions(text, cursor_path="/relationships/local_vm/target", path=path)["items"]
    }

    assert (labels["nodes.vm"], labels["nodes.first.vm"]) == ("vm", "first.vm")
    assert "/relationships/local_vm/target" in {
        item["path"] for item in language_references(text, "nodes.vm", path=path)["occurrences"]
    }


def test_a_namespace_imported_twice_collides_in_the_editor_as_in_file_backed_parsing(tmp_path: Path) -> None:
    text, path = _write(tmp_path, _root("first", "first"))

    assert _messages(language_diagnostics(text, path=path)) == [_file_error(path)]
    assert "collides on nodes: first." in _file_error(path)


def _registry_workspace(tmp_path: Path, source: str) -> tuple[str, Path]:
    (tmp_path / "raes-trust.yaml").write_text(
        yaml.safe_dump({"registries": {"registry.example": {"require_signatures": False}}}), encoding="utf-8"
    )
    lock = {
        "source": _OCI,
        "namespace": "first",
        "resolved_source": "oci:registry.example/acme/hosts@sha256:" + "0" * 64,
        "module_id": "example/hosts",
        "module_version": "1.0.0",
        "manifest_digest": "sha256:" + "1" * 64,
        "content_digest": "sha256:" + "2" * 64,
        "export_hash": "sha256:" + "3" * 64,
    }
    (tmp_path / "raes.lock.json").write_text(json.dumps({"imports": [lock]}), encoding="utf-8")
    root = _root(to_first="first.vm")
    root["imports"] = [{"source": source, "namespace": "first"}]
    return _write(tmp_path, root)


@pytest.mark.parametrize("source", [_OCI, f"locked:{_OCI}"], ids=["oci", "locked-oci"])
def test_path_mode_refuses_a_registry_import_without_fetching_or_caching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    def fetch(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("editor path mode must not resolve a registry import")

    monkeypatch.setattr(resolution, "_resolve_oci_import", fetch)
    monkeypatch.setattr(resolution, "_resolve_oci_manifest", fetch)
    text, path = _registry_workspace(tmp_path, source)

    messages = _messages(language_diagnostics(text, path=path))
    completion = language_completions(text, cursor_path="/relationships/to_first/target", path=path)
    references = language_references(text, "nodes.local", path=path)

    assert messages == [
        f"Registry import '{source}' is not resolved in editor path mode; validate with parse_sdl_file()"
    ]
    assert not any("not allowed by trust policy" in message for message in messages)
    assert {item["detail"] for item in completion["items"]} >= {"nodes.local"}
    assert references["status"] == "ok"
    assert not (tmp_path / ".raes").exists()


def test_a_locked_import_missing_from_the_lockfile_keeps_the_existing_refusal(tmp_path: Path) -> None:
    source = "locked:oci:registry.example/acme/other:1.0.0"
    text, path = _registry_workspace(tmp_path, source)

    assert _messages(language_diagnostics(text, path=path)) == [_file_error(path)]
    assert _file_error(path) == f"Locked import '{source}' is not present in raes.lock.json"


def test_a_workspace_that_refuses_unsigned_local_sources_refuses_them_in_path_mode(tmp_path: Path) -> None:
    (tmp_path / "raes-trust.yaml").write_text(yaml.safe_dump({"allow_unsigned_local_sources": False}), encoding="utf-8")
    text, path = _write(tmp_path, _root("first", to_first="first.vm"))

    assert _messages(language_diagnostics(text, path=path)) == [_file_error(path)]


def test_format_and_structured_edits_report_path_mode_diagnostics(tmp_path: Path) -> None:
    text, path = _write(tmp_path, _root("first", "second", to_first="first.vm"))

    edited = apply_structured_edit(
        text, operation="set", pointer="/relationships/to_first/target", value="vm", path=path
    )
    path.write_text(edited["content"], encoding="utf-8")

    assert language_format(text, path=path)["diagnostics"] == []
    assert edited["diagnostics"] == language_diagnostics(edited["content"], path=path)["diagnostics"]
    assert _messages(edited) == [_file_error(path)]
    assert _messages(language_format(text)) == ["SDL imports require file-backed parsing via parse_sdl_file()"]


def test_completions_offered_in_a_module_validate_in_each_namespace_when_it_is_imported_twice(tmp_path: Path) -> None:
    module = {**_MODULE, "relationships": {"link": {"type": "connects_to", "source": "vm", "target": "vm"}}}
    module["module"] = {
        **_MODULE["module"],
        "exports": {"nodes": ["vm", "services", "runtime"], "relationships": ["link"]},
    }

    items = language_completions(yaml.safe_dump(module), cursor_path="/relationships/link/target")["items"]

    assert items
    for item in items:
        module["relationships"]["link"]["target"] = item["label"]
        _text, path = _write(tmp_path, _root("first", "second"), module)
        scenario = parse_sdl_file(path)
        # Each copy's reference is rewritten into its own namespace.
        assert scenario.relationships["first.link"].target != scenario.relationships["second.link"].target


@pytest.mark.parametrize(
    ("detail", "value", "occurrence"),
    [
        ("database_access", "nodes.first.runtime.runtime.applications.resolver", True),
        ("database_access", "nodes.first.services.runtime.applications.portal", True),
        ("database_access", "nodes.first.runtime", False),
        ("domain_controller", "nodes.first.services", True),
        ("domain_controller", "nodes.first.runtime.runtime.applications.resolver", False),
    ],
)
def test_imported_grammar_word_nodes_keep_their_kinds_in_an_incomplete_root(
    tmp_path: Path, detail: str, value: str, occurrence: bool
) -> None:
    root = _root("first")
    relationship_type = "domain_controller_for" if detail == "domain_controller" else "connects_to"
    root["relationships"]["probe"] = {"type": relationship_type, "source": value, "target": "local", detail: {}}
    root["conditions"] = {"pending": {"command": "true", "interval": "soon"}}
    text, path = _write(tmp_path, root)

    occurrences = {item["path"] for item in language_references(text, value, path=path)["occurrences"]}

    assert language_diagnostics(text, path=path)["status"] == "invalid"
    assert ("/relationships/probe/source" in occurrences) is occurrence
