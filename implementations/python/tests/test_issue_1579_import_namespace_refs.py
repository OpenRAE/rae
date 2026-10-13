"""ACL networks and detection-definition references under an import namespace (issue #1579).

ADR-053 requires composition to rewrite every SDL reference surface that can
point at imported symbols. An infrastructure ACL's ``from_net``/``to_net`` name
an infrastructure key (``specs/sdl/references.md`` section 6), and a
security-monitoring detection definition's ``source_artifact_ref`` and
``target_refs`` resolve through the generic named-reference index (ADR-045).
A module that is valid alone must stay valid when imported once or twice, and
each copy must bind its own namespace's declarations, never a same-named root
declaration. Values that name no module declaration keep today's resolution
and diagnostics.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from raes import (
    RenameSDLDeclarationRequest,
    SDLValidationError,
    build_declaration_index,
    parse_sdl,
    parse_sdl_file,
    rename_sdl_declaration,
)
from raes_contracts.contracts import ArtifactTransformationStatus
from raes_processor.compiler import compile_runtime_model

_RULES = "runtime.security_monitoring_managers.siem.content_sets.rules"
_EXPORTED = "{nodes: [lan, app], infrastructure: [lan]}"
_ROOT_SHARES_NAMES = """\
nodes:
  lan: {type: switch}
  app: {type: compute}
infrastructure:
  lan: {count: 1, properties: {cidr: 10.9.0.0/24, gateway: 10.9.0.1}}
"""
_ROOT_EDGE = """\
nodes:
  edge: {type: switch}
infrastructure:
  edge: {count: 1, properties: {cidr: 10.8.0.0/24, gateway: 10.8.0.1}}
"""


def _segment(
    *,
    exports: str | None = _EXPORTED,
    from_net: str = "lan",
    source_artifact: str = "nodes.app",
    targets: str = f"[nodes.app, nodes.app.{_RULES}]",
) -> str:
    descriptor = (
        f"module: {{id: acme/monitored-segment, version: 1.0.0, exports: {exports}}}\n" if exports is not None else ""
    )
    return f"name: monitored-segment\nversion: 1.0.0\n{descriptor}" + textwrap.dedent(
        f"""\
        nodes:
          lan: {{type: switch}}
          app:
            type: compute
            runtime:
              security_monitoring_managers:
                - security_monitoring_manager_id: siem
                  manager_kind: siem
                  content_sets:
                    - {{content_id: rules, kind: rule-corpus}}
                  detection_definitions:
                    - {{definition_id: d1, source_artifact_ref: {source_artifact}, target_refs: {targets}}}
                    - {{definition_id: d2, target_refs: nodes.app}}
        infrastructure:
          lan:
            count: 1
            properties: {{cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
            acls:
              - {{name: a1, direction: in, from_net: {from_net}, to_net: lan, action: allow}}
        """
    )


def _compose(tmp_path: Path, module: str, namespaces: tuple[str, ...], root_body: str = "") -> Path:
    (tmp_path / "segment.yaml").write_text(module, encoding="utf-8")
    imports = "".join(f"  - {{source: local:segment.yaml, namespace: {name}, version: 1.0.0}}\n" for name in namespaces)
    root = tmp_path / "root.yaml"
    root.write_text(f"name: root\n{root_body}imports:\n{imports}", encoding="utf-8")
    return root


def _copy_refs(scenario: object, local: str) -> tuple[object, ...]:
    acl = scenario.infrastructure[f"{local}lan"].acls[0]
    definitions = scenario.nodes[f"{local}app"].runtime.security_monitoring_managers[0].detection_definitions
    return (
        acl.from_net,
        acl.to_net,
        definitions[0].source_artifact_ref,
        definitions[0].target_refs,
        definitions[1].target_refs,
    )


@pytest.mark.parametrize("root_body", ["", _ROOT_SHARES_NAMES], ids=["bare-root", "root-declares-same-names"])
@pytest.mark.parametrize("namespaces", [("first",), ("first", "second")], ids=["imported-once", "imported-twice"])
@pytest.mark.parametrize(("exports", "private"), [(_EXPORTED, ""), ("{}", "__private.")], ids=["exported", "private"])
def test_each_imported_copy_binds_its_own_declarations(
    tmp_path: Path, root_body: str, namespaces: tuple[str, ...], exports: str, private: str
) -> None:
    module = _segment(exports=exports)
    parse_sdl(module)

    scenario = parse_sdl_file(_compose(tmp_path, module, namespaces, root_body))

    addresses = build_declaration_index(scenario).addresses
    for namespace in namespaces:
        local = f"{namespace}.{private}"
        network, node = f"{local}lan", f"nodes.{local}app"
        assert _copy_refs(scenario, local) == (network, network, node, [node, f"{node}.{_RULES}"], [node])
        assert {f"infrastructure.{network}", node, f"{node}.{_RULES}"} <= addresses
    if root_body:
        assert scenario.infrastructure["lan"].acls == []
        assert scenario.nodes["app"].runtime is None


def test_compiled_copies_carry_their_own_bindings(tmp_path: Path) -> None:
    namespaces = ("first", "second")
    model = compile_runtime_model(parse_sdl_file(_compose(tmp_path, _segment(), namespaces)))

    compiled = {}
    for namespace in namespaces:
        acl = model.networks[f"provision.network.{namespace}.lan"].spec["infrastructure"]["acls"][0]
        runtime = model.node_deployments[f"provision.node.{namespace}.app"].spec["node"]["runtime"]
        definition = runtime["security_monitoring_managers"][0]["detection_definitions"][0]
        assert f"provision.network.{acl['from_net']}" in model.networks
        compiled[namespace] = (
            acl["from_net"],
            acl["to_net"],
            definition["source_artifact_ref"],
            definition["target_refs"],
        )
    assert compiled == {
        name: (f"{name}.lan", f"{name}.lan", f"nodes.{name}.app", [f"nodes.{name}.app", f"nodes.{name}.app.{_RULES}"])
        for name in namespaces
    }


def test_rename_updates_detection_definition_references() -> None:
    scenario = parse_sdl(_segment(exports=None, targets="[nodes.app]"))

    result = rename_sdl_declaration(
        scenario, RenameSDLDeclarationRequest(target_address="nodes.app", new_local_name="web")
    )

    assert result.report.status == ArtifactTransformationStatus.SUCCESS, result.report.checks
    definitions = result.output.nodes["web"].runtime.security_monitoring_managers[0].detection_definitions
    assert [(item.source_artifact_ref, item.target_refs) for item in definitions] == [
        ("nodes.web", ["nodes.web"]),
        ("", ["nodes.web"]),
    ]


def test_cross_fragment_network_resolves_against_the_root(tmp_path: Path) -> None:
    root = _compose(tmp_path, _segment(from_net="edge"), ("first",), _ROOT_EDGE)

    acl = parse_sdl_file(root).infrastructure["first.lan"].acls[0]

    assert (acl.from_net, acl.to_net) == ("edge", "first.lan")


def test_values_naming_no_module_declaration_keep_todays_diagnostics(tmp_path: Path) -> None:
    root = _compose(tmp_path, _segment(from_net="ghost", source_artifact="nodes.ghost"), ("first",))

    with pytest.raises(SDLValidationError) as raised:
        parse_sdl_file(root)

    assert "Infrastructure 'first.lan' ACL references undefined network 'ghost'" in raised.value.errors
    assert (
        "Node 'first.app' runtime security-monitoring manager 'siem' detection_definition 'd1' "
        "source_artifact_ref 'nodes.ghost' does not reference any defined element"
    ) in raised.value.errors
    expanded = _copy_refs(parse_sdl_file(root, skip_semantic_validation=True), "first.")
    assert (expanded[0], expanded[2]) == ("ghost", "nodes.ghost")
