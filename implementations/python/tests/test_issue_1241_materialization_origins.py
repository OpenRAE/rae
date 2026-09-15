"""Materialization differences preserve native collection identities and order."""

import json

import pytest
from raes import instantiate_scenario, parse_sdl
from test_issue_1241_materialized_sdl import materialization_provenance


def _pair(source, update):
    from copy import deepcopy

    source = instantiate_scenario(parse_sdl(json.dumps({"name": "origins", **source})))
    content = source.model_dump(mode="json", exclude={"instantiation_provenance"})
    changed = deepcopy(content)
    update(changed)
    changed["materialization_provenance"] = materialization_provenance()
    return source, parse_sdl(json.dumps(changed))


def _differences(source, changed):
    from raes_processor.compiler import materialization_differences

    return {
        (item.change, item.field_pointer, item.source_pointer) for item in materialization_differences(source, changed)
    }


def test_new_environment_entry_is_not_an_authored_node_replacement():
    source, changed = _pair(
        {"nodes": {"host": {"type": "compute", "runtime": {"environment": [{"name": "MODE", "value": "authored"}]}}}},
        lambda document: document["nodes"]["host"]["runtime"]["environment"].append(
            {"name": "COLLECTOR", "value": "enabled"}
        ),
    )
    assert _differences(source, changed) == {("added", "/nodes/host/runtime/environment/1", None)}


def test_keyed_environment_reordering_preserves_authored_origins():
    source, changed = _pair(
        {
            "nodes": {
                "host": {
                    "type": "compute",
                    "runtime": {
                        "environment": [
                            {"name": "A", "value": "first"},
                            {"name": "B", "value": "second"},
                        ]
                    },
                }
            }
        },
        lambda document: document["nodes"]["host"]["runtime"]["environment"].reverse(),
    )
    assert not _differences(source, changed)


def test_changed_keyed_member_tracks_both_original_and_materialized_positions():
    def update(document):
        entries = document["nodes"]["host"]["runtime"]["environment"]
        entries.reverse()
        entries[0]["value"] = "changed"

    source, changed = _pair(
        {
            "nodes": {
                "host": {
                    "type": "compute",
                    "runtime": {
                        "environment": [
                            {"name": "A", "value": "first"},
                            {"name": "B", "value": "second"},
                        ]
                    },
                }
            }
        },
        update,
    )
    assert _differences(source, changed) == {
        ("selected", "/nodes/host/runtime/environment/0/value", "/nodes/host/runtime/environment/1/value")
    }


def test_ordered_commands_are_not_treated_as_an_unordered_inventory():
    source, changed = _pair(
        {"nodes": {"host": {"type": "compute", "runtime": {"container": {"command": ["first", "second"]}}}}},
        lambda document: document["nodes"]["host"]["runtime"]["container"]["command"].reverse(),
    )
    assert len(_differences(source, changed)) == 2


@pytest.mark.parametrize("change", ["added", "selected"])
def test_origin_claims_must_exactly_account_for_actual_differences(change):
    from raes_processor.compiler import validate_materialization_origins

    source, changed = _pair({"nodes": {"host": {"type": "compute"}}}, lambda document: None)
    payload = changed.model_dump(mode="json")
    payload["materialization_provenance"]["origins"] = [
        {
            "field_pointer": "/nodes/host",
            "change": change,
            "origin": "backend-realized",
            **({"source_pointer": "/nodes/host"} if change == "selected" else {}),
        }
    ]
    described = parse_sdl(json.dumps(payload))
    with pytest.raises(ValueError, match="origins"):
        validate_materialization_origins(source, described)


def test_replaced_keyed_member_has_distinct_removed_and_added_origins_at_same_index():
    from raes_processor.compiler import materialization_differences, validate_materialization_origins

    source, changed = _pair(
        {"nodes": {"host": {"type": "compute", "runtime": {"environment": [{"name": "OLD", "value": "v"}]}}}},
        lambda document: document["nodes"]["host"]["runtime"]["environment"][0].update(name="NEW"),
    )
    payload = changed.model_dump(mode="json")
    payload["materialization_provenance"]["origins"] = [
        item.model_dump(mode="json") for item in materialization_differences(source, changed)
    ]
    admitted = parse_sdl(json.dumps(payload))
    validate_materialization_origins(source, admitted)
    assert {item.change for item in admitted.materialization_provenance.origins} == {"added", "removed"}


def test_login_wrapper_and_rewritten_rule_corpus_have_their_own_origins():
    def update(document):
        runtime = document["nodes"]["host"]["runtime"]
        runtime["ssh_servers"][0]["forced_command"]["command"] = "/usr/local/bin/session-wrapper"
        runtime["filesystem_inventory"][0]["content_digest"] = "b" * 64

    source, changed = _pair(
        {
            "nodes": {
                "host": {
                    "type": "compute",
                    "services": [{"name": "ssh", "port": 22}],
                    "runtime": {
                        "ssh_servers": [
                            {
                                "ssh_server_id": "login",
                                "service": "ssh",
                                "forced_command": {
                                    "command_kind": "absolute_path",
                                    "command": "/bin/sh",
                                },
                            }
                        ],
                        "filesystem_inventory": [
                            {
                                "path": "/etc/sensor/rules",
                                "entry_type": "file",
                                "digest_algorithm": "sha256",
                                "content_digest": "a" * 64,
                            }
                        ],
                    },
                }
            }
        },
        update,
    )
    assert _differences(source, changed) == {
        (
            "selected",
            "/nodes/host/runtime/ssh_servers/0/forced_command/command",
            "/nodes/host/runtime/ssh_servers/0/forced_command/command",
        ),
        (
            "selected",
            "/nodes/host/runtime/filesystem_inventory/0/content_digest",
            "/nodes/host/runtime/filesystem_inventory/0/content_digest",
        ),
    }


def test_imported_source_identity_survives_realization_diff(tmp_path):
    from raes import parse_sdl_file

    (tmp_path / "module.sdl").write_text(
        "name: imported\nversion: 1.0.0\nmodule:\n  id: example/imported\n  version: 1.0.0\n  exports: {nodes: [host]}\nnodes:\n  host: {type: compute}\n",
        encoding="utf-8",
    )
    root = tmp_path / "root.sdl"
    root.write_text("name: root\nimports:\n  - {source: local:module.sdl, namespace: lab}\n", encoding="utf-8")
    source = instantiate_scenario(parse_sdl_file(root))
    content = source.model_dump(mode="json", exclude={"instantiation_provenance"})
    content["nodes"]["lab.host"]["services"] = [{"name": "metrics", "port": 9090}]
    content["materialization_provenance"] = materialization_provenance()
    changed = parse_sdl(json.dumps(content))
    assert _differences(source, changed) == {("added", "/nodes/lab.host/services/0", None)}
    assert source.instantiation_provenance.imports[0].namespace == ("lab",)
