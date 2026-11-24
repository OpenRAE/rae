"""Issue #1836: a listening-socket source is a provable forwarding-agent fact."""

from __future__ import annotations

import pytest
import yaml
from raes import parse_sdl
from raes_contracts.realization_structure import RealizationRelationStatus, evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization_runtime_common import observed_projection

_AGENT = {
    "forwarding_agent_id": "syslog-forwarder",
    "implementation": "rsyslog",
    "agent_kind": "log_forwarder",
    "sources": [{"source_id": "local-syslog", "kind": "socket", "selector": "*.*", "parse_format": "syslog"}],
}


def _requirement(kind: str):
    agent = {**_AGENT, "sources": [{**_AGENT["sources"][0], "kind": kind}]}
    source = {
        "name": "socket-source",
        "realization": {"default": "open"},
        "nodes": {"host": {"type": "compute", "runtime": {"forwarding_agents": [agent]}}},
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == "forwarding-agents")
    return requirement, agent


def _status(requirement, value) -> RealizationRelationStatus:
    diagnostic, projection = observed_projection(requirement, value)
    assert diagnostic is None
    return evaluate_realization_constraint(requirement.constraint_document, projection).status


def test_a_realized_socket_source_conforms():
    requirement, agent = _requirement("socket")

    assert _status(requirement, [agent]) is RealizationRelationStatus.CONFORMANT


@pytest.mark.parametrize("realized", ["tailed_path", "queue"])
def test_a_different_realized_source_kind_does_not_conform(realized):
    requirement, agent = _requirement("socket")
    changed = {**agent, "sources": [{**agent["sources"][0], "kind": realized}]}

    assert _status(requirement, [changed]) is RealizationRelationStatus.NONCONFORMANT


def test_the_other_sentinel_cannot_be_proven():
    requirement, agent = _requirement("other")

    assert _status(requirement, [agent]) is RealizationRelationStatus.UNRESOLVED
