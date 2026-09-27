"""Exporter ingress, independence, drift and complete publication."""

import hashlib
import json
import shutil

import pytest
from crossing_model_fixtures import ROOT, profile_payload
from implementations.formal.participant_crossing import abstract, concrete, export


def workspace(tmp_path):
    for name in export.SOURCE_PATHS:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    payload = profile_payload()
    for carrier in (payload["parameters"]["left"], payload["parameters"]["right"]):
        carrier["source_digest"] = (
            "sha256:" + hashlib.sha256((tmp_path / carrier["source_path"]).read_bytes()).hexdigest()
        )
    for source in payload["source_refs"]:
        source["source_digest"] = "sha256:" + hashlib.sha256((tmp_path / source["source_ref"]).read_bytes()).hexdigest()
    path = tmp_path / export.PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return tmp_path


def test_export_readback_and_counts(tmp_path):
    root = workspace(tmp_path)
    bundle = export.build_bundle(root)
    manifest = json.loads(bundle["manifest.json"])
    for name, module in (("abstract", abstract), ("concrete", concrete)):
        initial, states, edges = export.parse_aut(bundle[f"{name}.aut"])
        graph = module.build()
        assert initial == 0
        assert states == len(graph.states)
        assert len(edges) == len(graph.edges)
        assert manifest["models"][name]["states"] == states
        assert manifest["models"][name]["transitions"] == len(edges)
        assert manifest["models"][name]["initial_states"] == 1
        assert (
            manifest["artifact_digests"][f"{name}.aut"] == "sha256:" + hashlib.sha256(bundle[f"{name}.aut"]).hexdigest()
        )
        state_map = json.loads(bundle[f"{name}.json"])
        assert len(state_map["states"]) == states
        assert len(state_map["semantic_edges"]) == len(edges)
    assert manifest["domain_counts"]["input_class"] == 5
    assert manifest["domain_counts"]["history_head"] == 4
    assert manifest["equivalence_result"] == "not-established"
    assert export.build_bundle(root) == bundle
    export.publish(root)
    export.check(root)
    export.publish(root)  # identical publication is idempotent


@pytest.mark.parametrize("drift", ["source", "profile", "artifact", "counts"])
def test_drift_fails_without_replacing_published_bundle(tmp_path, drift):
    root = workspace(tmp_path)
    export.publish(root)
    output = root / export.OUTPUT_PATH
    if drift == "source":
        path = root / "implementations/formal/participant_crossing/abstract.py"
        path.write_bytes(path.read_bytes() + b"\n# source drift\n")
    elif drift == "profile":
        path = root / export.PROFILE_PATH
        data = json.loads(path.read_bytes())
        data["limitations"] = ["Changed interpretation"]
        path.write_text(json.dumps(data))
    elif drift == "artifact":
        (output / "abstract.aut").write_bytes(b"des (0, 0, 1)\n")
    else:
        data = json.loads((output / "manifest.json").read_bytes())
        data["models"]["abstract"]["states"] = 1
        (output / "manifest.json").write_text(json.dumps(data))
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(ValueError, match="drift"):
        export.check(root)
    with pytest.raises(ValueError, match="drift"):
        export.publish(root)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_shared_transition_authority_is_rejected(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    monkeypatch.setattr(concrete, "successors", abstract.successors)
    with pytest.raises(ValueError, match="independent"):
        export.build_bundle(root)


def test_rebound_source_cannot_describe_different_executing_code(tmp_path):
    root = workspace(tmp_path)
    path = root / "implementations/formal/participant_crossing/abstract.py"
    path.write_bytes(path.read_bytes() + b"\n# different source identity\n")
    profile_path = root / export.PROFILE_PATH
    payload = json.loads(profile_path.read_bytes())
    payload["parameters"]["left"]["source_digest"] = export.digest(path.read_bytes())
    for source in payload["source_refs"]:
        if source["source_ref"] == path.relative_to(root).as_posix():
            source["source_digest"] = export.digest(path.read_bytes())
    profile_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="executing source"):
        export.publish(root)
    assert not (root / export.OUTPUT_PATH).exists()


@pytest.mark.parametrize(
    "value",
    [
        b'des (0, 1, 1)\n(0,"tau",0)\n',
        b"des (0, 0, 0)\n",
        b'des (0, 1, 1)\n(0,"crossing.request",1)\n',
        b'des (0, 2, 1)\n(0,"crossing.request",0)\n(0,"crossing.request",0)\n',
    ],
)
def test_invalid_aut_is_rejected(value):
    with pytest.raises(ValueError):
        export.parse_aut(value)


def test_failed_generation_publishes_nothing(tmp_path, monkeypatch):
    root = workspace(tmp_path)

    def exhausted():
        raise ValueError("resource limit exceeded")

    monkeypatch.setattr(concrete, "build", exhausted)
    with pytest.raises(ValueError):
        export.publish(root)
    assert not (root / export.OUTPUT_PATH).exists()


def test_truncated_graph_is_rejected(tmp_path, monkeypatch):
    from dataclasses import replace

    root = workspace(tmp_path)
    graph = abstract.build()
    monkeypatch.setattr(abstract, "build", lambda: replace(graph, edges=graph.edges[:-1]))
    with pytest.raises(ValueError, match="closure"):
        export.publish(root)
    assert not (root / export.OUTPUT_PATH).exists()


def test_symlink_input_and_output_are_rejected(tmp_path):
    root = workspace(tmp_path / "root")
    path = root / export.PROFILE_PATH
    path.unlink()
    path.symlink_to(tmp_path / "unread-target")
    with pytest.raises(ValueError):
        export.build_bundle(root)


def test_published_repository_bundle_matches_sources():
    export.check(ROOT)


def test_symlink_output_cannot_publish_outside_root(tmp_path):
    root = workspace(tmp_path / "root")
    outside = tmp_path / "outside"
    outside.mkdir()
    target = root / export.OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        export.publish(root)
    assert list(outside.iterdir()) == []


def test_cli_failure_does_not_echo_rejected_values(monkeypatch, capsys):
    from implementations.formal.participant_crossing import __main__

    def fail(_root):
        raise ValueError("synthetic-private-value")

    monkeypatch.setattr(export, "check", fail)
    assert __main__.main([]) == 1
    assert capsys.readouterr().err == "participant-crossing model export failed validation\n"
