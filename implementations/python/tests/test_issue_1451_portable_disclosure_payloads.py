"""Realization concerns read alike inside admitted payload carriers (issue #1451).

Backend snapshot admission accepts tuple, enum, dataclass and model carriers
that the portable codec serializes. The SEM-218 disclosure readers and the
safe-persistence sanitizer now read declared and returned payloads through that
projection. Wrapping a value therefore cannot hide a closed concern or let a raw
observation persist, and a tuple in a planned payload matches the same value
returned as a JSON array.
"""

from __future__ import annotations

import enum
import json
from copy import deepcopy
from dataclasses import dataclass, replace

import pytest
from pydantic_core import to_jsonable_python
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.apparatus import RealizationSupportMode
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan as build_plan
from raes_reference_backend import create_reference_backend_target
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from raes_runtime.manager import RuntimeManager
from test_issue_985_runtime_observation_contract import (
    _ADDRESS,
    _authoritative_environment_plan,
    _authoritative_snapshot,
)

_SCENARIO = """
name: portable-disclosure
nodes:
  lab: {type: switch}
  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [lab]}
"""
_DOMAIN_SCENARIO = """
name: portable-plan-payloads
nodes:
  dc: {type: compute}
accounts:
  domain-admin: {username: Administrator, node: dc}
identity_domains:
  corp: {profile: active_directory, dns_name: corp.example, netbios_name: CORP, authority_account_ref: domain-admin}
relationships:
  dc-role: {type: domain_controller_for, source: dc, target: corp, domain_controller: {}}
"""
_OPEN_ENVIRONMENT_SCENARIO = """
name: portable-open-environment
realization:
  default: closed
  scopes:
    - {field_pointer: /nodes/worker/runtime/environment, posture: open}
nodes:
  worker: {type: compute, resources: {ram: 1 gib, cpu: 1}, runtime: {}}
"""
_WEB = "provision.node.web"
_EXCESS = {"environment": [{"name": "EXCESS", "value": "1"}]}
_OBSERVED = [
    {
        "name": "MODE",
        "value": "production",
        "value_classification": "plain",
        "provenance": "runtime",
        "source": "",
        "description": "backend annotation must not persist",
    }
]


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


def _enum_member_environment(spec):
    wrapped = deepcopy(spec)
    runtime = wrapped["node"]["runtime"]
    runtime["environment"] = _enum_member(runtime["environment"])
    return wrapped


_SPEC_CARRIERS = {"plain-dict": _plain, "enum-member": _enum_member, "dataclass": _dataclass}


def _unchanged(entry):
    return entry


def _json_readback(entry):
    return replace(entry, payload=json.loads(json.dumps(entry.payload)))


def _closed_excess(wrap):
    def rewrite(entry):
        if entry.address != _WEB:
            return entry
        spec = deepcopy(entry.payload["spec"])
        spec["node"]["runtime"] = _EXCESS
        return replace(entry, payload={**entry.payload, "spec": wrap(spec)})

    return rewrite


class _RewritesEntries:
    """Delegates to a provisioner and rewrites each entry of a successful result."""

    def __init__(self, inner, rewrite):
        self._inner = inner
        self._rewrite = rewrite

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def apply(self, plan, snapshot):
        result = self._inner.apply(plan, snapshot)
        if not result.success:
            return result
        entries = {address: self._rewrite(entry) for address, entry in result.snapshot.entries.items()}
        return replace(result, snapshot=result.snapshot.with_entries(entries))


def _manager(target, rewrite):
    return RuntimeManager(replace(target, provisioner=_RewritesEntries(target.provisioner, rewrite)))


def _apply(rewrite):
    manager = _manager(create_reference_backend_target(), rewrite)
    return manager, manager.apply(manager.plan(parse_sdl(_SCENARIO)))


def _open_environment_plan():
    _exact, manifest = _authoritative_environment_plan()
    support = replace(manifest.realization_support[0], support_mode=RealizationSupportMode.OPEN_REALIZATION)
    manifest = replace(manifest, realization_support=(support,))
    return build_plan(compile_runtime_model(parse_sdl(_OPEN_ENVIRONMENT_SCENARIO)), manifest).provisioning, manifest


_POSTURES = {"exact": _authoritative_environment_plan, "open": _open_environment_plan}


def _observed_apply(posture, wrap):
    plan, manifest = _POSTURES[posture]()
    returned = _authoritative_snapshot(plan, deepcopy(_OBSERVED))
    entry = returned.entries[_ADDRESS]
    wrapped = replace(entry, payload={**entry.payload, "spec": wrap(entry.payload["spec"])})
    result = ApplyResult(
        success=True, snapshot=returned.with_entries({_ADDRESS: wrapped}), changed_addresses=[_ADDRESS]
    )
    return _call_backend_apply(
        lambda _request, _previous: result,
        plan,
        RuntimeSnapshot(),
        address="runtime.provision.node.worker",
        snapshot=RuntimeSnapshot(),
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )


def test_honest_apply_is_admitted():
    manager, result = _apply(_unchanged)

    assert result.success, [diagnostic.message for diagnostic in result.diagnostics]
    assert _WEB in manager.snapshot.entries


@pytest.mark.parametrize("wrap", list(_SPEC_CARRIERS.values()), ids=list(_SPEC_CARRIERS))
def test_closed_runtime_environment_is_refused_inside_any_admitted_carrier(wrap):
    manager, result = _apply(_closed_excess(wrap))

    assert result.success is False
    refusals = [d for d in result.diagnostics if (d.code, d.address) == ("runtime.backend-contract-invalid", _WEB)]
    assert [d.message for d in refusals] == ["Backend materialized closed realization concern 'runtime-environment'."]
    assert manager.snapshot.entries == {}


@pytest.mark.parametrize(
    "wrap",
    [*_SPEC_CARRIERS.values(), _enum_member_environment],
    ids=[*_SPEC_CARRIERS, "enum-member-environment"],
)
@pytest.mark.parametrize("posture", list(_POSTURES))
def test_only_the_safe_projection_persists_inside_any_admitted_carrier(posture, wrap):
    plain, result = _observed_apply(posture, _plain), _observed_apply(posture, wrap)

    assert result.success is True, [diagnostic.message for diagnostic in result.diagnostics]
    persisted = to_jsonable_python(result.snapshot.entries[_ADDRESS].payload)
    environment = persisted["spec"]["node"]["runtime"]["environment"]
    assert environment[0]["value_present"] is True
    assert environment[0]["value_commitment"].startswith("raes-runtime-value-jcs-sha256-v1:")
    assert "production" not in repr(persisted)
    assert "description" not in repr(environment)
    assert persisted == to_jsonable_python(plain.snapshot.entries[_ADDRESS].payload)
    assert result.snapshot.realization_provenance == plain.snapshot.realization_provenance


@pytest.mark.parametrize("rewrite", [_unchanged, _json_readback], ids=["returned-as-planned", "returned-as-json"])
def test_planned_tuple_matches_the_same_value_returned_as_json(rewrite):
    manager = _manager(create_stub_target(), rewrite)
    plan = manager.plan(parse_sdl(_DOMAIN_SCENARIO))
    controller = next(op for op in plan.provisioning.operations if op.address == "provision.node.dc")
    assert controller.payload["domain_topology"]["controller_addresses"] == ("provision.node.dc",)

    result = manager.apply(plan)

    assert result.success, [diagnostic.message for diagnostic in result.diagnostics]
    assert controller.address in manager.snapshot.entries
