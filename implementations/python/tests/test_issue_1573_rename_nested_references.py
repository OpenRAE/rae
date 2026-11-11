"""Issue #1573: a declaration rename moves its nested service, runtime and content-item references."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from raes import (
    RenameSDLDeclarationRequest,
    build_declaration_index,
    canonical_sdl_bytes,
    parse_sdl,
    parse_sdl_file,
    rename_sdl_declaration,
)
from raes_contracts.contracts import ArtifactTransformationStatus, PreservationOutcome

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = (
    REPO_ROOT / "contracts" / "fixtures" / "artifact-transformations-v1" / "sources" / "nested-references.sdl.yaml"
)
MODULE_EXPORTS = {
    "nodes": ["lan", "web"],
    "content": ["bundle"],
    "entities": ["red-team"],
    "agents": ["red-agent"],
    "action_contracts": ["probe"],
    "behavior_specifications": ["probe-behavior"],
}
RENAMES = {
    "node": (
        "nodes.web",
        "frontend",
        {
            "nodes.web.services.http": "nodes.frontend.services.http",
            "nodes.web.runtime.service_listeners.telemetry": "nodes.frontend.runtime.service_listeners.telemetry",
        },
    ),
    "content": (
        "content.bundle",
        "kit",
        {"content.bundle.items.report": "content.kit.items.report"},
    ),
}


def _source_payload() -> dict:
    return yaml.safe_load(SOURCE_PATH.read_text(encoding="utf-8"))


def _write_module(directory: Path) -> None:
    module = _source_payload()
    module["version"] = "1.0.0"
    module["module"] = {"id": "raes/issue-1573", "version": "1.0.0", "exports": MODULE_EXPORTS}
    (directory / "module.yaml").write_text(yaml.safe_dump(module, sort_keys=False), encoding="utf-8")


def _composed_source(directory: Path, root_nodes: dict | None = None):
    _write_module(directory)
    root = {"name": "issue-1573-root", "imports": [{"path": "module.yaml", "namespace": "shared", "version": "1.0.0"}]}
    if root_nodes:
        root["nodes"] = root_nodes
    root_path = directory / "root.yaml"
    root_path.write_text(yaml.safe_dump(root, sort_keys=False), encoding="utf-8")
    return parse_sdl_file(root_path)


def _qualify(address: str, namespace: str) -> str:
    if not namespace:
        return address
    section, rest = address.split(".", 1)
    return f"{section}.{namespace}.{rest}"


def _rename(scenario, target_address: str, new_local_name: str):
    return rename_sdl_declaration(
        scenario,
        RenameSDLDeclarationRequest(target_address=target_address, new_local_name=new_local_name),
    )


def _only(mapping):
    (value,) = mapping.values()
    return value


@pytest.mark.parametrize("namespace", ["", "shared"], ids=["authored", "composed"])
@pytest.mark.parametrize("rename", RENAMES.values(), ids=RENAMES.keys())
def test_rename_moves_nested_references_to_the_renamed_declaration(
    tmp_path: Path,
    namespace: str,
    rename: tuple[str, str, dict[str, str]],
) -> None:
    target_address, new_local_name, authored_moves = rename
    source = _composed_source(tmp_path) if namespace else parse_sdl_file(SOURCE_PATH)
    moves = {_qualify(before, namespace): _qualify(after, namespace) for before, after in authored_moves.items()}
    source_refs = _only(source.behavior_specifications).authority_scope_refs
    source_scope = _only(source.agents).operating_scope

    result = _rename(source, _qualify(target_address, namespace), new_local_name)

    assert result.report.status == ArtifactTransformationStatus.SUCCESS
    assert result.report.preservation.outcome == PreservationOutcome.VERIFIED
    assert result.output is not None
    assert _only(result.output.behavior_specifications).authority_scope_refs == [
        moves.get(ref, ref) for ref in source_refs
    ]
    assert _only(result.output.agents).operating_scope == [moves.get(ref, ref) for ref in source_scope]
    source_index = build_declaration_index(source)
    target_index = build_declaration_index(result.output)
    for before, after in moves.items():
        source_declaration = source_index.declaration_for(before)
        target_declaration = target_index.declaration_for(after)
        assert source_declaration is not None
        assert target_declaration is not None
        assert target_declaration.kind == source_declaration.kind
        assert target_index.declaration_for(before) is None


def test_rename_leaves_nested_references_under_a_namespaced_sibling(tmp_path: Path) -> None:
    root_node = {"type": "compute", "resources": {"ram": "1 GiB", "cpu": 1}, "services": [{"port": 22, "name": "ssh"}]}
    source = _composed_source(tmp_path, root_nodes={"shared": root_node})
    source_refs = _only(source.behavior_specifications).authority_scope_refs

    result = _rename(source, "nodes.shared", "hub")

    assert result.report.status == ArtifactTransformationStatus.SUCCESS
    assert result.output is not None
    assert set(result.output.nodes) == {"hub", "shared.lan", "shared.web"}
    assert _only(result.output.behavior_specifications).authority_scope_refs == source_refs
    assert "nodes.shared.web.services.http" in source_refs


@settings(max_examples=12, deadline=None)
@given(
    rename=st.sampled_from(list(RENAMES.values())),
    node_order=st.permutations(["lan", "web"]),
    section_order=st.permutations(["nodes", "content", "agents", "behavior_specifications"]),
)
def test_rename_is_order_independent_and_inverted_by_the_reverse_rename(
    rename: tuple[str, str, dict[str, str]],
    node_order: list[str],
    section_order: list[str],
) -> None:
    target_address, new_local_name, _ = rename
    baseline = parse_sdl_file(SOURCE_PATH)
    payload = _source_payload()
    payload["nodes"] = {name: payload["nodes"][name] for name in node_order}
    payload = {key: payload[key] for key in ["name", *section_order]} | payload
    permuted = parse_sdl(yaml.safe_dump(payload, sort_keys=False))

    expected = _rename(baseline, target_address, new_local_name)
    result = _rename(permuted, target_address, new_local_name)

    assert result.output is not None
    assert result.report.target_digest == expected.report.target_digest
    section, old_local_name = target_address.split(".", 1)
    restored = _rename(result.output, f"{section}.{new_local_name}", old_local_name)
    assert restored.output is not None
    assert canonical_sdl_bytes(restored.output) == canonical_sdl_bytes(permuted)
