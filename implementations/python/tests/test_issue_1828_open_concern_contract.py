"""Issues #1827 and #1828: open concerns plan and pass the runtime gate consistently."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from raes import parse_sdl
from raes_contracts.realization_structure import RealizationRelationStatus, evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, realization_authority_disclosure, realization_disclosure
from raes_processor.semantics.realization_runtime_common import observed_projection
from test_issue_1758_open_empty_concern import _CAPABILITY, _model, _open_manifest, _requirement, _snapshot

_FIELDS = {
    "runtime-mail-services": "mail_services",
    "runtime-ssh-servers": "ssh_servers",
    "runtime-scheduled-jobs": "scheduled_jobs",
}
_MEMBERS = {
    "mail_services": [{"mail_service_id": "mx"}],
    "ssh_servers": [{"ssh_server_id": "sshd"}],
    "scheduled_jobs": [{"scheduled_job_id": "rotate", "name": "rotate", "kind": "interval"}],
}


def _case(kind, capabilities=None):
    model = _model()
    requirement = _requirement(model, kind)
    assert requirement.authored_empty
    manifest = _open_manifest(capabilities)
    provisioning = plan(model, manifest).provisioning
    operation = next(item for item in provisioning.operations if item.address == requirement.address)
    return requirement, provisioning, operation, manifest


def _evaluate(route, requirement, provisioning, snapshot, manifest):
    if route == "compiled":
        return realization_disclosure((requirement,), provisioning, snapshot, manifest=manifest)
    diagnostics, provenance = realization_authority_disclosure(provisioning, snapshot, manifest=manifest)
    return (
        [
            item
            for item in diagnostics
            if item.address == requirement.address and requirement.requirement_kind in item.message
        ],
        tuple(item for item in provenance if item.requirement_kind == requirement.requirement_kind),
    )


@pytest.mark.parametrize("route", ["compiled", "portable"])
@pytest.mark.parametrize("kind", sorted(_FIELDS))
@pytest.mark.parametrize("capable", [False, True])
def test_a_backend_realizes_no_member_without_a_report(route, kind, capable):
    requirement, provisioning, operation, manifest = _case(kind, {kind: _CAPABILITY} if capable else None)

    for snapshot in (
        _snapshot(operation, requirement),
        _snapshot(operation, requirement, runtime={_FIELDS[kind]: []}),
    ):
        diagnostics, provenance = _evaluate(route, requirement, provisioning, snapshot, manifest)
        assert diagnostics == []
        assert provenance == ()


@pytest.mark.parametrize("kind", sorted(_FIELDS))
def test_a_backend_without_readback_cannot_report_a_member(kind):
    requirement, provisioning, operation, manifest = _case(kind)
    field = _FIELDS[kind]
    snapshot = _snapshot(operation, requirement, runtime={field: _MEMBERS[field]}, observed=True)

    diagnostics, provenance = realization_disclosure((requirement,), provisioning, snapshot, manifest=manifest)

    assert [item.code for item in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


@pytest.mark.parametrize("kind", sorted(_FIELDS))
def test_a_backend_with_readback_can_leave_the_concern_empty(kind):
    requirement, provisioning, operation, manifest = _case(kind, {kind: _CAPABILITY})

    diagnostics, provenance = realization_disclosure(
        (requirement,), provisioning, _snapshot(operation, requirement), manifest=manifest
    )
    assert diagnostics == []
    assert provenance == ()

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        provisioning,
        _snapshot(operation, requirement, runtime={_FIELDS[kind]: []}, observed=True),
        manifest=manifest,
    )
    assert diagnostics == []
    assert [entry.requirement_kind for entry in provenance] == [kind]


def _applications(route_count: int) -> list[dict[str, object]]:
    return [
        {
            "application_id": "portal",
            "service": "http",
            "routes": [
                {
                    "route_id": f"route-{index:02d}",
                    "path": f"/r{index:02d}",
                    "methods": ["GET", "POST"],
                    "parameters": [{"name": "q", "location": "query"}],
                    "responses": [{"status_code": 200}],
                }
                for index in range(route_count)
            ],
        }
    ]


def _applications_requirement(route_count: int):
    source = {
        "name": "keyed-routes",
        "realization": {"default": "open"},
        "nodes": {
            "web": {
                "type": "compute",
                "services": [{"name": "http", "port": 80}],
                "runtime": {"applications": _applications(route_count)},
            }
        },
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "runtime-applications"
    )
    return requirement, _applications(route_count)


def _status(requirement, value) -> RealizationRelationStatus:
    diagnostic, projection = observed_projection(requirement, value)
    assert diagnostic is None
    return evaluate_realization_constraint(requirement.constraint_document, projection).status


def test_routes_compare_by_identity_not_position():
    requirement, authored = _applications_requirement(3)
    reordered = deepcopy(authored)
    reordered[0]["routes"].reverse()
    changed = deepcopy(authored)
    changed[0]["routes"][0]["path"] = "/changed"
    missing = deepcopy(authored)
    del missing[0]["routes"][0]

    assert _status(requirement, authored) is RealizationRelationStatus.CONFORMANT
    assert _status(requirement, reordered) is RealizationRelationStatus.CONFORMANT
    assert _status(requirement, changed) is RealizationRelationStatus.NONCONFORMANT
    assert _status(requirement, missing) is RealizationRelationStatus.NONCONFORMANT


def test_many_keyed_routes_evaluate_within_the_default_budget():
    requirement, authored = _applications_requirement(30)
    reordered = deepcopy(authored)
    reordered[0]["routes"].reverse()

    assert _status(requirement, reordered) is RealizationRelationStatus.CONFORMANT
