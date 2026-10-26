"""SEM-218 realization provenance recorded by RuntimeManager.apply on the stub target."""

from __future__ import annotations

import textwrap

from raes import parse_sdl
from raes.explicitness import ExplicitnessClass
from raes_backend_stubs.stubs import create_stub_target
from raes_runtime.manager import RuntimeManager

_EXACT_SCENARIO = """
name: stub-sem-218
nodes:
  web:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
"""


def test_apply_records_realization_provenance():
    manager = RuntimeManager(create_stub_target())
    plan = manager.plan(parse_sdl(textwrap.dedent(_EXACT_SCENARIO)))

    result = manager.apply(plan)

    assert result.success, [diag.message for diag in result.diagnostics]
    by_field = {entry.field_path: entry for entry in result.snapshot.realization_provenance}
    assert by_field["nodes.web.type"].explicitness is ExplicitnessClass.EXACT


def test_apply_snapshot_preserves_planned_payload_without_backend_state():
    manager = RuntimeManager(create_stub_target())
    plan = manager.plan(parse_sdl(textwrap.dedent(_EXACT_SCENARIO)))

    result = manager.apply(plan)

    entry = result.snapshot.entries["provision.node.web"]
    assert entry.payload.get("node_kind") == "compute"
    rendered = repr(result.snapshot.entries)
    for forbidden in ("container_id", "docker", "podman", "/var/run", "StubProvisioner"):
        assert forbidden not in rendered
