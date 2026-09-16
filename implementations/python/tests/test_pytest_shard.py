"""Tests for the deterministic CI shard partition, manifests, and reducer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools import pytest_shard_plugin
from tools.pytest_shard import (
    MAX_SHARD_COUNT,
    SHARD_ALGORITHM_VERSION,
    ShardConfigurationError,
    ShardManifest,
    ShardManifestError,
    owned_nodeids,
    read_manifest,
    shard_for_nodeid,
    validate_shard_count,
    validate_shard_index,
    verify_shard_partition,
    write_manifest,
)

_SUITE = [f"tests/test_module_{index % 7}.py::test_case_{index}" for index in range(400)]
_PARAMETRIZED = [f"tests/test_p.py::test_x[{value}-{value * 2}]" for value in range(50)]


def _manifests(nodeids: list[str], shard_count: int, *, source_sha: str = "abc") -> list[ShardManifest]:
    return [
        ShardManifest(
            algorithm_version=SHARD_ALGORITHM_VERSION,
            source_sha=source_sha,
            suite_expression="not fuzz and not integration and not docker",
            shard_count=shard_count,
            shard_index=index,
            node_ids=tuple(owned_nodeids(nodeids, shard_count, index)),
        )
        for index in range(shard_count)
    ]


def test_partition_is_stable_and_within_bounds() -> None:
    for nodeid in _SUITE:
        first = shard_for_nodeid(nodeid, 4)
        assert first == shard_for_nodeid(nodeid, 4)
        assert 0 <= first < 4


def test_partition_is_independent_of_input_order() -> None:
    forward = {index: set(owned_nodeids(_SUITE, 8, index)) for index in range(8)}
    reversed_suite = list(reversed(_SUITE))
    backward = {index: set(owned_nodeids(reversed_suite, 8, index)) for index in range(8)}
    assert forward == backward


def test_partition_covers_every_node_exactly_once() -> None:
    buckets = [set(owned_nodeids(_SUITE, 5, index)) for index in range(5)]
    union: set[str] = set()
    for bucket in buckets:
        assert not (union & bucket)
        union |= bucket
    assert union == set(_SUITE)


def test_changing_shard_count_reassigns_without_a_table() -> None:
    four = {nodeid: shard_for_nodeid(nodeid, 4) for nodeid in _SUITE}
    six = {nodeid: shard_for_nodeid(nodeid, 6) for nodeid in _SUITE}
    assert set(four.values()) <= set(range(4))
    assert set(six.values()) <= set(range(6))
    # A different modulus must actually move some ownership.
    assert four != six


def test_parametrized_node_ids_partition_and_verify() -> None:
    manifests = _manifests(_PARAMETRIZED, 3)
    verify_shard_partition(manifests, _PARAMETRIZED, shard_count=3, source_sha="abc")


@pytest.mark.parametrize("bad", [0, -1, MAX_SHARD_COUNT + 1, True, 2.0, "4"])
def test_validate_shard_count_rejects_out_of_bounds(bad: object) -> None:
    with pytest.raises(ShardConfigurationError):
        validate_shard_count(bad)


@pytest.mark.parametrize("bad_index", [-1, 4, True, 1.0])
def test_validate_shard_index_rejects_out_of_bounds(bad_index: object) -> None:
    with pytest.raises(ShardConfigurationError):
        validate_shard_index(bad_index, 4)


def test_shard_for_nodeid_rejects_empty_nodeid() -> None:
    with pytest.raises(ShardConfigurationError):
        shard_for_nodeid("", 4)


def test_manifest_round_trips_through_disk(tmp_path: Path) -> None:
    manifest = _manifests(_SUITE, 4)[2]
    path = tmp_path / "shard-2.json"
    write_manifest(path, manifest)
    assert read_manifest(path) == manifest


def test_read_manifest_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ShardManifestError):
        read_manifest(path)


def test_manifest_from_dict_requires_fields() -> None:
    with pytest.raises(ShardManifestError):
        ShardManifest.from_dict({"shard_index": 0})
    with pytest.raises(ShardManifestError):
        ShardManifest.from_dict("not a mapping")


def test_verify_accepts_a_complete_disjoint_partition() -> None:
    verify_shard_partition(_manifests(_SUITE, 4), _SUITE, shard_count=4, source_sha="abc")


def test_verify_rejects_missing_shard_index() -> None:
    manifests = _manifests(_SUITE, 4)[:-1]
    with pytest.raises(ShardManifestError, match="complete set"):
        verify_shard_partition(manifests, _SUITE, shard_count=4)


def test_verify_rejects_duplicate_shard_index() -> None:
    manifests = _manifests(_SUITE, 4)
    manifests.append(manifests[0])
    with pytest.raises(ShardManifestError, match="complete set"):
        verify_shard_partition(manifests, _SUITE, shard_count=4)


def test_verify_rejects_overlapping_shards() -> None:
    manifests = _manifests(_SUITE, 4)
    stolen = manifests[1].node_ids[0]
    manifests[0] = ShardManifest(
        algorithm_version=manifests[0].algorithm_version,
        source_sha=manifests[0].source_sha,
        suite_expression=manifests[0].suite_expression,
        shard_count=4,
        shard_index=0,
        node_ids=(*manifests[0].node_ids, stolen),
    )
    with pytest.raises(ShardManifestError, match="overlaps|does not own"):
        verify_shard_partition(manifests, _SUITE, shard_count=4)


def test_verify_rejects_misowned_node() -> None:
    manifests = _manifests(_SUITE, 4)
    foreign = next(nodeid for nodeid in _SUITE if shard_for_nodeid(nodeid, 4) != 0)
    manifests[0] = ShardManifest(
        algorithm_version=manifests[0].algorithm_version,
        source_sha=manifests[0].source_sha,
        suite_expression=manifests[0].suite_expression,
        shard_count=4,
        shard_index=0,
        node_ids=(foreign,),
    )
    with pytest.raises(ShardManifestError):
        verify_shard_partition(manifests, _SUITE, shard_count=4)


def test_verify_rejects_union_missing_a_test() -> None:
    manifests = _manifests(_SUITE, 4)
    with pytest.raises(ShardManifestError, match="missing"):
        verify_shard_partition(manifests, [*_SUITE, "tests/test_new.py::test_added"], shard_count=4)


def test_verify_rejects_duplicate_canonical_ids() -> None:
    manifests = _manifests(_SUITE, 4)
    with pytest.raises(ShardManifestError, match="duplicate"):
        verify_shard_partition(manifests, [*_SUITE, _SUITE[0]], shard_count=4)


def test_verify_rejects_empty_canonical() -> None:
    with pytest.raises(ShardManifestError, match="empty"):
        verify_shard_partition(_manifests([], 1), [], shard_count=1)


def test_verify_rejects_algorithm_version_drift() -> None:
    manifests = _manifests(_SUITE, 2)
    manifests[0] = ShardManifest(
        algorithm_version="sha256-nodeid-v0",
        source_sha=manifests[0].source_sha,
        suite_expression=manifests[0].suite_expression,
        shard_count=2,
        shard_index=0,
        node_ids=manifests[0].node_ids,
    )
    with pytest.raises(ShardManifestError, match="algorithm"):
        verify_shard_partition(manifests, _SUITE, shard_count=2)


def test_verify_rejects_source_sha_drift() -> None:
    manifests = _manifests(_SUITE, 2, source_sha="abc")
    with pytest.raises(ShardManifestError, match="source"):
        verify_shard_partition(manifests, _SUITE, shard_count=2, source_sha="def")


def test_verify_rejects_shard_count_drift() -> None:
    manifests = _manifests(_SUITE, 2)
    manifests[0] = ShardManifest(
        algorithm_version=manifests[0].algorithm_version,
        source_sha=manifests[0].source_sha,
        suite_expression=manifests[0].suite_expression,
        shard_count=3,
        shard_index=0,
        node_ids=manifests[0].node_ids,
    )
    with pytest.raises(ShardManifestError, match="shard_count"):
        verify_shard_partition(manifests, _SUITE, shard_count=2)


# --- plugin wiring -------------------------------------------------------------


class _StubGroup:
    def __init__(self) -> None:
        self.options: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def addoption(self, *args: object, **kwargs: object) -> None:
        self.options.append((args, kwargs))


class _StubParser:
    def __init__(self) -> None:
        self.group = _StubGroup()

    def getgroup(self, *_args: object, **_kwargs: object) -> _StubGroup:
        return self.group


class _StubHook:
    def __init__(self) -> None:
        self.deselected: list[object] = []

    def pytest_deselected(self, items: list[object]) -> None:
        self.deselected.extend(items)


class _StubItem:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


class _StubConfig:
    def __init__(self, options: dict[str, object], *, worker: bool = False) -> None:
        self._options = options
        self.hook = _StubHook()
        if worker:
            self.workerinput = {"workerid": "gw0"}

    def getoption(self, name: str) -> object:
        return self._options.get(name)


def _shard_options(**overrides: object) -> dict[str, object]:
    options = {
        "raes_shard_count": None,
        "raes_shard_index": None,
        "raes_shard_manifest": None,
        "raes_shard_source_sha": "",
        "raes_shard_suite_expression": "",
    }
    options.update(overrides)
    return options


def test_plugin_registers_every_shard_option() -> None:
    parser = _StubParser()
    pytest_shard_plugin.pytest_addoption(parser)
    dests = {kwargs.get("dest") for _args, kwargs in parser.group.options}
    assert {
        "raes_shard_count",
        "raes_shard_index",
        "raes_shard_manifest",
        "raes_shard_source_sha",
        "raes_shard_suite_expression",
    } <= dests


def test_plugin_is_inert_without_shard_options() -> None:
    config = _StubConfig(_shard_options())
    items = [_StubItem(nodeid) for nodeid in _SUITE]
    original = list(items)
    pytest_shard_plugin.pytest_collection_modifyitems(config, items)
    assert items == original
    assert config.hook.deselected == []


def test_plugin_requires_both_count_and_index() -> None:
    config = _StubConfig(_shard_options(raes_shard_count=4))
    with pytest.raises(pytest.UsageError):
        pytest_shard_plugin.pytest_collection_modifyitems(config, [_StubItem("tests/test_a.py::test_b")])


def test_plugin_selects_owned_and_writes_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "shard-1.json"
    config = _StubConfig(
        _shard_options(
            raes_shard_count=4,
            raes_shard_index=1,
            raes_shard_manifest=str(manifest_path),
            raes_shard_source_sha="deadbeef",
            raes_shard_suite_expression="not fuzz",
        )
    )
    items = [_StubItem(nodeid) for nodeid in _SUITE]
    pytest_shard_plugin.pytest_collection_modifyitems(config, items)

    expected = set(owned_nodeids(_SUITE, 4, 1))
    assert {item.nodeid for item in items} == expected
    assert {item.nodeid for item in config.hook.deselected} == set(_SUITE) - expected

    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert recorded["shard_index"] == 1
    assert recorded["shard_count"] == 4
    assert recorded["source_sha"] == "deadbeef"
    assert set(recorded["node_ids"]) == expected


def test_plugin_writes_complete_manifest_under_xdist_worker(tmp_path: Path) -> None:
    # Regression for the xdist manifest lifecycle: collection runs in each worker
    # (all carry workerinput) over the full suite, so a worker must still write
    # the complete owned manifest. A workerinput guard would suppress it entirely
    # and the required upload would then fail closed.
    manifest_path = tmp_path / "shard-worker.json"
    config = _StubConfig(
        _shard_options(raes_shard_count=2, raes_shard_index=0, raes_shard_manifest=str(manifest_path)),
        worker=True,
    )
    pytest_shard_plugin.pytest_collection_modifyitems(config, [_StubItem(nodeid) for nodeid in _SUITE])
    assert manifest_path.exists()
    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(recorded["node_ids"]) == set(owned_nodeids(_SUITE, 2, 0))
