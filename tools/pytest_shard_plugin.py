"""Pytest plugin that restricts collection to one deterministic CI shard.

Loaded only by the ``verify-shard`` nox session via ``-p tools.pytest_shard_plugin``.
It is inert unless both ``--shard-count`` and ``--shard-index`` are supplied, so a
normal local ``pytest`` / ``nox -s verify`` run is unaffected. The partition
itself lives in :mod:`tools.pytest_shard`; this module is the thin pytest wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.pytest_shard import (
    SHARD_ALGORITHM_VERSION,
    ShardManifest,
    shard_for_nodeid,
    validate_shard_index,
    write_manifest,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("raes-shard", "deterministic CI test sharding")
    group.addoption("--shard-count", action="store", type=int, default=None, dest="raes_shard_count")
    group.addoption("--shard-index", action="store", type=int, default=None, dest="raes_shard_index")
    group.addoption("--shard-manifest", action="store", default=None, dest="raes_shard_manifest")
    group.addoption("--shard-source-sha", action="store", default="", dest="raes_shard_source_sha")
    group.addoption("--shard-suite-expression", action="store", default="", dest="raes_shard_suite_expression")


def _record_manifest(config: pytest.Config, index: int, count: int, owned: list[pytest.Item]) -> None:
    # Record ownership. This hook runs during collection, which under xdist happens
    # in each worker (all of which carry ``workerinput``) over the FULL suite before
    # execution is distributed, so every context computes the identical complete
    # owned set. Write it atomically rather than guarding on ``workerinput`` —
    # guarding on the controller would suppress the write entirely under xdist and
    # leave the required manifest absent.
    manifest_path = config.getoption("raes_shard_manifest")
    if not manifest_path:
        return
    manifest = ShardManifest(
        algorithm_version=SHARD_ALGORITHM_VERSION,
        source_sha=str(config.getoption("raes_shard_source_sha") or ""),
        suite_expression=str(config.getoption("raes_shard_suite_expression") or ""),
        shard_count=count,
        shard_index=index,
        node_ids=tuple(item.nodeid for item in owned),
    )
    write_manifest(Path(manifest_path), manifest)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # trylast so the incumbent marker expression (`-m 'not fuzz and not
    # integration and not docker'`) has already deselected its items: the shard
    # partitions the default suite, and the manifest must match the reducer's
    # fresh default-suite collection exactly.
    shard_count = config.getoption("raes_shard_count")
    shard_index = config.getoption("raes_shard_index")
    if shard_count is None and shard_index is None:
        return
    if shard_count is None or shard_index is None:
        raise pytest.UsageError("--shard-count and --shard-index must be supplied together")
    index, count = validate_shard_index(shard_index, shard_count)

    owned: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        (owned if shard_for_nodeid(item.nodeid, count) == index else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = owned

    _record_manifest(config, index, count, owned)
