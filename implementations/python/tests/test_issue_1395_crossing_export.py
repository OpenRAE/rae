"""Complete, source-bound offline export and fail-closed publication."""

import importlib
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def producer():
    return importlib.import_module("implementations.formal.participant_crossing.multi_export")


def workspace(tmp_path):
    export = producer()
    for name in (*export.SOURCE_PATHS, export.PROFILE_PATH):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    return tmp_path


def test_complete_bundle_is_deterministic_and_readable(tmp_path):
    export = producer()
    root = workspace(tmp_path)
    bundle = export.build_bundle(root)
    manifest = json.loads(bundle["manifest.json"])
    assert manifest["complete_reachable_fixed_point"] is True
    assert manifest["equivalence_result"] == manifest["runtime_realization"] == "not-established"
    for name in ("abstract", "concrete"):
        count = manifest["models"][name]
        assert count["initial_states"] == 1
        aut = b"".join(bundle[path] for path in count["aut_parts"])
        assert export.digest(aut) == count["aut_digest"]
        assert len(aut) == count["aut_bytes"]
        assert all(len(content) < 500 * 1024 for content in bundle.values())
        states = []
        ledgers = json.loads(bundle[count["ledger_map"]])["entries"]
        for chunk in count["state_maps"]:
            page = json.loads(bundle[chunk])
            assert page["first_ordinal"] == len(states)
            for row in page["states"]:
                state = dict(zip(page["columns"], row, strict=True))
                state["ledger"] = ledgers[state["ledger"]]
                states.append(state)
        assert len(states) == count["states"]
        assert count["states"] > 178
        assert all(len(state["ledger"]) <= 2 for state in states)
    assert export.build_bundle(root) == bundle
    export.publish(root)
    export.check(root)
    export.publish(root)


@pytest.mark.parametrize(
    "path",
    [
        "implementations/formal/participant_crossing/multi_abstract.py",
        "implementations/python/packages/raes_runtime/control_plane_store.py",
        "contracts/schemas/profiles/behavioral-relation-profile-v1.json",
    ],
)
def test_source_and_contract_drift_never_relabels_evidence(tmp_path, path):
    export = producer()
    root = workspace(tmp_path)
    export.publish(root)
    target = root / path
    target.write_bytes(target.read_bytes() + b"\n")
    before = (root / export.OUTPUT_PATH / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="drift"):
        export.check(root)
    with pytest.raises(ValueError, match="drift"):
        export.publish(root)
    assert (root / export.OUTPUT_PATH / "manifest.json").read_bytes() == before


def test_shared_semantic_authority_and_truncation_publish_nothing(tmp_path, monkeypatch):
    from dataclasses import replace

    from implementations.formal.participant_crossing import multi_abstract, multi_concrete

    export = producer()
    root = workspace(tmp_path)
    original = multi_concrete.successors
    monkeypatch.setattr(multi_concrete, "successors", multi_abstract.successors)
    with pytest.raises(ValueError, match="independent"):
        export.publish(root)
    assert not (root / export.OUTPUT_PATH).exists()
    monkeypatch.setattr(multi_concrete, "successors", original)
    graph = multi_abstract.build()
    monkeypatch.setattr(multi_abstract, "build", lambda: replace(graph, edges=graph.edges[:-1]))
    with pytest.raises(ValueError, match="closure"):
        export.publish(root)
    assert not (root / export.OUTPUT_PATH).exists()


def test_unsafe_profile_and_output_are_rejected(tmp_path):
    export = producer()
    root = workspace(tmp_path / "root")
    profile = root / export.PROFILE_PATH
    profile.unlink()
    profile.symlink_to(tmp_path / "unread")
    with pytest.raises(ValueError):
        export.build_bundle(root)


def test_published_multi_bundle_retains_exact_graphs_and_reports_source_drift():
    # Runtime supervision evolves source anchors without relabeling the
    # independently constructed historical model or claiming realization.
    export = producer()
    retained = ROOT / export.OUTPUT_PATH
    manifest = json.loads((retained / "manifest.json").read_bytes())
    current = export.build_bundle(ROOT)
    for name, expected in manifest["artifact_digests"].items():
        content = (retained / name).read_bytes()
        assert export.digest(content) == expected
        assert current[name] == content
    derived = json.loads(current["manifest.json"])
    assert derived["source_digests"] != manifest["source_digests"]
    for key in manifest.keys() - {"source_revision", "source_digests"}:
        assert derived[key] == manifest[key]
    with pytest.raises(ValueError, match="drift"):
        export.check(ROOT)
