"""Navigation and imported diagnostics retain original declaration locations through canonical composition."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml
from raes import instantiate_scenario, parse_sdl_file
from raes._declarations import build_declaration_index
from raes._language_context import reference_context
from raes.language_service import language_diagnostics, language_references
from test_issue_1339_editor_imports import _MODULE, _root, _write
from test_issue_1339_relationship_endpoints import matrix_payload


@pytest.mark.parametrize(
    "symbol",
    [
        "nodes.app.services.http",
        "nodes.dc.roles.ops",
        "workflows.response.steps.validate",
        "nodes.app.runtime.security_monitoring_managers.siem.detection_definitions.detection-definitions",
        "nodes.app.runtime.mail_services.mail.listeners.listeners",
        "content.briefing",
    ],
)
def test_nested_local_definitions_have_their_actual_key_or_identifier_range(symbol: str) -> None:
    text = yaml.safe_dump(matrix_payload(), sort_keys=False)
    definitions = language_references(text, symbol)["definitions"]
    assert len(definitions) == 1
    definition = definitions[0]
    assert definition["qualified_name"] == symbol
    position = definition["range"]["start"]
    line = text.splitlines()[position["line"] - 1]
    assert symbol.rsplit(".", 1)[-1] in line[position["column"] - 1 :]


def test_twice_imported_definitions_share_the_fragment_range_and_keep_distinct_composed_paths(tmp_path: Path) -> None:
    text, path = _write(tmp_path, _root("first", "second", to_first="nodes.first.vm", to_second="nodes.second.vm"))
    module_path = tmp_path / "module.yaml"
    definitions = [language_references(text, f"nodes.{ns}.vm", path=path)["definitions"] for ns in ("first", "second")]
    assert all(len(items) == 1 for items in definitions)
    first, second = (items[0] for items in definitions)
    assert first["range"] == second["range"]
    for namespace, definition in zip(("first", "second"), (first, second), strict=True):
        assert definition["source"] == str(module_path)
        assert definition["path"] == "/nodes/vm"
        assert definition["composed_path"] == f"/nodes/{namespace}.vm"
        assert definition["namespace"] == [namespace]
        assert definition["module_id"] == "example/hosts"
        assert definition["content_digest"] == "sha256:" + hashlib.sha256(module_path.read_bytes()).hexdigest()
    instantiated = instantiate_scenario(parse_sdl_file(path))
    index = build_declaration_index(instantiated)
    assert index.declaration_for("nodes.first.vm").source == str(module_path)
    assert index.declaration_for("nodes.second.vm").source == str(module_path)


def test_every_imported_nested_kind_has_source_provenance_without_rewalking_imports(tmp_path: Path) -> None:
    payload = matrix_payload()
    payload["module"] = {
        "id": "example/all-kinds",
        "version": "1.0.0",
        "exports": {
            key: list(value) for key, value in payload.items() if isinstance(value, dict) and key != "variables"
        },
    }
    text, path = _write(tmp_path, {"name": "root", "imports": [{"path": "module.yaml", "namespace": "first"}]}, payload)
    assert language_diagnostics(text, path=path)["status"] == "valid"
    document = reference_context(text, path)
    imported = [
        declaration for declaration in document.declaration_index.declarations if declaration.kind != "scenario"
    ]
    assert imported
    for declaration in imported:
        assert declaration.source == str(tmp_path / "module.yaml"), declaration.address
        assert declaration.source_location is not None, declaration.address
        assert declaration.source_location.source_range.start.line > 1
    definition = language_references(text, "nodes.first.app.services.http", path=path)["definitions"][0]
    assert definition["path"].startswith("/nodes/app/services/")
    assert definition["composed_path"].startswith("/nodes/first.app/services/")


def test_nested_import_locations_remain_in_the_original_fragment(tmp_path: Path) -> None:
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(_MODULE), encoding="utf-8")
    container = {
        "name": "container",
        "module": {"id": "example/container", "version": "1.0.0", "exports": {"nodes": ["inner.vm"]}},
        "imports": [{"path": "module.yaml", "namespace": "inner"}],
    }
    (tmp_path / "container.yaml").write_text(yaml.safe_dump(container), encoding="utf-8")
    text = yaml.safe_dump({"name": "root", "imports": [{"path": "container.yaml", "namespace": "outer"}]})
    path = tmp_path / "root.yaml"
    path.write_text(text, encoding="utf-8")
    definition = language_references(text, "nodes.outer.inner.vm", path=path)["definitions"][0]
    assert definition["source"] == str(tmp_path / "module.yaml")
    assert definition["path"] == "/nodes/vm"
    assert definition["composed_path"] == "/nodes/outer.inner.vm"
    assert definition["namespace"] == ["outer", "inner"]


def test_imported_semantic_diagnostics_identify_the_fragment_and_composed_declaration(tmp_path: Path) -> None:
    module = {**_MODULE, "relationships": {"link": {"type": "connects_to", "source": "vm", "target": "nodes.missing"}}}
    module["module"] = {**_MODULE["module"], "exports": {**_MODULE["module"]["exports"], "relationships": ["link"]}}
    text, path = _write(tmp_path, _root("first"), module)
    diagnostics = language_diagnostics(text, path=path)["diagnostics"]
    diagnostic = next(item for item in diagnostics if "first.link" in item["message"])
    assert diagnostic["source"] == str(tmp_path / "module.yaml")
    assert diagnostic["path"] == "/relationships/first.link"
    assert diagnostic["original_path"] == "/relationships/link"
    assert diagnostic["canonical_address"] == "relationships.first.link"
    position = diagnostic["range"]["start"]
    assert (
        (tmp_path / "module.yaml")
        .read_text()
        .splitlines()[position["line"] - 1][position["column"] - 1 :]
        .startswith("link:")
    )


def test_a_failed_namespace_collision_does_not_fabricate_an_imported_definition(tmp_path: Path) -> None:
    text, path = _write(tmp_path, _root("first", "first"))
    assert language_diagnostics(text, path=path)["status"] == "invalid"
    assert language_references(text, "nodes.first.vm", path=path)["definitions"] == []
