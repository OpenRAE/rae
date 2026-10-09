"""Closed realization concerns stay closed inside admitted payload carriers (issue #1451).

Backend snapshot admission accepts tuple, enum, dataclass and model carriers
that the portable codec serializes. The SEM-218 disclosure now reads declared
and returned payloads through that projection, so wrapping a resource's spec
cannot hide a closed concern that the same plain mapping would expose.
"""

from __future__ import annotations

import enum
from copy import deepcopy
from dataclasses import dataclass, replace

import pytest
from raes import parse_sdl
from raes_reference_backend import create_reference_backend_target
from raes_runtime.manager import RuntimeManager

_SCENARIO = """
name: portable-disclosure
nodes:
  lab: {type: switch}
  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [lab]}
"""
_WEB = "provision.node.web"
_EXCESS = {"environment": [{"name": "EXCESS", "value": "1"}]}


@dataclass
class _SpecCarrier:
    node: dict
    infrastructure: object


def _plain(spec):
    return spec


def _enum_member(spec):
    return enum.Enum("_SpecMember", {"PLANNED": spec}).PLANNED


def _dataclass(spec):
    return _SpecCarrier(**spec)


class _WrapsSpec:
    """Delegates to the reference provisioner; the web spec comes back with closed excess, wrapped."""

    def __init__(self, inner, wrap):
        self._inner = inner
        self._wrap = wrap

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def apply(self, plan, snapshot):
        result = self._inner.apply(plan, snapshot)
        if not result.success or self._wrap is None:
            return result
        entry = result.snapshot.entries[_WEB]
        spec = deepcopy(entry.payload["spec"])
        spec["node"]["runtime"] = _EXCESS
        payload = {**entry.payload, "spec": self._wrap(spec)}
        entries = {**result.snapshot.entries, _WEB: replace(entry, payload=payload)}
        return replace(result, snapshot=result.snapshot.with_entries(entries))


def _apply(wrap):
    target = create_reference_backend_target()
    manager = RuntimeManager(replace(target, provisioner=_WrapsSpec(target.provisioner, wrap)))
    return manager, manager.apply(manager.plan(parse_sdl(_SCENARIO)))


def test_honest_apply_is_admitted():
    manager, result = _apply(None)

    assert result.success, [diagnostic.message for diagnostic in result.diagnostics]
    assert _WEB in manager.snapshot.entries


@pytest.mark.parametrize("wrap", [_plain, _enum_member, _dataclass], ids=["plain-dict", "enum-member", "dataclass"])
def test_closed_runtime_environment_is_refused_inside_any_admitted_carrier(wrap):
    manager, result = _apply(wrap)

    assert result.success is False
    refusals = [d for d in result.diagnostics if (d.code, d.address) == ("runtime.backend-contract-invalid", _WEB)]
    assert [d.message for d in refusals] == ["Backend materialized closed realization concern 'runtime-environment'."]
    assert manager.snapshot.entries == {}
