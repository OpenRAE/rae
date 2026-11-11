"""Complete, source-bound offline export and fail-closed publication."""

import importlib
import json
import shutil
from pathlib import Path

import pytest
from raes_contracts.errors import InvalidInputError

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
    export.check(root)


def test_shared_semantic_authority_and_truncation_are_refused(tmp_path, monkeypatch):
    from dataclasses import replace

    from implementations.formal.participant_crossing import multi_abstract, multi_concrete

    export = producer()
    root = workspace(tmp_path)
    original = multi_concrete.successors
    monkeypatch.setattr(multi_concrete, "successors", multi_abstract.successors)
    with pytest.raises(InvalidInputError, match="independent"):
        export.build_bundle(root)
    monkeypatch.setattr(multi_concrete, "successors", original)
    graph = multi_abstract.build()
    monkeypatch.setattr(multi_abstract, "build", lambda: replace(graph, edges=graph.edges[:-1]))
    with pytest.raises(InvalidInputError, match="closure"):
        export.build_bundle(root)


def test_unsafe_profile_and_output_are_rejected(tmp_path):
    export = producer()
    root = workspace(tmp_path / "root")
    profile = root / export.PROFILE_PATH
    profile.unlink()
    profile.symlink_to(tmp_path / "unread")
    with pytest.raises(InvalidInputError):
        export.build_bundle(root)


def test_multi_profile_of_another_parameter_kind_is_an_input_refusal(tmp_path):
    export = producer()
    root = workspace(tmp_path)
    single = ROOT / "contracts/profiles/behavioral-relation/participant-crossing-dpbb-finite-v1.json"
    shutil.copyfile(single, root / export.PROFILE_PATH)
    with pytest.raises(InvalidInputError, match="expected exact multi-operation profile"):
        export.build_bundle(root)
